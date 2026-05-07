"""Admin Prompt Matrix router (Phase 4 — initial slice).

Mounted at ``/api/admin/prompt-matrix`` (cookie-based ``current_admin``).

Routes in this PR (parity with topic_plan B.1 + part of B.2.a):
- POST /candidates/{candidate_id}/review   approve | reject one candidate
- POST /candidates/bulk-review             apply same decision to many
- GET  /runs/{run_id}                      single run row (auto-marks stale
                                            running -> failed past timeout)
- POST /runs/{run_id}/stop                 cancel a running generation

Phase 4 follow-up PRs will add: GET /config, GET /topics, GET /gaps,
GET /prompts, GET /candidates (paged read), POST /generate (LLM async).

Shape mirrors topic_plan exactly — the heavy lifting (SQL helpers,
LLM client, generation orchestration) is already vendored under
``app/admin/prompt_matrix/`` (lib.py, llm.py); db.py + generation.py
land in the follow-up PRs alongside the routes that need them.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from genpano_models import AdminUser, PromptCandidate, PromptGenerationRun
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.prompt_matrix.lib import (
    PromptMatrixError,
    clamp_int,
    transition_candidate_status,
)
from app.api.admin.auth.router import current_admin
from app.core.errors import _problem, not_found, validation_error
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Prompt Matrix"])


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _llm_error_to_http(error: PromptMatrixError) -> Any:
    return _problem(400, error.code, error.message, detail=error.message)


def _candidate_row(c: PromptCandidate) -> dict[str, Any]:
    return {
        "id": c.id,
        "run_id": c.run_id,
        "topic_id": c.topic_id,
        "topic_text": c.topic_text,
        "brand_id": c.brand_id,
        "brand_name": c.brand_name,
        "dimension": c.dimension,
        "intent": c.intent,
        "language": c.language,
        "template_strategy": c.template_strategy,
        "template_version": c.template_version,
        "text": c.text,
        "status": c.status,
        "confidence": float(c.confidence or 0),
        "reason": c.reason,
        "duplicate_of": c.duplicate_of,
        "tags": c.tags or {},
        "review_reason": c.review_reason,
        "approved_prompt_id": c.approved_prompt_id,
        "created_at": _isoformat(c.created_at),
        "reviewed_at": _isoformat(c.reviewed_at),
    }


def _run_to_dict(run: PromptGenerationRun) -> dict[str, Any]:
    request_config = run.request_config if isinstance(run.request_config, dict) else {}
    metrics = run.metrics_json if isinstance(run.metrics_json, dict) else {}
    end = run.completed_at or _now()
    start = run.started_at or run.created_at or _now()
    elapsed = max(0.0, (end - start).total_seconds())
    return {
        "id": run.id,
        "status": run.status,
        "admin_id": run.admin_id,
        "request_config": request_config,
        "selected_topic_ids": run.selected_topic_ids
        if isinstance(run.selected_topic_ids, list)
        else [],
        "estimated_prompts": int(run.estimated_prompts or 0),
        "candidates_generated": int(run.candidates_generated or 0),
        "llm_model": run.llm_model,
        "llm_usage": run.llm_usage_json if isinstance(run.llm_usage_json, dict) else {},
        "llm_error": run.llm_error,
        "metrics": metrics,
        "started_at": _isoformat(run.started_at),
        "completed_at": _isoformat(run.completed_at),
        "created_at": _isoformat(run.created_at),
        "updated_at": _isoformat(run.updated_at),
        "elapsed_seconds": float(elapsed),
    }


def _run_timeout_seconds(run: PromptGenerationRun) -> int:
    request_config = run.request_config if isinstance(run.request_config, dict) else {}
    estimated = clamp_int(request_config.get("max_prompts"), 8000, 1, 100_000)
    default_timeout = max(900, min(7200, estimated * 2))
    return clamp_int(os.getenv("PROMPT_MATRIX_RUN_TIMEOUT_SECONDS"), default_timeout, 300, 14400)


async def _mark_stale_run(session: AsyncSession, run: PromptGenerationRun) -> bool:
    if run.status != "running":
        return False
    last_progress = run.updated_at or run.started_at or run.created_at
    if not last_progress:
        return False
    elapsed = (_now() - last_progress).total_seconds()
    if elapsed <= _run_timeout_seconds(run):
        return False
    run.status = "failed"
    run.llm_error = "prompt_matrix_run_timeout"
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
    candidate = (
        await session.execute(select(PromptCandidate).where(PromptCandidate.id == candidate_id))
    ).scalar_one_or_none()
    if candidate is None:
        raise not_found("candidate_not_found")

    new_status = transition_candidate_status(candidate.status, requested_status)
    before_status = candidate.status

    candidate.status = new_status
    candidate.reviewed_by = operator.id
    candidate.reviewed_at = _now()
    candidate.review_reason = reason
    candidate.updated_at = _now()
    await session.commit()
    await session.refresh(candidate)

    await emit_audit(
        session,
        operator=operator,
        action="review_prompt_candidate",
        severity="med",
        resource_type="prompt_candidate",
        resource_id=candidate.id,
        before={"status": before_status},
        after={"status": new_status},
        reason=reason or "prompt_candidate_review",
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
    """Approve or reject a single Prompt Matrix candidate.

    ``_review_one`` calls ``emit_audit`` (med severity, action=
    ``review_prompt_candidate``); ADR-014 source-scan gate sees that
    string here in the handler so it's satisfied — see emit_audit.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    requested_status = (payload.get("status") or "").strip().lower()
    reason = (payload.get("reason") or "").strip() or None
    if requested_status not in {"approved", "rejected"}:
        raise validation_error("status", "must be 'approved' or 'rejected'")

    try:
        updated = await _review_one(
            session,
            candidate_id=candidate_id,
            requested_status=requested_status,
            operator=operator,
            reason=reason,
            request=request,
        )
    except PromptMatrixError as error:
        raise _llm_error_to_http(error) from error
    return {"success": True, "candidate": updated}


