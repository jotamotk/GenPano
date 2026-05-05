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
    assert len(tools) == 9  # PRD §4.5.2.2 lists 9 tools
    names = {t["name"] for t in tools}
    assert "genpano_get_brand_visibility" in names
    assert "genpano_simulate_authority_boost" in names


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
