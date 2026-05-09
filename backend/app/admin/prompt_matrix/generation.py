"""Prompt Matrix generation orchestration (Phase 4 slice 3).

Async port of admin_console.app.py's ``_execute_prompt_matrix_generation``
+ ``_insert_prompt_matrix_candidate_batch``. Same shape as
``app/admin/topic_plan/generation.py``: the ``execute_generation`` coroutine
is awaited directly in sync mode and dispatched via ``asyncio.create_task``
in background mode.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from genpano_models import AdminUser, PromptCandidate, PromptGenerationRun
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.admin.audit import emit_audit
from app.admin.prompt_matrix.lib import (
    LLMPromptCandidate,
    PromptMatrixError,
    dedupe_prompt_candidates,
    detect_brand_leaks,
    has_prompt_language_mismatch,
    is_natural_user_prompt,
    is_prompt_relevant_to_topic,
    merge_usage,
    normalize_competitive_type,
    normalize_prompt_scope,
    prompt_text_has_brand_anchor,
    prompt_text_has_competitive_signal,
    prompt_text_mentions_competitor,
    sample_existing_for_context,
)
from app.admin.prompt_matrix.llm import PromptMatrixClient
from app.admin.topic_plan.layer_classifier import reject_reason

logger = logging.getLogger(__name__)

REVIEWABLE_QUALITY_REASONS = {
    "looks_like_topic",
    "looks_like_query",
    "prompt_not_natural",
    "prompt_language_mismatch",
    "category_brand_leak",
    "competitive_competitor_missing",
    "competitive_brand_anchor_missing",
    "prompt_scope_mismatch",
    "prompt_topic_mismatch",
}


PROMPT_METADATA_ALIASES = {
    "slot_id": ("slot_id", "slotId"),
    "competitor_name": ("competitor_name", "competitorName"),
    "competitor_brand_id": ("competitor_brand_id", "competitorBrandId"),
    "competitor_source": ("competitor_source", "competitorSource"),
    "scenario_axis": ("scenario_axis", "scenarioAxis"),
}


def _reviewable_quality_issue(
    *,
    text: str,
    language: str,
    prompt_scope: str,
    topic: dict[str, Any],
    known_brands: list[dict[str, Any]],
    competitor_name: Any | None = None,
) -> dict[str, Any] | None:
    if not is_natural_user_prompt(text):
        return {"reason": "prompt_not_natural", "message": "Prompt is not a natural user question"}
    layer_reason = reject_reason(text, "prompt")
    if layer_reason in REVIEWABLE_QUALITY_REASONS:
        return {"reason": layer_reason, "message": "Prompt crosses the prompt layer boundary"}
    if has_prompt_language_mismatch(text, language):
        return {"reason": "prompt_language_mismatch", "message": "Prompt language does not match"}
    if prompt_scope == "non_branded":
        leaked = detect_brand_leaks(text, known_brands)
        if leaked:
            reason = (
                "category_brand_leak"
                if topic.get("dimension_key") == "category"
                else "prompt_scope_mismatch"
            )
            return {
                "reason": reason,
                "message": "Non-branded prompt contains brand terms",
                "leaks": leaked[:5],
            }
    if prompt_scope == "branded" and not prompt_text_has_brand_anchor(text, topic, known_brands):
        return {
            "reason": "prompt_scope_mismatch",
            "message": "Branded prompt must include the topic brand or product",
        }
    if prompt_scope == "competitive":
        if not prompt_text_has_competitive_signal(text):
            return {
                "reason": "prompt_scope_mismatch",
                "message": "Competitive prompt must include comparison or alternative intent",
            }
        if competitor_name and not prompt_text_mentions_competitor(text, competitor_name):
            return {
                "reason": "competitive_competitor_missing",
                "message": "Competitive prompt must directly mention the selected competitor",
            }
        if competitor_name and not prompt_text_has_brand_anchor(text, topic, known_brands):
            return {
                "reason": "competitive_brand_anchor_missing",
                "message": "Competitive prompt must compare against the topic brand or product",
            }
    if not is_prompt_relevant_to_topic(text, topic, known_brands, language=language):
        return {"reason": "prompt_topic_mismatch", "message": "Prompt does not match its topic"}
    return None


async def _is_run_cancelled(session: AsyncSession, run_id: str) -> bool:
    if not run_id:
        return False
    try:
        row = (
            await session.execute(
                text("SELECT status FROM prompt_generation_runs WHERE id = :id"),
                {"id": run_id},
            )
        ).first()
    except Exception:
        return False
    if row is None:
        return False
    return str(row[0] or "").lower() == "cancelled"


async def _insert_candidate_batch(
    session: AsyncSession,
    *,
    run_id: str,
    candidates: list[LLMPromptCandidate],
    topic_by_id: dict[int, dict[str, Any]],
    config: dict[str, Any],
    known_brands: list[dict[str, Any]],
    existing_prompts: list[str],
    remaining: int,
    skipped: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Dedup + filter + insert PromptCandidate rows for one LLM batch."""
    if remaining <= 0:
        return []
    accepted, batch_skipped = dedupe_prompt_candidates(
        candidates, existing_prompts, max_count=remaining, layer_check=False
    )
    skipped.extend(batch_skipped)
    inserted: list[dict[str, Any]] = []
    for candidate in accepted:
        item: dict[str, Any] = candidate.as_dict()
        topic_id_raw = item.get("topic_id")
        if topic_id_raw is None:
            skipped.append({"text": item.get("text", ""), "reason": "invalid_topic_id"})
            continue
        try:
            topic_id = int(topic_id_raw)
        except (TypeError, ValueError):
            skipped.append({"text": item.get("text", ""), "reason": "invalid_topic_id"})
            continue
        topic = topic_by_id.get(topic_id)
        if topic is None:
            skipped.append({"text": item.get("text", ""), "reason": "topic_not_selected"})
            continue
        text_v = item.get("text") or ""
        language = item.get("language") or ""
        raw_tags_value = item.get("tags")
        raw_tags: dict[str, Any] = raw_tags_value if isinstance(raw_tags_value, dict) else {}
        tags = {k: v for k, v in raw_tags.items() if k != "engines"}
        try:
            prompt_scope = normalize_prompt_scope(
                item.get("prompt_scope")
                or item.get("promptScope")
                or tags.get("prompt_scope")
                or tags.get("promptScope")
            )
            competitive_type = normalize_competitive_type(
                prompt_scope,
                item.get("competitive_type")
                or item.get("competitiveType")
                or tags.get("competitive_type")
                or tags.get("competitiveType"),
            )
        except PromptMatrixError as error:
            skipped.append({"text": text_v, "reason": error.code, "message": error.message})
            continue
        for normalized_key, aliases in PROMPT_METADATA_ALIASES.items():
            value = next(
                (
                    item.get(alias)
                    for alias in aliases
                    if item.get(alias) is not None and item.get(alias) != ""
                ),
                None,
            )
            if value is None:
                value = next(
                    (
                        tags.get(alias)
                        for alias in aliases
                        if tags.get(alias) is not None and tags.get(alias) != ""
                    ),
                    None,
                )
            if value is not None and not tags.get(normalized_key):
                tags[normalized_key] = value
            for alias in aliases:
                if alias != normalized_key:
                    tags.pop(alias, None)
        quality_issue = _reviewable_quality_issue(
            text=text_v,
            language=language,
            prompt_scope=prompt_scope,
            topic=topic,
            known_brands=known_brands,
            competitor_name=tags.get("competitor_name"),
        )
        tags.pop("promptScope", None)
        tags.pop("competitiveType", None)
        tags.pop("competitive_type", None)
        tags = {
            **tags,
            "prompt_scope": prompt_scope,
            **({"competitive_type": competitive_type} if competitive_type else {}),
            "source": "prompt_matrix",
            "routing": "deferred_to_query_pool",
        }
        if quality_issue:
            tags = {
                **tags,
                "quality_gate_status": "blocked",
                "quality_gate_reason": quality_issue["reason"],
                "quality_gate_message": quality_issue.get("message") or quality_issue["reason"],
                **(
                    {"quality_gate_leaks": quality_issue["leaks"]}
                    if quality_issue.get("leaks")
                    else {}
                ),
            }

        row = PromptCandidate(
            id=str(uuid.uuid4()),
            run_id=run_id,
            topic_id=topic_id,
            topic_text=topic.get("title"),
            brand_id=topic.get("brand_id"),
            brand_name=topic.get("brand"),
            dimension=topic.get("dimension_key"),
            intent=item.get("intent"),
            language=language,
            template_strategy=item.get("template_strategy") or config.get("template_strategy"),
            template_version=item.get("template_version") or "v1",
            text=text_v,
            status="pending",
            confidence=item.get("confidence", 0.75),
            reason=item.get("reason") or "",
            duplicate_of=item.get("duplicate_of"),
            tags=tags,
        )
        session.add(row)
        await session.flush()
        inserted.append(
            {
                "id": row.id,
                "run_id": row.run_id,
                "topic_id": row.topic_id,
                "topic_text": row.topic_text,
                "brand_id": row.brand_id,
                "brand_name": row.brand_name,
                "dimension": row.dimension,
                "intent": row.intent,
                "language": row.language,
                "text": row.text,
                "status": row.status,
                "confidence": float(row.confidence or 0),
                "reason": row.reason,
                "duplicate_of": row.duplicate_of,
                "tags": row.tags,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    await session.commit()
    return inserted


async def _update_run_progress(
    session: AsyncSession,
    *,
    run_id: str,
    llm_model: str | None,
    usage: dict[str, Any],
    candidates_generated: int,
) -> None:
    run = (
        await session.execute(select(PromptGenerationRun).where(PromptGenerationRun.id == run_id))
    ).scalar_one_or_none()
    if run is None or run.status in {"cancelled", "failed"}:
        return
    run.llm_model = llm_model
    run.llm_usage_json = dict(usage)
    run.candidates_generated = candidates_generated
    await session.commit()


async def _finalize_run(
    session: AsyncSession,
    *,
    run_id: str,
    status: str,
    llm_model: str | None,
    usage: dict[str, Any],
    candidates_generated: int,
    metrics: dict[str, Any] | None = None,
    llm_error: str | None = None,
    request_config: dict[str, Any] | None = None,
) -> None:
    from datetime import UTC, datetime

    run = (
        await session.execute(select(PromptGenerationRun).where(PromptGenerationRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        return
    if run.status == "cancelled" and status == "failed":
        return
    run.status = status
    run.llm_model = llm_model
    if usage:
        run.llm_usage_json = dict(usage)
    run.candidates_generated = candidates_generated
    if metrics is not None:
        run.metrics_json = dict(metrics)
    if request_config is not None:
        run.request_config = dict(request_config)
    if llm_error is not None:
        run.llm_error = llm_error
    run.completed_at = datetime.now(UTC).replace(tzinfo=None)
    await session.commit()


def _request_config_with_generation_context(
    request_config: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    merged = dict(request_config)
    for key in ("competitors_by_topic", "competitor_discovery_error"):
        if config.get(key):
            merged[key] = config[key]
    return merged


def run_failed_status_code(error_code: str | None) -> int:
    return 503 if str(error_code or "").startswith("llm_") else 502


async def execute_generation(
    session: AsyncSession,
    *,
    run_id: str,
    operator: AdminUser,
    topics: list[dict[str, Any]],
    config: dict[str, Any],
    known_brands: list[dict[str, Any]],
    existing_prompts: list[str],
    estimated: int,
    request_config: dict[str, Any],
    llm_client: PromptMatrixClient | None = None,
) -> dict[str, Any]:
    """Drive the full prompt-matrix LLM generation loop.

    Updates ``prompt_generation_runs`` row through running -> completed /
    failed / cancelled. Emits audit on terminal state.
    """
    inserted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    usage: dict[str, Any] = {}
    batches = 0
    llm_model: str | None = None
    cancelled = False

    topic_by_id = {int(t["raw_id"]): t for t in topics}
    existing_for_llm = sample_existing_for_context(existing_prompts, total_quota=400)

    try:
        client = llm_client or PromptMatrixClient()
        llm_model = client.config.model
        async for batch_candidates, batch_meta in client.generate_prompt_batches(
            topics=topics,
            config=config,
            known_brands=known_brands,
            existing_prompts=existing_for_llm,
        ):
            if await _is_run_cancelled(session, run_id):
                cancelled = True
                break
            batches += 1
            llm_model = (batch_meta or {}).get("model") or llm_model
            usage = merge_usage(usage, (batch_meta or {}).get("usage") or {})
            remaining = estimated - len(inserted)
            if remaining <= 0:
                break
            batch_inserted = await _insert_candidate_batch(
                session,
                run_id=run_id,
                candidates=batch_candidates,
                topic_by_id=topic_by_id,
                config=config,
                known_brands=known_brands,
                existing_prompts=existing_prompts,
                remaining=remaining,
                skipped=skipped,
            )
            inserted.extend(batch_inserted)
            existing_prompts.extend([row["text"] for row in batch_inserted if row.get("text")])
            await _update_run_progress(
                session,
                run_id=run_id,
                llm_model=llm_model,
                usage=usage,
                candidates_generated=len(inserted),
            )

        if cancelled or await _is_run_cancelled(session, run_id):
            final_request_config = _request_config_with_generation_context(request_config, config)
            await _finalize_run(
                session,
                run_id=run_id,
                status="cancelled",
                llm_model=llm_model,
                usage=usage,
                candidates_generated=len(inserted),
                request_config=final_request_config,
            )
            await emit_audit(
                session,
                operator=operator,
                action="generate_prompt_matrix_cancelled",
                severity="med",
                resource_type="prompt_generation_run",
                resource_id=run_id,
                after={
                    "request_config": final_request_config,
                    "estimated_prompts": estimated,
                    "candidates_generated": len(inserted),
                    "batches": batches,
                },
                reason="prompt_matrix_generate",
            )
            return {
                "inserted": inserted,
                "skipped": skipped,
                "usage": usage,
                "model": llm_model,
                "batches": batches,
                "cancelled": True,
            }

        from app.admin.topic_plan.db import compute_generation_metrics

        quality_passed = sum(
            1 for row in inserted if (row.get("tags") or {}).get("quality_gate_status") != "blocked"
        )
        reviewable_blocked = len(inserted) - quality_passed
        metrics = compute_generation_metrics(
            requested=estimated,
            accepted=quality_passed,
            skipped=skipped,
            batches=batches,
            llm_model=llm_model,
        )
        hard_rejected = len(skipped)
        metrics.update(
            {
                "reviewable_blocked": reviewable_blocked,
                "hard_rejected": hard_rejected,
                "visible_candidates": len(inserted),
                "rejected_total": reviewable_blocked + hard_rejected,
                "quality_blocked": len(inserted) == 0 and hard_rejected > 0,
                **(
                    {"competitor_discovery_error": config["competitor_discovery_error"]}
                    if config.get("competitor_discovery_error")
                    else {}
                ),
            }
        )
        terminal = "failed" if metrics.get("quality_blocked") else "completed"
        final_request_config = _request_config_with_generation_context(request_config, config)
        await _finalize_run(
            session,
            run_id=run_id,
            status=terminal,
            llm_model=llm_model,
            usage=usage,
            candidates_generated=len(inserted),
            metrics=metrics,
            llm_error="quality_gate_blocked" if metrics.get("quality_blocked") else None,
            request_config=final_request_config,
        )
        action = (
            "generate_prompt_matrix_quality_blocked"
            if metrics.get("quality_blocked")
            else "generate_prompt_matrix"
        )
        await emit_audit(
            session,
            operator=operator,
            action=action,
            severity="med",
            resource_type="prompt_generation_run",
            resource_id=run_id,
            after={
                "request_config": final_request_config,
                "estimated_prompts": estimated,
                "candidates_generated": len(inserted),
                "batches": batches,
                "quality_blocked": bool(metrics.get("quality_blocked")),
            },
            reason="prompt_matrix_generate",
        )
        return {
            "inserted": inserted,
            "skipped": skipped,
            "usage": usage,
            "model": llm_model,
            "batches": batches,
            "metrics": metrics,
            "quality_blocked": bool(metrics.get("quality_blocked")),
        }
    except Exception as error:
        topic_error = (
            error
            if isinstance(error, PromptMatrixError)
            else PromptMatrixError(
                "prompt_matrix_generation_failed",
                str(error)[:500] or "Prompt Matrix generation failed",
            )
        )
        from app.admin.topic_plan.db import compute_generation_metrics

        metrics = compute_generation_metrics(
            requested=estimated,
            accepted=sum(
                1
                for row in inserted
                if (row.get("tags") or {}).get("quality_gate_status") != "blocked"
            ),
            skipped=skipped,
            batches=batches,
            llm_model=llm_model,
        )
        reviewable_blocked = sum(
            1 for row in inserted if (row.get("tags") or {}).get("quality_gate_status") == "blocked"
        )
        metrics.update(
            {
                "reviewable_blocked": reviewable_blocked,
                "hard_rejected": len(skipped),
                "visible_candidates": len(inserted),
                "rejected_total": reviewable_blocked + len(skipped),
                **(
                    {"competitor_discovery_error": config["competitor_discovery_error"]}
                    if config.get("competitor_discovery_error")
                    else {}
                ),
                "partial_failure": bool(inserted),
                "batch_error_code": topic_error.code,
                "batch_error_message": topic_error.message,
            }
        )
        llm_error_detail = f"{topic_error.code}: {topic_error.message}"
        try:
            final_request_config = _request_config_with_generation_context(request_config, config)
            if inserted:
                metrics["partial_completion"] = True
                await _finalize_run(
                    session,
                    run_id=run_id,
                    status="completed",
                    llm_model=llm_model,
                    usage=usage,
                    candidates_generated=len(inserted),
                    metrics=metrics,
                    request_config=final_request_config,
                )
                await emit_audit(
                    session,
                    operator=operator,
                    action="generate_prompt_matrix",
                    severity="med",
                    resource_type="prompt_generation_run",
                    resource_id=run_id,
                    after={
                        "request_config": final_request_config,
                        "estimated_prompts": estimated,
                        "candidates_generated": len(inserted),
                        "batches": batches,
                        "partial_failure": True,
                        "error": topic_error.code,
                        "error_message": topic_error.message,
                    },
                    reason="prompt_matrix_generate",
                )
                return {
                    "inserted": inserted,
                    "skipped": skipped,
                    "usage": usage,
                    "model": llm_model,
                    "batches": batches,
                    "metrics": metrics,
                    "partial_failure": True,
                }
            await _finalize_run(
                session,
                run_id=run_id,
                status="failed",
                llm_model=llm_model,
                usage=usage,
                candidates_generated=len(inserted),
                metrics=metrics,
                llm_error=llm_error_detail,
                request_config=final_request_config,
            )
            await emit_audit(
                session,
                operator=operator,
                action="generate_prompt_matrix_failed",
                severity="med",
                resource_type="prompt_generation_run",
                resource_id=run_id,
                after={
                    "request_config": final_request_config,
                    "error": topic_error.code,
                    "error_message": topic_error.message,
                    "candidates_generated": len(inserted),
                },
                reason="prompt_matrix_generate",
            )
        except Exception:
            logger.exception("prompt_matrix finalize_run failed for run_id=%s", run_id)
        raise topic_error from error


async def execute_generation_background(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    run_id: str,
    operator_id: str,
    topics: list[dict[str, Any]],
    config: dict[str, Any],
    known_brands: list[dict[str, Any]],
    existing_prompts: list[str],
    estimated: int,
    request_config: dict[str, Any],
) -> None:
    """Background entry — opens own session, swallows errors."""
    try:
        async with sessionmaker() as session:
            operator = (
                await session.execute(select(AdminUser).where(AdminUser.id == operator_id))
            ).scalar_one_or_none()
            if operator is None:
                logger.error("prompt_matrix generate background: operator %s gone", operator_id)
                return
            await execute_generation(
                session,
                run_id=run_id,
                operator=operator,
                topics=topics,
                config=config,
                known_brands=known_brands,
                existing_prompts=existing_prompts,
                estimated=estimated,
                request_config=request_config,
            )
    except PromptMatrixError:
        logger.warning("prompt_matrix generate background failed for run_id=%s", run_id)
    except Exception:
        logger.exception("prompt_matrix generate background crashed for run_id=%s", run_id)
