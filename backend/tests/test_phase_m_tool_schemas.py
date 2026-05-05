"""MCP `tools/list` real input schemas."""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from genpano_models import User
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.api_keys.mcp_schemas import TOOL_SCHEMAS, get_tool_descriptors
from app.api.v1.api_keys.service import MCP_TOOLS
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
        email=f"sch-{uuid.uuid4().hex[:6]}@example.com",
        name="Sch",
        role="paid",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


# ── unit: TOOL_SCHEMAS shape ──────────────────────────────────────


def test_every_registered_tool_has_a_schema_entry():
    """Every tool name in MCP_TOOLS should have a TOOL_SCHEMAS entry."""
    missing = [name for name in MCP_TOOLS if name not in TOOL_SCHEMAS]
    assert missing == [], f"missing schema for: {missing}"


def test_schema_entries_are_well_formed():
    for name, entry in TOOL_SCHEMAS.items():
        assert "description" in entry, f"{name} missing description"
        assert "inputSchema" in entry, f"{name} missing inputSchema"
        schema = entry["inputSchema"]
        assert schema.get("type") == "object", f"{name} schema must be object"
        assert "properties" in schema, f"{name} schema missing properties"
        assert isinstance(schema.get("properties"), dict)
        # All described props should have a `description` field
        for prop_name, prop_def in schema["properties"].items():
            assert isinstance(prop_def, dict), f"{name}.{prop_name} not a dict"
            # nested $ref or merged props (with **_PROJECT_ID_REQUIRED) skip the
            # check on shared fragments; but each fragment we wrote does have
            # description.
            assert "description" in prop_def or "type" in prop_def, (
                f"{name}.{prop_name} missing description/type"
            )


def test_required_fields_subset_of_properties():
    for name, entry in TOOL_SCHEMAS.items():
        schema = entry["inputSchema"]
        required = set(schema.get("required", []))
        props = set(schema.get("properties", {}).keys())
        bad = required - props
        assert bad == set(), f"{name} declares required not in properties: {bad}"


def test_descriptors_fall_back_for_unregistered_tools(monkeypatch):
    """If MCP_TOOLS gains a name not in TOOL_SCHEMAS, fall back gracefully."""
    from app.api.v1.api_keys import service as svc

    monkeypatch.setattr(svc, "MCP_TOOLS", [*MCP_TOOLS, "genpano_unknown_new_tool"])
    descriptors = get_tool_descriptors()
    unknown = next(d for d in descriptors if d["name"] == "genpano_unknown_new_tool")
    assert unknown["inputSchema"] == {"type": "object"}
    # Existing tools still get their real schema
    for name in MCP_TOOLS:
        d = next(it for it in descriptors if it["name"] == name)
        assert d["inputSchema"] != {"type": "object"}, f"{name} should have real schema"


# ── e2e: tools/list returns real schemas ─────────────────────────


async def _mk_secret(client, user) -> str:
    return (
        await client.post("/api/v1/users/me/api-keys", headers=_bearer(user), json={"name": "sch"})
    ).json()["secret"]


@pytest.mark.asyncio
async def test_e2e_tools_list_returns_real_schemas(client, user):
    secret = await _mk_secret(client, user)
    resp = await client.post(
        "/mcp/v1",
        headers={"Authorization": f"Bearer {secret}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    body = resp.json()["result"]
    tools = body["tools"]
    # Every tool now has a non-trivial schema with properties + descriptions
    placeholder = {"type": "object"}
    for t in tools:
        assert t["inputSchema"] != placeholder, f"{t['name']} still placeholder"
        assert "properties" in t["inputSchema"], f"{t['name']} no properties"


@pytest.mark.asyncio
async def test_e2e_specific_tool_schema_correct(client, user):
    """Spot-check genpano_get_industry_kg has the depth field bounded."""
    secret = await _mk_secret(client, user)
    resp = await client.post(
        "/mcp/v1",
        headers={"Authorization": f"Bearer {secret}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    tools = resp.json()["result"]["tools"]
    kg = next(t for t in tools if t["name"] == "genpano_get_industry_kg")
    schema = kg["inputSchema"]
    assert "industry_id" in schema["required"]
    depth = schema["properties"]["depth"]
    assert depth["minimum"] == 1
    assert depth["maximum"] == 5
    assert depth["default"] == 2


@pytest.mark.asyncio
async def test_e2e_simulate_authority_boost_required_fields(client, user):
    secret = await _mk_secret(client, user)
    resp = await client.post(
        "/mcp/v1",
        headers={"Authorization": f"Bearer {secret}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    tools = resp.json()["result"]["tools"]
    sim = next(t for t in tools if t["name"] == "genpano_simulate_authority_boost")
    schema = sim["inputSchema"]
    assert set(schema["required"]) == {"brand_id", "delta_by_tier"}
    assert "additionalProperties" in schema
    assert schema["additionalProperties"] is False
