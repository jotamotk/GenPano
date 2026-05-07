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


# ---------------------------------------------------------------------------
# Phase 6 slice 6a-bis — bulk import + LLM generate
# ---------------------------------------------------------------------------


from app.admin.segments.db import (  # noqa: E402
    BrandSelectionAmbiguous,
    import_segments_bulk,
    resolve_admin_brand_selection,
    write_segment_generation_log,
)
from app.admin.segments.llm import (  # noqa: E402
    SegmentProfileGenerationError,
    SegmentProfileGenerationService,
    drafts_with_brand_context,
    segment_profile_generation_status,
)


@router.post("/import", response_model=None)
async def import_segments(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Bulk-upsert segments from a SPA-supplied ``rows`` array.

    Per-row validation failures are skipped (counted in ``skipped``)
    rather than aborting the batch — admin_console parity. Single
    ``import_segments`` audit row covers the whole batch.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    rows_raw = payload.get("rows") or payload.get("segments") or []
    if not isinstance(rows_raw, list):
        raise validation_error("rows", "rows_must_be_array")
    rows = [r for r in rows_raw if isinstance(r, dict)]
    result = await import_segments_bulk(session, rows, operator.id)
    await emit_audit(
        session,
        operator=operator,
        action="import_segments",
        severity="med",
        resource_type="segment",
        resource_id="",  # batch op — no single id
        after={
            "added": result["added"],
            "updated": result["updated"],
            "skipped": result["skipped"],
        },
        reason=str(payload.get("reason") or "import_segments"),
        request=request,
    )
    return {"success": True, **result}


_GENERATE_VALUE_ERRORS = {"brand_name_required", "ambiguous_brand"}


@router.post("/generate", response_model=None)
async def generate_segments_route(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Generate Segment drafts via LLM and return them for operator
    review (no DB write to ``segments``).

    Two-phase flow:
    1. Resolve operator-supplied ``brand_name``/``brand_id`` against
       the production brands table. Multiple matches → 409 with
       candidate list so the SPA can prompt the operator to pick one.
    2. Call the async ``SegmentProfileGenerationService``. Successful
       drafts are written to ``segment_generation_logs`` (best-effort)
       and returned with ``brand_*`` context so the SPA preview can
       render brand-aware fields.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    try:
        brand_selection = await resolve_admin_brand_selection(session, payload)
    except BrandSelectionAmbiguous as error:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": "ambiguous_brand",
                "brands": error.candidates,
            },
        )

    brand_name = brand_selection.get("brand_name") or ""
    brand_id = brand_selection.get("brand_id")
    payload = {**payload, "brand_id": brand_id, "brand_name": brand_name}
    if not brand_name:
        raise validation_error("brand_name", "brand_name_required")

    service = SegmentProfileGenerationService(
        model=payload.get("llm_model"),
        allow_fallback=False,
    )
    try:
        result = await service.generate_segments(
            brand_name=brand_name,
            industry=str(payload.get("industry") or payload.get("industry_id") or "").strip(),
            count=int(payload.get("count") or 6),
            status=str(payload.get("status") or "draft").strip().lower(),
            positioning=str(payload.get("positioning") or ""),
            goal=str(payload.get("goal") or ""),
            constraints=str(payload.get("constraints") or ""),
        )
    except SegmentProfileGenerationError as error:
        # Audit the LLM-side failure so an outage shows up in audit-log
        # search before a human surfaces it. emit_audit (med).
        await emit_audit(
            session,
            operator=operator,
            action="generate_segments_failed",
            severity="med",
            resource_type="segment",
            resource_id="",
            after={"error_code": error.code, "brand_name": brand_name},
            reason="generate_segments",
            request=request,
        )
        return JSONResponse(
            status_code=segment_profile_generation_status(error),
            content={
                "success": False,
                "error": error.code,
                "message": error.message,
            },
        )

    drafts = drafts_with_brand_context(result.items, brand_id=brand_id, brand_name=brand_name)
    await write_segment_generation_log(
        session,
        admin_id=operator.id,
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
        action="generate_segments",
        severity="med",
        resource_type="segment",
        resource_id="",
        after={
            "count": len(result.items),
            "model": result.model,
            "brand_id": brand_id,
            "brand_name": brand_name,
        },
        reason=str(payload.get("reason") or "generate_segments"),
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "drafts": drafts,
            "model": result.model,
            "usage": result.usage,
        },
    )
