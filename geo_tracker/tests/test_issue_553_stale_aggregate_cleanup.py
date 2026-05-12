from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from geo_tracker.analyzer.aggregator import Aggregator
from geo_tracker.db.models import (
    AnalysisStatus,
    Base,
    Brand,
    BrandMention,
    GEOScoreDaily,
    LLMResponse,
    ProductScoreDaily,
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


async def _seed_base_brands(session: AsyncSession) -> None:
    session.add_all(
        [
            Brand(id=12, name="Estee Lauder", aliases=["EL"], industry="beauty"),
            Brand(id=77, name="Source Owner", aliases=[], industry="beauty"),
        ]
    )
    await session.flush()


async def _add_analyzed_response(
    session: AsyncSession,
    *,
    response_id: int,
    query_brand_id: int,
    day: datetime,
    prompt_id: int | None,
    topic_id: int | None,
    minutes: int = 0,
) -> LLMResponse:
    collected_at = day + timedelta(minutes=minutes)
    if topic_id is not None:
        session.add(
            Topic(
                id=topic_id,
                brand_id=query_brand_id,
                text=f"topic-{topic_id}",
                category="category",
            )
        )
        await session.flush()
    if prompt_id is not None:
        session.add(
            Prompt(
                id=prompt_id,
                topic_id=topic_id,
                text=f"prompt-{prompt_id}",
                intent="non_brand",
                language="en",
            )
        )
        await session.flush()

    query = Query(
        id=response_id + 1000,
        prompt_id=prompt_id,
        brand_id=query_brand_id,
        query_text=f"query-{response_id}",
        target_llm="doubao",
        status=QueryStatus.DONE.value,
        created_at=collected_at,
    )
    response = LLMResponse(
        id=response_id,
        query_id=query.id,
        raw_text="Estee Lauder evidence",
        citations_json=[],
        response_time_ms=800,
        collected_at=collected_at,
        analysis_status=AnalysisStatus.DONE.value,
    )
    analysis = ResponseAnalysis(
        response_id=response.id,
        dimension_industry="beauty",
        target_brand_mentioned=True,
        raw_analysis_json={"source": "issue-553"},
    )
    session.add_all([query, response, analysis])
    await session.flush()
    return response


def _stale_day(day: datetime) -> datetime:
    return day.replace(hour=0, minute=0, second=0, microsecond=0)


async def _stale_geo_topic_product_rows(session: AsyncSession, day: datetime) -> None:
    date_start = _stale_day(day)
    session.add_all(
        [
            GEOScoreDaily(
                brand_id=12,
                date=date_start,
                target_llm=None,
                intent=None,
                language=None,
                total_queries=56,
                mention_count=56,
                mention_rate=1.0,
                avg_sov=1.0,
                citation_rate=0.0,
                avg_geo_score=91.0,
                industry="beauty",
            ),
            TopicScoreDaily(
                brand_id=12,
                topic_id=20,
                date=date_start,
                mention_count=56,
                total_responses=56,
                mention_rate=1.0,
                avg_geo_score=91.0,
            ),
            ProductScoreDaily(
                brand_id=12,
                product_name="Advanced Night Repair",
                date=date_start,
                total_queries=56,
                mention_count=56,
                mention_rate=1.0,
                avg_sentiment_score=0.9,
                win_rate=1.0,
            ),
        ]
    )


@pytest.mark.asyncio
async def test_reaggregation_removes_stale_rows_when_no_valid_replacement_exists(
    session: AsyncSession,
) -> None:
    day = datetime(2026, 4, 24, 10, 0)
    await _seed_base_brands(session)
    response = await _add_analyzed_response(
        session,
        response_id=55301,
        query_brand_id=77,
        day=day,
        prompt_id=None,
        topic_id=None,
    )
    session.add(
        BrandMention(
            response_id=response.id,
            brand_id=12,
            brand_name="Estee Lauder",
            is_target=False,
            position_type="mentioned_only",
            sentiment="neutral",
            sentiment_score=0.0,
            mention_count=1,
        )
    )
    await _stale_geo_topic_product_rows(session, day)
    await session.commit()

    stats = await Aggregator(session).aggregate_daily(day, brand_id=12)

    assert stats["geo_score_daily"] == 0
    assert stats["topic_score"] == 0
    assert stats["product_score"] == 0
    assert stats["geo_score_daily_removed"] == 1
    assert stats["topic_score_removed"] == 1
    assert stats["product_score_removed"] == 1
    assert (await session.execute(select(GEOScoreDaily))).scalars().all() == []
    assert (await session.execute(select(TopicScoreDaily))).scalars().all() == []
    assert (await session.execute(select(ProductScoreDaily))).scalars().all() == []


@pytest.mark.asyncio
async def test_reaggregation_recomputes_stale_rows_when_valid_evidence_exists(
    session: AsyncSession,
) -> None:
    day = datetime(2026, 5, 6, 10, 0)
    await _seed_base_brands(session)
    mentioned = await _add_analyzed_response(
        session,
        response_id=55311,
        query_brand_id=12,
        day=day,
        prompt_id=30,
        topic_id=20,
    )
    await _add_analyzed_response(
        session,
        response_id=55312,
        query_brand_id=12,
        day=day,
        prompt_id=None,
        topic_id=None,
        minutes=1,
    )
    session.add(
        BrandMention(
            response_id=mentioned.id,
            brand_id=12,
            brand_name="Estee Lauder",
            product_name="Advanced Night Repair",
            is_target=True,
            position_type="mentioned_only",
            sentiment="positive",
            sentiment_score=0.8,
            mention_count=1,
        )
    )
    await _stale_geo_topic_product_rows(session, day)
    await session.commit()

    stats = await Aggregator(session).aggregate_daily(day, brand_id=12)

    assert stats["geo_score_daily"] == 2
    assert stats["geo_score_daily_removed"] == 1
    assert stats["topic_score_removed"] == 1
    assert stats["product_score_removed"] == 1
    geo = (
        await session.execute(
            select(GEOScoreDaily).where(
                GEOScoreDaily.brand_id == 12,
                GEOScoreDaily.target_llm.is_(None),
            )
        )
    ).scalar_one()
    assert geo.total_queries == 1
    assert geo.mention_count == 1
    assert geo.mention_rate == pytest.approx(1.0)
    assert geo.avg_sov is None

    topic = (await session.execute(select(TopicScoreDaily))).scalar_one()
    assert topic.total_responses == 1
    assert topic.mention_count == 1
    assert topic.mention_rate == pytest.approx(1.0)

    product = (await session.execute(select(ProductScoreDaily))).scalar_one()
    assert product.total_queries == 1
    assert product.mention_count == 1
    assert product.avg_sentiment_score == pytest.approx(0.8)
    assert product.win_rate is None
