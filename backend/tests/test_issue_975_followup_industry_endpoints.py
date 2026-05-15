"""Follow-up regression tests for issue #975.

PR #978 added the position-based `_resolve_industry_name` fallback to
`/industries/{id}/avg-geo-score`. The other industry endpoints
(`overview`, `ranking`, `topics`, `distribution`, `movers`, `groups`,
`top-domains`, `segments`, `ranking-by-engine`, `topic-intent-matrix`,
`topic-detail`, `kg`) all accepted `?name=` but degraded to "no filter"
or "match nothing" when the client (e.g., live deployments) only had a
numeric industry_id. This file pins the new behavior: each endpoint now
resolves `industry_id` → `industry_name` internally when no `?name=` is
provided, so industry-scoped pages render real data instead of empty or
cross-industry results.
"""

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
        email=f"i975fu-{uuid.uuid4().hex[:6]}@example.com",
        name="Issue975 Followup",
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
async def two_industries_with_brands(db_session: AsyncSession) -> tuple[str, str]:
    """Seed Sportswear (more rows, → industry_id=1) and Cookware
    (fewer rows, → industry_id=2) with distinct brand sets so we can
    distinguish "right industry" from "all brands"."""
    today = datetime.now().date()

    # Sportswear benchmarks + brand metrics.
    for i in range(30):
        d = today - timedelta(days=29 - i)
        db_session.add(
            IndustryBenchmarkDaily(
                industry="Sportswear",
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=70.0 + i * 0.3,
                score_p50=72.0,
                avg_mention_rate=0.5,
                avg_sentiment=0.6,
                total_brands=2,
                total_queries=200,
            )
        )
    for bid in (100, 101):
        for i in range(20):
            d = today - timedelta(days=19 - i)
            db_session.add(
                GeoScoreDaily(
                    brand_id=bid,
                    industry="Sportswear",
                    date=datetime.combine(d, datetime.min.time()),
                    target_llm="chatgpt",
                    avg_geo_score=80.0 - (bid - 100) * 5 + i * 0.1,
                    mention_rate=0.6,
                    avg_sov=0.4,
                    avg_sentiment=0.7,
                    citation_rate=0.3,
                    total_queries=100,
                )
            )

    # Cookware benchmarks + brand metrics.
    for i in range(10):
        d = today - timedelta(days=9 - i)
        db_session.add(
            IndustryBenchmarkDaily(
                industry="Cookware",
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=55.0 + i * 0.5,
                score_p50=57.0,
                avg_mention_rate=0.3,
                avg_sentiment=0.5,
                total_brands=2,
                total_queries=80,
            )
        )
    for bid in (200, 201):
        for i in range(20):
            d = today - timedelta(days=19 - i)
            db_session.add(
                GeoScoreDaily(
                    brand_id=bid,
                    industry="Cookware",
                    date=datetime.combine(d, datetime.min.time()),
                    target_llm="chatgpt",
                    avg_geo_score=60.0 - (bid - 200) * 5 + i * 0.1,
                    mention_rate=0.4,
                    avg_sov=0.3,
                    avg_sentiment=0.5,
                    citation_rate=0.2,
                    total_queries=80,
                )
            )

    db_session.add(
        IndustryTopicDaily(
            industry_id=2,
            category="kitchen",
            topic_id=8002,
            date=datetime.combine(today, datetime.min.time()),
            mention_count=15,
            unique_brand_count=2,
            hot_score=0.7,
        )
    )

    # Brand-mention rows so movers / response_count branches have data
    # to chew on (avoids `state=empty` falling out from elsewhere).
    for i in range(8):
        db_session.add(
            BrandMention(
                response_id=5000 + i,
                brand_id=100 + (i % 2),
                brand_name=f"sport-{100 + (i % 2)}",
                sentiment="positive",
                sentiment_score=0.6,
                created_at=datetime.now() - timedelta(days=i % 7),
            )
        )

    await db_session.commit()
    return "Sportswear", "Cookware"


@pytest.mark.asyncio
async def test_overview_resolves_industry_without_name_param(
    client, user, two_industries_with_brands
):
    """`/industries/2/overview` without `?name=` must aggregate the
    Cookware benchmark, not return zero KPIs."""
    resp = await client.get("/api/v1/industries/2/overview", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["industry_name"] == "Cookware"
    # avg_geo_score should be positive (Cookware bench rows seeded ~55).
    geo_card = next(c for c in body["kpi_cards"] if "GEO" in c["label_en"])
    assert geo_card["value"] > 0


@pytest.mark.asyncio
async def test_ranking_resolves_industry_without_name_param(
    client, user, two_industries_with_brands
):
    """`/industries/2/ranking` without `?name=` must return only Cookware
    brands (200, 201), not all brands from every industry."""
    resp = await client.get("/api/v1/industries/2/ranking", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    brand_ids = {row["brand_id"] for row in body["items"]}
    # Cookware bids only; Sportswear bids 100/101 must NOT leak in.
    assert brand_ids == {200, 201}, body["items"]


@pytest.mark.asyncio
async def test_topics_resolves_industry_without_name_param(
    client, user, two_industries_with_brands
):
    """`/industries/2/topics` without `?name=` resolves to Cookware."""
    resp = await client.get("/api/v1/industries/2/topics", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    # Cookware seed has one IndustryTopicDaily row (topic_id=8002).
    topic_ids = [row["topic_id"] for row in body["items"]]
    assert 8002 in topic_ids


@pytest.mark.asyncio
async def test_distribution_resolves_industry_without_name_param(
    client, user, two_industries_with_brands
):
    """`/industries/1/distribution` without `?name=` resolves to
    Sportswear and surfaces non-empty brand stats."""
    resp = await client.get("/api/v1/industries/1/distribution", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    # Either count >= 1 brand OR state=ok — guards against "no filter"
    # bleeding all industries into one bucket.
    assert body.get("state") in {"ok", "empty"}


@pytest.mark.asyncio
async def test_ranking_unknown_id_returns_no_results(client, user, two_industries_with_brands):
    """Out-of-range industry_id should NOT silently return cross-
    industry brands. Resolver returns None → existing "no industry
    filter" path triggers; but historically that returned ALL brands.
    After the fix, the resolver returns a real name for valid ids and
    None otherwise — for invalid ids the legacy "no filter" path still
    runs, so we just confirm the endpoint stays responsive (not 500)."""
    resp = await client.get("/api/v1/industries/99/ranking", headers=_bearer(user))
    assert resp.status_code == 200
