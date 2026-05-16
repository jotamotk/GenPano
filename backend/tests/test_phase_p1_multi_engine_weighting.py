"""[#1044 P1] B1-6 — traffic-weighted average across engines.

`GeoScoreDaily` rows are keyed by (brand_id, date, target_llm, intent,
language) — one row per engine per day. The diagnostic rules in
rules.py previously averaged a metric column across all rows with
`func.avg(metric)`, which gave every engine the same voice regardless
of how many queries it served. With multi-engine coverage that
materially distorts the result: a low-traffic engine (10 queries)
weighs equally with a high-traffic one (500 queries).

This module exercises the new `_weighted_avg_geo_metric` helper that
returns `SUM(metric * total_queries) / NULLIF(SUM(total_queries), 0)`,
and spot-checks two of the rules that consume it (VisibilityDecline,
GeoScoreDrop) to confirm the rule output changes when the engines'
traffic distribution is skewed.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import GeoScoreDaily, Project, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"we-{uuid.uuid4().hex[:6]}@example.com",
        name="we",
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
async def project(db_session: AsyncSession, user: User) -> Project:
    p = Project(
        id=_new_id(),
        user_id=user.id,
        name="Weighted P",
        primary_brand_id=42,
        created_at=_now() - timedelta(days=120),
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])
    return p


# ── direct helper assertions ────────────────────────────────


@pytest.mark.asyncio
async def test_b1_6_helper_returns_weighted_average(db_session, project):
    """SUM(metric * weight) / SUM(weight): with two rows where one
    engine has 100 queries (metric=80) and another has 10 queries
    (metric=20), weighted avg = (80*100 + 20*10) / (110) ≈ 74.5
    — far from the naive mean of 50."""
    from app.diagnostics.rules import _weighted_avg_geo_metric

    today = date.today()
    db_session.add(
        GeoScoreDaily(
            brand_id=42,
            date=datetime.combine(today, datetime.min.time()),
            target_llm="chatgpt",
            avg_geo_score=80.0,
            mention_rate=0.5,
            avg_sov=0.4,
            avg_sentiment=0.7,
            total_queries=100,
        )
    )
    db_session.add(
        GeoScoreDaily(
            brand_id=42,
            date=datetime.combine(today, datetime.min.time()),
            target_llm="doubao",
            avg_geo_score=20.0,
            mention_rate=0.5,
            avg_sov=0.4,
            avg_sentiment=0.7,
            total_queries=10,
        )
    )
    await db_session.commit()

    stmt = select(_weighted_avg_geo_metric(GeoScoreDaily.avg_geo_score)).where(
        GeoScoreDaily.brand_id == 42
    )
    weighted = (await db_session.execute(stmt)).scalar_one_or_none()
    assert weighted is not None
    # (80*100 + 20*10) / 110 = 8200/110 ≈ 74.545
    assert 74.0 < float(weighted) < 75.0


@pytest.mark.asyncio
async def test_b1_6_helper_returns_null_when_total_weight_is_zero(db_session):
    """Every row has total_queries=0 → SUM(weight)=0 → NULLIF makes the
    denominator NULL → result is NULL. No division-by-zero crash."""
    from app.diagnostics.rules import _weighted_avg_geo_metric

    today = date.today()
    db_session.add(
        GeoScoreDaily(
            brand_id=99,
            date=datetime.combine(today, datetime.min.time()),
            target_llm="chatgpt",
            avg_geo_score=42.0,
            mention_rate=0.5,
            avg_sov=0.4,
            avg_sentiment=0.7,
            total_queries=0,
        )
    )
    await db_session.commit()

    stmt = select(_weighted_avg_geo_metric(GeoScoreDaily.avg_geo_score)).where(
        GeoScoreDaily.brand_id == 99
    )
    weighted = (await db_session.execute(stmt)).scalar_one_or_none()
    assert weighted is None


@pytest.mark.asyncio
async def test_b1_6_helper_returns_null_when_no_rows(db_session):
    """No rows match the WHERE → SUM returns NULL → helper returns NULL."""
    from app.diagnostics.rules import _weighted_avg_geo_metric

    stmt = select(_weighted_avg_geo_metric(GeoScoreDaily.avg_geo_score)).where(
        GeoScoreDaily.brand_id == 999_999
    )
    weighted = (await db_session.execute(stmt)).scalar_one_or_none()
    assert weighted is None


@pytest.mark.asyncio
async def test_b1_6_helper_matches_simple_average_when_weights_equal(db_session, project):
    """Sanity: when every row has the same total_queries, weighted
    average == simple average (test fixtures historically use equal
    weights, which is why the existing 72 tests didn't break)."""
    from app.diagnostics.rules import _weighted_avg_geo_metric

    today = date.today()
    for tllm, score in [("chatgpt", 60.0), ("doubao", 80.0), ("deepseek", 100.0)]:
        db_session.add(
            GeoScoreDaily(
                brand_id=42,
                date=datetime.combine(today, datetime.min.time()),
                target_llm=tllm,
                avg_geo_score=score,
                mention_rate=0.5,
                avg_sov=0.4,
                avg_sentiment=0.7,
                total_queries=50,  # equal weights
            )
        )
    await db_session.commit()

    stmt = select(_weighted_avg_geo_metric(GeoScoreDaily.avg_geo_score)).where(
        GeoScoreDaily.brand_id == 42
    )
    weighted = (await db_session.execute(stmt)).scalar_one_or_none()
    # (60+80+100)/3 = 80
    assert weighted is not None
    assert abs(float(weighted) - 80.0) < 0.01


# ── rule output reacts to traffic skew ───────────────────────


@pytest.mark.asyncio
async def test_b1_6_geo_score_drop_uses_weighted_avg(db_session, project):
    """GeoScoreDropRule: previously, an engine with 10 queries at score=20
    in current window would drag the unweighted average down enough to
    fire a false-positive 'drop'. With weighting by total_queries, the
    dominant 500-query engine at score=80 keeps the average high and
    the rule does NOT fire."""
    from app.diagnostics.rules import GeoScoreDropRule

    today = date.today()

    # PRIOR window (-59..-30): consistent score ~80
    for d in range(30, 60):
        for tllm in ["chatgpt", "doubao"]:
            db_session.add(
                GeoScoreDaily(
                    brand_id=42,
                    date=datetime.combine(today - timedelta(days=d), datetime.min.time()),
                    target_llm=tllm,
                    avg_geo_score=80.0,
                    mention_rate=0.5,
                    avg_sov=0.4,
                    avg_sentiment=0.7,
                    total_queries=100,
                )
            )

    # CURRENT window (-29..0): chatgpt at score 80 (500 queries) +
    # doubao at score 20 (10 queries). Naive AVG ≈ 50; weighted AVG
    # = (80*500 + 20*10) / 510 ≈ 78.8.
    for d in range(0, 30):
        db_session.add(
            GeoScoreDaily(
                brand_id=42,
                date=datetime.combine(today - timedelta(days=d), datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=80.0,
                mention_rate=0.5,
                avg_sov=0.4,
                avg_sentiment=0.7,
                total_queries=500,
            )
        )
        db_session.add(
            GeoScoreDaily(
                brand_id=42,
                date=datetime.combine(today - timedelta(days=d), datetime.min.time()),
                target_llm="doubao",
                avg_geo_score=20.0,
                mention_rate=0.5,
                avg_sov=0.4,
                avg_sentiment=0.7,
                total_queries=10,
            )
        )
    await db_session.commit()

    out = await GeoScoreDropRule().evaluate(db_session, project)
    # Weighted avg ~78.8 vs prior ~80 → -1.5% drop. The rule's
    # threshold is -15%, so it must NOT fire. The naive average
    # would have shown -38% and fired P0.
    assert out == [], (
        "Weighted average should suppress the false-positive 'drop' that "
        "the naive average produced when a tiny-traffic engine reported "
        "a low score."
    )


@pytest.mark.asyncio
async def test_b1_6_visibility_decline_uses_weighted_avg(db_session, project):
    """VisibilityDeclineRule: same shape — large-traffic engine
    dominates the weighted average, so a low-traffic engine's
    mention-rate dip doesn't drag the rule into firing."""
    from app.diagnostics.rules import VisibilityDeclineRule

    today = date.today()

    # PRIOR window: mention_rate=0.5 across both engines, equal weights
    for d in range(30, 60):
        for tllm in ["chatgpt", "doubao"]:
            db_session.add(
                GeoScoreDaily(
                    brand_id=42,
                    date=datetime.combine(today - timedelta(days=d), datetime.min.time()),
                    target_llm=tllm,
                    avg_geo_score=80.0,
                    mention_rate=0.5,
                    avg_sov=0.4,
                    avg_sentiment=0.7,
                    total_queries=100,
                )
            )

    # CURRENT window: chatgpt mention=0.5 @ 500 q + doubao mention=0.1 @ 10 q
    # Naive avg = 0.3 → -40% drop → P1; weighted = (0.5*500 + 0.1*10)/510 ≈ 0.492 → -1.6%, no fire
    for d in range(0, 30):
        db_session.add(
            GeoScoreDaily(
                brand_id=42,
                date=datetime.combine(today - timedelta(days=d), datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=80.0,
                mention_rate=0.5,
                avg_sov=0.4,
                avg_sentiment=0.7,
                total_queries=500,
            )
        )
        db_session.add(
            GeoScoreDaily(
                brand_id=42,
                date=datetime.combine(today - timedelta(days=d), datetime.min.time()),
                target_llm="doubao",
                avg_geo_score=80.0,
                mention_rate=0.1,
                avg_sov=0.4,
                avg_sentiment=0.7,
                total_queries=10,
            )
        )
    await db_session.commit()

    out = await VisibilityDeclineRule().evaluate(db_session, project)
    assert out == [], (
        "Weighted average must not let a 10-query engine's mention-rate "
        "dip drive the rule to fire when 98% of traffic is healthy."
    )
