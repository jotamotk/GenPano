"""Topic Plan generation orchestration (Phase 3 B.2.b).

Async port of admin_console.app.py's ``_execute_topic_plan_generation``.
Drives the LLM batching loop, dedup, candidate insertion, and final run
state. Used by both the sync code path (``await`` directly) and the
background ``asyncio.create_task`` path for the FastAPI ``/generate``
route — same coroutine, different invocation.

Design notes:
- Background mode opens its own session via the sessionmaker factory
  passed in (so the request-scoped session can close immediately after
  returning ``run_id`` to the client).
- Cancellation is checked between batches by re-reading the run row;
  /runs/{id}/stop sets status='cancelled' and this loop notices on the
  next iteration.
- LLM errors are caught and recorded as ``run.status='failed'`` with the
  error code in ``llm_error``; never raised back through ``create_task``
  (would print to logs and warn the event loop).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from genpano_models import AdminUser, TopicCandidate
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.admin.audit import emit_audit
from app.admin.brand_context import (
    persist_brand_context_snapshots,
    topic_context_refs,
)
from app.admin.topic_plan import db as tp_db
from app.admin.topic_plan.lib import (
    LLMTopic,
    TopicPlanLLMError,
    dedupe_topic_candidates,
    is_natural_consumer_topic,
    is_title_brand_named,
    normalize_topic_title,
    over_request_count,
    sample_existing_for_context,
)
from app.admin.topic_plan.llm import DoubaoTopicPlanClient

logger = logging.getLogger(__name__)


def _resolve_brand_for_topic(item: LLMTopic, brands: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Best-effort match LLM-supplied ``brand`` text to one of ``brands``."""
    brand_by_norm = {
        normalize_topic_title(b["name"]): b for b in brands if normalize_topic_title(b["name"])
    }
    brand = brand_by_norm.get(normalize_topic_title(item.brand))
    if brand is not None:
        return brand
    item_norm = normalize_topic_title(item.brand)
    matches = [
        b
        for b in brands
        if item_norm
        and (
            item_norm in normalize_topic_title(b["name"])
            or normalize_topic_title(b["name"]) in item_norm
        )
    ]
    if len(matches) == 1:
        return matches[0]
    if len(brands) == 1:
        return brands[0]
    return None


def _resolve_product_id(item: LLMTopic, brand: dict[str, Any]) -> tuple[int | None, str | None]:
    """Map LLM-supplied product_name to a brand.products row id, if any."""
    product_name = (item.product_name or "").strip() or None
    if not product_name:
        return None, None
    target_norm = normalize_topic_title(product_name)
    for prod in brand.get("products") or []:
        if not prod.get("name"):
            continue
        pname_norm = normalize_topic_title(prod["name"])
        if pname_norm and (
            pname_norm == target_norm or pname_norm in target_norm or target_norm in pname_norm
        ):
            return int(prod["id"]), str(prod["name"])
        for alias in prod.get("aliases") or []:
            if alias and normalize_topic_title(str(alias)) == target_norm:
                return int(prod["id"]), str(prod["name"])
    return None, None


