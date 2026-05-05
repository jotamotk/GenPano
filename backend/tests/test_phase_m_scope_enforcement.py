"""Phase M — api_key.scope enforcement on tools/call + resources/read."""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from genpano_models import User
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.api_keys.scope import is_resource_allowed, is_tool_allowed
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
        email=f"sc-{uuid.uuid4().hex[:6]}@example.com",
        name="Scope User",
        role="paid",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


# ── pure unit tests on the matcher ───────────────────────────────


def test_no_scope_allows_anything():
    assert is_tool_allowed(None, "anything") is True
    assert is_resource_allowed(None, "genpano://industry/X/benchmark") is True


def test_wildcard_scope_allows_anything():
    assert is_tool_allowed({"tools": ["*"]}, "any_tool") is True
    assert is_resource_allowed({"resources": ["*"]}, "genpano://anything/here") is True


def test_explicit_tool_allowlist():
    s = {"tools": ["genpano_get_brand_visibility"]}
    assert is_tool_allowed(s, "genpano_get_brand_visibility") is True
    assert is_tool_allowed(s, "genpano_generate_report") is False


def test_empty_tools_list_blocks_all():
    assert is_tool_allowed({"tools": []}, "anything") is False


def test_resource_glob_prefix():
    s = {"resources": ["genpano://industry/*"]}
    assert is_resource_allowed(s, "genpano://industry/Beauty/benchmark") is True
    assert is_resource_allowed(s, "genpano://brands/101/report") is False


def test_resource_exact_match():
    s = {"resources": ["genpano://industry/Beauty/benchmark"]}
    assert is_resource_allowed(s, "genpano://industry/Beauty/benchmark") is True
    assert is_resource_allowed(s, "genpano://industry/Other/benchmark") is False


def test_separate_capabilities_independent():
    """tools list ≠ resources list — restricting one doesn't restrict the other."""
    s = {"tools": ["only_one"], "resources": ["*"]}
    assert is_tool_allowed(s, "another") is False
    assert is_resource_allowed(s, "genpano://anything") is True


# ── end-to-end: real MCP /v1 call honors scope ─────────────────


async def _make_key(client, user: User, scope: dict | None) -> str:
    body = {"name": "scoped"}
    if scope is not None:
        body["scope"] = scope  # type: ignore[assignment]
    resp = await client.post("/api/v1/users/me/api-keys", headers=_bearer(user), json=body)
    return resp.json()["secret"]


@pytest.mark.asyncio
async def test_e2e_tool_call_blocked_by_scope(client, user):
    secret = await _make_key(client, user, {"tools": ["genpano_get_brand_visibility"]})
    resp = await client.post(
        "/mcp/v1",
        headers={"Authorization": f"Bearer {secret}"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "genpano_generate_report", "arguments": {}},
        },
    )
    assert resp.status_code == 200
    body = resp.json()["result"]
    assert body["isError"] is True
    assert "tool_forbidden" in (body.get("_meta") or {}).get("error_code", "")


@pytest.mark.asyncio
async def test_e2e_tool_call_allowed_by_scope(client, user):
    secret = await _make_key(client, user, {"tools": ["genpano_get_brand_visibility"]})
    resp = await client.post(
        "/mcp/v1",
        headers={"Authorization": f"Bearer {secret}"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "genpano_get_brand_visibility",
                "arguments": {"brand_id": 9999},
            },
        },
    )
    assert resp.status_code == 200
    body = resp.json()["result"]
    # allowed → not blocked at scope layer; downstream may still error on
    # business logic (unowned brand), but it's not the scope_forbidden code
    assert (body.get("_meta") or {}).get("error_code") != "tool_forbidden"


@pytest.mark.asyncio
async def test_e2e_resource_read_blocked_by_scope(client, user):
    secret = await _make_key(client, user, {"resources": ["genpano://industry/*"]})
    resp = await client.post(
        "/mcp/v1",
        headers={"Authorization": f"Bearer {secret}"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "resources/read",
            "params": {"uri": "genpano://brands/101/report"},
        },
    )
    body = resp.json()["result"]
    assert body["isError"] is True
    text = body["contents"][0]["text"]
    assert "resource_forbidden" in text


@pytest.mark.asyncio
async def test_e2e_no_scope_means_full_access(client, user):
    """Default (no scope set) keys still work as before — no regression."""
    secret = await _make_key(client, user, None)
    resp = await client.post(
        "/mcp/v1",
        headers={"Authorization": f"Bearer {secret}"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "genpano_get_brand_visibility",
                "arguments": {"brand_id": 1},
            },
        },
    )
    body = resp.json()["result"]
    assert (body.get("_meta") or {}).get("error_code") != "tool_forbidden"
