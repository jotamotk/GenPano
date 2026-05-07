"""Phase 8 slice 8a — admin/products (CRUD + LLM discover).

Pure-python validators tested directly; LLM + DB helpers mocked since
neither has a sqlite-friendly path. Audit-gate self-check at the end.
"""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from genpano_models import AdminAuditLog, AdminUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.products.lib import (
    PRODUCT_STATUSES,
    ProductValidationError,
    coerce_product_aliases,
    parse_create_payload,
    parse_discover_payload,
    parse_update_payload,
    product_row_to_dict,
)

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture
async def admin_operator(db_session: AsyncSession) -> AsyncGenerator[AdminUser, None]:
    from app.api.admin.auth.router import current_admin
    from app.main import app

    a = AdminUser(
        id=_new_id(),
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="$2b$04$dummyhashfortestsdummyhashfortestsdummyhashfortest",
        role="super_admin",
        status="active",
    )
    db_session.add(a)
    await db_session.commit()

    async def _override_current_admin() -> AdminUser:
        return a

    app.dependency_overrides[current_admin] = _override_current_admin
    try:
        yield a
    finally:
        app.dependency_overrides.pop(current_admin, None)


def _products_router_module():
    import app.api.admin.products.router  # noqa: F401

    return sys.modules["app.api.admin.products.router"]


def _patch_db(
    monkeypatch,
    *,
    list_returns: tuple[list[dict], int] = ([], 0),
    detail: dict | None = None,
    create_returns: dict | None = None,
    create_raises: Exception | None = None,
    update_returns: dict | None = None,
    update_raises: Exception | None = None,
    delete_returns: tuple[bool, int] = (True, 0),
    fetch_brand: dict | None = None,
    bulk_returns: tuple[list[dict], list[dict]] = ([], []),
    bulk_raises: Exception | None = None,
):
    a = _products_router_module()
    monkeypatch.setattr(a.products_db, "list_products", AsyncMock(return_value=list_returns))
    monkeypatch.setattr(a.products_db, "get_product", AsyncMock(return_value=detail))
    if create_raises is not None:
        monkeypatch.setattr(a.products_db, "create_product", AsyncMock(side_effect=create_raises))
    else:
        monkeypatch.setattr(
            a.products_db,
            "create_product",
            AsyncMock(return_value=create_returns or _product_row(1)),
        )
    if update_raises is not None:
        monkeypatch.setattr(a.products_db, "update_product", AsyncMock(side_effect=update_raises))
    else:
        monkeypatch.setattr(
            a.products_db,
            "update_product",
            AsyncMock(return_value=update_returns or _product_row(1)),
        )
    monkeypatch.setattr(a.products_db, "delete_product", AsyncMock(return_value=delete_returns))
    monkeypatch.setattr(a.products_db, "fetch_brand_context", AsyncMock(return_value=fetch_brand))
    if bulk_raises is not None:
        monkeypatch.setattr(
            a.products_db,
            "bulk_insert_discovered_products",
            AsyncMock(side_effect=bulk_raises),
        )
    else:
        monkeypatch.setattr(
            a.products_db,
            "bulk_insert_discovered_products",
            AsyncMock(return_value=bulk_returns),
        )


def _product_row(product_id: int = 1) -> dict:
    return {
        "id": product_id,
        "brand_id": 7,
        "brand_name": "TestBrand",
        "name": "TestProduct",
        "sku": "",
        "category": "",
        "description": "",
        "aliases": [],
        "status": "active",
        "topic_count": 0,
        "created_at": "2026-05-07T10:00:00",
        "updated_at": "2026-05-07T10:00:00",
    }


# ── lib.py: pure helpers ─────────────────────────────────────


def test_product_statuses_constant():
    assert PRODUCT_STATUSES == ("active", "archived")


def test_coerce_aliases_list_strips_blanks():
    assert coerce_product_aliases([" a ", "", "  ", "b"]) == ["a", "b"]


def test_coerce_aliases_json_string():
    assert coerce_product_aliases('["x","y"]') == ["x", "y"]


def test_coerce_aliases_comma_string():
    assert coerce_product_aliases("x, y, z") == ["x", "y", "z"]


def test_coerce_aliases_newline_separated():
    assert coerce_product_aliases("x\ny\nz") == ["x", "y", "z"]


def test_coerce_aliases_none():
    assert coerce_product_aliases(None) == []
    assert coerce_product_aliases("") == []


def test_parse_create_payload_minimum():
    out = parse_create_payload({"name": " Apple "})
    assert out == {
        "name": "Apple",
        "sku": None,
        "category": None,
        "description": None,
        "aliases": [],
        "status": "active",
    }


def test_parse_create_payload_full():
    out = parse_create_payload(
        {
            "name": "iPhone",
            "sku": "ABC-1",
            "category": "phone",
            "description": "x",
            "aliases": ["A", "B"],
            "status": "archived",
        }
    )
    assert out["name"] == "iPhone"
    assert out["sku"] == "ABC-1"
    assert out["status"] == "archived"
    assert out["aliases"] == ["A", "B"]


