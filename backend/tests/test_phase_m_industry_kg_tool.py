"""Phase M — genpano_get_industry_kg MCP tool."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import (
    GeoScoreDaily,
    KgBrand,
    KgBrandRelation,
    User,
)
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
        email=f"kgt-{uuid.uuid4().hex[:6]}@example.com",
        name="KG Tool User",
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
async def kg_data(db_session: AsyncSession) -> str:
    industry_name = "Mcp"
    today = datetime.now().date()
    for bid in (501, 502):
        for i in range(30):
            d = today - timedelta(days=29 - i)
            db_session.add(
                GeoScoreDaily(
                    brand_id=bid,
                    industry=industry_name,
                    date=datetime.combine(d, datetime.min.time()),
                    target_llm="chatgpt",
                    avg_geo_score=75.0,
                    mention_rate=0.5,
                    avg_sov=0.3,
                    avg_sentiment=0.6,
                    total_queries=100,
                )
            )
    db_session.add_all(
        [
            KgBrand(
                brand_id=501,
                industry_id=99,
                primary_name="Alpha",
                status="approved",
            ),
            KgBrand(
                brand_id=502,
                industry_id=99,
                primary_name="Bravo",
                status="approved",
            ),
        ]
    )
    db_session.add(
        KgBrandRelation(
            id=_new_id(),
            brand_a_id=501,
            brand_b_id=502,
            type="COMPETES_WITH",
            confidence=0.8,
            source="admin",
        )
    )
    await db_session.commit()
    return industry_name


async def _new_secret(client, user: User) -> str:
    return (
        await client.post("/api/v1/users/me/api-keys", headers=_bearer(user), json={"name": "kgt"})
    ).json()["secret"]


@pytest.mark.asyncio
async def test_industry_kg_tool_returns_graph(client, user, kg_data):
    secret = await _new_secret(client, user)
    resp = await client.post(
        "/mcp/v1",
        headers={"Authorization": f"Bearer {secret}"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "genpano_get_industry_kg",
                "arguments": {
                    "industry_id": 99,
                    "industry_name": kg_data,
                    "depth": 2,
                },
            },
        },
    )
    assert resp.status_code == 200
    body = resp.json()["result"]
    assert body["isError"] is False
    payload = body["structuredContent"]
    brand_nodes = [n for n in payload["nodes"] if n["type"] == "brand"]
    assert len(brand_nodes) == 2
    assert {n["name"] for n in brand_nodes} == {"Alpha", "Bravo"}
    competes = [e for e in payload["edges"] if e["type"] == "COMPETES_WITH"]
    assert len(competes) == 1


@pytest.mark.asyncio
async def test_industry_kg_tool_blocked_by_scope(client, user, kg_data):
    """Scope allowlist for tools=[get_brand_visibility] denies industry_kg call."""
    resp = await client.post(
        "/api/v1/users/me/api-keys",
        headers=_bearer(user),
        json={
            "name": "narrow",
            "scope": {"tools": ["genpano_get_brand_visibility"]},
        },
    )
    secret = resp.json()["secret"]

    resp = await client.post(
        "/mcp/v1",
        headers={"Authorization": f"Bearer {secret}"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "genpano_get_industry_kg",
                "arguments": {"industry_id": 99},
            },
        },
    )
    body = resp.json()["result"]
    assert body["isError"] is True
    assert (body.get("_meta") or {}).get("error_code") == "tool_forbidden"


@pytest.mark.asyncio
async def test_industry_kg_tool_listed_in_tools_list(client, user):
    secret = await _new_secret(client, user)
    resp = await client.post(
        "/mcp/v1",
        headers={"Authorization": f"Bearer {secret}"},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
    names = {t["name"] for t in resp.json()["result"]["tools"]}
    assert "genpano_get_industry_kg" in names
