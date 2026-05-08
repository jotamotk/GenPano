"""Phase 9 slice 9a — /api/stats + /api/queries (read-only)."""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from genpano_models import AdminUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.queries.lib import (
    QUERIES_DEFAULT_SORT,
    QUERIES_SORT_MAP,
    is_iso_date,
    normalize_sort,
    split_pending_status,
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


def _queries_router_module():
    import app.api.queries.router  # noqa: F401

    return sys.modules["app.api.queries.router"]


# ── lib.py ──────────────────────────────────────────────────


def test_normalize_sort_whitelist():
    assert normalize_sort("id_desc") == QUERIES_SORT_MAP["id_desc"]
    assert normalize_sort("ID_DESC") == QUERIES_SORT_MAP["id_desc"]
    assert normalize_sort("status") == QUERIES_SORT_MAP["status"]


def test_normalize_sort_falls_back():
    assert normalize_sort("weird") == QUERIES_SORT_MAP[QUERIES_DEFAULT_SORT]
    assert normalize_sort(None) == QUERIES_SORT_MAP[QUERIES_DEFAULT_SORT]


def test_is_iso_date():
    assert is_iso_date("2026-05-08")
    assert not is_iso_date("2026/05/08")
    assert not is_iso_date("2026-5-8")
    assert not is_iso_date("not-a-date")


def test_split_pending_status():
    assert split_pending_status("unqueued") == "unqueued"
    assert split_pending_status("QUEUED") == "queued"
    assert split_pending_status("done") is None
    assert split_pending_status("") is None
    assert split_pending_status(None) is None


# ── auth gate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stats_unauth_401(client):
    resp = await client.get("/api/stats")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_queries_unauth_401(client):
    resp = await client.get("/api/queries")
    assert resp.status_code == 401


# ── /api/stats ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stats_zero_when_table_missing(client, admin_operator):
    """sqlite test fixture has no queries table → returns the empty
    {total:0, done:0, pending:0, running:0, failed:0} shape rather than
    500ing."""
    resp = await client.get("/api/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"total": 0, "done": 0, "pending": 0, "running": 0, "failed": 0}


@pytest.mark.asyncio
async def test_stats_passes_through_db_helper(client, admin_operator, monkeypatch):
    a = _queries_router_module()
    monkeypatch.setattr(
        a.queries_db,
        "fetch_status_stats",
        AsyncMock(return_value={"total": 17, "done": 10, "pending": 5, "running": 1, "failed": 1}),
    )
    resp = await client.get("/api/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 17
    assert body["done"] == 10


# ── /api/queries ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_queries_empty_when_table_missing(client, admin_operator):
    resp = await client.get("/api/queries")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_queries_with_count_returns_object(client, admin_operator, monkeypatch):
    a = _queries_router_module()
    monkeypatch.setattr(
        a.queries_db,
        "list_queries",
        AsyncMock(return_value=([{"id": 1}], 33, {"done": 30, "pending": 3})),
    )
    resp = await client.get("/api/queries?count=1&limit=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 33
    assert body["by_status"]["done"] == 30
    assert body["rows"][0]["id"] == 1


@pytest.mark.asyncio
async def test_queries_without_count_returns_array(client, admin_operator, monkeypatch):
    a = _queries_router_module()
    monkeypatch.setattr(
        a.queries_db,
        "list_queries",
        AsyncMock(return_value=([{"id": 1}, {"id": 2}], None, None)),
    )
    resp = await client.get("/api/queries?limit=10")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 2


@pytest.mark.asyncio
async def test_queries_passes_filters_through(client, admin_operator, monkeypatch):
    """Smoke that the router wires every documented query param through
    to the db helper. Mocked helper records its args so we can assert."""
    a = _queries_router_module()
    captured: dict = {}

    async def _capture(session, **kwargs):
        captured.update(kwargs)
        return [], None, None

    monkeypatch.setattr(a.queries_db, "list_queries", _capture)
    resp = await client.get(
        "/api/queries"
        "?llm=doubao&status=done&brand_id=1&topic_id=2&prompt_id=3"
        "&id=42&q=hello&date=2026-05-08&date_from=2026-05-01"
        "&date_to=2026-05-08&limit=20&offset=10&sort=status"
    )
    assert resp.status_code == 200
    assert captured["llm"] == "doubao"
    assert captured["status"] == "done"
    assert captured["brand_id"] == 1
    assert captured["topic_id"] == 2
    assert captured["prompt_id"] == 3
    assert captured["query_id"] == 42
    assert captured["prompt_q"] == "hello"
    assert captured["date_filter"] == "2026-05-08"
    assert captured["date_from"] == "2026-05-01"
    assert captured["date_to"] == "2026-05-08"
    assert captured["limit"] == 20
    assert captured["offset"] == 10
    assert captured["sort"] == "status"
    assert captured["include_count"] is False


@pytest.mark.asyncio
async def test_queries_invalid_limit_422(client, admin_operator):
    resp = await client.get("/api/queries?limit=99999")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_queries_invalid_brand_id_422(client, admin_operator):
    resp = await client.get("/api/queries?brand_id=not-int")
    assert resp.status_code == 422
