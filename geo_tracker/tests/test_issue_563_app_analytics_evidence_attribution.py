from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime

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
    SentimentDriver,
    Topic,
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


async def _seed_owner_response(
    session: AsyncSession,
    *,
    response_id: int,
    raw_text: str,
    citations_json: list[dict] | None = None,
    prompt_intent: str | None = "non_brand",
    prompt_tags: object | None = None,
    topic_category: str | None = "category",
    raw_analysis_json: dict | None = None,
) -> tuple[datetime, LLMResponse, BrandMention]:
    day = datetime(2026, 5, 7, 10, 30)
    session.add_all(
        [
            Brand(id=2, name="La Roche-Posay", aliases=["LRP"], industry="beauty"),
            Brand(
                id=12,
                name="Estee Lauder",
                aliases=["雅诗兰黛", "EL"],
                industry="beauty",
            ),
        ]
    )
    await session.flush()
    session.add(Topic(id=500 + response_id, brand_id=2, text="skincare", category=topic_category))
    await session.flush()
    session.add(
        Prompt(
            id=600 + response_id,
            topic_id=500 + response_id,
            text="best repair serum",
            intent=prompt_intent,
            language="en",
            tags=prompt_tags,
        )
    )
    session.add(
        Query(
            id=700 + response_id,
            prompt_id=600 + response_id,
            brand_id=2,
            query_text="best repair serum",
            target_llm="doubao",
            status=QueryStatus.DONE.value,
            created_at=day,
        )
    )
    response = LLMResponse(
        id=response_id,
        query_id=700 + response_id,
        raw_text=raw_text,
        citations_json=citations_json or [],
        response_time_ms=1000,
        collected_at=day,
        analysis_status=AnalysisStatus.DONE.value,
    )
    session.add(response)
    await session.flush()
    mention = BrandMention(
        response_id=response_id,
        brand_id=12,
        brand_name="Estee Lauder",
        is_target=False,
        position_type="mentioned_only",
        detail_level="passing",
        sentiment=None,
        sentiment_score=None,
        context_snippet=raw_text,
        mention_count=1,
    )
    session.add(mention)
    await session.flush()
    raw = dict(raw_analysis_json or {})
    raw.setdefault(
        "canonical_alias_repairs",
        [
            {
                "source": "canonical_alias_repair_v1",
                "inserted_by_repair": True,
                "inserted_mention_id": mention.id,
                "state": "partial",
                "brand_id": 12,
                "owner_brand_id": 2,
            }
        ],
    )
    session.add(
        ResponseAnalysis(
            response_id=response_id,
            dimension_industry="beauty",
            dimension_category=topic_category,
            target_brand_mentioned=True,
            raw_analysis_json=raw,
        )
    )
    await session.commit()
    return day, response, mention


@pytest.mark.asyncio
async def test_repair_dry_run_reports_and_write_repairs_indexed_citation_context(
    session: AsyncSession,
) -> None:
    day, _response, mention = await _seed_owner_response(
        session,
        response_id=56301,
        raw_text="Estee Lauder Advanced Night Repair is recommended for repair [1].",
        citations_json=[
            {
                "url": "https://research.example/repair-study",
                "title": "Repair study",
                "index": 1,
            }
        ],
    )
    session.add(
        CitationSource(
            response_id=56301,
            mention_id=None,
            url="https://research.example/repair-study",
            domain="research.example",
            title="Repair study",
            citation_index=1,
            source_type="other",
        )
    )
    await session.commit()

    dry_stats = await repair_canonical_brand_mentions(
        session,
        brand_id=12,
        start_at=day.replace(hour=0, minute=0, second=0),
        end_at=day.replace(hour=23, minute=59, second=59),
        source_brand_id=2,
        dry_run=True,
    )

    assert dry_stats["citations_seen"] == 1
    assert dry_stats["citations_existing"] == 1
    assert dry_stats["citations_repairable"] == 1
    citation = (
        await session.execute(select(CitationSource).where(CitationSource.response_id == 56301))
    ).scalar_one()
    assert citation.mention_id is None

    write_stats = await repair_canonical_brand_mentions(
        session,
        brand_id=12,
        start_at=day.replace(hour=0, minute=0, second=0),
        end_at=day.replace(hour=23, minute=59, second=59),
        source_brand_id=2,
        dry_run=False,
    )

    assert write_stats["citations_repaired"] == 1
    citation = (
        await session.execute(select(CitationSource).where(CitationSource.response_id == 56301))
    ).scalar_one()
    assert citation.mention_id == mention.id

    repeat_stats = await repair_canonical_brand_mentions(
        session,
        brand_id=12,
        start_at=day.replace(hour=0, minute=0, second=0),
        end_at=day.replace(hour=23, minute=59, second=59),
        source_brand_id=2,
        dry_run=False,
    )

    assert repeat_stats["citations_repaired"] == 0
    assert repeat_stats["citations_existing"] == 1
    assert repeat_stats["citations_attributed"] == 1
    citations = (
        await session.execute(select(CitationSource).where(CitationSource.response_id == 56301))
    ).scalars().all()
    assert len(citations) == 1


