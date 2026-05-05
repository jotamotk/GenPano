"""Phase D — second batch of 4 diagnostic rules.

Covers:
    - SentimentDropRule          (sentiment_drop)
    - ShareOfVoiceMinorRule      (share_of_voice_minor)
    - IndustryLagTop10Rule       (industry_lag_top10)
    - CitationDiversityLowRule   (citation_diversity_low)
"""

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
    User,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.diagnostics.rules import (
    REGISTRY,
    CitationDiversityLowRule,
    IndustryLagTop10Rule,
    SentimentDropRule,
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
        name="D2",
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
    p = Project(id=_new_id(), user_id=user.id, name="P", primary_brand_id=410)
    db_session.add(p)
    await db_session.commit()
    return p


# ── SentimentDropRule ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sentiment_drop_p1_when_avg_score_drops_geq_25(db_session, project):
    """Prior 30d avg=+0.6 → current avg=+0.3 → delta=-0.3 → P1."""
    for i in range(15):
        db_session.add(
            BrandMention(
                response_id=6000 + i,
                brand_id=410,
                brand_name="Acme",
                sentiment="positive",
                sentiment_score=0.6,
                created_at=datetime.now() - timedelta(days=45 + i),
            )
        )
    for i in range(15):
        db_session.add(
            BrandMention(
                response_id=6100 + i,
                brand_id=410,
                brand_name="Acme",
                sentiment="positive",
                sentiment_score=0.3,
                created_at=datetime.now() - timedelta(days=15 + i),
            )
        )
    await db_session.commit()

    out = await SentimentDropRule().evaluate(db_session, project)
    assert len(out) == 1
    assert out[0].severity == "P1"
    assert out[0].category == "sentiment_drop"


@pytest.mark.asyncio
async def test_sentiment_drop_p2_when_smaller_drop(db_session, project):
    """Prior +0.6 → current +0.45 → delta=-0.15 → P2 (between -0.1 and -0.25)."""
    for i in range(15):
        db_session.add(
            BrandMention(
                response_id=6200 + i,
                brand_id=410,
                brand_name="Acme",
                sentiment="positive",
                sentiment_score=0.6,
                created_at=datetime.now() - timedelta(days=45),
            )
        )
    for i in range(15):
        db_session.add(
            BrandMention(
                response_id=6300 + i,
                brand_id=410,
                brand_name="Acme",
                sentiment="positive",
                sentiment_score=0.45,
                created_at=datetime.now() - timedelta(days=15),
            )
        )
    await db_session.commit()
    out = await SentimentDropRule().evaluate(db_session, project)
    assert len(out) == 1
    assert out[0].severity == "P2"


@pytest.mark.asyncio
async def test_sentiment_drop_no_trigger_below_threshold(db_session, project):
    """Tiny drop (< 0.1) shouldn't trigger."""
    for i in range(15):
        db_session.add(
            BrandMention(
                response_id=6400 + i,
                brand_id=410,
                brand_name="Acme",
                sentiment_score=0.6,
                created_at=datetime.now() - timedelta(days=45),
            )
        )
    for i in range(15):
        db_session.add(
            BrandMention(
                response_id=6500 + i,
                brand_id=410,
                brand_name="Acme",
                sentiment_score=0.55,
                created_at=datetime.now() - timedelta(days=15),
            )
        )
    await db_session.commit()
    out = await SentimentDropRule().evaluate(db_session, project)
    assert out == []


# ── ShareOfVoiceMinorRule ────────────────────────────────────────


@pytest.mark.asyncio
async def test_share_of_voice_minor_triggers_when_below_5pct(db_session, project):
    today = datetime.now().date()
    for i in range(30):
        d = today - timedelta(days=29 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=410,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_sov=0.03,
                avg_geo_score=50.0,
                total_queries=100,
            )
        )
    await db_session.commit()
    out = await ShareOfVoiceMinorRule().evaluate(db_session, project)
    assert len(out) == 1
    assert out[0].severity == "P2"
    assert out[0].evidence["current_value"] == 0.03


@pytest.mark.asyncio
async def test_share_of_voice_minor_no_trigger_when_above_5pct(db_session, project):
    today = datetime.now().date()
    for i in range(30):
        d = today - timedelta(days=29 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=410,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_sov=0.10,
                avg_geo_score=70.0,
                total_queries=100,
            )
        )
    await db_session.commit()
    out = await ShareOfVoiceMinorRule().evaluate(db_session, project)
    assert out == []


