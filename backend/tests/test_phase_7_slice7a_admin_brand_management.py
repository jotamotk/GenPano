"""Phase 7 slice 7a — admin/brand-management CRUD + industries.

``brands`` is an upstream stub in backend's ORM (ADR-002 — only ``id``
modeled), so the route handlers' SQL won't execute against the sqlite
test fixture. Tests therefore mock the ``brand_db`` helpers and
exercise the handler logic (auth, validation, error mapping, audit
emission). Pure-python validators in ``app/admin/brand_management/lib.py``
are tested directly without DB.
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

from app.admin.brand_management.lib import (
    ALLOWED_BRAND_SOURCES,
    ALLOWED_BRAND_STATUSES,
    BrandManagementError,
    coerce_str_list,
    normalize_brand_draft,
    normalize_brand_source_input,
    normalize_competitors,
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


def _bm_router_module():
    import app.api.admin.brand_management.router  # noqa: F401

    return sys.modules["app.api.admin.brand_management.router"]


def _patch_db(
    monkeypatch,
    *,
    industries=None,
    brands=None,
    total=0,
    detail=None,
    persist_brand_id=None,
    name_exists=False,
    archived=True,
    persist_raises=None,
):
    bm = _bm_router_module()
    monkeypatch.setattr(
        bm.brand_db, "fetch_industries", AsyncMock(return_value=list(industries or []))
    )
    monkeypatch.setattr(
        bm.brand_db, "fetch_brands", AsyncMock(return_value=(list(brands or []), int(total)))
    )
    monkeypatch.setattr(bm.brand_db, "get_brand", AsyncMock(return_value=detail))
    monkeypatch.setattr(bm.brand_db, "brand_name_exists", AsyncMock(return_value=name_exists))
    if persist_raises is not None:
        monkeypatch.setattr(
            bm.brand_db,
            "persist_brand_draft",
            AsyncMock(side_effect=persist_raises),
        )
    else:
        monkeypatch.setattr(
            bm.brand_db,
            "persist_brand_draft",
            AsyncMock(return_value=int(persist_brand_id or 1)),
        )
    monkeypatch.setattr(bm.brand_db, "archive_brand", AsyncMock(return_value=bool(archived)))


def _wire(brand_id: int = 1) -> dict:
    return {
        "id": brand_id,
        "name": f"Brand {brand_id}",
        "name_zh": "中文名",
        "name_en": "English Name",
        "industry": "Beauty",
        "target_market": "tier 1",
        "description": "x",
        "positioning": "premium",
        "headquarters": "Shanghai",
        "founded_year": 2010,
        "aliases": [],
        "official_domains": ["example.com"],
        "tags": ["t1"],
        "status": "active",
        "source": "manual",
        "created_by": "admin-1",
        "created_at": None,
        "updated_at": None,
    }


# ── lib.py: pure validators ──────────────────────────────────


def test_constants_have_expected_values():
    assert "active" in ALLOWED_BRAND_STATUSES
    assert "manual" in ALLOWED_BRAND_SOURCES


def test_normalize_brand_draft_minimum_required():
    out = normalize_brand_draft({"name": "Acme"})
    assert out["name"] == "Acme"
    assert out["status"] == "draft"
    assert out["source"] == "manual"
    assert out["aliases"] == []


def test_normalize_brand_draft_missing_name_raises():
    with pytest.raises(BrandManagementError) as exc:
        normalize_brand_draft({})
    assert exc.value.code == "missing_brand_name"


def test_normalize_brand_draft_invalid_payload_raises():
    with pytest.raises(BrandManagementError) as exc:
        normalize_brand_draft("not a dict")  # type: ignore[arg-type]
    assert exc.value.code == "invalid_brand_payload"


def test_normalize_brand_draft_clamps_founded_year_to_plausible_range():
    out = normalize_brand_draft({"name": "x", "founded_year": 100})
    assert out["founded_year"] is None
    out2 = normalize_brand_draft({"name": "x", "founded_year": 2050})
    assert out2["founded_year"] == 2050
    out3 = normalize_brand_draft({"name": "x", "founded_year": 9999})
    assert out3["founded_year"] is None


def test_normalize_brand_draft_caps_string_lengths():
    out = normalize_brand_draft({"name": "x" * 500, "description": "y" * 5000})
    assert len(out["name"]) <= 256
    assert len(out["description"]) <= 2000


def test_normalize_brand_draft_aliases_competitors():
    out = normalize_brand_draft({"name": "x", "aliases": "alpha,beta", "competitors": ["foo"]})
    assert out["aliases"] == ["alpha", "beta"]
    assert out["competitors"] == [{"name": "foo", "type": "COMPETES_WITH", "note": ""}]


def test_normalize_brand_draft_status_aliases():
    assert normalize_brand_draft({"name": "x", "status": "approved"})["status"] == "active"
    assert normalize_brand_draft({"name": "x", "status": "归档"})["status"] == "archived"
    assert normalize_brand_draft({"name": "x", "status": "weird"})["status"] == "draft"


def test_coerce_str_list_dedupe_and_cap():
    out = coerce_str_list("a, b, A, c", max_items=2)
    assert out == ["a", "b"]


def test_normalize_competitors_dict_passthrough():
    out = normalize_competitors([{"name": "X", "type": "RIVAL", "note": "ok"}])
    assert out == [{"name": "X", "type": "COMPETES_WITH", "note": "ok"}]


def test_normalize_brand_source_input_filters_unknown():
    assert normalize_brand_source_input("manual") == "manual"
    assert normalize_brand_source_input("imaginary") == ""


# ── auth ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_industries_unauth_401(client):
    resp = await client.get("/api/admin/brand-management/industries")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_unauth_401(client):
    resp = await client.get("/api/admin/brand-management")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_unauth_401(client):
    resp = await client.get("/api/admin/brand-management/1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_unauth_401(client):
    resp = await client.post("/api/admin/brand-management", json={"name": "x"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_put_unauth_401(client):
    resp = await client.put("/api/admin/brand-management/1", json={"name": "x"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_unauth_401(client):
    resp = await client.delete("/api/admin/brand-management/1")
    assert resp.status_code == 401


# ── GET /industries ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_industries_returns_list(client, admin_operator, monkeypatch):
    _patch_db(
        monkeypatch,
        industries=[
            {"industry": "Beauty", "brand_count": 12},
            {"industry": "Tech", "brand_count": 8},
        ],
    )
    resp = await client.get("/api/admin/brand-management/industries")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(body["industries"]) == 2
    assert body["industries"][0]["industry"] == "Beauty"


@pytest.mark.asyncio
async def test_industries_empty_when_table_missing(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, industries=[])
    resp = await client.get("/api/admin/brand-management/industries")
    assert resp.status_code == 200
    assert resp.json()["industries"] == []


# ── GET / list ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_returns_paged_brands(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, brands=[_wire(1), _wire(2)], total=12)
    resp = await client.get("/api/admin/brand-management?per_page=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(body["brands"]) == 2
    pag = body["pagination"]
    assert pag["page"] == 1 and pag["per_page"] == 2 and pag["total"] == 12
    assert pag["total_pages"] == 6


@pytest.mark.asyncio
async def test_list_passes_filters_to_db(client, admin_operator, monkeypatch):
    bm = _bm_router_module()
    captured: dict = {}

    async def fake_fetch(session, **kwargs):
        captured.update(kwargs)
        return ([], 0)

    monkeypatch.setattr(bm.brand_db, "fetch_brands", fake_fetch)
    monkeypatch.setattr(bm.brand_db, "fetch_industries", AsyncMock(return_value=[]))
    monkeypatch.setattr(bm.brand_db, "get_brand", AsyncMock(return_value=None))
    monkeypatch.setattr(bm.brand_db, "brand_name_exists", AsyncMock(return_value=False))
    monkeypatch.setattr(bm.brand_db, "persist_brand_draft", AsyncMock(return_value=1))
    monkeypatch.setattr(bm.brand_db, "archive_brand", AsyncMock(return_value=True))

    resp = await client.get(
        "/api/admin/brand-management"
        "?industry=Beauty&source=manual&status=active&q=test&page=2&per_page=10"
    )
    assert resp.status_code == 200
    assert captured["industry"] == "Beauty"
    assert captured["source"] == "manual"
    assert captured["status"] == "active"
    assert captured["q"] == "test"
    assert captured["page"] == 2
    assert captured["per_page"] == 10


# ── GET /{id} ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_existing_returns_brand(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, detail=_wire(7))
    resp = await client.get("/api/admin/brand-management/7")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["brand"]["id"] == 7


@pytest.mark.asyncio
async def test_get_missing_returns_404(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, detail=None)
    resp = await client.get("/api/admin/brand-management/999")
    assert resp.status_code == 404


# ── POST / create ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_returns_201_and_audit(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_db(monkeypatch, persist_brand_id=42, detail=_wire(42))
    resp = await client.post(
        "/api/admin/brand-management",
        json={"name": "Acme", "industry": "Beauty"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["brand"]["id"] == 42
    assert body["relation_candidates"] == 0

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "create_brand")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1


@pytest.mark.asyncio
async def test_create_missing_name_422(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch)
    resp = await client.post("/api/admin/brand-management", json={"industry": "Beauty"})
    assert resp.status_code == 422
    assert "missing_brand_name" in str(resp.json())


@pytest.mark.asyncio
async def test_create_invalid_payload_422(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch)
    resp = await client.post(
        "/api/admin/brand-management", data="not-json", headers={"Content-Type": "application/json"}
    )
    # Empty / non-dict payload → missing_brand_name (handler defends by
    # treating non-dict body as {} before calling normalize_brand_draft).
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_duplicate_name_409(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, name_exists=True)
    resp = await client.post(
        "/api/admin/brand-management",
        json={"name": "Existing"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "duplicate_brand_name"


# ── PUT /{id} ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_returns_200_and_audit(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_db(monkeypatch, persist_brand_id=5, detail=_wire(5), name_exists=False)
    resp = await client.put(
        "/api/admin/brand-management/5",
        json={"name": "Renamed", "industry": "Tech", "status": "active"},
    )
    assert resp.status_code == 200
    assert resp.json()["brand"]["id"] == 5

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "update_brand")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1


@pytest.mark.asyncio
async def test_update_missing_returns_404(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, detail=None)
    resp = await client.put(
        "/api/admin/brand-management/999",
        json={"name": "x"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_duplicate_name_409(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, detail=_wire(5), name_exists=True)
    resp = await client.put(
        "/api/admin/brand-management/5",
        json={"name": "OtherBrand"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_update_missing_name_422(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, detail=_wire(5))
    resp = await client.put(
        "/api/admin/brand-management/5",
        json={"industry": "Beauty"},
    )
    assert resp.status_code == 422


# ── DELETE /{id} ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_archives_and_audits_high(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_db(monkeypatch, detail=_wire(9), archived=True)
    resp = await client.delete("/api/admin/brand-management/9")
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "archive_brand")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "high"


@pytest.mark.asyncio
async def test_delete_missing_returns_404(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, detail=None)
    resp = await client.delete("/api/admin/brand-management/999")
    assert resp.status_code == 404


# ── audit gate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_slice7a():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
