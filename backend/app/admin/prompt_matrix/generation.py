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
    merge_usage,
    sample_existing_for_context,
)
from app.admin.prompt_matrix.llm import PromptMatrixClient

logger = logging.getLogger(__name__)


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
        candidates, existing_prompts, max_count=remaining
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
        if not is_natural_user_prompt(text_v):
            skipped.append({"text": text_v, "reason": "prompt_not_natural"})
            continue
        if has_prompt_language_mismatch(text_v, language):
            skipped.append({"text": text_v, "reason": "prompt_language_mismatch"})
            continue
        if topic.get("dimension_key") == "category":
            leaked = detect_brand_leaks(text_v, known_brands)
            if leaked:
                skipped.append(
                    {"text": text_v, "reason": "category_brand_leak", "leaks": leaked[:5]}
                )
                continue
        raw_tags_value = item.get("tags")
        raw_tags: dict[str, Any] = raw_tags_value if isinstance(raw_tags_value, dict) else {}
        tags = {k: v for k, v in raw_tags.items() if k != "engines"}
        tags = {**tags, "source": "prompt_matrix", "routing": "deferred_to_query_pool"}

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
    if llm_error is not None:
        run.llm_error = llm_error
    run.completed_at = datetime.now(UTC).replace(tzinfo=None)
    await session.commit()


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
            await _finalize_run(
                session,
                run_id=run_id,
                status="cancelled",
                llm_model=llm_model,
                usage=usage,
                candidates_generated=len(inserted),
            )
            await emit_audit(
                session,
                operator=operator,
                action="generate_prompt_matrix_cancelled",
                severity="med",
                resource_type="prompt_generation_run",
                resource_id=run_id,
                after={
                    "request_config": request_config,
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

        metrics = compute_generation_metrics(
            requested=estimated,
            accepted=len(inserted),
            skipped=skipped,
            batches=batches,
            llm_model=llm_model,
        )
        terminal = "failed" if metrics.get("quality_blocked") else "completed"
        await _finalize_run(
            session,
            run_id=run_id,
            status=terminal,
            llm_model=llm_model,
            usage=usage,
            candidates_generated=len(inserted),
            metrics=metrics,
            llm_error="quality_gate_blocked" if metrics.get("quality_blocked") else None,
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
                "request_config": request_config,
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
        try:
            await _finalize_run(
                session,
                run_id=run_id,
                status="failed",
                llm_model=llm_model,
                usage=usage,
                candidates_generated=len(inserted),
                llm_error=topic_error.code,
            )
            await emit_audit(
                session,
                operator=operator,
                action="generate_prompt_matrix_failed",
                severity="med",
                resource_type="prompt_generation_run",
                resource_id=run_id,
                after={"request_config": request_config, "error": topic_error.code},
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
