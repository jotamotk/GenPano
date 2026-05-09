"""Async profile-generation job manager + worker (Phase 6 slice 6b-bis).

Replaces admin_console's ``threading.Thread`` profile-generation worker
with ``asyncio.create_task`` (matches the topic_plan / prompt_matrix /
query_pool background-task pattern).

The job state lives in an in-memory dict guarded by ``asyncio.Lock``;
the SPA polls ``GET /generate/{job_id}`` for status. Jobs evict at
``_PROFILE_GENERATION_JOB_LIMIT`` (50) — same cap admin_console used.

Public:
- ``set_profile_generation_job(job_id, **updates)``
- ``get_profile_generation_job(job_id)``
- ``schedule_profile_generation_job(...)``
- ``execute_profile_generation_job(...)`` (async; awaited by the
  background task)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from genpano_models import AdminUser
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.admin.audit import emit_audit
from app.admin.segments import db as segments_db
from app.admin.segments.llm import (
    GenerationResult,
    SegmentProfileGenerationError,
    SegmentProfileGenerationService,
    drafts_with_brand_context,
    segment_profile_generation_status,
)

logger = logging.getLogger(__name__)


_PROFILE_GENERATION_JOB_LIMIT = 50

# Process-local state. Multi-worker deploys would lose continuity here,
# but admin_console had the same constraint (threading.Lock + dict) and
# the SPA polls the same hostname; ops already knows to scale to 1 worker.
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock: asyncio.Lock | None = None
# Strong-ref to in-flight tasks; without this Python may GC the coroutine.
_BACKGROUND_PROFILE_GENERATION_TASKS: set[asyncio.Task[None]] = set()


def _lock() -> asyncio.Lock:
    """Lazily allocate the lock so tests / sync imports don't trip
    ``RuntimeError: no running event loop``."""
    global _jobs_lock
    if _jobs_lock is None:
        _jobs_lock = asyncio.Lock()
    return _jobs_lock


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _snapshot(job: dict[str, Any] | None) -> dict[str, Any] | None:
    if not job:
        return None
    status = job.get("status")
    return {
        "job_id": job.get("job_id"),
        "segment_id": job.get("segment_id"),
        "status": status,
        "pending": status in {"queued", "running"},
        "error": job.get("error"),
        "message": job.get("message"),
        "drafts": list(job.get("drafts") or []),
        "model": job.get("model"),
        "usage": dict(job.get("usage") or {}),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "http_status": job.get("http_status"),
    }


async def set_profile_generation_job(job_id: str, **updates: Any) -> dict[str, Any] | None:
    """Upsert a job row + evict the oldest if the cap is reached.

    Returns a snapshot of the post-update state (matches admin_console).
    """
    async with _lock():
        job = _jobs.setdefault(
            job_id,
            {"job_id": job_id, "created_at": _now_iso(), "status": "queued"},
        )
        job.update(updates)
        job["updated_at"] = _now_iso()
        if len(_jobs) > _PROFILE_GENERATION_JOB_LIMIT:
            oldest = sorted(_jobs.values(), key=lambda item: item.get("created_at") or "")[
                : len(_jobs) - _PROFILE_GENERATION_JOB_LIMIT
            ]
            for stale in oldest:
                _jobs.pop(stale["job_id"], None)
        return _snapshot(job)


async def get_profile_generation_job(job_id: str) -> dict[str, Any] | None:
    async with _lock():
        return _snapshot(_jobs.get(job_id))


def _bounded_count(value: Any, default: int, low: int, high: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(low, min(n, high))


async def execute_profile_generation_job(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    job_id: str,
    operator_id: str,
    segment_id: str,
    payload: dict[str, Any],
) -> None:
    """Run the LLM call inside its own DB session + record the result.

    Always finishes the job in ``completed`` or ``failed`` state, even
    on unexpected exceptions. Mirrors admin_console's contract: the
    job snapshot is what ``GET /generate/{job_id}`` returns.
    """
    payload = dict(payload or {})
    brand_name = (payload.get("brand_name") or payload.get("brand") or "").strip()
    await set_profile_generation_job(job_id, status="running", message="LLM generation started")
    try:
        async with sessionmaker() as session:
            operator = await session.get(AdminUser, operator_id)
            if operator is None:
                await set_profile_generation_job(
                    job_id,
                    status="failed",
                    error="operator_gone",
                    message="Operator account no longer exists",
                    http_status=500,
                )
                return

            seg = await segments_db.get_segment(session, segment_id)
            if seg is None:
                await set_profile_generation_job(
                    job_id,
                    status="failed",
                    error="segment_not_found",
                    message="Segment not found",
                    http_status=404,
                )
                return

            from app.admin.segments.lib import brand_id_value

            brand_id = seg.get("brand_id") or brand_id_value(payload)
            draft_brand_name = seg.get("brand_name") or brand_name

            service = SegmentProfileGenerationService(
                model=payload.get("llm_model"),
                allow_fallback=False,
            )
            try:
                result = await service.generate_profiles(
                    segment=seg,
                    brand_name=brand_name,
                    count=_bounded_count(payload.get("count"), 6, 1, 50),
                    goal=str(payload.get("goal") or ""),
                    constraints=str(payload.get("constraints") or payload.get("notes") or ""),
                    products=payload.get("products")
                    if isinstance(payload.get("products"), list)
                    else [],
                )
            except SegmentProfileGenerationError as error:
                await set_profile_generation_job(
                    job_id,
                    status="failed",
                    error=error.code,
                    message=error.message,
                    http_status=segment_profile_generation_status(error),
                )
                return

            await segments_db.write_profile_generation_log(
                session,
                admin_id=operator_id,
                segment_id=segment_id,
                payload=payload,
                model=result.model,
                prompt=result.prompt,
                items=result.items,
                usage=result.usage,
                estimated_cost=result.estimated_cost,
            )
            await emit_audit(
                session,
                operator=operator,
                action="generate_profiles",
                severity="med",
                resource_type="segment",
                resource_id=str(segment_id).strip().upper(),
                after={"count": len(result.items), "model": result.model},
                reason=str(payload.get("reason") or "generate_profiles"),
            )

            drafts = drafts_with_brand_context(
                result.items,
                brand_id=brand_id,
                brand_name=draft_brand_name,
                segment_id=segment_id,
            )
            await set_profile_generation_job(
                job_id,
                status="completed",
                message="Profile generation completed",
                drafts=drafts,
                model=result.model,
                usage=result.usage,
            )
    except Exception as exc:  # pragma: no cover — last-resort safety net
        logger.exception("profile_generation_job %s crashed", job_id)
        await set_profile_generation_job(
            job_id,
            status="failed",
            error=type(exc).__name__,
            message=(str(exc) or "profile_generation_failed")[:500],
            http_status=500,
        )


async def schedule_profile_generation_job(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    operator_id: str,
    segment_id: str,
    payload: dict[str, Any],
) -> str:
    """Allocate a job_id, queue an asyncio.Task, return the id.

    The route handler returns 202 with the id; the SPA polls
    ``GET /generate/{job_id}`` until the snapshot's ``pending`` flag
    flips false.
    """
    job_id = str(uuid.uuid4())
    await set_profile_generation_job(
        job_id,
        status="queued",
        segment_id=str(segment_id).strip().upper(),
        message="Profile generation queued",
    )
    task = asyncio.create_task(
        execute_profile_generation_job(
            sessionmaker,
            job_id=job_id,
            operator_id=operator_id,
            segment_id=segment_id,
            payload=payload,
        )
    )
    _BACKGROUND_PROFILE_GENERATION_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_PROFILE_GENERATION_TASKS.discard)
    return job_id


async def execute_profile_generation_sync(
    session: AsyncSession,
    *,
    operator: AdminUser,
    segment_id: str,
    payload: dict[str, Any],
    request: Any,
    llm_service: SegmentProfileGenerationService | None = None,
) -> tuple[GenerationResult, str | None, str, str | None]:
    """Synchronous LLM call (no job manager) used by ``async_generation=False``.

    Returns ``(result, brand_id, draft_brand_name, segment_resolved_id)``.
    Raises ``ValueError("segment_not_found")`` or
    ``SegmentProfileGenerationError`` for the route to map to HTTP.
    """
    from app.admin.segments.lib import brand_id_value

    seg = await segments_db.get_segment(session, segment_id)
    if seg is None:
        raise ValueError("segment_not_found")
    brand_name = (payload.get("brand_name") or payload.get("brand") or "").strip()
    brand_id = seg.get("brand_id") or brand_id_value(payload)
    draft_brand_name = seg.get("brand_name") or brand_name

    service = llm_service or SegmentProfileGenerationService(
        model=payload.get("llm_model"),
        allow_fallback=False,
    )
    result = await service.generate_profiles(
        segment=seg,
        brand_name=brand_name,
        count=_bounded_count(payload.get("count"), 6, 1, 50),
        goal=str(payload.get("goal") or ""),
        constraints=str(payload.get("constraints") or payload.get("notes") or ""),
        products=payload.get("products") if isinstance(payload.get("products"), list) else [],
    )

    await segments_db.write_profile_generation_log(
        session,
        admin_id=operator.id,
        segment_id=segment_id,
        payload=payload,
        model=result.model,
        prompt=result.prompt,
        items=result.items,
        usage=result.usage,
        estimated_cost=result.estimated_cost,
    )
    await emit_audit(
        session,
        operator=operator,
        action="generate_profiles",
        severity="med",
        resource_type="segment",
        resource_id=str(segment_id).strip().upper(),
        after={"count": len(result.items), "model": result.model},
        reason=str(payload.get("reason") or "generate_profiles"),
        request=request,
    )
    return result, brand_id, draft_brand_name, str(segment_id).strip().upper()
