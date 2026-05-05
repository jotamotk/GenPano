"""Phase O.2.3 — admin MCP operations sub-router."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import McpCallLog, User, UserApiKey
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def admin_operator(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        name="Admin",
        role="paid",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def regular_user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"u-{uuid.uuid4().hex[:6]}@example.com",
        name="User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


# ── /summary ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_summary_zero_state(client, admin_operator):
    resp = await client.get("/api/admin/mcp-ops/summary", headers=_bearer(admin_operator))
    assert resp.status_code == 200
    body = resp.json()
    assert body["window_hours"] == 24
    assert body["total_calls"] == 0
    assert body["by_tool"] == []


@pytest.mark.asyncio
async def test_summary_aggregates_by_tool(client, admin_operator, db_session: AsyncSession):
    now = _now()
    rows = [
        McpCallLog(
            tool="genpano_get_brand_visibility",
            status="ok",
            latency_ms=120,
            cost_estimate_cny=0.5,
            occurred_at=now,
        ),
        McpCallLog(
            tool="genpano_get_brand_visibility",
            status="error",
            error_code="MCP_AUTH_REQUIRED",
            latency_ms=80,
            occurred_at=now,
        ),
        McpCallLog(
            tool="genpano_simulate_authority_boost",
            status="ok",
            latency_ms=200,
            cost_estimate_cny=1.0,
            occurred_at=now,
        ),
    ]
    db_session.add_all(rows)
    await db_session.commit()

    resp = await client.get("/api/admin/mcp-ops/summary?hours=1", headers=_bearer(admin_operator))
    body = resp.json()
    assert body["total_calls"] == 3
    assert body["total_errors"] == 1
    assert body["overall_error_rate"] == pytest.approx(1 / 3, rel=1e-2)

    by_tool = {it["tool"]: it for it in body["by_tool"]}
    bv = by_tool["genpano_get_brand_visibility"]
    assert bv["calls"] == 2
    assert bv["errors"] == 1
    assert bv["error_rate"] == 0.5
    assert bv["avg_latency_ms"] == 100.0


@pytest.mark.asyncio
async def test_summary_window_excludes_old(client, admin_operator, db_session: AsyncSession):
    db_session.add(
        McpCallLog(
            tool="ancient_tool",
            status="ok",
            latency_ms=10,
            occurred_at=_now() - timedelta(hours=72),
        )
    )
    await db_session.commit()

    resp = await client.get("/api/admin/mcp-ops/summary?hours=24", headers=_bearer(admin_operator))
    assert resp.json()["total_calls"] == 0


@pytest.mark.asyncio
async def test_summary_non_admin_403(client, regular_user):
    resp = await client.get("/api/admin/mcp-ops/summary", headers=_bearer(regular_user))
    assert resp.status_code == 403


# ── /top-users ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_top_users_joins_api_key_metadata(client, admin_operator, db_session: AsyncSession):
    key1 = UserApiKey(
        id=_new_id(),
        user_id=admin_operator.id,
        name="Heavy User",
        prefix="gp_sk_AAA",
        hash="$2b$12$dummy",
        scope=None,
        rate_limit_per_minute=60,
        expires_at=None,
    )
    key2 = UserApiKey(
        id=_new_id(),
        user_id=admin_operator.id,
        name="Light User",
        prefix="gp_sk_BBB",
        hash="$2b$12$dummy",
        scope=None,
        rate_limit_per_minute=60,
        expires_at=None,
    )
    db_session.add_all([key1, key2])
    await db_session.commit()

    now = _now()
    db_session.add_all(
        [
            *[
                McpCallLog(
                    tool="genpano_get_brand_visibility",
                    api_key_id=key1.id,
                    user_id=admin_operator.id,
                    status="ok",
                    latency_ms=100,
                    occurred_at=now,
                )
                for _ in range(5)
            ],
            McpCallLog(
                tool="genpano_get_brand_visibility",
                api_key_id=key2.id,
                user_id=admin_operator.id,
                status="ok",
                latency_ms=100,
                occurred_at=now,
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get("/api/admin/mcp-ops/top-users?hours=1", headers=_bearer(admin_operator))
    items = resp.json()["items"]
    # First (most calls) is Heavy User
    assert items[0]["prefix"] == "gp_sk_AAA"
    assert items[0]["calls"] == 5
    assert items[0]["key_name"] == "Heavy User"
    assert items[1]["calls"] == 1


@pytest.mark.asyncio
async def test_top_users_non_admin_403(client, regular_user):
    resp = await client.get("/api/admin/mcp-ops/top-users", headers=_bearer(regular_user))
    assert resp.status_code == 403


# ── /errors ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_errors_returns_only_failures(client, admin_operator, db_session: AsyncSession):
    now = _now()
    db_session.add_all(
        [
            McpCallLog(tool="t1", status="ok", latency_ms=10, occurred_at=now),
            McpCallLog(
                tool="t1",
                status="error",
                error_code="MCP_AUTH_REQUIRED",
                latency_ms=15,
                occurred_at=now,
            ),
            McpCallLog(
                tool="t2",
                status="error",
                error_code="TOOL_INVALID",
                latency_ms=20,
                occurred_at=now,
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get("/api/admin/mcp-ops/errors?hours=1", headers=_bearer(admin_operator))
    body = resp.json()
    assert body["total"] == 2
    statuses = {it["status"] for it in body["items"]}
    assert statuses == {"error"}


@pytest.mark.asyncio
async def test_errors_filter_by_error_code(client, admin_operator, db_session: AsyncSession):
    now = _now()
    db_session.add_all(
        [
            McpCallLog(
                tool="t",
                status="error",
                error_code="MCP_AUTH_REQUIRED",
                latency_ms=10,
                occurred_at=now,
            ),
            McpCallLog(
                tool="t",
                status="error",
                error_code="TOOL_INVALID",
                latency_ms=10,
                occurred_at=now,
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get(
        "/api/admin/mcp-ops/errors?error_code=MCP_AUTH_REQUIRED&hours=1",
        headers=_bearer(admin_operator),
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["error_code"] == "MCP_AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_errors_unauth_401(client):
    resp = await client.get("/api/admin/mcp-ops/errors")
    assert resp.status_code == 401


# ── coverage gate ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_with_mcp_ops_routes_all_read():
    """mcp-ops sub-router has only GET endpoints — gate must still pass."""
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
