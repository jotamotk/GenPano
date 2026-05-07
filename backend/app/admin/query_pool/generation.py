"""Query Pool generation orchestrator (Phase 5 slice 3b-iii).

Async port of admin_console.app._execute_query_pool_assembly_run +
_spawn_query_pool_assembly_worker. Drives the LLM loop:

1. ``QueryPoolLLMClient`` yields one ``(queries, batch_meta)`` per batch
2. ``query_pool_candidates_from_llm_queries`` cleans / repairs / dedupes
3. ``insert_query_pool_candidates`` writes the batch
4. ``update_query_pool_run_progress`` streams counters + summary
5. After all batches: ``finalize`` (success), ``mark_failed`` (quality
   gate or LLM error), or ``mark_cancelled`` if a parallel ``stop_run``
   flipped the row to ``cancelled`` mid-stream.

Background entry mirrors topic_plan/prompt_matrix: ``asyncio.create_task``
with a strong-ref module-level set to defeat Python's GC of unreferenced
tasks. The route handler keeps a strong ref via ``add_done_callback`` to
remove it from the set when finished.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from genpano_models import AdminUser
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.admin.audit import emit_audit
from app.admin.query_pool import db as qp_db
from app.admin.query_pool.lib import query_pool_summary
from app.admin.query_pool.llm import QueryPoolLLMClient
from app.admin.query_pool.text_clean import (
    query_pool_candidates_from_llm_queries,
    query_pool_merge_usage,
)
from app.admin.topic_plan.lib import TopicPlanLLMError

logger = logging.getLogger(__name__)


# Strong-ref to in-flight worker tasks; without this Python may GC the
# coroutine before it finishes (asyncio.create_task only holds a weak
# reference). Tasks remove themselves from the set on completion via
# ``add_done_callback`` in ``schedule_assembly_worker``.
_BACKGROUND_QUERY_POOL_TASKS: set[asyncio.Task[None]] = set()


async def _is_run_cancelled(session: AsyncSession, run_id: str) -> bool:
    if not run_id:
        return False
    try:
        row = (
            await session.execute(
                text("SELECT status FROM query_generation_runs WHERE id = :id"),
                {"id": run_id},
            )
        ).first()
    except Exception:
        return False
    if row is None:
        return False
    return str(row[0] or "").lower() == "cancelled"


async def execute_generation(
    session: AsyncSession,
    *,
    run_id: str,
    operator: AdminUser,
    contexts: list[dict[str, Any]],
    profile_pool: list[dict[str, Any]],
    config: dict[str, Any],
    selection: dict[str, Any],
    raw_estimated: int,
    llm_client: QueryPoolLLMClient | None = None,
) -> dict[str, Any]:
    """Drive the LLM loop end-to-end, transitioning the run row.

    Always finishes the run row in a terminal state (completed / failed /
    cancelled) and emits one audit log row. Returns a small summary
    dict — same shape the synchronous test path expects.
    """
    candidates: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    duplicate_review = 0
    query_repaired = 0
    rejected_by_reason: dict[str, int] = {}
    rejected_sample: list[dict[str, Any]] = []
    llm_meta: dict[str, Any] = {"model": None, "usage": {}, "batches": 0}
    cancelled = False

    try:
        client = llm_client or QueryPoolLLMClient()
        async for batch_idx, (queries, batch_meta) in _enumerate_batches(client, contexts):
            if await _is_run_cancelled(session, run_id):
                cancelled = True
                break
            llm_meta["model"] = (batch_meta or {}).get("model") or llm_meta["model"]
            llm_meta["usage"] = query_pool_merge_usage(
                llm_meta.get("usage") or {}, (batch_meta or {}).get("usage") or {}
            )
            llm_meta["batches"] = int(llm_meta.get("batches") or 0) + 1
            batch_contexts = _slice_for_batch(contexts, batch_idx, client)
            batch_candidates, batch_stats = query_pool_candidates_from_llm_queries(
                batch_contexts,
                queries,
                batch_meta,
                start_seq=len(candidates) + 1,
                seen_hashes=seen_hashes,
            )
            duplicate_review += int(batch_stats.get("duplicate_review") or 0)
            query_repaired += int(batch_stats.get("query_repaired") or 0)
            for reason, count in (batch_stats.get("by_reason") or {}).items():
                rejected_by_reason[reason] = int(rejected_by_reason.get(reason) or 0) + int(
                    count or 0
                )
            rejected_sample.extend(batch_stats.get("rejected_sample") or [])
            rejected_sample = rejected_sample[:20]
            if await _is_run_cancelled(session, run_id):
                cancelled = True
                break
            if batch_candidates:
                await qp_db.insert_query_pool_candidates(session, run_id, batch_candidates)
                candidates.extend(batch_candidates)
            preflight_summary = query_pool_summary(
                contexts=contexts,
                profile_pool=profile_pool,
                config=config,
                raw_estimated=raw_estimated,
                candidates=candidates,
                duplicate_review=duplicate_review,
                query_repaired=query_repaired,
                rejected_by_reason=rejected_by_reason,
                rejected_sample=rejected_sample,
                generation_method="llm",
                llm_meta=llm_meta,
            )
            preflight_summary["scheduler_intake"] = "running"
            await qp_db.update_query_pool_run_progress(
                session,
                run_id=run_id,
                candidates=candidates,
                preflight_summary=preflight_summary,
            )

        # After the loop — terminal state transition + audit.
        preflight_summary = query_pool_summary(
            contexts=contexts,
            profile_pool=profile_pool,
            config=config,
            raw_estimated=raw_estimated,
            candidates=candidates,
            duplicate_review=duplicate_review,
            query_repaired=query_repaired,
            rejected_by_reason=rejected_by_reason,
            rejected_sample=rejected_sample,
            generation_method="llm",
            llm_meta=llm_meta,
        )

        if cancelled or await _is_run_cancelled(session, run_id):
            preflight_summary["scheduler_intake"] = "cancelled"
            await qp_db.mark_query_pool_run_cancelled(
                session,
                run_id=run_id,
                candidates=candidates,
                preflight_summary=preflight_summary,
            )
            await emit_audit(
                session,
                operator=operator,
                action="query_pool_assemble_cancelled",
                severity="med",
                resource_type="query_generation_run",
                resource_id=run_id,
                after={
                    "selection": selection,
                    "config": config,
                    "candidates_assembled": len(candidates),
                },
                reason="query_pool_assemble",
            )
            return {
                "run_id": run_id,
                "candidates": candidates,
                "preflight_summary": preflight_summary,
                "cancelled": True,
            }

        if preflight_summary.get("quality_blocked"):
            preflight_summary["scheduler_intake"] = "blocked"
            await qp_db.mark_query_pool_run_failed(
                session,
                run_id=run_id,
                error_code="quality_gate_blocked",
                error_message="quality_gate_blocked",
                preflight_summary=preflight_summary,
            )
            await emit_audit(
                session,
                operator=operator,
                action="query_pool_assemble_quality_blocked",
                severity="med",
                resource_type="query_generation_run",
                resource_id=run_id,
                after={
                    "selection": selection,
                    "config": config,
                    "candidates_assembled": 0,
                },
                reason="query_pool_assemble",
            )
            return {
                "run_id": run_id,
                "candidates": candidates,
                "preflight_summary": preflight_summary,
                "quality_blocked": True,
            }

        await qp_db.finalize_query_pool_run(
            session,
            run_id=run_id,
            candidates=candidates,
            preflight_summary=preflight_summary,
        )
        await emit_audit(
            session,
            operator=operator,
            action="query_pool_assemble",
            severity="med",
            resource_type="query_generation_run",
            resource_id=run_id,
            after={
                "selection": selection,
                "config": config,
                "candidates_assembled": len(candidates),
            },
            reason="query_pool_assemble",
        )
        return {
            "run_id": run_id,
            "candidates": candidates,
            "preflight_summary": preflight_summary,
        }
    except TopicPlanLLMError as error:
        # LLM-side failure (network / schema / quality) — record + audit
        # so the SPA shows a clear llm_error code.
        try:
            await qp_db.mark_query_pool_run_failed(
                session,
                run_id=run_id,
                error_code=error.code or "llm_call_failed",
                error_message=error.message or "Query Pool LLM generation failed",
            )
            await emit_audit(
                session,
                operator=operator,
                action="query_pool_assemble_failed",
                severity="med",
                resource_type="query_generation_run",
                resource_id=run_id,
                after={
                    "selection": selection,
                    "config": config,
                    "error": error.code,
                },
                reason="query_pool_assemble",
            )
        except Exception:
            logger.exception("query_pool finalize-on-llm-error failed for run_id=%s", run_id)
        raise
    except Exception as error:
        # Anything else — wrap so we always finalize the run row.
        try:
            await qp_db.mark_query_pool_run_failed(
                session,
                run_id=run_id,
                error_code=type(error).__name__,
                error_message=(str(error) or "query_pool_assemble_failed")[:500],
            )
            await emit_audit(
                session,
                operator=operator,
                action="query_pool_assemble_failed",
                severity="med",
                resource_type="query_generation_run",
                resource_id=run_id,
                after={
                    "selection": selection,
                    "config": config,
                    "error": type(error).__name__,
                },
                reason="query_pool_assemble",
            )
        except Exception:
            logger.exception("query_pool finalize-on-error failed for run_id=%s", run_id)
        raise


async def _enumerate_batches(
    client: Any, contexts: list[dict[str, Any]]
) -> AsyncIterator[tuple[int, tuple[dict[str, str], dict[str, Any]]]]:
    """Yield ``(batch_index, (queries, meta))``.

    Wrapping the async iterator here lets ``execute_generation`` track
    which batch its iteration is on without holding a separate counter
    state machine.
    """
    idx = 0
    async for queries, meta in client.generate_query_batches(contexts):
        yield idx, (queries, meta)
        idx += 1


def _slice_for_batch(
    contexts: list[dict[str, Any]], batch_idx: int, client: Any
) -> list[dict[str, Any]]:
    """Return the contexts slice that maps to ``batch_idx``.

    The LLM client yields per-batch ``queries`` keyed by ``candidate_key``;
    for ``query_pool_candidates_from_llm_queries`` we still need the
    matching subset of context dicts in the original order.
    """
    from app.admin.query_pool.text_clean import query_pool_chunked, query_pool_llm_batch_size

    # Re-run the same chunking the client did so we slice in lockstep.
    # client.generate_query_batches uses query_pool_llm_batch_size() so
    # repeating the call gives the same boundaries.
    _ = client  # only used to keep parity with the client's chunking; size from env
    batch_size = query_pool_llm_batch_size()
    chunks = query_pool_chunked(contexts, batch_size)
    return chunks[batch_idx] if 0 <= batch_idx < len(chunks) else []


async def execute_generation_background(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    run_id: str,
    operator_id: str,
    contexts: list[dict[str, Any]],
    profile_pool: list[dict[str, Any]],
    config: dict[str, Any],
    selection: dict[str, Any],
    raw_estimated: int,
) -> None:
    """Background entry — opens its own session, swallows errors after
    they've been recorded on the run row.
    """
    try:
        async with sessionmaker() as session:
            operator = (
                await session.execute(select(AdminUser).where(AdminUser.id == operator_id))
            ).scalar_one_or_none()
            if operator is None:
                logger.error("query_pool assemble background: operator %s gone", operator_id)
                return
            await execute_generation(
                session,
                run_id=run_id,
                operator=operator,
                contexts=contexts,
                profile_pool=profile_pool,
                config=config,
                selection=selection,
                raw_estimated=raw_estimated,
            )
    except TopicPlanLLMError:
        logger.warning("query_pool assemble background failed for run_id=%s", run_id)
    except Exception:
        logger.exception("query_pool assemble background crashed for run_id=%s", run_id)


def schedule_assembly_worker(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    run_id: str,
    operator_id: str,
    contexts: list[dict[str, Any]],
    profile_pool: list[dict[str, Any]],
    config: dict[str, Any],
    selection: dict[str, Any],
    raw_estimated: int,
) -> None:
    """Fire-and-forget: schedule ``execute_generation_background`` as a
    Task on the running event loop, with a strong-ref to defeat GC.
    """
    task = asyncio.create_task(
        execute_generation_background(
            sessionmaker,
            run_id=run_id,
            operator_id=operator_id,
            contexts=contexts,
            profile_pool=profile_pool,
            config=config,
            selection=selection,
            raw_estimated=raw_estimated,
        )
    )
    _BACKGROUND_QUERY_POOL_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_QUERY_POOL_TASKS.discard)
