"""Analyzer router — Phase 9 slice 9c.

Mounted at the legacy ``/api/analyzer/*`` paths so admin.html keeps
working unchanged. admin_console served these without auth; the
FastAPI port adds ``Depends(current_admin)`` (security hardening).

Routes:
- GET    /api/analyzer/stats                   (read)
- GET    /api/analyzer/brands                  (read)
- GET    /api/analyzer/llms                    (read)
- GET    /api/analyzer/responses               (read, filtered + paginated)
- GET    /api/analyzer/responses/{id}/status   (read, Admin Attempts compat)
- POST   /api/analyzer/responses/batch/dry-run (Admin Attempts rewrite compat)
- POST   /api/analyzer/responses/{id}/analyze  (Admin Attempts rewrite compat)
- POST   /api/analyzer/responses/batch         (Admin Attempts rewrite compat)
- GET    /api/analyzer/batches/{id}            (Admin Attempts rewrite compat)
- GET    /api/analyzer/response/{id}           (read, detail with mentions)
- GET    /api/analyzer/daily                   (read, geo_score_daily)
- POST   /api/analyzer/trigger                 dispatch + emit_audit (high
                                               for reanalyze, med otherwise)
- POST   /api/analyzer/rerun/{id}              dispatch + emit_audit (med)
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from genpano_models import AdminUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.analyzer import db as analyzer_db
from app.admin.analyzer.celery_dispatch import (
    dispatch_aggregate_daily_scores,
    dispatch_analyze_response,
    dispatch_run_daily_analysis,
)
from app.admin.analyzer.lib import (
    AnalyzerValidationError,
    parse_trigger_payload,
)
from app.admin.audit import emit_audit
from app.admin.queries.db import format_attempt_analysis_fields
from app.api.admin.analyzer.router import (
    analyze_response as _admin_analyze_response,
)
from app.api.admin.analyzer.router import (
    analyzer_batch_dry_run as _admin_analyzer_batch_dry_run,
)
from app.api.admin.analyzer.router import (
    analyzer_batch_status as _admin_analyzer_batch_status,
)
from app.api.admin.analyzer.router import (
    analyzer_batch_submit as _admin_analyzer_batch_submit,
)
from app.api.admin.auth.router import current_admin
from app.core.security import _DependsDb

router = APIRouter(tags=["Analyzer"])


def _validation_400(error: AnalyzerValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"success": False, "error": error.code, "message": error.message},
    )


# ── reads ────────────────────────────────────────────────────


@router.get("/analyzer/stats", response_model=None)
async def analyzer_stats(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> Any:
    return await analyzer_db.fetch_analyzer_stats(session)


@router.get("/analyzer/brands", response_model=None)
async def analyzer_brands(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> Any:
    return await analyzer_db.list_brands(session)


@router.get("/analyzer/llms", response_model=None)
async def analyzer_llms(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> Any:
    return await analyzer_db.list_distinct_llms(session)


@router.get("/analyzer/responses", response_model=None)
async def analyzer_responses(
    operator: Annotated[AdminUser, Depends(current_admin)],
    status: str | None = Query(None),
    brand_id: int | None = Query(None),
    llm: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = _DependsDb,
) -> Any:
    return await analyzer_db.list_responses(
        session,
        status=status,
        brand_id=brand_id,
        llm=llm,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


@router.get("/analyzer/responses/{response_id}/status", response_model=None)
async def analyzer_response_status(
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


@router.post("/analyzer/responses/batch/dry-run", response_model=None)
async def analyzer_batch_dry_run_compat(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    return await _admin_analyzer_batch_dry_run(request, operator, session)


@router.post("/analyzer/responses/{response_id}/analyze", response_model=None)
async def analyze_response_compat(
    response_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    return await _admin_analyze_response(response_id, request, operator, session)


@router.post("/analyzer/responses/batch", response_model=None)
async def analyzer_batch_submit_compat(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    return await _admin_analyzer_batch_submit(request, operator, session)


@router.get("/analyzer/batches/{batch_id}", response_model=None)
async def analyzer_batch_status_compat(
    batch_id: str,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    return await _admin_analyzer_batch_status(batch_id, operator, session)


@router.get("/analyzer/response/{response_id}", response_model=None)
async def analyzer_response_detail(
    response_id: int,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> Any:
    return await analyzer_db.fetch_response_detail(session, response_id)


@router.get("/analyzer/daily", response_model=None)
async def analyzer_daily(
    operator: Annotated[AdminUser, Depends(current_admin)],
    brand_id: int | None = Query(None),
    llm: str | None = Query(None),
    days: int = Query(30, ge=1, le=90),
    session: AsyncSession = _DependsDb,
) -> Any:
    return await analyzer_db.fetch_daily_scores(session, brand_id=brand_id, llm=llm, days=days)


# ── write paths ──────────────────────────────────────────────


@router.post("/analyzer/trigger", response_model=None)
async def analyzer_trigger(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Dispatch a daily analyzer job. ``action`` selects:
    - ``analyze`` (default): run_daily_analysis
    - ``aggregate``: aggregate_daily_scores
    - ``reanalyze``: reset llm_responses for the date back to pending
      then run_daily_analysis (severity HIGH because of the bulk reset)
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        normalized = parse_trigger_payload(payload)
    except AnalyzerValidationError as error:
        return _validation_400(error)

    action = normalized["action"]
    date_str = normalized["date"]
    brand_id = normalized["brand_id"]

    reset_count = 0
    task_id: str | None
    message: str
    severity: Literal["low", "med", "high"] = "med"

    if action == "analyze":
        task_id = dispatch_run_daily_analysis(date_str, brand_id)
        message = f"Analysis queued for {date_str}"
    elif action == "aggregate":
        task_id = dispatch_aggregate_daily_scores(date_str, brand_id)
        message = f"Aggregation queued for {date_str}"
    else:  # reanalyze
        severity = "high"
        reset_count = await analyzer_db.reset_responses_for_date(session, date_str=date_str)
        task_id = dispatch_run_daily_analysis(date_str, brand_id)
        message = f"Reset {reset_count} responses, analysis queued"

    if task_id is None:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "celery_unavailable",
                "message": (
                    "Celery is not configured in this deployment. "
                    "Use CLI: python -m geo_tracker.analyzer.cli run-daily "
                    f"--date {date_str}"
                ),
            },
        )

    await emit_audit(
        session,
        operator=operator,
        action=f"analyzer_trigger_{action}",
        severity=severity,
        resource_type="analyzer",
        after={
            "action": action,
            "date": date_str,
            "brand_id": brand_id,
            "task_id": task_id,
            "reset_count": reset_count if action == "reanalyze" else None,
        },
        reason=f"analyzer_trigger_{action}",
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={"success": True, "task_id": task_id, "message": message},
    )


@router.post("/analyzer/rerun/{response_id}", response_model=None)
async def analyzer_rerun(
    response_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Reset a single response to pending and queue analysis."""
    flipped = await analyzer_db.reset_response_for_rerun(session, response_id)
    if not flipped:
        return JSONResponse(status_code=404, content={"error": "Response not found"})

    task_id = dispatch_analyze_response(response_id)
    if task_id is None:
        await emit_audit(
            session,
            operator=operator,
            action="analyzer_rerun_response",
            severity="med",
            resource_type="llm_response",
            resource_id=str(response_id),
            after={"task_id": None, "celery_unavailable": True},
            reason="analyzer_rerun_response",
            request=request,
        )
        return JSONResponse(status_code=503, content={"error": "Celery not available"})

    await emit_audit(
        session,
        operator=operator,
        action="analyzer_rerun_response",
        severity="med",
        resource_type="llm_response",
        resource_id=str(response_id),
        after={"task_id": task_id},
        reason="analyzer_rerun_response",
        request=request,
    )
    return JSONResponse(status_code=200, content={"success": True, "task_id": task_id})


__all__ = ["router"]
