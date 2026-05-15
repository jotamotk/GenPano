"""Regression tests for issue #975.

Issue: industry-scoped metrics (e.g., `行业平均`, `行业排名`) returned empty
payloads, and the competitor comparison panel listed brands from
unrelated industries.

Root causes addressed here:
1. `_resolve_industry_name` did fragile substring matching against the
   industry name — for `industry_id=2`, the resolver would scan
   `IndustryBenchmarkDaily.industry` for a name containing "2" and fall
   back to the most-frequent name, so the avg-geo-score endpoint would
   silently load the wrong (or empty) industry.
2. `discover_related_brand_ids` returned brands co-mentioned in the same
   response as the primary, with no industry filter — so a cookware
   brand could appear as a competitor for a sportswear brand simply
   because both names landed in one AI answer.

These tests fail on the pre-fix codebase.
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
    Project,
    User,
)
from sqlalchemy import text
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
        email=f"i975-{uuid.uuid4().hex[:6]}@example.com",
        name="Issue975 User",
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
async def two_industries(db_session: AsyncSession) -> tuple[str, str]:
    """Seed two industries with distinct benchmark histories.

    `Sportswear` is the heavier-mention industry (30d, total_brands=10)
    and gets `industry_id=1` from `list_industries`. `Cookware` is the
    lighter one (10d, total_brands=4) → `industry_id=2`.
    """
    today = datetime.now().date()
    # Sportswear → industry_id=1 (more rows)
    for i in range(30):
        d = today - timedelta(days=29 - i)
        db_session.add(
            IndustryBenchmarkDaily(
                industry="Sportswear",
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=70.0 + i * 0.3,
                score_p50=72.0 + i * 0.2,
                avg_mention_rate=0.5,
                avg_sentiment=0.6,
                total_brands=10,
                total_queries=200,
            )
        )
    # Cookware → industry_id=2 (fewer rows)
    for i in range(10):
        d = today - timedelta(days=9 - i)
        db_session.add(
            IndustryBenchmarkDaily(
                industry="Cookware",
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=55.0 + i * 0.5,
                score_p50=58.0 + i * 0.4,
                avg_mention_rate=0.3,
                avg_sentiment=0.5,
                total_brands=4,
                total_queries=80,
            )
        )
    await db_session.commit()
    return "Sportswear", "Cookware"


@pytest.mark.asyncio
async def test_list_industries_assigns_position_based_ids(client, user, two_industries):
    sportswear, cookware = two_industries
    resp = await client.get("/api/v1/industries/", headers=_bearer(user))
    assert resp.status_code == 200
    items = resp.json()["items"]
    # Mention-count desc: Sportswear (30) before Cookware (10).
    assert items[0]["name"] == sportswear
    assert items[0]["industry_id"] == 1
    assert items[1]["name"] == cookware
    assert items[1]["industry_id"] == 2


@pytest.mark.asyncio
async def test_avg_geo_score_resolves_industry_by_id_without_name_param(
    client, user, two_industries
):
    """Issue #975: hitting /industries/{id}/avg-geo-score without ?name=
    must return data for the industry at position `id` — not empty, not
    the wrong industry."""
    sportswear, cookware = two_industries

    # industry_id=2 → Cookware (position 2 in /industries list).
    resp = await client.get("/api/v1/industries/2/avg-geo-score", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["industry_name"] == cookware
    assert body["state"] == "ok"
    assert len(body["points"]) >= 1
    assert body["summary"].get("avg_geo_score") is not None

    # industry_id=1 → Sportswear.
    resp1 = await client.get("/api/v1/industries/1/avg-geo-score", headers=_bearer(user))
    body1 = resp1.json()
    assert body1["industry_name"] == sportswear
    assert body1["state"] == "ok"
    assert len(body1["points"]) >= 10


@pytest.mark.asyncio
async def test_avg_geo_score_unknown_industry_id_returns_empty(client, user, two_industries):
    """Out-of-range industry_id should fall through to `state=empty`
    rather than silently aliasing to the most-frequent industry."""
    resp = await client.get("/api/v1/industries/9/avg-geo-score", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["industry_name"] is None
    assert body["state"] == "empty"
    assert body["points"] == []


@pytest_asyncio.fixture
async def cross_industry_project(db_session: AsyncSession, user: User) -> Project:
    """Seed brands across two industries with cross-industry co-mentions.

    Primary brand 200 is Sportswear; competitor 201 is also Sportswear
    (should appear in /competitors/metrics). Brand 300 is Cookware and
    co-occurs in the same response_id set (used to appear in the panel
    incorrectly — issue #975).
    """
    # Brands table is created bare by Base.metadata; ensure `industry`
    # column exists for filtering.
    try:
        await db_session.execute(text("ALTER TABLE brands ADD COLUMN industry TEXT"))
    except Exception:
        pass

    await db_session.execute(
        text(
            "INSERT INTO brands (id, industry) VALUES "
            "(200, 'Sportswear'), (201, 'Sportswear'), (300, 'Cookware')"
        )
    )

    project = Project(
        user_id=user.id,
        name="Cross-Industry",
        primary_brand_id=200,
        industry_id=1,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project, ["competitors"])

    now = datetime.now()
    today = now.date()
    # GeoScoreDaily for all three brands so /competitors/metrics has metric rows.
    for bid, score in ((200, 78.0), (201, 70.0), (300, 60.0)):
        for i in range(10):
            d = today - timedelta(days=9 - i)
            db_session.add(
                GeoScoreDaily(
                    brand_id=bid,
                    date=datetime.combine(d, datetime.min.time()),
                    target_llm="chatgpt",
                    avg_geo_score=score + i * 0.1,
                    mention_rate=0.5,
                    avg_sov=0.3,
                    avg_sentiment=0.5,
                    total_queries=80,
                )
            )

    # Co-mentions: primary 200 + competitor 201 + cross-industry 300 all
    # appear in the same response_ids. Without industry scoping, 300
    # outranks 201 by mention count and crowds it out of the top-N panel.
    for i in range(8):
        rid = 9000 + i
        db_session.add(
            BrandMention(
                response_id=rid,
                brand_id=200,
                brand_name="PrimarySport",
                sentiment_score=0.7,
                created_at=now - timedelta(days=i % 5),
            )
        )
        db_session.add(
            BrandMention(
                response_id=rid,
                brand_id=300,
                brand_name="CookwareCo",
                sentiment_score=0.5,
                created_at=now - timedelta(days=i % 5),
            )
        )
        if i < 4:
            db_session.add(
                BrandMention(
                    response_id=rid,
                    brand_id=201,
                    brand_name="RivalSport",
                    sentiment_score=0.6,
                    created_at=now - timedelta(days=i % 5),
                )
            )
    await db_session.commit()
    return project


@pytest.mark.asyncio
async def test_competitors_metrics_excludes_cross_industry_brands(
    client, user, cross_industry_project
):
    """Brand 300 (Cookware) must not show up in a Sportswear project's
    competitor comparison even though it co-occurs in BrandMention rows."""
    resp = await client.get(
        f"/api/v1/projects/{cross_industry_project.id}/competitors/metrics",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    competitor_ids = {c["brand_id"] for c in body["competitors"]}
    assert 300 not in competitor_ids, (
        f"Cross-industry brand 300 leaked into competitors: {body['competitors']}"
    )
    # Same-industry rival should still be discoverable when no
    # ProjectCompetitor pins exist, via the brand_id override path.


@pytest.mark.asyncio
async def test_competitors_metrics_keeps_same_industry_via_override(
    client, user, cross_industry_project
):
    """With brand_id override (auto-discovery path), same-industry
    competitors are kept and cross-industry brands are dropped."""
    resp = await client.get(
        f"/api/v1/projects/{cross_industry_project.id}/competitors/metrics",
        headers=_bearer(user),
        params={"brand_id": 200},
    )
    assert resp.status_code == 200
    body = resp.json()
    competitor_ids = {c["brand_id"] for c in body["competitors"]}
    assert 300 not in competitor_ids
    # Brand 201 is the only same-industry co-mention → must be present.
    assert 201 in competitor_ids
