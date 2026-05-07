"""Admin Products router — Phase 8 slice 8a.

Mounted at ``/api/admin/products`` (canonical) and at the legacy
admin_console paths via the included router. All handlers are gated
by ``Depends(current_admin)`` and emit_audit fires on every write
(ADR-014).

Routes:
- GET    /api/admin/products                                list + pagination
- POST   /api/admin/brands/{brand_id}/products              create + emit_audit (med)
- POST   /api/admin/brands/{brand_id}/products/discover     LLM bulk + emit_audit (med)
- PUT    /api/admin/products/{product_id}                   update + emit_audit (med/high)
- DELETE /api/admin/products/{product_id}                   delete + emit_audit (high)

The brands-prefixed create/discover routes are mounted on the same
router because admin.html POSTs them to ``/api/admin/brands/{id}/...``.
This is a deliberate non-/admin/products prefix to mirror legacy.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from genpano_models import AdminUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.products import db as products_db
from app.admin.products.lib import (
    ProductValidationError,
    parse_create_payload,
    parse_discover_payload,
    parse_update_payload,
    product_row_to_dict,
)
from app.admin.products.llm import (
    discover_products,
    llm_status_code_for_error,
)
from app.admin.topic_plan.lib import TopicPlanLLMError
from app.api.admin.auth.router import current_admin
from app.core.errors import not_found
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Products"])


def _validation_400(error: ProductValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"success": False, "error": error.code, "message": error.message},
    )


def _db_error_response(error: products_db.ProductDBError) -> JSONResponse:
    """Map db-layer ``ProductDBError`` codes to HTTP statuses."""
    if error.code == "products_table_missing":
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "products_unavailable",
                "message": "products table is not available; run migrations first.",
            },
        )
    if error.code == "duplicate_product_name":
        return JSONResponse(
            status_code=409,
            content={"success": False, "error": "duplicate_product_name", "message": error.message},
        )
    if error.code == "brand_not_found":
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "brand_not_found", "message": error.message},
        )
    if error.code == "no_fields":
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "no_fields", "message": error.message},
        )
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": error.code, "message": error.message},
    )


# ────────────────────── /admin/products list ────────────────────────


@router.get("/products", response_model=None)
async def list_products(
    operator: Annotated[AdminUser, Depends(current_admin)],
    brand_id: int | None = Query(None),
    status: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = _DependsDb,
) -> Any:
    rows, total = await products_db.list_products(
        session,
        brand_id=brand_id,
        status=status,
        q=q,
        limit=limit,
        offset=offset,
    )
    return {
        "success": True,
        "products": [product_row_to_dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ────────────────── /admin/brands/{id}/products create ──────────────


@router.post("/brands/{brand_id}/products", response_model=None)
async def create_product(
    brand_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        normalized = parse_create_payload(payload)
    except ProductValidationError as error:
        return _validation_400(error)

    try:
        row = await products_db.create_product(session, brand_id=brand_id, payload=normalized)
    except products_db.ProductDBError as error:
        return _db_error_response(error)

    await emit_audit(
        session,
        operator=operator,
        action="create_product",
        severity="med",
        resource_type="product",
        resource_id=str(row["id"]),
        after={
            "brand_id": brand_id,
            "name": normalized["name"],
            "status": normalized["status"],
            "aliases_count": len(normalized.get("aliases") or []),
        },
        reason=str(payload.get("reason") or "create_product"),
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={"success": True, "product": product_row_to_dict(row)},
    )


# ───────────────── /admin/brands/{id}/products/discover ─────────────


@router.post("/brands/{brand_id}/products/discover", response_model=None)
async def discover_brand_products(
    brand_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    query, limit = parse_discover_payload(payload)

    brand = await products_db.fetch_brand_context(session, brand_id=brand_id)
    if not brand:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "brand_not_found"},
        )

    try:
        result = await discover_products(brand, query=query, limit=limit)
    except TopicPlanLLMError as error:
        return JSONResponse(
            status_code=llm_status_code_for_error(error),
            content={"success": False, "error": error.code, "message": str(error)},
        )
    except Exception as error:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "product_discovery_failed",
                "message": ("Product discovery failed: " + str(error)[:500]),
            },
        )

    try:
        created, skipped = await products_db.bulk_insert_discovered_products(
            session,
            brand_id=brand_id,
            brand_name=str(brand.get("name") or "") or None,
            candidates=result.items,
        )
    except products_db.ProductDBError as error:
        return _db_error_response(error)

    await emit_audit(
        session,
        operator=operator,
        action="discover_products",
        severity="med",
        resource_type="brand",
        resource_id=str(brand_id),
        after={
            "candidates_count": len(result.items),
            "created_count": len(created),
            "skipped_count": len(skipped),
            "llm_model": result.model,
            "operator_query": query,
            "limit": limit,
        },
        reason=str(payload.get("reason") or "discover_products"),
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "products": [product_row_to_dict(r) for r in created],
            "created_count": len(created),
            "skipped_count": len(skipped),
            "skipped": skipped,
            "candidates_count": len(result.items),
            "llm_model": result.model,
            "llm_usage": result.usage,
            "discovery_source": "llm",
            "llm_error": None,
        },
    )


# ───────────────────── /admin/products/{id} update ──────────────────


@router.put("/products/{product_id}", response_model=None)
async def update_product(
    product_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        fields = parse_update_payload(payload)
    except ProductValidationError as error:
        return _validation_400(error)
    if not fields:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "no_fields",
                "message": "no updatable fields supplied",
            },
        )

    before = await products_db.get_product(session, product_id)
    if before is None:
        raise not_found("not_found")

    try:
        row = await products_db.update_product(session, product_id=product_id, fields=fields)
    except products_db.ProductDBError as error:
        return _db_error_response(error)
    if row is None:
        raise not_found("not_found")

    severity: Literal["low", "med", "high"] = "med"
    if "status" in fields and fields["status"] != before.get("status"):
        # Status flips (active↔archived) get HIGH; other field edits MED.
        severity = "high"
    await emit_audit(
        session,
        operator=operator,
        action="update_product",
        severity=severity,
        resource_type="product",
        resource_id=str(product_id),
        before={k: before.get(k) for k in fields if k in before},
        after={k: row.get(k) for k in fields if k in row},
        reason=str(payload.get("reason") or "update_product"),
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={"success": True, "product": product_row_to_dict(row)},
    )


# ───────────────────── /admin/products/{id} delete ──────────────────


@router.delete("/products/{product_id}", response_model=None)
async def delete_product(
    product_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    before = await products_db.get_product(session, product_id)
    if before is None:
        raise not_found("not_found")

    deleted, unlinked = await products_db.delete_product(session, product_id)
    if not deleted:
        raise not_found("not_found")

    await emit_audit(
        session,
        operator=operator,
        action="delete_product",
        severity="high",
        resource_type="product",
        resource_id=str(product_id),
        before={
            "brand_id": before.get("brand_id"),
            "name": before.get("name"),
            "status": before.get("status"),
            "topic_count": before.get("topic_count"),
        },
        after={"deleted": True, "unlinked_topics": unlinked},
        reason=str(payload.get("reason") or "delete_product"),
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={"success": True, "unlinked_topics": unlinked},
    )


__all__ = ["router"]
