"""Misc admin router — Phase 9 slice 9f.

Mounted at the legacy ``/api/...`` paths so admin.html keeps working
unchanged. admin_console served these without auth; the FastAPI port
adds ``Depends(current_admin)`` (security hardening).

Routes shipped in this slice:
- POST /api/sms_register                trigger account registration  (high)
- GET  /api/task_status/{task_id}       celery task probe
- GET  /api/html_files                  list debug artifacts
- GET  /api/html                        text file content
- GET  /api/screenshot                  binary image
- POST /api/backfill_citations          backfill llm_responses.citations_json (high)
- GET  /api/queries/by-day              calendar heat-map / grouped list
"""

from __future__ import annotations

import datetime as dt
import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from genpano_models import AdminUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.misc import db as misc_db
from app.admin.misc.celery_dispatch import (
    fetch_task_status,
    trigger_sms_register,
)
from app.admin.misc.lib import (
    MiscValidationError,
    list_debug_files,
    parse_by_day_args,
    validate_screenshot_path,
)
from app.api.admin.auth.router import current_admin
from app.core.security import _DependsDb

router = APIRouter(tags=["Misc legacy routes"])


def _validation_400(error: MiscValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"success": False, "error": error.code, "message": error.message},
    )


def _screenshot_dir() -> str:
    """admin_console reads SCREENSHOT_DIR from env at module import time;
    we resolve it per-request so test fixtures and prod can override
    it independently."""
    return os.environ.get("SCREENSHOT_DIR") or "/tmp/screenshots"


# ── celery wrappers ─────────────────────────────────────────