def test_parse_create_payload_missing_name():
    with pytest.raises(ProductValidationError) as exc:
        parse_create_payload({})
    assert exc.value.code == "name_required"


def test_parse_create_payload_invalid_status_falls_back_to_active():
    out = parse_create_payload({"name": "x", "status": "weird"})
    assert out["status"] == "active"


def test_parse_update_payload_partial():
    out = parse_update_payload({"name": "X", "sku": "S"})
    assert out == {"name": "X", "sku": "S"}


def test_parse_update_payload_status_invalid():
    with pytest.raises(ProductValidationError) as exc:
        parse_update_payload({"status": "weird"})
    assert exc.value.code == "invalid_status"


def test_parse_update_payload_status_normalized():
    assert parse_update_payload({"status": "ARCHIVED"}) == {"status": "archived"}


def test_parse_update_payload_empty_returns_empty():
    assert parse_update_payload({}) == {}


def test_parse_update_payload_blank_name_rejected():
    with pytest.raises(ProductValidationError) as exc:
        parse_update_payload({"name": "   "})
    assert exc.value.code == "name_required"


def test_parse_discover_payload_clamps():
    assert parse_discover_payload({"limit": 100}) == ("", 20)
    assert parse_discover_payload({"limit": 0}) == ("", 1)
    assert parse_discover_payload({"limit": "weird"}) == ("", 8)
    assert parse_discover_payload({"hint": "foo"}) == ("foo", 8)
    assert parse_discover_payload({"query": "bar", "hint": "ignored"}) == ("bar", 8)


def test_product_row_to_dict_jsonb_string_aliases():
    row = {"id": 1, "aliases": '["x","y"]', "name": "X"}
    out = product_row_to_dict(row)
    assert out is not None
    assert out["aliases"] == ["x", "y"]


def test_product_row_to_dict_handles_none():
    assert product_row_to_dict(None) is None


# ── auth (current_admin gate) ────────────────────────────────


