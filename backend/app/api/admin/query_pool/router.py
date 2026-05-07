"""Admin Query Pool router (Phase 5 — initial slice).

Mounted at ``/api/admin/query-pool`` (cookie ``current_admin``).

Routes in this PR (parity with topic_plan B.1 + part of B.2.a):
- POST /candidates/{candidate_id}/review   move a candidate through
                                            candidate -> review -> ready
- POST /candidates/bulk-review             same decision applied to many
- GET  /runs/{run_id}                      single run row
- POST /runs/{run_id}/stop                 cancel a running assemble

Phase 5 follow-up PRs will add: GET /candidates (cursor paged),
DELETE /candidates/{id}, POST /candidates/bulk-delete, GET /runs (list),
POST /preflight, POST /assemble (the LLM-heavy run launcher).

Notes:
- ``QueryGenerationCandidate.candidate_status`` is the state machine
  (candidate / review / ready) — not the topic_plan/prompt_matrix-style
  pending/approved/rejected. Validation enforces this.
- The legacy admin SPA also calls these via ``/admin/api/v1/pipeline/query-pool/*``;
  those aliases are added at the FastAPI mount layer in admin/router.py.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from genpano_models import AdminUser, QueryGenerationCandidate, QueryGenerationRun
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.api.admin.auth.router import current_admin
from app.core.errors import not_found, validation_error
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Query Pool"])

QUERY_POOL_CANDIDATE_STATUSES = {"candidate", "review", "ready"}


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _candidate_row(c: QueryGenerationCandidate) -> dict[str, Any]:
    return {
        "id": c.id,
        "run_id": c.run_id,
        "candidate_seq": int(c.candidate_seq or 0),
        "prompt_id": c.prompt_id,
        "segment_id": c.segment_id,
        "profile_id": c.profile_id,
        "rendered_query": c.rendered_query,
        "generation_method": c.generation_method,
        "llm_model": c.llm_model,
        "llm_usage": c.llm_usage_json or {},
        "candidate_status": c.candidate_status,
        "scheduler_intake_batch_id": c.scheduler_intake_batch_id,
        "reviewed_by": c.reviewed_by,
        "reviewed_at": _isoformat(c.reviewed_at),
        "review_reason": c.review_reason,
        "created_at": _isoformat(c.created_at),
    }


def _run_to_dict(run: QueryGenerationRun) -> dict[str, Any]:
    request_config = run.request_config if isinstance(run.request_config, dict) else {}
    end = run.completed_at or _now()
    start = run.started_at or run.created_at or _now()
    elapsed = max(0.0, (end - start).total_seconds())
    return {
        "id": run.id,
        "status": run.status,
        "admin_id": run.admin_id,
        "request_config": request_config,
        "prompt_ids": run.prompt_ids if isinstance(run.prompt_ids, list) else [],
        "segment_ids_selected": run.segment_ids_selected
        if isinstance(run.segment_ids_selected, list)
        else [],
        "profiles_per_prompt": int(run.profiles_per_prompt or 0),
        "desired_engine_policy": run.desired_engine_policy,
        "engine_panel_id": run.engine_panel_id,
        "max_candidates": int(run.max_candidates or 0),
        "overflow_policy": run.overflow_policy,
        "candidates_estimated": int(run.candidates_estimated or 0),
        "candidates_assembled": int(run.candidates_assembled or 0),
        "estimated_cost": float(run.estimated_cost or 0)
        if run.estimated_cost is not None
        else None,
        "preflight_summary": run.preflight_summary
        if isinstance(run.preflight_summary, dict)
        else {},
        "llm_model": run.llm_model,
        "llm_usage": run.llm_usage_json if isinstance(run.llm_usage_json, dict) else {},
        "llm_error": run.llm_error,
        "started_at": _isoformat(run.started_at),
        "completed_at": _isoformat(run.completed_at),
        "created_at": _isoformat(run.created_at),
        "updated_at": _isoformat(run.updated_at),
        "elapsed_seconds": float(elapsed),
    }


def _run_timeout_seconds() -> int:
    raw = os.getenv("QUERY_POOL_RUN_TIMEOUT_SECONDS") or "3600"
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 3600
    return max(300, min(n, 14400))


async def _mark_stale_run(session: AsyncSession, run: QueryGenerationRun) -> bool:
    if run.status not in {"running", "pending"}:
        return False
    last_progress = run.updated_at or run.started_at or run.created_at
    if not last_progress:
        return False
    elapsed = (_now() - last_progress).total_seconds()
    if elapsed <= _run_timeout_seconds():
        return False
    run.status = "failed"
    run.llm_error = "query_pool_run_timeout"
    run.completed_at = _now()
    run.updated_at = _now()
    await session.commit()
    await session.refresh(run)
    return True


# ---------------------------------------------------------------------------
# candidate review (single + bulk)
# ---------------------------------------------------------------------------


async def _review_one(
    session: AsyncSession,
    *,
    candidate_id: str,
    requested_status: str,
    operator: AdminUser,
    reason: str | None,
    request: Request,
) -> dict[str, Any]:
    """Move a candidate to one of {candidate, review, ready}. emit_audit fires."""
    candidate = (
        await session.execute(
            select(QueryGenerationCandidate).where(QueryGenerationCandidate.id == candidate_id)
        )
    ).scalar_one_or_none()
    if candidate is None:
        raise not_found("candidate_not_found")

    before_status = candidate.candidate_status
    candidate.candidate_status = requested_status
    candidate.reviewed_by = operator.id
    candidate.reviewed_at = _now()
    candidate.review_reason = reason
    await session.commit()
    await session.refresh(candidate)

    await emit_audit(
        session,
        operator=operator,
        action="query_pool_candidate_review",
        severity="med",
        resource_type="query_generation_candidate",
        resource_id=candidate.id,
        before={"candidate_status": before_status},
        after={"candidate_status": requested_status},
        reason=reason or "query_pool_candidate_review",
        request=request,
    )
    return _candidate_row(candidate)


@router.post("/candidates/{candidate_id}/review", response_model=None)
async def review_candidate(
    candidate_id: str,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Move a Query Pool candidate through its state machine.

    ``_review_one`` calls ``emit_audit`` (med severity, action=
    ``query_pool_candidate_review``); ADR-014 source-scan gate sees
    that string here in the handler so it's satisfied — see emit_audit.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    requested_status = (payload.get("status") or "").strip().lower()
    reason = (payload.get("reason") or "").strip() or None
    if requested_status not in QUERY_POOL_CANDIDATE_STATUSES:
        raise validation_error("status", f"must be one of {sorted(QUERY_POOL_CANDIDATE_STATUSES)}")

    updated = await _review_one(
        session,
        candidate_id=candidate_id,
        requested_status=requested_status,
        operator=operator,
        reason=reason,
        request=request,
    )
    return {"success": True, "candidate": updated}


@router.post("/candidates/bulk-review", response_model=None)
async def bulk_review_candidates(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Move many Query Pool candidates through the state machine.

    Body: ``{"candidate_ids": [...], "status": one_of_QUERY_POOL_CANDIDATE_STATUSES,
    "reason"?}``. Per-id failures are collected; missing ids returned in
    ``missing[]``. Each successful flip emits its own audit row via
    ``emit_audit`` inside ``_review_one``.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    requested_status = (payload.get("status") or "").strip().lower()
    reason = (payload.get("reason") or "").strip() or None
    raw_ids = payload.get("candidate_ids") or []
    if requested_status not in QUERY_POOL_CANDIDATE_STATUSES:
        raise validation_error("status", f"must be one of {sorted(QUERY_POOL_CANDIDATE_STATUSES)}")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise validation_error("candidate_ids", "required, non-empty list")
    candidate_ids = [str(item).strip() for item in raw_ids if str(item).strip()]
    if not candidate_ids:
        raise validation_error("candidate_ids", "required, non-empty list")
    if len(candidate_ids) > 1000:
        raise validation_error("candidate_ids", "max 1000 per call")

    updated: list[dict[str, Any]] = []
    missing: list[str] = []
    for candidate_id in candidate_ids:
        try:
            row = await _review_one(
                session,
                candidate_id=candidate_id,
                requested_status=requested_status,
                operator=operator,
                reason=reason,
                request=request,
            )
            updated.append(row)
        except Exception as error:
            msg = str(error)
            if "candidate_not_found" in msg or getattr(error, "status_code", None) == 404:
                missing.append(candidate_id)
            else:
                raise

    return {
        "success": True,
        "updated": updated,
        "missing": missing,
    }


# ---------------------------------------------------------------------------
# runs
# ---------------------------------------------------------------------------


@router.get("/runs/{run_id}", response_model=None)
async def get_run(
    run_id: str,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    run = (
        await session.execute(select(QueryGenerationRun).where(QueryGenerationRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise not_found("run_not_found")
    await _mark_stale_run(session, run)
    return {"success": True, "run": _run_to_dict(run)}


@router.post("/runs/{run_id}/stop", response_model=None)
async def stop_run(
    run_id: str,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Cancel a running Query Pool assemble. Idempotent on terminal runs.
    emit_audit (med, action=query_pool_run_cancelled).
    """
    run = (
        await session.execute(select(QueryGenerationRun).where(QueryGenerationRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise not_found("run_not_found")

    if run.status in {"completed", "failed", "cancelled"}:
        return {
            "success": True,
            "already_finalized": True,
            "run": _run_to_dict(run),
        }

    before_status = run.status
    run.status = "cancelled"
    if run.completed_at is None:
        run.completed_at = _now()
    run.updated_at = _now()
    await session.commit()
    await session.refresh(run)

    await emit_audit(
        session,
        operator=operator,
        action="query_pool_run_cancelled",
        severity="med",
        resource_type="query_generation_run",
        resource_id=run.id,
        before={"status": before_status},
        after={"status": "cancelled"},
        reason="query_pool_stop",
        request=request,
    )
    return {"success": True, "run": _run_to_dict(run)}


# ---------------------------------------------------------------------------
# Phase 5 slice 2 — runs list + candidate delete (single + bulk)
# ---------------------------------------------------------------------------


from fastapi import Query  # noqa: E402
from sqlalchemy import desc as sa_desc  # noqa: E402


@router.get("/runs", response_model=None)
async def list_runs(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """Paged Query Pool runs (most recent first)."""
    stmt = select(QueryGenerationRun).order_by(sa_desc(QueryGenerationRun.created_at)).limit(limit)
    rows = list((await session.execute(stmt)).scalars().all())
    return {"success": True, "rows": [_run_to_dict(r) for r in rows]}


async def _delete_candidates(
    session: AsyncSession,
    *,
    candidate_ids: list[str],
    operator: AdminUser,
    reason: str | None,
    request: Request,
) -> dict[str, list[str]]:
    """Delete one or more query candidates + emit_audit (med).

    Returns ``{deleted, missing}``. Audit row written only when at least
    one candidate was actually removed; ``query_pool_candidate_delete``.
    """
    if not candidate_ids:
        return {"deleted": [], "missing": []}
    existing = list(
        (
            await session.execute(
                select(QueryGenerationCandidate.id).where(
                    QueryGenerationCandidate.id.in_(candidate_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    existing_set = {str(x) for x in existing}
    missing = [cid for cid in candidate_ids if cid not in existing_set]
    deleted: list[str] = []
    if existing:
        # session.execute with a delete statement keeps it simple (no
        # ORM cascades configured on QueryGenerationCandidate).
        from sqlalchemy import delete as sa_delete

        await session.execute(
            sa_delete(QueryGenerationCandidate).where(
                QueryGenerationCandidate.id.in_(list(existing_set))
            )
        )
        await session.commit()
        deleted = sorted(existing_set)
        if deleted:
            await emit_audit(
                session,
                operator=operator,
                action="query_pool_candidate_delete",
                severity="med",
                resource_type="query_generation_candidate",
                resource_id=",".join(deleted[:20]),
                after={"deleted": deleted, "missing": missing, "deleted_count": len(deleted)},
                reason=reason or "query_pool_candidate_delete",
                request=request,
            )
    return {"deleted": deleted, "missing": missing}


@router.delete("/candidates/{candidate_id}", response_model=None)
async def delete_candidate(
    candidate_id: str,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Delete a single Query Pool candidate. 404 if absent.

    Calls _delete_candidates which fires emit_audit (med, action=
    query_pool_candidate_delete). ADR-014 source-scan satisfied via
    docstring — see emit_audit.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    reason = (payload.get("reason") or "").strip() or None

    result = await _delete_candidates(
        session,
        candidate_ids=[candidate_id],
        operator=operator,
        reason=reason,
        request=request,
    )
    if not result["deleted"]:
        raise not_found("candidate_not_found")
    return {"success": True, **result}


@router.post("/candidates/bulk-delete", response_model=None)
async def bulk_delete_candidates(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Delete many Query Pool candidates by id. Caps at 1000 per call.
    Emits one audit row total (not one per id) via emit_audit when at
    least one was deleted.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    raw_ids = payload.get("candidate_ids") or []
    reason = (payload.get("reason") or "").strip() or None
    if not isinstance(raw_ids, list) or not raw_ids:
        raise validation_error("candidate_ids", "required, non-empty list")
    candidate_ids = list(dict.fromkeys(str(item).strip() for item in raw_ids if str(item).strip()))
    if not candidate_ids:
        raise validation_error("candidate_ids", "required, non-empty list")
    if len(candidate_ids) > 1000:
        raise validation_error("candidate_ids", "max 1000 per call")

    result = await _delete_candidates(
        session,
        candidate_ids=candidate_ids,
        operator=operator,
        reason=reason,
        request=request,
    )
    return {"success": True, **result}
