"""Phase 9 slice 9e — /api/admin/queries/analytics + ensure_default_prompt.

Mirrors test_phase_9a/9b style: lib parsing first, then full HTTP roundtrips
with admin_operator override + db_session-bound monkeypatches.
"""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from genpano_models import AdminUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.queries import analytics as analytics_mod
from app.admin.queries.lib import (
    QueryValidationError,
    parse_create_query_payload,
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


# ── lib.parse_create_query_payload now accepts prompt_id ────────────


def test_parse_create_payload_accepts_prompt_id():
    out = parse_create_query_payload(
        {"target_llm": "doubao", "query_text": "x", "brand_id": 7, "prompt_id": "42"}
    )
    assert out["prompt_id"] == 42


def test_parse_create_payload_invalid_prompt_id():
    with pytest.raises(QueryValidationError) as exc:
        parse_create_query_payload({"target_llm": "x", "query_text": "y", "prompt_id": "weird"})
    assert exc.value.code == "invalid_prompt_id"


def test_parse_create_payload_omits_prompt_id_when_blank():
    out = parse_create_query_payload({"target_llm": "x", "query_text": "y", "prompt_id": ""})
    assert out["prompt_id"] is None


# ── analytics._resolve_window ───────────────────────────────────────


def test_resolve_window_defaults_to_last_30():
    from datetime import date

    df, dt = analytics_mod._resolve_window(None, None)
    # Both ISO date strings with df <= dt; 30-day spread.
    assert date.fromisoformat(df) <= date.fromisoformat(dt)
    assert (date.fromisoformat(dt) - date.fromisoformat(df)).days == 30


def test_resolve_window_swaps_when_inverted():
    df, dt = analytics_mod._resolve_window("2026-05-10", "2026-04-10")
    assert df == "2026-04-10"
    assert dt == "2026-05-10"


def test_resolve_window_rejects_garbage_falls_back():
    from datetime import date

    df, dt = analytics_mod._resolve_window("not-a-date", "also-not")
    # Falls through to defaults — same shape as `_defaults`.
    assert date.fromisoformat(df) <= date.fromisoformat(dt)


# ── analytics._round helper ────────────────────────────────────────


def test_round_handles_none_and_strings():
    assert analytics_mod._round(None, 2) is None
    assert analytics_mod._round("abc", 2) is None
    assert analytics_mod._round(0.123456, 4) == 0.1235


# ── analytics endpoint — auth + empty shape ────────────────────────


@pytest.mark.asyncio
async def test_analytics_unauth_401(client):
    resp = await client.get("/api/admin/queries/analytics")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_analytics_empty_brand(client, admin_operator):
    """No brand_id → returns the canonical empty shape (all keys, zero values)."""
    resp = await client.get("/api/admin/queries/analytics")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {
        "filters",
        "totals",
        "by_status",
        "by_engine",
        "daily_trend",
        "by_topic",
        "sentiment_distribution",
        "position_distribution",
    }
    assert body["totals"] == {
        "queries": 0,
        "responses": 0,
        "analyzed": 0,
        "mentions_target": 0,
    }
    assert body["by_engine"] == []
    assert body["daily_trend"] == []
    assert body["by_topic"] == []
    assert body["sentiment_distribution"] == {"positive": 0, "neutral": 0, "negative": 0}
    assert body["position_distribution"] == [
        {"bucket": "Top1", "count": 0},
        {"bucket": "Top3", "count": 0},
        {"bucket": "Top5", "count": 0},
        {"bucket": "Top10", "count": 0},
        {"bucket": "Other", "count": 0},
    ]


@pytest.mark.asyncio
async def test_analytics_passes_filters_to_service(client, admin_operator, monkeypatch):
    """Route delegates to fetch_query_analytics with the right kwargs and
    returns its dict verbatim. We don't exercise SQL on sqlite; just verify
    the wiring."""
    a = _queries_router_module()
    fake_payload = {
        "filters": {
            "brand_id": 7,
            "date_from": "2026-04-01",
            "date_to": "2026-05-10",
            "engine": "chatgpt",
        },
        "totals": {"queries": 12, "responses": 10, "analyzed": 9, "mentions_target": 5},
        "by_status": {"done": 10, "failed": 1, "pending": 1, "running": 0},
        "by_engine": [
            {
                "engine": "chatgpt",
                "queries": 12,
                "mention_rate": 0.4,
                "avg_sentiment": 0.2,
                "avg_position_rank": 2.0,
                "avg_geo_score": 0.7,
            }
        ],
        "daily_trend": [
            {
                "date": "2026-05-01",
                "queries": 5,
                "mention_rate": 0.4,
                "avg_sentiment": 0.1,
                "avg_geo_score": 0.65,
            }
        ],
        "by_topic": [
            {
                "topic_id": 1,
                "topic_text": "x",
                "queries": 5,
                "mention_rate": 0.4,
                "avg_sentiment": 0.1,
                "avg_geo_score": 0.65,
            }
        ],
        "sentiment_distribution": {"positive": 3, "neutral": 2, "negative": 1},
        "position_distribution": [
            {"bucket": "Top1", "count": 1},
            {"bucket": "Top3", "count": 2},
            {"bucket": "Top5", "count": 1},
            {"bucket": "Top10", "count": 1},
            {"bucket": "Other", "count": 0},
        ],
    }
    spy = AsyncMock(return_value=fake_payload)
    monkeypatch.setattr(a, "fetch_query_analytics", spy)
    resp = await client.get(
        "/api/admin/queries/analytics"
        "?brand_id=7&date_from=2026-04-01&date_to=2026-05-10&engine=chatgpt"
    )
    assert resp.status_code == 200
    spy.assert_awaited_once()
    kwargs = spy.await_args.kwargs
    assert kwargs == {
        "brand_id": 7,
        "date_from": "2026-04-01",
        "date_to": "2026-05-10",
        "engine": "chatgpt",
    }
    assert resp.json() == fake_payload


# ── ensure_default_prompt: returns None when tables missing ────────


@pytest.mark.asyncio
async def test_ensure_default_prompt_none_when_tables_missing(db_session: AsyncSession):
    """sqlite test bind has no `topics`/`prompts` — the helper must
    short-circuit to None without raising."""
    from app.admin.queries.db import ensure_default_prompt

    out = await ensure_default_prompt(db_session, brand_id=7, query_text="hi")
    assert out is None


@pytest.mark.asyncio
async def test_ensure_default_prompt_none_when_brand_id_missing(db_session: AsyncSession):
    from app.admin.queries.db import ensure_default_prompt

    out = await ensure_default_prompt(db_session, brand_id=None, query_text="hi")
    assert out is None


# ── create_query plumbing — prompt_id passes through ───────────────


@pytest.mark.asyncio
async def test_create_query_passes_prompt_id_through(client, admin_operator, monkeypatch):
    """When prompt_id is in the POST body, it must reach create_query()
    unchanged (no fallback to ensure_default_prompt)."""
    a = _queries_router_module()
    monkeypatch.setattr(a.queries_db, "create_query", AsyncMock(return_value=88))
    monkeypatch.setattr(a, "dispatch_execute_query", MagicMock(return_value=False))

    resp = await client.post(
        "/api/queries",
        json={"target_llm": "doubao", "query_text": "x", "brand_id": 7, "prompt_id": 42},
    )
    assert resp.status_code == 200
    a.queries_db.create_query.assert_awaited_once()
    kwargs = a.queries_db.create_query.await_args.kwargs
    assert kwargs["prompt_id"] == 42
    assert kwargs["brand_id"] == 7


@pytest.mark.asyncio
async def test_create_query_no_prompt_id_passes_none(client, admin_operator, monkeypatch):
    """When the caller omits prompt_id, the router passes None — the db
    helper itself decides whether to call ensure_default_prompt."""
    a = _queries_router_module()
    monkeypatch.setattr(a.queries_db, "create_query", AsyncMock(return_value=88))
    monkeypatch.setattr(a, "dispatch_execute_query", MagicMock(return_value=False))

    resp = await client.post(
        "/api/queries",
        json={"target_llm": "doubao", "query_text": "x", "brand_id": 7},
    )
    assert resp.status_code == 200
    kwargs = a.queries_db.create_query.await_args.kwargs
    assert kwargs["prompt_id"] is None
