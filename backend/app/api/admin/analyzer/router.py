"""Admin Attempts analyzer API.

Mounted only at /admin/api/analyzer/* for the orange Admin Attempts surface.
Legacy /api/analyzer/* routes remain in app.api.analyzer.router for Analyzer
Quality compatibility.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from genpano_models import AdminUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.analyzer import db as analyzer_db
from app.admin.analyzer.celery_dispatch import dispatch_analyze_response
from app.admin.analyzer.lib import (
    AnalyzerValidationError,
    build_batch_dry_run_result,
    parse_batch_dry_run_payload,
    parse_single_analyze_payload,
)
from app.admin.audit import emit_audit
from app.admin.queries.db import format_attempt_analysis_fields
from app.api.admin.auth.router import current_admin
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin Analyzer"])


def _validation_400(error: AnalyzerValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"success": False, "error": error.code, "message": error.message},
    )


def _dependency_blocked(content: dict[str, Any] | None = None) -> JSONResponse:
    body: dict[str, Any] = {
        "success": False,
        "error": "analyzer_run_persistence_required",
        "message": (
            "#781 must provide durable run/batch persistence and "
            "validate/stage-before-replace semantics before this endpoint can mutate facts."
        ),
        "blocked_by_issue": 781,
    }
    if content:
        body.update(content)
    return JSONResponse(status_code=409, content=body)


@router.post("/analyzer/responses/batch/dry-run", response_model=None)
async def analyzer_batch_dry_run(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    try:
        normalized = parse_batch_dry_run_payload(payload)
    except AnalyzerValidationError as error:
        return _validation_400(error)

    rows = await analyzer_db.preview_batch_analyzer_candidates(
        session,
        scope=normalized["scope"],
    )
    result = build_batch_dry_run_result(normalized, rows)
    return JSONResponse(status_code=200, content=result)


@router.get("/analyzer/responses/{response_id}/status", response_model=None)
async def response_analyzer_status(
    response_id: int,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    status = await analyzer_db.fetch_response_analyzer_status(session, response_id)
    if status is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "response_not_found"},
        )

    item = format_attempt_analysis_fields(status)
    item["success"] = True
    return JSONResponse(status_code=200, content=item)


@router.post("/analyzer/responses/{response_id}/analyze", response_model=None)
async def analyze_response(
    response_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    try:
        normalized = parse_single_analyze_payload(payload)
    except AnalyzerValidationError as error:
        return _validation_400(error)

    status = await analyzer_db.fetch_response_analyzer_status(session, response_id)
    if status is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "response_not_found"},
        )
    if not str(status.get("raw_text") or "").strip():
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "ineligible_no_response",
                "response_id": response_id,
                "skipped_reason": "no_response_text",
            },
        )

    if (
        normalized["mode"] == "missing_or_failed_only"
        and str(status.get("analysis_status") or "").lower() == "done"
        and status.get("analysis_id") is not None
    ):
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "accepted": False,
                "response_id": response_id,
                "mode": normalized["mode"],
                "analysis_status": status.get("analysis_status"),
                "analysis_id": status.get("analysis_id"),
                "skipped_reason": "already_done",
            },
        )

    run = await analyzer_db.create_or_get_queued_analyzer_run(
        session,
        response_id=response_id,
        mode=normalized["mode"],
        trigger_source="admin_single",
        previous_analysis_status=status.get("analysis_status"),
        idempotency_key=normalized.get("idempotency_key"),
    )
    if run.get("idempotent"):
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "accepted": True,
                "idempotent": True,
                "response_id": response_id,
                "mode": normalized["mode"],
                "run_id": run.get("run_id"),
                "task_id": run.get("task_id"),
                "status": run.get("status"),
            },
        )

    task_id = dispatch_analyze_response(response_id, analyzer_run_id=int(run["run_id"]))
    if task_id is None:
        await analyzer_db.mark_analyzer_run_enqueue_failed(
            session,
            run_id=int(run["run_id"]),
            previous_analysis_status=run.get("previous_analysis_status"),
        )
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "accepted": False,
                "error": "analyzer_enqueue_failed",
                "response_id": response_id,
                "run_id": run.get("run_id"),
                "task_id": None,
            },
        )

    await analyzer_db.mark_analyzer_run_enqueued(
        session,
        run_id=int(run["run_id"]),
        task_id=task_id,
    )
    await emit_audit(
        session,
        operator=operator,
        action="admin_analyzer_analyze_response",
        severity="med",
        resource_type="llm_response",
        resource_id=str(response_id),
        after={
            "run_id": run.get("run_id"),
            "task_id": task_id,
            "mode": normalized["mode"],
        },
        reason=normalized.get("reason") or "admin_analyzer_analyze_response",
        request=request,
    )
    return JSONResponse(
        status_code=202,
        content={
            "success": True,
            "accepted": True,
            "idempotent": False,
            "response_id": response_id,
            "mode": normalized["mode"],
            "run_id": run.get("run_id"),
            "task_id": task_id,
            "status": "queued",
        },
    )


@router.post("/analyzer/responses/batch", response_model=None)
async def analyzer_batch_submit(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    try:
        normalized = parse_batch_dry_run_payload(payload)
    except AnalyzerValidationError as error:
        return _validation_400(error)

    if not normalized.get("confirm"):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "confirmation_required",
                "message": "confirm=true is required to submit analyzer batch work",
            },
        )

    rows = await analyzer_db.preview_batch_analyzer_candidates(
        session,
        scope=normalized["scope"],
    )
    result = build_batch_dry_run_result(normalized, rows)
    if not result.get("success"):
        return JSONResponse(status_code=400, content=result)
    result["_candidate_rows"] = list(rows)
    batch = await analyzer_db.create_analyzer_batch_submission(
        session,
        normalized=normalized,
        preview=result,
        operator_id=str(operator.id),
    )
    if batch.get("idempotent"):
        return JSONResponse(status_code=200, content=batch)

    submitted_response_ids: list[int] = []
    for item in batch.get("items") or []:
        if item.get("status") != "queued" or not item.get("run_id") or not item.get("response_id"):
            continue
        response_id = int(item["response_id"])
        run_id = int(item["run_id"])
        task_id = dispatch_analyze_response(response_id, analyzer_run_id=run_id)
        if task_id is None:
            await analyzer_db.mark_analyzer_batch_item_enqueue_failed(
                session,
                item_id=int(item["item_id"]),
                run_id=run_id,
            )
            continue
        await analyzer_db.mark_analyzer_batch_item_enqueued(
            session,
            item_id=int(item["item_id"]),
            run_id=run_id,
            task_id=task_id,
        )
        item["task_id"] = task_id
        submitted_response_ids.append(response_id)

    refreshed = await analyzer_db.refresh_analyzer_batch_status(session, str(batch["batch_id"]))
    if refreshed:
        batch.update(refreshed)
    batch["success"] = True
    batch["submitted_response_ids"] = submitted_response_ids or batch.get(
        "submitted_response_ids", []
    )
    batch["accepted_count"] = len(submitted_response_ids)
    await emit_audit(
        session,
        operator=operator,
        action="admin_analyzer_batch_submit",
        severity="med",
        resource_type="analyzer_batch",
        resource_id=str(batch["batch_id"]),
        after={
            "batch_id": batch["batch_id"],
            "accepted_count": batch["accepted_count"],
            "skipped_count": batch.get("skipped_count", 0),
            "mode": normalized["mode"],
        },
        reason=normalized.get("reason") or "admin_analyzer_batch_submit",
        request=request,
    )
    return JSONResponse(
        status_code=202 if batch["accepted_count"] else 200,
        content=batch,
    )


@router.get("/analyzer/batches/{batch_id}", response_model=None)
async def analyzer_batch_status(
    batch_id: str,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    status = await analyzer_db.fetch_analyzer_batch_status(session, batch_id)
    if status is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "batch_not_found", "batch_id": batch_id},
        )
    if status.get("error") == "analyzer_batch_persistence_required":
        return JSONResponse(status_code=409, content=status)
    return JSONResponse(status_code=200, content=status)


__all__ = ["router"]
