"""Admin Brand Management router (Phase 7 slice 7a — CRUD + industries).

Mounted at ``/api/admin/brand-management`` (cookie ``current_admin``).

Routes in this PR:
- GET    /industries        distinct industries currently in ``brands``
- GET    /                  paged list with industry/source/status/search
- GET    /{brand_id}        detail
- POST   /                  create + emit_audit (med, action=create_brand)
- PUT    /{brand_id}        update + emit_audit (med, action=update_brand)
- DELETE /{brand_id}        soft delete (status='archived') + emit_audit (high)

Bulk import + LLM generate / enrich are deferred to slice 7a-bis. Cookies
+ accounts are slice 7b.

Notes:
- ``brands`` is an upstream stub in backend's ORM (ADR-002); all DB ops
  use raw text() with defensive ``information_schema`` probes — see
  app/admin/brand_management/db.py.
- The optional ``kg_brands`` mirror + competitor relation candidates that
  admin_console's handlers wrote alongside the main brand row are
  intentionally NOT ported here. They were ``_run_optional_brand_side_effect``
  best-effort writes; the ``kg_discovery`` admin job repopulates kg_brands
  from brands periodically. Slice 7a-bis can reintroduce the relation
  candidates path if needed.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from genpano_models import AdminUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.brand_management import db as brand_db
from app.admin.brand_management.lib import (
    BrandManagementError,
    brand_management_status_for_error,
    normalize_brand_draft,
    normalize_brand_source_input,
)
from app.api.admin.auth.router import current_admin
from app.core.errors import not_found, validation_error
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Brand Management"])


@router.get("/industries", response_model=None)
async def list_industries(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Distinct industries with brand counts (for filter dropdowns)."""
    industries = await brand_db.fetch_industries(session)
    return {"success": True, "industries": industries}


@router.get("", response_model=None)
async def list_brands(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
    page: int = Query(1, ge=1, le=100_000),
    per_page: int = Query(25, ge=1, le=200),
    q: str | None = Query(None),
    industry: str | None = Query(None),
    source: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
) -> dict[str, Any]:
    """Paginated brand list — same wire shape as admin_console."""
    rows, total = await brand_db.fetch_brands(
        session,
        page=page,
        per_page=per_page,
        q=q,
        industry=industry,
        source=source,
        status=status_filter,
    )
    total_pages = (total + per_page - 1) // per_page if per_page else 1
    return {
        "success": True,
        "brands": rows,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
    }


@router.get("/{brand_id}", response_model=None)
async def get_brand(
    brand_id: int,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    row = await brand_db.get_brand(session, brand_id)
    if row is None:
        raise not_found("brand_not_found")
    return {"success": True, "brand": row}


@router.post("", response_model=None)
async def create_brand(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Insert a new brand + emit_audit (med, action=create_brand).

    400 on validation error (``missing_brand_name`` /
    ``invalid_brand_payload``); 409 on duplicate brand name.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        draft = normalize_brand_draft(payload)
    except BrandManagementError as error:
        raise validation_error("payload", error.code) from error
    draft["source"] = normalize_brand_source_input(payload.get("source")) or "manual"

    if await brand_db.brand_name_exists(session, draft["name"]):
        return JSONResponse(
            status_code=409,
            content={"success": False, "error": "duplicate_brand_name"},
        )

    try:
        brand_id = await brand_db.persist_brand_draft(session, draft, admin_id=operator.id)
    except Exception as exc:
        # Fall through to controlled 500 (admin_console returned the
        # same on unexpected DB errors).
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "brand_create_failed", "message": str(exc)[:300]},
        )

    row = await brand_db.get_brand(session, brand_id)
    await emit_audit(
        session,
        operator=operator,
        action="create_brand",
        severity="med",
        resource_type="brand",
        resource_id=str(brand_id),
        after={
            "name": draft["name"],
            "industry": draft["industry"],
            "source": draft["source"],
        },
        reason=str(payload.get("reason") or "create_brand"),
        request=request,
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"success": True, "brand": row, "relation_candidates": 0},
    )


@router.put("/{brand_id}", response_model=None)
async def update_brand(
    brand_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Update a brand + emit_audit (med, action=update_brand)."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        draft = normalize_brand_draft(payload)
    except BrandManagementError as error:
        raise validation_error("payload", error.code) from error

    existing = await brand_db.get_brand(session, brand_id)
    if existing is None:
        raise not_found("brand_not_found")

    if await brand_db.brand_name_exists(session, draft["name"], exclude_id=brand_id):
        return JSONResponse(
            status_code=409,
            content={"success": False, "error": "duplicate_brand_name"},
        )

    try:
        await brand_db.persist_brand_draft(session, draft, admin_id=operator.id, brand_id=brand_id)
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "brand_update_failed",
                "message": str(exc)[:300],
            },
        )

    row = await brand_db.get_brand(session, brand_id)
    await emit_audit(
        session,
        operator=operator,
        action="update_brand",
        severity="med",
        resource_type="brand",
        resource_id=str(brand_id),
        before=existing,
        after={"name": draft["name"], "status": draft["status"]},
        reason=str(payload.get("reason") or "update_brand"),
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={"success": True, "brand": row},
    )


@router.delete("/{brand_id}", response_model=None)
async def archive_brand(
    brand_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Soft-delete (status='archived') + emit_audit (high, action=archive_brand).

    Hard delete is intentionally not supported here — it would cascade
    into ``kg_brands`` / ``brand_mentions`` and other upstream tables.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    existing = await brand_db.get_brand(session, brand_id)
    if existing is None:
        raise not_found("brand_not_found")
    archived = await brand_db.archive_brand(session, brand_id)
    if not archived:
        raise not_found("brand_not_found")
    await emit_audit(
        session,
        operator=operator,
        action="archive_brand",
        severity="high",
        resource_type="brand",
        resource_id=str(brand_id),
        before=existing,
        after={"status": "archived"},
        reason=str(payload.get("reason") or "archive_brand"),
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={"success": True, "status": "archived"},
    )


# Re-export for slice 7a-bis tests + backward-compat with admin_console
# error mapping conventions.
__all__ = [
    "BrandManagementError",
    "brand_management_status_for_error",
    "router",
]