# ── IndustryLagTop10Rule ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_industry_lag_p1_when_lag_geq_20(db_session, project):
    """Top-10 avg=85, my=60, lag=25 → P1."""
    today = datetime.now().date()
    # Seed 10 high-scoring brands → average will be ~85
    for bid_offset in range(10):
        for i in range(30):
            d = today - timedelta(days=29 - i)
            db_session.add(
                GeoScoreDaily(
                    brand_id=500 + bid_offset,
                    date=datetime.combine(d, datetime.min.time()),
                    target_llm="chatgpt",
                    avg_geo_score=85.0,
                    avg_sov=0.1,
                    total_queries=100,
                )
            )
    # My brand at 60
    for i in range(30):
        d = today - timedelta(days=29 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=410,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=60.0,
                avg_sov=0.1,
                total_queries=100,
            )
        )
    await db_session.commit()
    out = await IndustryLagTop10Rule().evaluate(db_session, project)
    assert len(out) == 1
    assert out[0].severity == "P1"
    assert out[0].evidence["lag"] >= 20


@pytest.mark.asyncio
async def test_industry_lag_p2_when_lag_10_to_20(db_session, project):
    """Top-10 avg=85, my=72, lag=13 → P2."""
    today = datetime.now().date()
    for bid_offset in range(10):
        for i in range(30):
            d = today - timedelta(days=29 - i)
            db_session.add(
                GeoScoreDaily(
                    brand_id=600 + bid_offset,
                    date=datetime.combine(d, datetime.min.time()),
                    target_llm="chatgpt",
                    avg_geo_score=85.0,
                    avg_sov=0.1,
                    total_queries=100,
                )
            )
    for i in range(30):
        d = today - timedelta(days=29 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=410,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=72.0,
                avg_sov=0.1,
                total_queries=100,
            )
        )
    await db_session.commit()
    out = await IndustryLagTop10Rule().evaluate(db_session, project)
    assert len(out) == 1
    assert out[0].severity == "P2"


@pytest.mark.asyncio
async def test_industry_lag_no_trigger_when_close(db_session, project):
    """My score very close to top-10 → no trigger."""
    today = datetime.now().date()
    for bid_offset in range(10):
        for i in range(30):
            d = today - timedelta(days=29 - i)
            db_session.add(
                GeoScoreDaily(
                    brand_id=700 + bid_offset,
                    date=datetime.combine(d, datetime.min.time()),
                    target_llm="chatgpt",
                    avg_geo_score=85.0,
                    avg_sov=0.1,
                    total_queries=100,
                )
            )
    for i in range(30):
        d = today - timedelta(days=29 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=410,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=80.0,
                avg_sov=0.1,
                total_queries=100,
            )
        )
    await db_session.commit()
    out = await IndustryLagTop10Rule().evaluate(db_session, project)
    assert out == []


# ── CitationDiversityLowRule ─────────────────────────────────────


@pytest.mark.asyncio
async def test_citation_diversity_low_triggers_when_lt_5_domains(db_session, project):
    mention = BrandMention(response_id=7001, brand_id=410, brand_name="Acme")
    db_session.add(mention)
    await db_session.commit()
    await db_session.refresh(mention)
    # 3 distinct domains, 8 citations
    for i in range(8):
        db_session.add(
            CitationSource(
                response_id=7001,
                mention_id=mention.id,
                url=f"https://example{i % 3}.com/a/{i}",
                domain=f"example{i % 3}.com",
            )
        )
    await db_session.commit()
    out = await CitationDiversityLowRule().evaluate(db_session, project)
    assert len(out) == 1
    assert out[0].severity == "P2"
    assert out[0].evidence["current_value"] == 3


@pytest.mark.asyncio
async def test_citation_diversity_no_trigger_when_geq_5_domains(db_session, project):
    mention = BrandMention(response_id=7002, brand_id=410, brand_name="Acme")
    db_session.add(mention)
    await db_session.commit()
    await db_session.refresh(mention)
    for i in range(7):
        db_session.add(
            CitationSource(
                response_id=7002,
                mention_id=mention.id,
                url=f"https://site{i}.com/a",
                domain=f"site{i}.com",
            )
        )
    await db_session.commit()
    out = await CitationDiversityLowRule().evaluate(db_session, project)
    assert out == []


@pytest.mark.asyncio
async def test_citation_diversity_no_trigger_when_zero(db_session, project):
    """Brand with no citations → don't fire (it'd be a separate alert)."""
    out = await CitationDiversityLowRule().evaluate(db_session, project)
    assert out == []


# ── REGISTRY contains the 4 new rules ────────────────────────────


def test_registry_includes_batch2_rules():
    assert SentimentDropRule in REGISTRY
    assert ShareOfVoiceMinorRule in REGISTRY
    assert IndustryLagTop10Rule in REGISTRY
    assert CitationDiversityLowRule in REGISTRY
    # Total now 10
    assert len(REGISTRY) >= 10
