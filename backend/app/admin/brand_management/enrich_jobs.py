"""Async brand-enrich job manager (Phase 7 slice 7a-bis).

Replaces admin_console's ``threading.Thread`` enrich worker with
``asyncio.create_task``. Same in-memory dict + lock pattern as
``app/admin/segments/profile_generation.py``.

Public:
- ``set_brand_enrich_job(job_id, **updates)``
- ``get_brand_enrich_job(job_id)``
- ``schedule_brand_enrich_job(...)``
- ``execute_brand_enrich_job(...)`` — awaitable; the worker.
- ``_BRAND_ENRICH_JOB_LIMIT`` — the 100-row cap admin_console used.
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
from app.admin.brand_management.lib import (
    BrandManagementError,
    brand_enrich_context_from_payload,
    brand_management_status_for_error,
)
from app.admin.brand_management.llm import (
    BrandGenerationResult,
    BrandManagementService,
    brand_enrich_timeout_seconds,
)

logger = logging.getLogger(__name__)


_BRAND_ENRICH_JOB_LIMIT = 100

_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock: asyncio.Lock | None = None
_BACKGROUND_BRAND_ENRICH_TASKS: set[asyncio.Task[None]] = set()


def _lock() -> asyncio.Lock:
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
        "status": status,
        "pending": status in {"queued", "running"},
        "error": job.get("error"),
        "message": job.get("message"),
        "draft": job.get("draft"),
        "drafts": list(job.get("drafts") or []),
        "model": job.get("model"),
        "usage": dict(job.get("usage") or {}),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "http_status": job.get("http_status"),
    }


async def set_brand_enrich_job(job_id: str, **updates: Any) -> dict[str, Any] | None:
    async with _lock():
        job = _jobs.setdefault(
            job_id,
            {"job_id": job_id, "created_at": _now_iso(), "status": "queued"},
        )
        job.update(updates)
        job["updated_at"] = _now_iso()
        if len(_jobs) > _BRAND_ENRICH_JOB_LIMIT:
            stale = sorted(_jobs.values(), key=lambda item: item.get("created_at") or "")[
                : len(_jobs) - _BRAND_ENRICH_JOB_LIMIT
            ]
            for entry in stale:
                _jobs.pop(entry["job_id"], None)
        return _snapshot(job)


async def get_brand_enrich_job(job_id: str) -> dict[str, Any] | None:
    async with _lock():
        return _snapshot(_jobs.get(job_id))


async def execute_brand_enrich_job(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    job_id: str,
    operator_id: str,
    name: str,
    payload: dict[str, Any],
) -> None:
    """Run the LLM enrich call inside its own DB session and record the
    result on the in-memory job snapshot. Always finishes in a terminal
    state.
    """
    payload = dict(payload or {})
    context = brand_enrich_context_from_payload(payload)
    await set_brand_enrich_job(job_id, status="running", message="Brand enrichment started")
    try:
        service = BrandManagementService(
            model=payload.get("llm_model"),
            allow_fallback=False,
            timeout_seconds=brand_enrich_timeout_seconds(),
        )
        try:
            result = await service.enrich_brand_by_name(name=name, context=context)
        except BrandManagementError as error:
            await set_brand_enrich_job(
                job_id,
                status="failed",
                error=error.code,
                message=error.message,
                http_status=brand_management_status_for_error(error),
            )
            return

        async with sessionmaker() as session:
            operator = await session.get(AdminUser, operator_id)
            if operator is not None:
                # Best-effort audit; if the table layout has drifted we
                # still want to surface the LLM result to the SPA.
                try:
                    await emit_audit(
                        session,
                        operator=operator,
                        action="enrich_brand",
                        severity="med",
                        resource_type="brand",
                        resource_id="",
                        after={
                            "name": name,
                            "model": result.model,
                            "context_fields": sorted(context.keys()),
                            "draft_count": len(result.items),
                        },
                        reason=str(payload.get("reason") or "enrich_brand"),
                    )
                except Exception:
                    logger.warning("enrich_brand audit emit failed for job %s", job_id)

        await set_brand_enrich_job(
            job_id,
            status="completed",
            message="Brand enrichment completed",
            drafts=list(result.items),
            draft=result.items[0] if len(result.items) == 1 else None,
            model=result.model,
            usage=result.usage,
        )
    except Exception as exc:  # pragma: no cover — last-resort safety net
        logger.exception("brand_enrich_job %s crashed", job_id)
        await set_brand_enrich_job(
            job_id,
            status="failed",
            error=type(exc).__name__,
            message=(str(exc) or "brand_enrich_failed")[:500],
            http_status=500,
        )


async def schedule_brand_enrich_job(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    operator_id: str,
    name: str,
    payload: dict[str, Any],
) -> str:
    """Allocate a job_id, fire-and-forget the worker, return the id."""
    job_id = str(uuid.uuid4())
    await set_brand_enrich_job(job_id, status="queued", message="Brand enrichment queued")
    task = asyncio.create_task(
        execute_brand_enrich_job(
            sessionmaker,
            job_id=job_id,
            operator_id=operator_id,
            name=name,
            payload=payload,
        )
    )
    _BACKGROUND_BRAND_ENRICH_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_BRAND_ENRICH_TASKS.discard)
    return job_id


async def execute_brand_enrich_sync(
    session: AsyncSession,
    *,
    operator: AdminUser,
    name: str,
    payload: dict[str, Any],
    request: Any,
    llm_service: BrandManagementService | None = None,
) -> BrandGenerationResult:
    """Synchronous LLM enrich for the non-async path.

    Caller maps ``BrandManagementError`` → HTTP status. Emits one
    ``enrich_brand`` audit row on success.
    """
    context = brand_enrich_context_from_payload(payload)
    service = llm_service or BrandManagementService(
        model=payload.get("llm_model"),
        allow_fallback=False,
        timeout_seconds=brand_enrich_timeout_seconds(),
    )
    result = await service.enrich_brand_by_name(name=name, context=context)
    try:
        await emit_audit(
            session,
            operator=operator,
            action="enrich_brand",
            severity="med",
            resource_type="brand",
            resource_id="",
            after={
                "name": name,
                "model": result.model,
                "context_fields": sorted(context.keys()),
                "draft_count": len(result.items),
            },
            reason=str(payload.get("reason") or "enrich_brand"),
            request=request,
        )
    except Exception:
        logger.warning("enrich_brand sync audit emit failed for name %s", name)
    return result
