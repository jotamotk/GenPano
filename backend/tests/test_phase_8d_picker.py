"""Phase 8 slice 8d — /api/topics + /api/prompts pickers.

Read-only routes used by admin.html's attempt-tracker filter dropdowns.
admin_console served them without auth; this slice adds
Depends(current_admin). Tests use the sqlite fixture; topics + prompts
tables are upstream stubs (ADR-002) so the helpers degrade to ``[]``.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from genpano_models import AdminUser
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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


# ── auth gate (security hardening) ──────────────────────────


@pytest.mark.asyncio
async def test_topics_unauth_401(client):
    resp = await client.get("/api/topics")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_prompts_unauth_401(client):
    resp = await client.get("/api/prompts")
    assert resp.status_code == 401


# ── read paths (sqlite fixture has no topics/prompts) ──────


@pytest.mark.asyncio
async def test_topics_returns_empty_when_table_missing(client, admin_operator):
    resp = await client.get("/api/topics")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_topics_with_brand_filter_empty(client, admin_operator):
    resp = await client.get("/api/topics?brand_id=1")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_topics_existing_stub_table_with_id_only_returns_empty(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    import importlib

    picker_router = importlib.import_module("app.api.picker.router")
    await db_session.execute(text("CREATE TABLE topics (id INTEGER PRIMARY KEY)"))
    await db_session.commit()

    async def _fake_table_exists(_session, name: str) -> bool:
        return name == "topics"

    async def _fake_table_columns(_session, name: str) -> set[str]:
        return {"id"} if name == "topics" else set()

    monkeypatch.setattr(picker_router, "_table_exists", _fake_table_exists)
    monkeypatch.setattr(picker_router, "_table_columns", _fake_table_columns, raising=False)

    resp = await client.get("/api/topics")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_prompts_returns_empty_when_table_missing(client, admin_operator):
    resp = await client.get("/api/prompts")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_prompts_with_filters(client, admin_operator):
    resp = await client.get("/api/prompts?brand_id=1&topic_id=2")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_prompts_existing_stub_table_with_id_only_returns_empty(
    client, admin_operator, monkeypatch
):
    import importlib

    picker_router = importlib.import_module("app.api.picker.router")

    async def _fake_table_exists(_session, name: str) -> bool:
        return name == "prompts"

    async def _fake_table_columns(_session, name: str) -> set[str]:
        return {"id"} if name == "prompts" else set()

    monkeypatch.setattr(picker_router, "_table_exists", _fake_table_exists)
    monkeypatch.setattr(picker_router, "_table_columns", _fake_table_columns, raising=False)

    resp = await client.get("/api/prompts")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_topics_invalid_brand_id_returns_422(client, admin_operator):
    resp = await client.get("/api/topics?brand_id=not-a-number")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_prompts_invalid_topic_id_returns_422(client, admin_operator):
    resp = await client.get("/api/prompts?topic_id=weird")
    assert resp.status_code == 422
