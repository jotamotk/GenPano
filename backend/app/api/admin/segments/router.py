"""Admin Segments router (Phase 6 slice 6a — CRUD only).

Mounted at ``/api/admin/segments`` (cookie ``current_admin``). The legacy
SPA also calls these via ``/api/segments/*``; the alias is mounted at
the FastAPI app layer in ``app/main.py`` so the same handlers serve both.

Routes in this PR:
- GET    /                — paged list + summary stats
- POST   /                — create (201)
- GET    /{segment_id}    — detail
- PUT    /{segment_id}    — update
- DELETE /{segment_id}    — soft delete + cascade-soft-delete profiles

Bulk import + LLM generate are deferred to slice 6a-bis. Profile sub-
routes (``/{segment_id}/profiles/...``) belong to slice 6b.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from genpano_models import AdminUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.segments import db as segments_db
from app.api.admin.auth.router import current_admin
from app.core.errors import not_found, validation_error
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Segments"])


_SEGMENT_PAYLOAD_ERRORS = {"segment_name_required", "invalid_segment_status"}


@router.get("", response_model=None)
async def list_segments(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
    page: int = Query(1, ge=1, le=100_000),
    per_page: int = Query(50, ge=1, le=200),
    q: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    industry_id: str | None = Query(None),
    brand_id: str | None = Query(None),
) -> dict[str, Any]:
    """Paged segments list with summary counters.

    Same wire shape as admin_console:
    ``{success, rows, pagination, summary}``.
    """
    rows, total, summary = await segments_db.fetch_segments(
        session,
        page=page,
        per_page=per_page,
        q=q,
        status=status_filter,
        industry_id=industry_id,
        brand_id=brand_id,
    )
    total_pages = (total + per_page - 1) // per_page if per_page else 1
    return {
        "success": True,
        "rows": rows,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
        "summary": summary,
    }


@router.post("", response_model=None)
async def create_segment(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Insert a new segment row + emit_audit (med, action=create_segment).

    201 on success; 422 on validation error (``segment_name_required``,
    ``invalid_segment_status``, ``segment_id_exists``).
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        row = await segments_db.create_segment(session, payload, operator.id)
    except ValueError as exc:
        code = (
            str(exc)
            if str(exc) in _SEGMENT_PAYLOAD_ERRORS or str(exc) == "segment_id_exists"
            else "segment_create_failed"
        )
        raise validation_error("payload", code) from exc

    await emit_audit(
        session,
        operator=operator,
        action="create_segment",
        severity="med",
        resource_type="segment",
        resource_id=str(row.get("id") or ""),
        after=row,
        reason=str(payload.get("reason") or "create_segment"),
        request=request,
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"success": True, "segment": row},
    )


@router.get("/{segment_id}", response_model=None)
async def get_segment(
    segment_id: str,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    row = await segments_db.get_segment(session, segment_id)
    if row is None:
        raise not_found("segment_not_found")
    return {"success": True, "segment": row}


@router.put("/{segment_id}", response_model=None)
async def update_segment(
    segment_id: str,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Update a segment + emit_audit (med, action=update_segment)."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    before = await segments_db.get_segment(session, segment_id)
    if before is None:
        raise not_found("segment_not_found")
    try:
        row = await segments_db.update_segment(session, segment_id, payload, operator.id)
    except ValueError as exc:
        if str(exc) == "segment_not_found":
            raise not_found("segment_not_found") from exc
        code = str(exc) if str(exc) in _SEGMENT_PAYLOAD_ERRORS else "segment_update_failed"
        raise validation_error("payload", code) from exc
    await emit_audit(
        session,
        operator=operator,
        action="update_segment",
        severity="med",
        resource_type="segment",
        resource_id=str(row.get("id") or ""),
        before=before,
        after=row,
        reason=str(payload.get("reason") or "update_segment"),
        request=request,
    )
    return {"success": True, "segment": row}


@router.delete("/{segment_id}", response_model=None)
async def delete_segment(
    segment_id: str,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Soft-delete segment + cascade to its profiles. emit_audit
    (high, action=delete_segment) — destructive op."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    before = await segments_db.soft_delete_segment(session, segment_id, operator.id)
    if before is None:
        raise not_found("segment_not_found")
    await emit_audit(
        session,
        operator=operator,
        action="delete_segment",
        severity="high",
        resource_type="segment",
        resource_id=str(before.get("id") or ""),
        before=before,
        after={"status": "deleted", "is_deleted": True},
        reason=str(payload.get("reason") or "delete_segment"),
        request=request,
    )
    return {"success": True, "segment": before}