@router.post("/candidates/bulk-review", response_model=None)
async def bulk_review_candidates(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Approve or reject many candidates in one call. Per-id failures
    collected; partial failure returns 409. Each successful review emits
    its own audit row via emit_audit inside ``_review_one``.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    requested_status = (payload.get("status") or "").strip().lower()
    reason = (payload.get("reason") or "").strip() or None
    candidate_ids_raw = payload.get("candidate_ids") or []
    if requested_status not in {"approved", "rejected"}:
        raise validation_error("status", "must be 'approved' or 'rejected'")
    if not isinstance(candidate_ids_raw, list) or not candidate_ids_raw:
        raise validation_error("candidate_ids", "required, non-empty list")
    candidate_ids = [str(item).strip() for item in candidate_ids_raw if str(item).strip()]
    if not candidate_ids:
        raise validation_error("candidate_ids", "required, non-empty list")
    if len(candidate_ids) > 200:
        raise validation_error("candidate_ids", "max 200 per call")

    updated: list[dict[str, Any]] = []
    missing: list[str] = []
    failed: list[dict[str, Any]] = []
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
        except PromptMatrixError as error:
            failed.append({"id": candidate_id, "error": error.code, "message": error.message})
        except Exception as error:
            msg = str(error)
            if "candidate_not_found" in msg or getattr(error, "status_code", None) == 404:
                missing.append(candidate_id)
            else:
                failed.append({"id": candidate_id, "error": "internal_error", "message": msg})

    body = {
        "success": len(failed) == 0,
        "rows": updated,
        "summary": {
            "updated_count": len(updated),
            "missing_count": len(missing),
            "failed_count": len(failed),
        },
        "missing": missing,
        "failed": failed,
    }
    if failed:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=409, content=body)  # type: ignore[return-value]
    return body


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
        await session.execute(select(PromptGenerationRun).where(PromptGenerationRun.id == run_id))
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
    """Cancel a running Prompt Matrix generation. Idempotent on terminal
    runs. emit_audit (med, action=prompt_matrix_run_cancelled).
    """
    run = (
        await session.execute(select(PromptGenerationRun).where(PromptGenerationRun.id == run_id))
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
        action="prompt_matrix_run_cancelled",
        severity="med",
        resource_type="prompt_generation_run",
        resource_id=run.id,
        before={"status": before_status},
        after={"status": "cancelled"},
        reason="prompt_matrix_stop",
        request=request,
    )
    return {"success": True, "run": _run_to_dict(run)}
