from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from geo_tracker.analyzer.aggregator import Aggregator
from geo_tracker.analyzer.canonical_brand_repair import repair_canonical_brand_mentions
from geo_tracker.db.models import (
    AnalysisStatus,
    Base,
    Brand,
    BrandMention,
    CitationSource,
    GEOScoreDaily,
    LLMResponse,
    Prompt,
    Query,
    QueryStatus,
    ResponseAnalysis,
    Topic,
    TopicScoreDaily,
)


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as db:
        yield db
    await engine.dispose()


async def _seed_cross_brand_fixture(session: AsyncSession) -> datetime:
    day = datetime(2026, 5, 10, 10, 30)
    session.add_all(
        [
            Brand(id=2, name="理肤泉", aliases=["La Roche-Posay"], industry="beauty"),
            Brand(
                id=12,
                name="雅诗兰黛",
                aliases=["Estee Lauder", "Estée Lauder"],
                industry="beauty",
            ),
        ]
    )
    await session.flush()

    topic = Topic(id=20, brand_id=2, text="功效护肤品类", category="品类")
    prompt = Prompt(id=30, topic_id=20, text="适合干皮的精华推荐", intent="non_brand", language="zh")
    session.add_all([topic, prompt])
    await session.flush()

    session.add_all(
        [
            Query(
                id=100,
                prompt_id=30,
                brand_id=2,
                query_text="适合干皮的精华推荐",
                target_llm="doubao",
                status=QueryStatus.DONE.value,
                created_at=day,
            ),
            Query(
                id=101,
                prompt_id=30,
                brand_id=2,
                query_text="敏感肌精华怎么选",
                target_llm="doubao",
                status=QueryStatus.DONE.value,
                created_at=day + timedelta(minutes=1),
            ),
        ]
    )
    await session.flush()

    session.add_all(
        [
            LLMResponse(
                id=200,
                query_id=100,
                raw_text="雅诗兰黛小棕瓶在保湿和抗氧化方面常被推荐。",
                citations_json=[
                    {"url": "https://example.com/estee-review", "title": "雅诗兰黛评测", "index": 1}
                ],
                response_time_ms=1200,
                collected_at=day,
                analysis_status=AnalysisStatus.DONE.value,
            ),
            LLMResponse(
                id=201,
                query_id=101,
                raw_text="敏感肌可以先看舒缓修护和屏障支持。",
                citations_json=[],
                response_time_ms=1000,
                collected_at=day + timedelta(minutes=1),
                analysis_status=AnalysisStatus.DONE.value,
            ),
        ]
    )
    await session.flush()

    session.add_all(
        [
            ResponseAnalysis(
                response_id=200,
                dimension_industry="beauty",
                dimension_category="品类",
                target_brand_mentioned=False,
                total_brands_mentioned=0,
                raw_analysis_json={"source": "owner-brand-analysis"},
            ),
            ResponseAnalysis(
                response_id=201,
                dimension_industry="beauty",
                dimension_category="品类",
                target_brand_mentioned=False,
                total_brands_mentioned=0,
                raw_analysis_json={"source": "owner-brand-analysis"},
            ),
        ]
    )
    await session.commit()
    return day


@pytest.mark.asyncio
async def test_repair_dry_run_reports_without_writing(session: AsyncSession):
    day = await _seed_cross_brand_fixture(session)

    stats = await repair_canonical_brand_mentions(
        session,
        brand_id=12,
        start_at=day.replace(hour=0, minute=0, second=0),
        end_at=day.replace(hour=23, minute=59, second=59),
        source_brand_id=2,
        dry_run=True,
    )

    assert stats["responses_matched"] == 1
    assert stats["mentions_inserted"] == 1
    mentions = (
        await session.execute(select(BrandMention).where(BrandMention.brand_id == 12))
    ).scalars().all()
    assert mentions == []


@pytest.mark.asyncio
async def test_repair_inserts_canonical_mention_without_reassigning_owner(
    session: AsyncSession,
):
    day = await _seed_cross_brand_fixture(session)

    stats = await repair_canonical_brand_mentions(
        session,
        brand_id=12,
        start_at=day.replace(hour=0, minute=0, second=0),
        end_at=day.replace(hour=23, minute=59, second=59),
        source_brand_id=2,
        dry_run=False,
    )

    assert stats["responses_matched"] == 1
    assert stats["mentions_inserted"] == 1

    mention = (
        await session.execute(select(BrandMention).where(BrandMention.brand_id == 12))
    ).scalar_one()
    assert mention.response_id == 200
    assert mention.brand_name == "雅诗兰黛"
    assert mention.is_target is False
    assert mention.mention_count == 1
    assert "雅诗兰黛" in (mention.context_snippet or "")

    owner_query = await session.get(Query, 100)
    assert owner_query is not None
    assert owner_query.brand_id == 2


@pytest.mark.asyncio
async def test_aggregator_builds_canonical_brand_aggregates_from_cross_brand_mentions(
    session: AsyncSession,
):
    day = await _seed_cross_brand_fixture(session)
    await repair_canonical_brand_mentions(
        session,
        brand_id=12,
        start_at=day.replace(hour=0, minute=0, second=0),
        end_at=day.replace(hour=23, minute=59, second=59),
        source_brand_id=2,
        dry_run=False,
    )
    mention = (
        await session.execute(select(BrandMention).where(BrandMention.brand_id == 12))
    ).scalar_one()
    session.add(
        CitationSource(
            response_id=200,
            mention_id=mention.id,
            url="https://example.com/estee-review",
            domain="example.com",
            source_type="review_site",
        )
    )
    await session.commit()

    stats = await Aggregator(session).aggregate_daily(day, brand_id=12)

    assert stats["geo_score_daily"] == 2
    assert stats["topic_score"] == 1

    geo = (
        await session.execute(
            select(GEOScoreDaily).where(
                GEOScoreDaily.brand_id == 12,
                GEOScoreDaily.target_llm.is_(None),
                GEOScoreDaily.intent.is_(None),
                GEOScoreDaily.language.is_(None),
            )
        )
    ).scalar_one()
    assert geo.total_queries == 2
    assert geo.mention_count == 1
    assert geo.mention_rate == pytest.approx(0.5)
    assert geo.avg_sov == pytest.approx(1.0)
    assert geo.citation_rate == pytest.approx(1.0)
    assert geo.avg_position_rank is None
    assert 0 < geo.avg_geo_score <= 100

    topic = (
        await session.execute(select(TopicScoreDaily).where(TopicScoreDaily.brand_id == 12))
    ).scalar_one()
    assert topic.topic_id == 20
    assert topic.total_responses == 2
    assert topic.mention_count == 1
    assert topic.mention_rate == pytest.approx(0.5)

    owner_query = await session.get(Query, 100)
    assert owner_query is not None
    assert owner_query.brand_id == 2