@router.post("/sms_register", response_model=None)
async def sms_register(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Manually trigger a new account registration via celery."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    platform = str(payload.get("platform") or "doubao").strip() or "doubao"

    task_id, error = trigger_sms_register(platform)
    if task_id is None:
        await emit_audit(
            session,
            operator=operator,
            action="trigger_sms_register",
            severity="high",
            resource_type="llm_account",
            after={
                "platform": platform,
                "task_id": None,
                "celery_unavailable": True,
                "error": error,
            },
            reason="trigger_sms_register",
            request=request,
        )
        return JSONResponse(
            status_code=503,
            content={"success": False, "error": error or "Celery not available"},
        )
    await emit_audit(
        session,
        operator=operator,
        action="trigger_sms_register",
        severity="high",
        resource_type="llm_account",
        after={"platform": platform, "task_id": task_id},
        reason="trigger_sms_register",
        request=request,
    )
    return JSONResponse(status_code=200, content={"success": True, "task_id": task_id})


@router.get("/task_status/{task_id}", response_model=None)
async def task_status(
    task_id: str,
    operator: Annotated[AdminUser, Depends(current_admin)],
) -> Any:
    return fetch_task_status(task_id)


# ── debug artifact endpoints ────────────────────────────────


@router.get("/html_files", response_model=None)
async def html_files(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
) -> Any:
    """List debug artifacts in SCREENSHOT_DIR. Pagination is opt-in
    (admin_console parity — bare list when neither ``page`` nor
    ``per_page`` is in the query string)."""
    qs = request.query_params
    query_id = qs.get("query_id")
    include_images = qs.get("include_images", "1") not in ("0", "false", "False")
    paginated = "page" in qs or "per_page" in qs
    try:
        page = max(1, int(qs.get("page") or 1))
    except ValueError:
        page = 1
    try:
        per_page = max(1, min(int(qs.get("per_page") or 20), 200))
    except ValueError:
        per_page = 20
    try:
        if paginated:
            page_items, total = list_debug_files(
                screenshot_dir=_screenshot_dir(),
                query_id=query_id,
                include_images=include_images,
                page=page,
                per_page=per_page,
            )
            return {
                "items": page_items,
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": (total + per_page - 1) // per_page if per_page else 1,
            }
        # Bare list path — admin_console returned every entry.
        page_items, _total = list_debug_files(
            screenshot_dir=_screenshot_dir(),
            query_id=query_id,
            include_images=include_images,
            page=1,
            per_page=10_000,
        )
        return page_items
    except Exception as error:
        return JSONResponse(status_code=500, content={"error": str(error)})


def _read_text_file(real_path: str) -> str:
    with open(real_path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _read_binary_file(real_path: str) -> bytes:
    with open(real_path, "rb") as fh:
        return fh.read()


@router.get("/html", response_model=None)
async def serve_html_source(
    operator: Annotated[AdminUser, Depends(current_admin)],
    path: str | None = Query(None),
) -> Any:
    """Serve a text/html debug file as plain text (admin_console did
    the same — for inspect-as-text)."""
    real_path, err = validate_screenshot_path(path, _screenshot_dir())
    if err is not None:
        return PlainTextResponse(err[0], status_code=err[1])
    assert real_path is not None
    import asyncio

    content = await asyncio.to_thread(_read_text_file, real_path)
    return PlainTextResponse(content, media_type="text/plain; charset=utf-8")


@router.get("/screenshot", response_model=None)
async def serve_screenshot(
    operator: Annotated[AdminUser, Depends(current_admin)],
    path: str | None = Query(None),
) -> Any:
    """Serve binary image files (PNG/JPG) from SCREENSHOT_DIR."""
    real_path, err = validate_screenshot_path(path, _screenshot_dir())
    if err is not None:
        return PlainTextResponse(err[0], status_code=err[1])
    assert real_path is not None
    lower = real_path.lower()
    if lower.endswith(".png"):
        mime = "image/png"
    elif lower.endswith((".jpg", ".jpeg")):
        mime = "image/jpeg"
    else:
        return PlainTextResponse("Unsupported file type", status_code=415)
    import asyncio

    data = await asyncio.to_thread(_read_binary_file, real_path)
    return Response(content=data, media_type=mime)


# ── backfill_citations ─────────────────────────────────────


@router.post("/backfill_citations", response_model=None)
async def backfill_citations(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Scan llm_responses with NULL citations_json and extract URLs
    from raw_text + response_html + saved HTML debug files. emit_audit
    HIGH because it bulk-rewrites the citations column."""
    try:
        result = await misc_db.backfill_citations_from_responses(
            session, screenshot_dir=_screenshot_dir()
        )
    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(error)[:300]},
        )
    await emit_audit(
        session,
        operator=operator,
        action="backfill_citations",
        severity="high",
        resource_type="llm_response",
        after={"scanned": result["scanned"], "updated": result["updated"]},
        reason="backfill_citations",
        request=request,
    )
    return JSONResponse(status_code=200, content={"success": True, **result})


# ── queries by-day ─────────────────────────────────────────


@router.get("/queries/by-day", response_model=None)
async def queries_by_day(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> Any:
    qs = request.query_params
    args: dict[str, Any] = {
        "month": qs.get("month") or "",
        "date": qs.get("date") or "",
        "llm": qs.get("llm") or "",
        "profile_id": qs.get("profile_id") or "",
    }
    try:
        normalized = parse_by_day_args(args)
    except MiscValidationError as error:
        return JSONResponse(status_code=400, content={"error": error.message})

    if normalized["mode"] == "month":
        month = normalized.get("month") or dt.datetime.utcnow().strftime("%Y-%m")
        days = await misc_db.queries_by_day_month(
            session,
            month=month,
            llm=normalized.get("llm"),
            profile_id=normalized.get("profile_id"),
        )
        return {"mode": "month", "month": month, "days": days}

    date = normalized["date"]
    detail = await misc_db.queries_by_day_date(
        session,
        date=date,
        llm=normalized.get("llm"),
        profile_id=normalized.get("profile_id"),
    )
    return {"mode": "date", "date": date, **detail}


__all__ = ["router"]