@pytest.mark.asyncio
async def test_list_unauth_401(client):
    resp = await client.get("/api/admin/products")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_unauth_401(client):
    resp = await client.post("/api/admin/brands/1/products", json={"name": "x"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_discover_unauth_401(client):
    resp = await client.post("/api/admin/brands/1/products/discover", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_update_unauth_401(client):
    resp = await client.put("/api/admin/products/1", json={"name": "x"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_unauth_401(client):
    resp = await client.delete("/api/admin/products/1")
    assert resp.status_code == 401


# ── GET /products ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_returns_pagination(client, admin_operator, monkeypatch):
    rows = [_product_row(1), _product_row(2)]
    _patch_db(monkeypatch, list_returns=(rows, 17))
    resp = await client.get("/api/admin/products?brand_id=7&status=active&q=ab&limit=10&offset=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["total"] == 17
    assert body["limit"] == 10
    assert body["offset"] == 5
    assert len(body["products"]) == 2


@pytest.mark.asyncio
async def test_list_validates_limit_high(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, list_returns=([], 0))
    resp = await client.get("/api/admin/products?limit=99999")
    # Pydantic validation: 422
    assert resp.status_code == 422


# ── POST /brands/{id}/products create ────────────────────────


@pytest.mark.asyncio
async def test_create_validation_400(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch)
    resp = await client.post("/api/admin/brands/7/products", json={})
    assert resp.status_code == 400
    assert resp.json()["error"] == "name_required"


@pytest.mark.asyncio
async def test_create_brand_not_found_404(client, admin_operator, monkeypatch):
    from app.admin.products.db import ProductDBError

    _patch_db(
        monkeypatch,
        create_raises=ProductDBError("brand_not_found", "Brand not found"),
    )
    resp = await client.post("/api/admin/brands/9999/products", json={"name": "x"})
    assert resp.status_code == 404
    assert resp.json()["error"] == "brand_not_found"


@pytest.mark.asyncio
async def test_create_duplicate_409(client, admin_operator, monkeypatch):
    from app.admin.products.db import ProductDBError

    _patch_db(
        monkeypatch,
        create_raises=ProductDBError(
            "duplicate_product_name", "A product with this name already exists"
        ),
    )
    resp = await client.post("/api/admin/brands/7/products", json={"name": "x"})
    assert resp.status_code == 409
    assert resp.json()["error"] == "duplicate_product_name"


@pytest.mark.asyncio
async def test_create_table_missing_503(client, admin_operator, monkeypatch):
    from app.admin.products.db import ProductDBError

    _patch_db(
        monkeypatch,
        create_raises=ProductDBError("products_table_missing", "no products"),
    )
    resp = await client.post("/api/admin/brands/7/products", json={"name": "x"})
    assert resp.status_code == 503
    assert resp.json()["error"] == "products_unavailable"


@pytest.mark.asyncio
async def test_create_audit_med_severity(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_db(monkeypatch, create_returns=_product_row(42))
    resp = await client.post(
        "/api/admin/brands/7/products",
        json={"name": "X", "aliases": ["a", "b"]},
    )
    assert resp.status_code == 200
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "create_product")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "med"
    assert audit[0].after.get("aliases_count") == 2


# ── POST /brands/{id}/products/discover ──────────────────────


@pytest.mark.asyncio
async def test_discover_brand_404(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, fetch_brand=None)
    resp = await client.post("/api/admin/brands/999/products/discover", json={})
    assert resp.status_code == 404
    assert resp.json()["error"] == "brand_not_found"


@pytest.mark.asyncio
async def test_discover_llm_failure_propagates(client, admin_operator, monkeypatch):
    from app.admin.products.llm import ProductDiscoveryResult
    from app.admin.topic_plan.lib import TopicPlanLLMError

    a = _products_router_module()
    _patch_db(monkeypatch, fetch_brand={"id": 7, "name": "TestBrand", "aliases": []})

    async def _llm_raise(*args, **kwargs):
        raise TopicPlanLLMError("llm_call_failed", "boom")

    monkeypatch.setattr(a, "discover_products", _llm_raise)
    resp = await client.post("/api/admin/brands/7/products/discover", json={})
    assert resp.status_code == 503
    assert resp.json()["error"] == "llm_call_failed"
    # ProductDiscoveryResult import sanity: ensure class importable
    assert ProductDiscoveryResult is not None


@pytest.mark.asyncio
async def test_discover_audit_records_counts(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    from app.admin.products.llm import ProductDiscoveryResult

    a = _products_router_module()
    created_rows = [_product_row(101), _product_row(102)]
    skipped_rows = [{"name": "Dup", "reason": "duplicate"}]
    _patch_db(
        monkeypatch,
        fetch_brand={"id": 7, "name": "TestBrand", "aliases": []},
        bulk_returns=(created_rows, skipped_rows),
    )

    async def _llm_ok(*args, **kwargs):
        return ProductDiscoveryResult(
            items=[
                {"name": "P1", "aliases": []},
                {"name": "P2", "aliases": []},
                {"name": "Dup", "aliases": []},
            ],
            model="doubao-test",
            usage={"prompt_tokens": 100},
        )

    monkeypatch.setattr(a, "discover_products", _llm_ok)
    resp = await client.post(
        "/api/admin/brands/7/products/discover", json={"query": "shoes", "limit": 5}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created_count"] == 2
    assert body["skipped_count"] == 1
    assert body["candidates_count"] == 3

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "discover_products")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    after = audit[0].after or {}
    assert after.get("created_count") == 2
    assert after.get("skipped_count") == 1
    assert after.get("operator_query") == "shoes"
    assert after.get("limit") == 5


# ── PUT /products/{id} ───────────────────────────────────────


@pytest.mark.asyncio
async def test_update_validation_400_no_fields(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, detail=_product_row(1))
    resp = await client.put("/api/admin/products/1", json={})
    assert resp.status_code == 400
    assert resp.json()["error"] == "no_fields"


@pytest.mark.asyncio
async def test_update_404_when_missing(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, detail=None)
    resp = await client.put("/api/admin/products/1", json={"name": "x"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_invalid_status_400(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, detail=_product_row(1))
    resp = await client.put("/api/admin/products/1", json={"status": "weird"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_status"


@pytest.mark.asyncio
async def test_update_audit_med_for_field_edits(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    before = _product_row(1)
    after = {**_product_row(1), "name": "X", "category": "Y"}
    _patch_db(monkeypatch, detail=before, update_returns=after)
    resp = await client.put("/api/admin/products/1", json={"name": "X", "category": "Y"})
    assert resp.status_code == 200
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "update_product")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "med"


@pytest.mark.asyncio
async def test_update_audit_high_for_status_change(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    before = {**_product_row(1), "status": "active"}
    after = {**_product_row(1), "status": "archived"}
    _patch_db(monkeypatch, detail=before, update_returns=after)
    resp = await client.put("/api/admin/products/1", json={"status": "archived"})
    assert resp.status_code == 200
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "update_product")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "high"


# ── DELETE /products/{id} ────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_404_when_missing(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, detail=None)
    resp = await client.delete("/api/admin/products/1")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_returns_unlinked_count(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_db(monkeypatch, detail=_product_row(5), delete_returns=(True, 3))
    resp = await client.delete("/api/admin/products/5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["unlinked_topics"] == 3
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "delete_product")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "high"
    assert audit[0].after.get("unlinked_topics") == 3


# ── lib.coerce_aliases edge cases ────────────────────────────


def test_coerce_aliases_invalid_json_falls_through_to_comma_split():
    """JSON parse fails → admin_console falls through to comma/newline split."""
    out = coerce_product_aliases("not, valid, json")
    assert out == ["not", "valid", "json"]


# ── audit gate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_slice8a():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
