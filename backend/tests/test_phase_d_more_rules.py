"""Phase D — additional diagnostic rules (competitor / outage / citation)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import (
    BrandMention,
    CitationSource,
    GeoScoreDaily,
    Project,
    ProjectCompetitor,
    User,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.diagnostics.rules import (
    REGISTRY,
    CitationVolumeDropRule,
    CompetitorOvertakeRule,
    MonitoringOutageRule,
)

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"d2-{uuid.uuid4().hex[:6]}@example.com",
        name="Diag2",
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
        name="P",
        primary_brand_id=300,
    )
    db_session.add(p)
    await db_session.commit()
    return p


# ── CompetitorOvertakeRule ────────────────────────────────────────


@pytest.mark.asyncio
async def test_competitor_overtake_p1_when_gap_geq_5(db_session, project):
    db_session.add(ProjectCompetitor(project_id=project.id, brand_id=400))
    today = datetime.now().date()
    for i in range(30):
        d = today - timedelta(days=29 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=300,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=70.0,
                mention_rate=0.5,
                total_queries=100,
            )
        )
        db_session.add(
            GeoScoreDaily(
                brand_id=400,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=80.0,
                mention_rate=0.6,
                total_queries=100,
            )
        )
    await db_session.commit()

    rule = CompetitorOvertakeRule()
    out = await rule.evaluate(db_session, project)
    assert len(out) == 1
    assert out[0].severity == "P1"
    assert out[0].evidence["competitor_brand_id"] == 400


@pytest.mark.asyncio
async def test_competitor_overtake_p2_when_small_gap(db_session, project):
    db_session.add(ProjectCompetitor(project_id=project.id, brand_id=401))
    today = datetime.now().date()
    for i in range(30):
        d = today - timedelta(days=29 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=300,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=70.0,
                mention_rate=0.5,
                total_queries=100,
            )
        )
        db_session.add(
            GeoScoreDaily(
                brand_id=401,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=72.0,
                mention_rate=0.5,
                total_queries=100,
            )
        )
    await db_session.commit()
    out = await CompetitorOvertakeRule().evaluate(db_session, project)
    assert len(out) == 1
    assert out[0].severity == "P2"


@pytest.mark.asyncio
async def test_competitor_overtake_no_competitors_pinned(db_session, project):
    out = await CompetitorOvertakeRule().evaluate(db_session, project)
    assert out == []


@pytest.mark.asyncio
async def test_competitor_overtake_competitor_below(db_session, project):
    """Competitor with lower score doesn't trigger."""
    db_session.add(ProjectCompetitor(project_id=project.id, brand_id=402))
    today = datetime.now().date()
    for i in range(30):
        d = today - timedelta(days=29 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=300,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=80.0,
                mention_rate=0.5,
                total_queries=100,
            )
        )
        db_session.add(
            GeoScoreDaily(
                brand_id=402,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=70.0,
                mention_rate=0.5,
                total_queries=100,
            )
        )
    await db_session.commit()
    out = await CompetitorOvertakeRule().evaluate(db_session, project)
    assert out == []


# ── MonitoringOutageRule ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_monitoring_outage_p0_when_24h_empty_but_14d_seeded(db_session, project):
    """Brand had data 5 days ago but nothing in last 24h → P0."""
    old = datetime.now() - timedelta(days=5)
    for i in range(5):
        db_session.add(
            BrandMention(
                response_id=2000 + i,
                brand_id=300,
                brand_name="primary",
                created_at=old,
            )
        )
    await db_session.commit()
    out = await MonitoringOutageRule().evaluate(db_session, project)
    assert len(out) == 1
    assert out[0].severity == "P0"
    assert out[0].evidence["current_value"] == 0
    assert out[0].evidence["prior_window_14d_count"] == 5


@pytest.mark.asyncio
async def test_monitoring_outage_no_history_no_trigger(db_session, project):
    """Project never had data → not an outage, just unconfigured. No trigger."""
    out = await MonitoringOutageRule().evaluate(db_session, project)
    assert out == []


@pytest.mark.asyncio
async def test_monitoring_outage_recent_data_no_trigger(db_session, project):
    db_session.add(
        BrandMention(
            response_id=2100,
            brand_id=300,
            brand_name="primary",
            created_at=datetime.now() - timedelta(hours=2),
        )
    )
    await db_session.commit()
    out = await MonitoringOutageRule().evaluate(db_session, project)
    assert out == []


# ── CitationVolumeDropRule ────────────────────────────────────────


@pytest.mark.asyncio
async def test_citation_volume_drop_p1_when_50_pct_drop(db_session, project):
    """Prior 30d had 20 citations, current has 8 → -60% → P1."""
    today = datetime.now().date()
    # Add a mention to chain through (CitationSource joins on mention_id → brand_id)
    mention = BrandMention(
        response_id=3001,
        brand_id=300,
        brand_name="primary",
    )
    db_session.add(mention)
    await db_session.commit()
    await db_session.refresh(mention)

    # Prior period: 20 citations
    for i in range(20):
        d = datetime.combine(today - timedelta(days=45), datetime.min.time())
        db_session.add(
            CitationSource(
                response_id=3001,
                mention_id=mention.id,
                url=f"https://x.com/{i}",
                created_at=d,
            )
        )
    # Current period: 8 citations
    for i in range(8):
        d = datetime.combine(today - timedelta(days=10), datetime.min.time())
        db_session.add(
            CitationSource(
                response_id=3001,
                mention_id=mention.id,
                url=f"https://y.com/{i}",
                created_at=d,
            )
        )
    await db_session.commit()
    out = await CitationVolumeDropRule().evaluate(db_session, project)
    assert len(out) == 1
    assert out[0].severity == "P1"
    assert out[0].evidence["change_percent"] <= -50


@pytest.mark.asyncio
async def test_citation_volume_drop_no_trigger_below_threshold(db_session, project):
    today = datetime.now().date()
    mention = BrandMention(response_id=3002, brand_id=300, brand_name="primary")
    db_session.add(mention)
    await db_session.commit()
    await db_session.refresh(mention)
    for i in range(20):
        d = datetime.combine(today - timedelta(days=45), datetime.min.time())
        db_session.add(
            CitationSource(
                response_id=3002, mention_id=mention.id, url=f"https://a/{i}", created_at=d
            )
        )
    for i in range(18):  # only 10% drop
        d = datetime.combine(today - timedelta(days=10), datetime.min.time())
        db_session.add(
            CitationSource(
                response_id=3002, mention_id=mention.id, url=f"https://b/{i}", created_at=d
            )
        )
    await db_session.commit()
    out = await CitationVolumeDropRule().evaluate(db_session, project)
    assert out == []


# ── REGISTRY contains the 3 new rules ─────────────────────────────


def test_registry_includes_new_rules():
    assert CompetitorOvertakeRule in REGISTRY
    assert MonitoringOutageRule in REGISTRY
    assert CitationVolumeDropRule in REGISTRY