async def _insert_candidate_batch(
    session: AsyncSession,
    *,
    run_id: str,
    candidates: list[LLMTopic],
    brands: list[dict[str, Any]],
    existing_titles: list[str],
    remaining: int,
    skipped: list[dict[str, Any]],
    brand_context_versions: dict[int, str] | None = None,
    brand_context_packs: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Dedup + filter + insert candidate rows for one LLM batch."""
    if remaining <= 0:
        return []
    accepted, batch_skipped = dedupe_topic_candidates(
        candidates, existing_titles, remaining, layer_check=False
    )
    skipped.extend(batch_skipped)
    inserted: list[dict[str, Any]] = []
    for item in accepted:
        if not is_natural_consumer_topic(item.title):
            skipped.append({"title": item.title, "reason": "topic_not_natural"})
            continue
        brand = _resolve_brand_for_topic(item, brands)
        if brand is None:
            skipped.append({"title": item.title, "reason": "brand_not_selected"})
            continue
        leaking_brand = next(
            (
                candidate_brand
                for candidate_brand in brands
                if is_title_brand_named(item.title, candidate_brand)
            ),
            None,
        )
        if leaking_brand is not None:
            skipped.append({"title": item.title, "reason": "topic_brand_leak"})
            continue
        product_id, product_name = _resolve_product_id(item, brand)
        brand_id = int(brand["id"])
        context_pack = (brand_context_packs or {}).get(brand_id)
        topic_axis, context_refs = topic_context_refs(
            topic_dimension=item.dimension,
            product_name=product_name or item.product_name,
            context_pack=context_pack,
        )
        row = TopicCandidate(
            id=str(uuid.uuid4()),
            run_id=run_id,
            brand_id=brand_id,
            brand_name=brand["name"],
            title=item.title,
            dimension=item.dimension,
            reason=item.reason,
            confidence=item.confidence,
            coverage_gap=item.coverage_gap,
            normalized_title=normalize_topic_title(item.title),
            product_id=product_id,
            product_name=product_name,
            brand_context_version=(brand_context_versions or {}).get(brand_id),
            context_refs_json=context_refs or None,
            topic_axis=topic_axis,
            status="pending",
        )
        session.add(row)
        await session.flush()
        inserted.append(
            {
                "id": row.id,
                "run_id": row.run_id,
                "title": row.title,
                "brand_id": row.brand_id,
                "brand": row.brand_name,
                "dimension": row.dimension,
                "reason": row.reason,
                "confidence": float(row.confidence or 0),
                "coverage_gap": row.coverage_gap,
                "status": row.status,
                "review_reason": row.review_reason,
                "approved_topic_id": row.approved_topic_id,
                "brand_context_version": row.brand_context_version,
                "context_refs": row.context_refs_json,
                "topic_axis": row.topic_axis,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
            }
        )
    await session.commit()
    return inserted


async def execute_generation(
    session: AsyncSession,
    *,
    run_id: str,
    operator: AdminUser,
    industry_id: str | None,
    category_id: str | None,
    brands: list[dict[str, Any]],
    llm_gaps: list[dict[str, Any]],
    max_per_brand: int,
    max_topics: int,
    existing_titles: list[str],
    request_config: dict[str, Any],
    llm_client: DoubaoTopicPlanClient | None = None,
) -> dict[str, Any]:
    """Drive the full LLM generation loop. Returns a summary dict.

    Updates ``topic_plan_runs`` row through `running` → `completed` /
    `failed` / `cancelled`. Emits audit on terminal state.
    """
    inserted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    usage: dict[str, Any] = {}
    batches = 0
    llm_model: str | None = None
    cancelled = False

    try:
        client = llm_client or DoubaoTopicPlanClient()
        llm_model = client.config.model
        for batch_brands, batch_gaps, batch_cap in tp_db.topic_plan_brand_batches(
            brands, llm_gaps, max_topics=max_topics, max_per_brand=max_per_brand
        ):
            if await tp_db.is_run_cancelled(session, run_id):
                cancelled = True
                break
            remaining = max_topics - len(inserted)
            if remaining <= 0:
                break
            batch_max = min(remaining, batch_cap)
            llm_topics, llm_meta = await client.generate_topics(
                industry=industry_id or "All industries",
                category=category_id or "All categories",
                brands=[
                    {
                        "id": b["id"],
                        "name": b["name"],
                        "industry": b.get("industry_name") or b.get("industry_id"),
                        "topic_count": b.get("topic_count", 0),
                        "products": b.get("products") or [],
                    }
                    for b in batch_brands
                ],
                coverage_gaps=batch_gaps,
                max_topics=over_request_count(batch_max),
                existing_topics=sample_existing_for_context(existing_titles, total_quota=400),
            )
            batches += 1
            llm_model = (llm_meta or {}).get("model") or llm_model
            usage = tp_db.merge_usage(usage, (llm_meta or {}).get("usage") or {})
            context_versions: dict[int, str] = {}
            context_packs_by_brand_id: dict[int, dict[str, Any]] = {}
            raw_context_packs = (llm_meta or {}).get("brand_context_packs")
            if isinstance(raw_context_packs, dict) and raw_context_packs:
                context_versions, context_packs_by_brand_id = await persist_brand_context_snapshots(
                    session,
                    brands=batch_brands,
                    context_packs_by_name={
                        str(name): pack
                        for name, pack in raw_context_packs.items()
                        if isinstance(pack, dict)
                    },
                    created_from_run_id=run_id,
                )
                if context_versions:
                    await tp_db.merge_run_request_config(
                        session,
                        run_id=run_id,
                        patch={
                            "brand_context_versions": {
                                str(k): v for k, v in context_versions.items()
                            }
                        },
                    )
            if await tp_db.is_run_cancelled(session, run_id):
                cancelled = True
                break
            batch_inserted = await _insert_candidate_batch(
                session,
                run_id=run_id,
                candidates=llm_topics,
                brands=batch_brands,
                existing_titles=existing_titles,
                remaining=remaining,
                skipped=skipped,
                brand_context_versions=context_versions,
                brand_context_packs=context_packs_by_brand_id,
            )
            inserted.extend(batch_inserted)
            existing_titles.extend([row["title"] for row in batch_inserted if row.get("title")])
            await tp_db.update_run_progress(
                session,
                run_id=run_id,
                llm_model=llm_model,
                usage=usage,
                candidates_generated=len(inserted),
            )

        if cancelled or await tp_db.is_run_cancelled(session, run_id):
            await tp_db.finalize_run(
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
                action="generate_topic_plan_cancelled",
                severity="med",
                resource_type="topic_plan_run",
                resource_id=run_id,
                after={
                    "request_config": request_config,
                    "candidates_generated": len(inserted),
                    "batches": batches,
                },
                reason="topic_plan_generate",
            )
            return {
                "inserted": inserted,
                "skipped": skipped,
                "usage": usage,
                "model": llm_model,
                "batches": batches,
                "cancelled": True,
            }

        metrics = tp_db.compute_generation_metrics(
            requested=max_topics,
            accepted=len(inserted),
            skipped=skipped,
            batches=batches,
            llm_model=llm_model,
        )
        terminal_status = "failed" if metrics.get("quality_blocked") else "completed"
        await tp_db.finalize_run(
            session,
            run_id=run_id,
            status=terminal_status,
            llm_model=llm_model,
            usage=usage,
            candidates_generated=len(inserted),
            metrics=metrics,
            llm_error="quality_gate_blocked" if metrics.get("quality_blocked") else None,
        )
        action = (
            "generate_topic_plan_quality_blocked"
            if metrics.get("quality_blocked")
            else "generate_topic_plan"
        )
        await emit_audit(
            session,
            operator=operator,
            action=action,
            severity="med",
            resource_type="topic_plan_run",
            resource_id=run_id,
            after={
                "request_config": request_config,
                "candidates_generated": len(inserted),
                "batches": batches,
                "quality_blocked": bool(metrics.get("quality_blocked")),
            },
            reason="topic_plan_generate",
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
            if isinstance(error, TopicPlanLLMError)
            else TopicPlanLLMError(
                "topic_plan_generation_failed",
                str(error)[:500] or "Topic Plan generation failed",
            )
        )
        try:
            await tp_db.finalize_run(
                session,
                run_id=run_id,
                status="failed",
                llm_model=llm_model,
                usage=usage,
                candidates_generated=len(inserted),
                llm_error=f"{topic_error.code}: {topic_error.message}"[:500],
            )
            await emit_audit(
                session,
                operator=operator,
                action="generate_topic_plan_failed",
                severity="med",
                resource_type="topic_plan_run",
                resource_id=run_id,
                after={"request_config": request_config, "error": topic_error.code},
                reason="topic_plan_generate",
            )
        except Exception:
            logger.exception("topic_plan finalize_run failed for run_id=%s", run_id)
        raise topic_error from error


async def execute_generation_background(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    run_id: str,
    operator_id: str,
    industry_id: str | None,
    category_id: str | None,
    brands: list[dict[str, Any]],
    llm_gaps: list[dict[str, Any]],
    max_per_brand: int,
    max_topics: int,
    existing_titles: list[str],
    request_config: dict[str, Any],
) -> None:
    """Background entry point — opens its own session, swallows errors.

    Called via ``asyncio.create_task``; never raises (would warn the
    event loop). All terminal state lands in ``topic_plan_runs`` via the
    sync execute_generation finalize_run calls.
    """
    try:
        async with sessionmaker() as session:
            from sqlalchemy import select

            operator = (
                await session.execute(select(AdminUser).where(AdminUser.id == operator_id))
            ).scalar_one_or_none()
            if operator is None:
                logger.error("topic_plan generate background: operator %s gone", operator_id)
                return
            await execute_generation(
                session,
                run_id=run_id,
                operator=operator,
                industry_id=industry_id,
                category_id=category_id,
                brands=brands,
                llm_gaps=llm_gaps,
                max_per_brand=max_per_brand,
                max_topics=max_topics,
                existing_titles=existing_titles,
                request_config=request_config,
            )
    except TopicPlanLLMError:
        # finalize_run already wrote status=failed via execute_generation's
        # error handler — don't re-raise; the caller has already returned.
        logger.warning("topic_plan generate background failed for run_id=%s", run_id)
    except Exception:
        logger.exception("topic_plan generate background crashed for run_id=%s", run_id)
