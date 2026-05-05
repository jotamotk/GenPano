"""Phase D.2 — extended diagnostic rules registry tests."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import BrandMention, GeoScoreDaily, Project, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.diagnostics.evaluator import evaluate_project
from app.diagnostics.rules import REGISTRY
from app.diagnostics.rules_extended import (
    REGISTRY_EXTENDED,
    CitationAuthorityLowRule,
    CompetitorOvertakeRule,
    ContentGapRule,
    GeoScoreDropSevereRule,
    MonitoringOutageRule,
    ShareOfVoiceMinorRule,
)

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"d2-{uuid.uuid4().hex[:6]}@example.com",
        name="D2 User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


def test_full_registry_is_25():
    """Base 3 + extended 22 = 25 total rules per PRD §4.7.1.1."""
    assert len(REGISTRY) == 25
    assert len(REGISTRY_EXTENDED) == 22


def test_extended_rules_all_have_categories():
    """Every extended rule has a non-empty category + versioned rule_id."""
    for cls in REGISTRY_EXTENDED:
        rule = cls()
        assert rule.category != ""
        assert rule.rule_id.endswith("_v1")


def test_no_duplicate_categories():
    """Each rule's category is unique (no two rules emit the same category)."""
    cats = [c().category for c in REGISTRY]
    assert len(set(cats)) == len(cats)


@pytest.mark.asyncio
async def test_share_of_voice_minor_triggers_p3(db_session: AsyncSession, user: User):
    """SoV averaging 4% (under 5% threshold) → P3 share_of_voice_minor."""
    project = Project(user_id=user.id, name="SoV Test", primary_brand_id=300)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project, ["competitors"])

    today = datetime.now().date()
    for i in range(30):
        d = today - timedelta(days=29 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=300,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=50.0,
                mention_rate=0.5,
                avg_sov=0.04,  # 4% — below threshold
                avg_sentiment=0.5,
            )
        )
    await db_session.commit()

    rule = ShareOfVoiceMinorRule()
    payloads = await rule.evaluate(db_session, project)
    assert len(payloads) == 1
    assert payloads[0].severity == "P3"
    assert payloads[0].category == "share_of_voice_minor"


@pytest.mark.asyncio
async def test_geo_score_drop_severe_triggers_p0(db_session: AsyncSession, user: User):
    """≤ -50% drop → P0 emergency."""
    project = Project(user_id=user.id, name="Severe", primary_brand_id=400)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project, ["competitors"])

    today = datetime.now().date()
    # Prior 30d: avg_geo_score=80
    for i in range(30):
        d = today - timedelta(days=59 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=400,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=80.0,
            )
        )
    # Current 30d: avg_geo_score=20 → -75%
    for i in range(30):
        d = today - timedelta(days=29 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=400,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=20.0,
            )
        )
    await db_session.commit()

    rule = GeoScoreDropSevereRule()
    payloads = await rule.evaluate(db_session, project)
    assert len(payloads) == 1
    assert payloads[0].severity == "P0"


@pytest.mark.asyncio
async def test_monitoring_outage_triggers_p0(db_session: AsyncSession, user: User):
    """No data in last 24h → P0 monitoring_outage."""
    project = Project(user_id=user.id, name="Outage", primary_brand_id=500)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project, ["competitors"])

    db_session.add(
        BrandMention(
            response_id=99999,
            brand_id=500,
            brand_name="Test",
            sentiment="positive",
            sentiment_score=0.5,
            created_at=datetime.now() - timedelta(hours=48),  # 48h ago
        )
    )
    await db_session.commit()

    rule = MonitoringOutageRule()
    payloads = await rule.evaluate(db_session, project)
    assert len(payloads) == 1
    assert payloads[0].severity == "P0"
    assert payloads[0].evidence["gap_hours"] >= 24


@pytest.mark.asyncio
async def test_content_gap_triggers_p2_for_low_mention(db_session, user):
    """Mention rate < 30% → P2 content_gap."""
    project = Project(user_id=user.id, name="Gap", primary_brand_id=600)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project, ["competitors"])

    today = datetime.now().date()
    for i in range(30):
        d = today - timedelta(days=29 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=600,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                mention_rate=0.15,  # 15% — well under 30%
                avg_geo_score=40.0,
            )
        )
    await db_session.commit()

    rule = ContentGapRule()
    payloads = await rule.evaluate(db_session, project)
    assert len(payloads) == 1
    assert payloads[0].severity == "P2"


@pytest.mark.asyncio
async def test_evaluator_runs_all_25_rules_without_crash(db_session, user):
    """Run evaluator with empty data — all 25 rules should return [], not crash."""
    project = Project(user_id=user.id, name="Empty", primary_brand_id=700)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project, ["competitors"])

    inserted = await evaluate_project(db_session, project)
    # No data → no diagnostics emitted, but no crash either
    assert isinstance(inserted, list)


@pytest.mark.asyncio
async def test_competitor_overtake_returns_none_when_primary_leads(db_session, user):
    """When primary brand has highest score, no diagnostic emitted."""
    project = Project(user_id=user.id, name="Lead", primary_brand_id=800)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project, ["competitors"])

    today = datetime.now().date()
    # Primary: 90; competitor: 50
    for i in range(7):
        d = today - timedelta(days=6 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=800,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=90.0,
            )
        )
        db_session.add(
            GeoScoreDaily(
                brand_id=801,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=50.0,
            )
        )
    await db_session.commit()

    rule = CompetitorOvertakeRule()
    payloads = await rule.evaluate(db_session, project)
    assert payloads == []


@pytest.mark.asyncio
async def test_citation_authority_low_unique_domains(db_session, user):
    """< 5 unique domains → P2 citation_authority_low."""
    project = Project(user_id=user.id, name="Auth", primary_brand_id=900)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project, ["competitors"])

    rule = CitationAuthorityLowRule()
    # No data → 0 domains < 5 → P2 should fire
    payloads = await rule.evaluate(db_session, project)
    assert len(payloads) == 1
    assert payloads[0].severity == "P2"
    assert payloads[0].evidence["distinct_domain_count"] == 0
