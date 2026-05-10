"""Phase 3 — industry endpoints (overview / ranking / topics / kg)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import (
    BrandMention,
    GeoScoreDaily,
    IndustryBenchmarkDaily,
    IndustryTopicDaily,
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
        email=f"i-{uuid.uuid4().hex[:6]}@example.com",
        name="Industry User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def industry_data(db_session: AsyncSession) -> str:
    industry_name = "FoodAndBev"
    today = datetime.now().date()
    # Insert 30d of industry_benchmark_daily
    for i in range(30):
        d = today - timedelta(days=29 - i)
        db_session.add(
            IndustryBenchmarkDaily(
                industry=industry_name,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=65.0 + i * 0.4,
                avg_mention_rate=0.5,
                avg_sentiment=0.7,
                total_brands=12,
                total_queries=200,
            )
        )
    # Insert 5 brands' geo_score_daily for ranking + top-brands
    for bid in range(50, 55):
        for i in range(30):
            d = today - timedelta(days=29 - i)
            db_session.add(
                GeoScoreDaily(
                    brand_id=bid,
                    industry=industry_name,
                    date=datetime.combine(d, datetime.min.time()),
                    target_llm="chatgpt",
                    avg_geo_score=80.0 - (bid - 50) * 5 + i * 0.1,
                    mention_rate=0.6 - (bid - 50) * 0.05,
                    avg_sov=0.4,
                    avg_sentiment=0.7,
                    total_queries=100,
                )
            )
    db_session.add(
        IndustryTopicDaily(
            industry_id=1,
            category="snacks",
            topic_id=9001,
            date=datetime.combine(today, datetime.min.time()),
            mention_count=25,
            unique_brand_count=5,
            hot_score=0.91,
        )
    )
    # brand_mentions for events_30d + topics
    for i in range(15):
        db_session.add(
            BrandMention(
                response_id=4000 + i,
                brand_id=50 + (i % 5),
                brand_name=f"brand-{50 + (i % 5)}",
                sentiment="positive",
                sentiment_score=0.6,
                created_at=datetime.now() - timedelta(days=i % 7),
            )
        )
    await db_session.commit()
    return industry_name


@pytest.mark.asyncio
async def test_list_industries(client, user, industry_data):
    resp = await client.get("/api/v1/industries/", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert any(it["name"] == industry_data for it in body["items"])


@pytest.mark.asyncio
async def test_top_brands(client, user, industry_data):
    resp = await client.get("/api/v1/industries/1/top-brands?n=3", headers=_bearer(user))
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) <= 3
    if rows:
        assert rows[0]["rank"] == 1


@pytest.mark.asyncio
async def test_industry_overview(client, user, industry_data):
    resp = await client.get(
        f"/api/v1/industries/1/overview?name={industry_data}",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "ok"
    assert body["industry_name"] == industry_data
    assert len(body["kpi_cards"]) == 4
    assert len(body["top_brands"]) >= 1
    assert len(body["events_30d"]) >= 1


@pytest.mark.asyncio
async def test_industry_ranking_with_paging(client, user, industry_data):
    resp = await client.get(
        f"/api/v1/industries/1/ranking?name={industry_data}&limit=2&offset=0",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "ok"
    assert len(body["items"]) == 2
    assert body["total"] >= 5
    assert body["items"][0]["rank"] == 1
    assert body["items"][1]["rank"] == 2

    # Second page
    resp2 = await client.get(
        f"/api/v1/industries/1/ranking?name={industry_data}&limit=2&offset=2",
        headers=_bearer(user),
    )
    body2 = resp2.json()
    assert body2["items"][0]["rank"] == 3


@pytest.mark.asyncio
async def test_industry_topics(client, user, industry_data):
    resp = await client.get(
        f"/api/v1/industries/1/topics?name={industry_data}",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "ok"
    assert len(body["items"]) >= 1
    assert body["items"][0]["topic_id"] == 9001
    assert body["items"][0]["topic_name"] != "brand-50"


@pytest.mark.asyncio
async def test_industry_kg_synthesizes_graph(client, user, industry_data):
    resp = await client.get(
        f"/api/v1/industries/1/kg?name={industry_data}&depth=2",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "ok"
    # 1 industry node + N brand nodes
    assert len(body["nodes"]) >= 2
    industry_nodes = [n for n in body["nodes"] if n["type"] == "industry"]
    brand_nodes = [n for n in body["nodes"] if n["type"] == "brand"]
    assert len(industry_nodes) == 1
    assert len(brand_nodes) >= 1
    # Industry → brand edges exist; relation edges (COMPETES_WITH / SAME_GROUP)
    # may also be present depending on kg_brand_relations data.
    belongs_to = [e for e in body["edges"] if e["type"] == "BELONGS_TO"]
    assert len(belongs_to) >= len(brand_nodes)


@pytest.mark.asyncio
async def test_industry_no_auth_returns_401(client):
    resp = await client.get("/api/v1/industries/")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "unauthorized"


@pytest.mark.asyncio
async def test_industry_invalid_date_returns_422(client, user, industry_data):
    resp = await client.get(
        f"/api/v1/industries/1/ranking?name={industry_data}&from=not-a-date",
        headers=_bearer(user),
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "validation_error"
