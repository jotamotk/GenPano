"""Phase M — API keys + MCP JSON-RPC endpoints."""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from genpano_models import User
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


# ── API Keys ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_api_key_returns_secret_once(client, user):
    resp = await client.post(
        "/api/v1/users/me/api-keys",
        headers=_bearer(user),
        json={"name": "MCP Agent"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["secret"].startswith("gp_sk_")
    assert body["prefix"].startswith("gp_sk_")
    assert body["rate_limit_per_minute"] == 60


@pytest.mark.asyncio
async def test_list_api_keys_omits_secret(client, user):
    await client.post(
        "/api/v1/users/me/api-keys",
        headers=_bearer(user),
        json={"name": "K1"},
    )
    await client.post(
        "/api/v1/users/me/api-keys",
        headers=_bearer(user),
        json={"name": "K2"},
    )
    resp = await client.get("/api/v1/users/me/api-keys", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    for k in body["items"]:
        assert "secret" not in k
        assert k["prefix"].startswith("gp_sk_")


@pytest.mark.asyncio
async def test_revoke_api_key(client, user):
    kid = (
        await client.post(
            "/api/v1/users/me/api-keys",
            headers=_bearer(user),
            json={"name": "to-revoke"},
        )
    ).json()["id"]

    resp = await client.delete(f"/api/v1/users/me/api-keys/{kid}", headers=_bearer(user))
    assert resp.status_code == 204

    # Listing now empty (revoked filtered out)
    resp = await client.get("/api/v1/users/me/api-keys", headers=_bearer(user))
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_usage_stats_stub(client, user):
    kid = (
        await client.post(
            "/api/v1/users/me/api-keys",
            headers=_bearer(user),
            json={"name": "u"},
        )
    ).json()["id"]
    resp = await client.get(f"/api/v1/users/me/api-keys/{kid}/usage", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_calls"] == 0
    assert body["by_tool"] == []


# ── MCP JSON-RPC ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_no_token_returns_401_with_mcp_code(client):
    resp = await client.post(
        "/mcp/v1",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "MCP_AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_mcp_invalid_token_returns_401(client):
    resp = await client.post(
        "/mcp/v1",
        headers={"Authorization": "Bearer gp_sk_invalid_garbage"},
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_mcp_initialize_with_valid_token(client, user):
    # Create key
    secret = (
        await client.post(
            "/api/v1/users/me/api-keys",
            headers=_bearer(user),
            json={"name": "mcp-test"},
        )
    ).json()["secret"]

    resp = await client.post(
        "/mcp/v1",
        headers={"Authorization": f"Bearer {secret}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"]["serverInfo"]["name"] == "genpano-mcp"


@pytest.mark.asyncio
async def test_mcp_tools_list(client, user):
    secret = (
        await client.post(
            "/api/v1/users/me/api-keys",
            headers=_bearer(user),
            json={"name": "tools"},
        )
    ).json()["secret"]

    resp = await client.post(
        "/mcp/v1",
        headers={"Authorization": f"Bearer {secret}"},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
    assert resp.status_code == 200
    tools = resp.json()["result"]["tools"]
    # PRD §4.5.2.2 originally listed 9 tools; phase-K.6 adds get_industry_kg.
    assert len(tools) == 10
    names = {t["name"] for t in tools}
    assert "genpano_get_brand_visibility" in names
    assert "genpano_simulate_authority_boost" in names
    assert "genpano_get_industry_kg" in names


@pytest.mark.asyncio
async def test_mcp_revoked_token_returns_401(client, user):
    create_resp = await client.post(
        "/api/v1/users/me/api-keys",
        headers=_bearer(user),
        json={"name": "to-revoke"},
    )
    secret = create_resp.json()["secret"]
    kid = create_resp.json()["id"]

    # Revoke
    await client.delete(f"/api/v1/users/me/api-keys/{kid}", headers=_bearer(user))

    # Use revoked token
    resp = await client.post(
        "/mcp/v1",
        headers={"Authorization": f"Bearer {secret}"},
        json={"jsonrpc": "2.0", "id": 3, "method": "initialize"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_mcp_resources_list(client, user):
    secret = (
        await client.post(
            "/api/v1/users/me/api-keys",
            headers=_bearer(user),
            json={"name": "r"},
        )
    ).json()["secret"]

    resp = await client.post(
        "/mcp/v1",
        headers={"Authorization": f"Bearer {secret}"},
        json={"jsonrpc": "2.0", "id": 4, "method": "resources/list"},
    )
    assert resp.status_code == 200
    resources = resp.json()["result"]["resources"]
    assert len(resources) == 3  # PRD §4.5.2.3


# ── Phase M.2 tools/call dispatch ────────────────────────────────


async def _new_secret(client, user) -> str:
    return (
        await client.post(
            "/api/v1/users/me/api-keys",
            headers=_bearer(user),
            json={"name": "mcp-call"},
        )
    ).json()["secret"]


@pytest.mark.asyncio
async def test_mcp_tools_call_unknown_tool(client, user):
    secret = await _new_secret(client, user)
    resp = await client.post(
        "/mcp/v1",
        headers={"Authorization": f"Bearer {secret}"},
        json={
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "genpano_does_not_exist", "arguments": {}},
        },
    )
    assert resp.status_code == 200
    body = resp.json()["result"]
    assert body["isError"] is True
    assert "unknown tool" in body["content"][0]["text"]


@pytest.mark.asyncio
async def test_mcp_tools_call_brand_visibility_empty(client, user):
    secret = await _new_secret(client, user)
    resp = await client.post(
        "/mcp/v1",
        headers={"Authorization": f"Bearer {secret}"},
        json={
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "genpano_get_brand_visibility",
                "arguments": {
                    "brand_id": 999999,
                    "project_id": "00000000-0000-0000-0000-000000000000",
                    "period": "30d",
                },
            },
        },
    )
    assert resp.status_code == 200
    body = resp.json()["result"]
    assert body["isError"] is False
    assert body["structuredContent"]["brand_id"] == 999999
    assert body["structuredContent"]["mention_rate"] == 0
    assert "time_series" in body["structuredContent"]


@pytest.mark.asyncio
async def test_mcp_tools_call_simulate_authority_boost(client, user):
    secret = await _new_secret(client, user)
    resp = await client.post(
        "/mcp/v1",
        headers={"Authorization": f"Bearer {secret}"},
        json={
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {
                "name": "genpano_simulate_authority_boost",
                "arguments": {
                    "brand_id": 1,
                    "delta_by_tier": {"1": 5, "2": 10},
                },
            },
        },
    )
    assert resp.status_code == 200
    body = resp.json()["result"]
    assert body["isError"] is False
    sc = body["structuredContent"]
    # Phase E simulator returns these keys
    assert "current_pano_a" in sc
    assert "simulated_pano_a" in sc


@pytest.mark.asyncio
async def test_mcp_tools_call_optimization_insights_empty(client, user):
    secret = await _new_secret(client, user)
    resp = await client.post(
        "/mcp/v1",
        headers={"Authorization": f"Bearer {secret}"},
        json={
            "jsonrpc": "2.0",
            "id": 13,
            "method": "tools/call",
            "params": {
                "name": "genpano_get_optimization_insights",
                "arguments": {
                    "project_id": "00000000-0000-0000-0000-000000000000",
                    "brand_id": 1,
                },
            },
        },
    )
    assert resp.status_code == 200
    body = resp.json()["result"]
    assert body["isError"] is False
    assert body["structuredContent"]["diagnostics"] == []


@pytest.mark.asyncio
async def test_mcp_tools_call_invalid_arguments(client, user):
    secret = await _new_secret(client, user)
    resp = await client.post(
        "/mcp/v1",
        headers={"Authorization": f"Bearer {secret}"},
        json={
            "jsonrpc": "2.0",
            "id": 14,
            "method": "tools/call",
            "params": {
                "name": "genpano_get_brand_visibility",
                # missing required brand_id / project_id
                "arguments": {"unrelated": 1},
            },
        },
    )
    assert resp.status_code == 200
    body = resp.json()["result"]
    assert body["isError"] is True
    assert "invalid arguments" in body["content"][0]["text"]


@pytest.mark.asyncio
async def test_mcp_tools_list_returns_real_tool_names(client, user):
    """Phase M.2 — tools/list now reflects the live TOOLS dict."""
    secret = await _new_secret(client, user)
    resp = await client.post(
        "/mcp/v1",
        headers={"Authorization": f"Bearer {secret}"},
        json={"jsonrpc": "2.0", "id": 15, "method": "tools/list"},
    )
    tools = resp.json()["result"]["tools"]
    names = {t["name"] for t in tools}
    expected = {
        "genpano_get_brand_visibility",
        "genpano_compare_brands",
        "genpano_get_industry_trends",
        "genpano_get_industry_kg",
        "genpano_get_product_ranking",
        "genpano_generate_report",
        "genpano_get_optimization_insights",
        "genpano_get_citations",
        "genpano_list_pr_targets",
        "genpano_simulate_authority_boost",
    }
    assert names == expected
