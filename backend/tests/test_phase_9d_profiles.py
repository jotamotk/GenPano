"""Phase 9 slice 9d — /api/profiles CRUD + lite + similar."""

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

from app.admin.profiles_legacy.lib import (
    ProfileValidationError,
    parse_profile_payload,
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


def _profiles_router_module():
    import app.api.profiles_legacy.router  # noqa: F401

    return sys.modules["app.api.profiles_legacy.router"]


def _patch_db(monkeypatch, **overrides):
    a = _profiles_router_module()
    defaults = {
        "list_profiles": AsyncMock(return_value=overrides.get("list", [])),
        "create_profile": AsyncMock(return_value=overrides.get("create", 1)),
        "update_profile": AsyncMock(return_value=overrides.get("update", True)),
        "delete_profile": AsyncMock(return_value=overrides.get("delete", (True, 0))),
        "list_profiles_lite": AsyncMock(return_value=overrides.get("lite", [])),
        "find_similar_profiles": AsyncMock(
            return_value=overrides.get(
                "similar",
                {"seed": {"id": "1"}, "strategy": "fallback", "rows": []},
            )
        ),
    }
    for name, mock in defaults.items():
        monkeypatch.setattr(a.profiles_db, name, mock)


# ── lib.py ──────────────────────────────────────────────────


def test_parse_profile_required_name():
    with pytest.raises(ProfileValidationError) as exc:
        parse_profile_payload({})
    assert exc.value.code == "name_required"


def test_parse_profile_defaults():
    out = parse_profile_payload({"name": " Op A "})
    assert out["name"] == "Op A"
    assert out["language"] == "zh"
    assert out["device_type"] == "desktop"
    assert out["persona_traits"] == {}


def test_parse_profile_traits_dict_passthrough():
    out = parse_profile_payload({"name": "x", "persona_traits": {"a": 1}})
    assert out["persona_traits"] == {"a": 1}


def test_parse_profile_traits_json_string():
    out = parse_profile_payload({"name": "x", "persona_traits": '{"k":"v"}'})
    assert out["persona_traits"] == {"k": "v"}


def test_parse_profile_traits_invalid_falls_back_to_empty():
    out = parse_profile_payload({"name": "x", "persona_traits": "not-json"})
    assert out["persona_traits"] == {}


# ── auth gate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_unauth_401(client):
    resp = await client.get("/api/profiles")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_unauth_401(client):
    resp = await client.post("/api/profiles", json={"name": "x"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_update_unauth_401(client):
    resp = await client.put("/api/profiles/1", json={"name": "x"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_unauth_401(client):
    resp = await client.delete("/api/profiles/1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_lite_unauth_401(client):
    resp = await client.get("/api/profiles/lite")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_similar_unauth_401(client):
    resp = await client.get("/api/profiles/1/similar")
    assert resp.status_code == 401


# ── reads ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_passes_through(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, list=[{"id": 1, "name": "A"}, {"id": 2, "name": "B"}])
    resp = await client.get("/api/profiles")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2


@pytest.mark.asyncio
async def test_lite_pass_through(client, admin_operator, monkeypatch):
    _patch_db(
        monkeypatch,
        lite=[{"id": "1", "code": "", "name": "A", "segment_id": None, "brand_id": None}],
    )
    resp = await client.get("/api/profiles/lite?q=foo&limit=10")
    assert resp.status_code == 200
    assert resp.json()[0]["name"] == "A"


@pytest.mark.asyncio
async def test_lite_invalid_limit_422(client, admin_operator):
    resp = await client.get("/api/profiles/lite?limit=99999")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_similar_404(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, similar=None)
    resp = await client.get("/api/profiles/9999/similar")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_similar_returns_strategy(client, admin_operator, monkeypatch):
    _patch_db(
        monkeypatch,
        similar={
            "seed": {"id": "1", "segment_id": "s1"},
            "strategy": "same_segment",
            "rows": [{"id": "2", "code": "", "name": "B", "segment_id": "s1"}],
        },
    )
    resp = await client.get("/api/profiles/1/similar")
    assert resp.status_code == 200
    body = resp.json()
    assert body["strategy"] == "same_segment"
    assert len(body["rows"]) == 1


# ── CRUD writes ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_validation_400(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch)
    resp = await client.post("/api/profiles", json={})
    assert resp.status_code == 400
    assert resp.json()["error"] == "name_required"


@pytest.mark.asyncio
async def test_create_503_when_table_missing(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, create=None)
    resp = await client.post("/api/profiles", json={"name": "Op"})
    assert resp.status_code == 503
    assert resp.json()["error"] == "profiles_unavailable"


@pytest.mark.asyncio
async def test_create_audit_med(client, admin_operator, monkeypatch, db_session: AsyncSession):
    _patch_db(monkeypatch, create=42)
    resp = await client.post(
        "/api/profiles",
        json={"name": "Op", "country_code": "US", "persona_traits": {"a": 1}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["profile_id"] == 42
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "create_profile")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "med"
    assert audit[0].after.get("country_code") == "US"
    assert audit[0].after.get("trait_keys") == ["a"]


@pytest.mark.asyncio
async def test_update_404_when_missing(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, update=False)
    resp = await client.put("/api/profiles/9999", json={"name": "X"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_audit_med(client, admin_operator, monkeypatch, db_session: AsyncSession):
    _patch_db(monkeypatch, update=True)
    resp = await client.put("/api/profiles/1", json={"name": "Renamed"})
    assert resp.status_code == 200
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "update_profile")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "med"


@pytest.mark.asyncio
async def test_delete_404_when_missing(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, delete=(False, 0))
    resp = await client.delete("/api/profiles/9999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_audit_high(client, admin_operator, monkeypatch, db_session: AsyncSession):
    _patch_db(monkeypatch, delete=(True, 5))
    resp = await client.delete("/api/profiles/1")
    assert resp.status_code == 200
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "delete_profile")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "high"
    assert audit[0].after.get("unlinked_query_count") == 5


# ── audit gate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_slice9d():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
