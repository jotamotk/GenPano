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
from app.admin.analyzer.lib import (
    AnalyzerValidationError,
    build_batch_dry_run_result,
    parse_batch_dry_run_payload,
    parse_single_analyze_payload,
)
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

    return _dependency_blocked(
        {
            "response_id": response_id,
            "mode": normalized["mode"],
            "analysis_status": status.get("analysis_status"),
            "analysis_id": status.get("analysis_id"),
            "accepted": False,
            "skipped_reason": "blocked_until_781_run_persistence",
        }
    )


@router.post("/analyzer/responses/batch", response_model=None)
async def analyzer_batch_submit(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    try:
        normalized = parse_batch_dry_run_payload(payload)
    except AnalyzerValidationError as error:
        return _validation_400(error)

    return _dependency_blocked(
        {
            "mode": normalized["mode"],
            "accepted_count": 0,
            "skipped_count": 0,
            "skipped_reason": "blocked_until_781_batch_persistence",
        }
    )


@router.get("/analyzer/batches/{batch_id}", response_model=None)
async def analyzer_batch_status(
    batch_id: str,
    operator: Annotated[AdminUser, Depends(current_admin)],
) -> JSONResponse:
    return _dependency_blocked(
        {
            "batch_job_id": batch_id,
            "status": "blocked",
        }
    )


__all__ = ["router"]