@pytest.mark.asyncio
async def test_repair_keeps_ambiguous_indexed_citation_unresolved(
    session: AsyncSession,
) -> None:
    day, _response, _mention = await _seed_owner_response(
        session,
        response_id=56302,
        raw_text="Estee Lauder and La Roche-Posay are compared in the same claim [1].",
        citations_json=[
            {
                "url": "https://research.example/comparison",
                "title": "Comparison study",
                "index": 1,
            }
        ],
    )

    stats = await repair_canonical_brand_mentions(
        session,
        brand_id=12,
        start_at=day.replace(hour=0, minute=0, second=0),
        end_at=day.replace(hour=23, minute=59, second=59),
        source_brand_id=2,
        competitive_brand_ids={2},
        dry_run=False,
    )

    assert stats["competitive_mentions_inserted"] == 1
    assert stats["citations_unattributed"] == 1
    citation = (
        await session.execute(select(CitationSource).where(CitationSource.response_id == 56302))
    ).scalar_one()
    assert citation.mention_id is None
    analysis = (
        await session.execute(select(ResponseAnalysis).where(ResponseAnalysis.response_id == 56302))
    ).scalar_one()
    citation_status = analysis.raw_analysis_json["metric_input_status"]["citation"]
    assert citation_status["state"] == "partial"
    assert "citation_sources.mention_id" in citation_status["missing_inputs"]


@pytest.mark.asyncio
async def test_repair_backfills_sentiment_driver_only_from_raw_llm_evidence(
    session: AsyncSession,
) -> None:
    day, _response, mention = await _seed_owner_response(
        session,
        response_id=56303,
        raw_text="Estee Lauder is praised for repair serum authority.",
        raw_analysis_json={
            "brands": [
                {
                    "brand_name": "雅诗兰黛",
                    "sentiment": "positive",
                    "sentiment_score": 0.72,
                    "sentiment_drivers": [
                        {
                            "driver_text": "repair serum authority",
                            "polarity": "positive",
                            "category": "brand_image",
                            "strength": 0.9,
                            "source_quote": "Estee Lauder is praised for repair serum authority.",
                        }
                    ],
                }
            ]
        },
    )

    stats = await repair_canonical_brand_mentions(
        session,
        brand_id=12,
        start_at=day.replace(hour=0, minute=0, second=0),
        end_at=day.replace(hour=23, minute=59, second=59),
        source_brand_id=2,
        dry_run=False,
    )

    assert stats["sentiment_mentions_updated"] == 1
    assert stats["sentiment_drivers_inserted"] == 1
    refreshed = await session.get(BrandMention, mention.id)
    assert refreshed is not None
    assert refreshed.sentiment == "positive"
    assert refreshed.sentiment_score == pytest.approx(0.72)
    driver = (
        await session.execute(select(SentimentDriver).where(SentimentDriver.mention_id == mention.id))
    ).scalar_one()
    assert driver.source_quote == "Estee Lauder is praised for repair serum authority."

    repeat_stats = await repair_canonical_brand_mentions(
        session,
        brand_id=12,
        start_at=day.replace(hour=0, minute=0, second=0),
        end_at=day.replace(hour=23, minute=59, second=59),
        source_brand_id=2,
        dry_run=False,
    )
    assert repeat_stats["sentiment_drivers_inserted"] == 0
    assert repeat_stats["sentiment_drivers_existing"] == 1
    drivers = (
        await session.execute(select(SentimentDriver).where(SentimentDriver.mention_id == mention.id))
    ).scalars().all()
    assert len(drivers) == 1

    analysis = (
        await session.execute(select(ResponseAnalysis).where(ResponseAnalysis.response_id == 56303))
    ).scalar_one()
    sentiment_status = analysis.raw_analysis_json["metric_input_status"]["sentiment"]
    assert sentiment_status["state"] == "ok"
    assert sentiment_status["missing_inputs"] == []
    assert sentiment_status["quoted_target_driver_count"] == 1


@pytest.mark.asyncio
async def test_aggregator_accepts_admin_non_branded_prompt_scope_for_geo_rows(
    session: AsyncSession,
) -> None:
    day, response, mention = await _seed_owner_response(
        session,
        response_id=56304,
        raw_text="Estee Lauder and La Roche-Posay both appear in a non-branded category prompt.",
        prompt_intent="informational",
        prompt_tags={"prompt_scope": "non_branded"},
        topic_category="品类",
    )
    mention.position_type = "listed"
    mention.position_rank = 1
    mention.detail_level = "detailed"
    mention.sentiment = "positive"
    mention.sentiment_score = 0.8
    competitor = BrandMention(
        response_id=response.id,
        brand_id=2,
        brand_name="La Roche-Posay",
        is_target=False,
        position_type="mentioned_only",
        detail_level="passing",
        sentiment="neutral",
        sentiment_score=0.0,
        context_snippet=response.raw_text,
        mention_count=1,
    )
    session.add(competitor)
    await session.flush()
    session.add(
        CitationSource(
            response_id=response.id,
            mention_id=mention.id,
            url="https://research.example/repair-study",
            domain="research.example",
            title="Repair study",
            citation_index=1,
            source_type="other",
        )
    )
    await session.commit()

    stats = await Aggregator(session).aggregate_daily(
        day,
        brand_id=12,
        competitive_brand_ids={12, 2},
    )

    assert stats["geo_score_daily"] == 2
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
    assert geo.total_queries == 1
    assert geo.mention_count == 1
    assert geo.avg_sov == pytest.approx(0.5)
    assert geo.citation_rate == pytest.approx(1.0)
    assert geo.avg_geo_score is not None
