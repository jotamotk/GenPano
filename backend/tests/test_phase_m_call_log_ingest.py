"""Phase O.2.3 — MCP call_log ingest hook (closes the loop with admin view)."""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from genpano_models import McpCallLog, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"k-{uuid.uuid4().hex[:6]}@example.com",
        name="API User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


# ── unit: helpers ───────────────────────────────────────


def test_http_status_for_known_codes():
    from app.api.v1.api_keys.call_log import _http_status_for

    assert _http_status_for("tools/call", None) == 200
    assert _http_status_for("tools/call", "MCP_AUTH_REQUIRED") == 401
    assert _http_status_for("tools/call", "rate_limited") == 429
    assert _http_status_for("tools/call", "validation_error") == 422
    assert _http_status_for("tools/call", "something_else") == 500


@pytest.mark.asyncio
async def test_record_mcp_call_inserts_row(db_session: AsyncSession):
    from app.api.v1.api_keys.call_log import record_mcp_call

    row = await record_mcp_call(
        db_session,
        api_key_id="key-1",
        user_id="user-1",
        method="tools/call",
        tool="genpano_get_brand_visibility",
        latency_ms=120,
    )
    assert row is not None
    assert row.tool == "genpano_get_brand_visibility"
    assert row.status == "ok"
    assert row.latency_ms == 120
    assert row.http_status == 200


@pytest.mark.asyncio
async def test_record_mcp_call_error_status(db_session: AsyncSession):
    from app.api.v1.api_keys.call_log import record_mcp_call

    row = await record_mcp_call(
        db_session,
        api_key_id="k",
        user_id="u",
        method="tools/call",
        tool="genpano_nonexistent",
        status="error",
        error_code="MCP_AUTH_REQUIRED",
        latency_ms=15,
    )
    assert row is not None
    assert row.status == "error"
    assert row.http_status == 401


# ── integration: dispatcher records call_log ────────────


@pytest.mark.asyncio
async def test_mcp_initialize_records_call_log(client, user, db_session: AsyncSession):
    """A successful initialize call leaves an mcp_call_log row."""
    secret = (
        await client.post(
            "/api/v1/users/me/api-keys",
            headers=_bearer(user),
            json={"name": "log-test"},
        )
    ).json()["secret"]

    resp = await client.post(
        "/mcp/v1",
        headers={"Authorization": f"Bearer {secret}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    )
    assert resp.status_code == 200

    rows = list(
        (await db_session.execute(select(McpCallLog).where(McpCallLog.user_id == user.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "ok"
    assert row.tool is None  # initialize doesn't have a tool name
    assert row.latency_ms is not None
    assert row.latency_ms >= 0


@pytest.mark.asyncio
async def test_mcp_tools_call_records_tool_name(client, user, db_session: AsyncSession):
    """tools/call records the specific tool name in the log row."""
    secret = (
        await client.post(
            "/api/v1/users/me/api-keys",
            headers=_bearer(user),
            json={"name": "log-test-2"},
        )
    ).json()["secret"]

    await client.post(
        "/mcp/v1",
        headers={"Authorization": f"Bearer {secret}"},
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "genpano_get_brand_visibility",
                "arguments": {
                    "brand_id": 999999,
                    "project_id": "00000000-0000-0000-0000-000000000000",
                },
            },
        },
    )

    rows = list(
        (
            await db_session.execute(
                select(McpCallLog).where(
                    McpCallLog.user_id == user.id,
                    McpCallLog.tool == "genpano_get_brand_visibility",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].status == "ok"


@pytest.mark.asyncio
async def test_mcp_unknown_method_records_error(client, user, db_session: AsyncSession):
    """JSON-RPC error response leaves an error row in the log."""
    secret = (
        await client.post(
            "/api/v1/users/me/api-keys",
            headers=_bearer(user),
            json={"name": "log-test-3"},
        )
    ).json()["secret"]

    await client.post(
        "/mcp/v1",
        headers={"Authorization": f"Bearer {secret}"},
        json={"jsonrpc": "2.0", "id": 3, "method": "totally_made_up_method"},
    )

    rows = list(
        (await db_session.execute(select(McpCallLog).where(McpCallLog.user_id == user.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    # Dispatcher returned an error envelope → status='error'
    assert rows[0].status == "error"


@pytest.mark.asyncio
async def test_mcp_unauth_does_not_create_log_row(client, db_session: AsyncSession):
    """No api_key context → no log row (auth fails before measure_mcp_call)."""
    resp = await client.post(
        "/mcp/v1",
        json={"jsonrpc": "2.0", "id": 4, "method": "initialize"},
    )
    assert resp.status_code == 401

    rows = list((await db_session.execute(select(McpCallLog))).scalars().all())
    assert rows == []


# ── admin mcp-ops view consumes the rows ────────────────


@pytest.mark.asyncio
async def test_admin_mcp_ops_summary_sees_recorded_calls(client, user, db_session: AsyncSession):
    """End-to-end: MCP call records → admin /mcp-ops/summary picks it up."""
    # Make admin user
    admin = User(
        id=_new_id(),
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        name="Admin",
        role="paid",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(admin)
    await db_session.commit()

    secret = (
        await client.post(
            "/api/v1/users/me/api-keys",
            headers=_bearer(user),
            json={"name": "e2e"},
        )
    ).json()["secret"]
    await client.post(
        "/mcp/v1",
        headers={"Authorization": f"Bearer {secret}"},
        json={"jsonrpc": "2.0", "id": 5, "method": "initialize"},
    )

    resp = await client.get(
        "/api/admin/mcp-ops/summary?hours=1",
        headers=_bearer(admin),
    )
    assert resp.status_code == 200
    assert resp.json()["total_calls"] >= 1
