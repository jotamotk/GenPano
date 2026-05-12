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
    Competitor,
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


async def _add_response(
    session: AsyncSession,
    *,
    query_id: int,
    response_id: int,
    prompt_id: int,
    brand_id: int,
    raw_text: str,
    intent: str = "non_brand",
    topic_category: str = "品类",
    minutes: int = 0,
) -> datetime:
    day = datetime(2026, 5, 10, 10, 30) + timedelta(minutes=minutes)
    topic = Topic(
        id=2000 + query_id,
        brand_id=brand_id,
        text=f"topic-{query_id}",
        category=topic_category,
    )
    prompt = Prompt(
        id=prompt_id,
        topic_id=topic.id,
        text=f"prompt-{query_id}",
        intent=intent,
        language="zh",
    )
    query = Query(
        id=query_id,
        prompt_id=prompt_id,
        brand_id=brand_id,
        query_text=f"query-{query_id}",
        target_llm="doubao",
        status=QueryStatus.DONE.value,
        created_at=day,
    )
    response = LLMResponse(
        id=response_id,
        query_id=query_id,
        raw_text=raw_text,
        citations_json=[],
        response_time_ms=1000,
        collected_at=day,
        analysis_status=AnalysisStatus.DONE.value,
    )
    analysis = ResponseAnalysis(
        response_id=response_id,
        dimension_industry="beauty",
        dimension_category=topic_category,
        target_brand_mentioned=False,
        total_brands_mentioned=0,
        raw_analysis_json={"source": "owner-brand-analysis"},
    )
    session.add_all([topic, prompt, query, response, analysis])
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
async def test_repair_does_not_mark_preexisting_canonical_mentions_for_rollback(
    session: AsyncSession,
):
    day = await _seed_cross_brand_fixture(session)
    session.add(
        BrandMention(
            response_id=200,
            brand_id=12,
            brand_name="雅诗兰黛",
            is_target=False,
            position_type="mentioned_only",
            sentiment="neutral",
            sentiment_score=0.0,
            mention_count=1,
        )
    )
    await session.commit()

    stats = await repair_canonical_brand_mentions(
        session,
        brand_id=12,
        start_at=day.replace(hour=0, minute=0, second=0),
        end_at=day.replace(hour=23, minute=59, second=59),
        source_brand_id=2,
        dry_run=False,
    )

    assert stats["mentions_existing"] == 1
    assert stats["mentions_inserted"] == 0
    analysis = (
        await session.execute(
            select(ResponseAnalysis).where(ResponseAnalysis.response_id == 200)
        )
    ).scalar_one()
    assert "canonical_alias_repairs" not in (analysis.raw_analysis_json or {})


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
    analysis = (
        await session.execute(
            select(ResponseAnalysis).where(ResponseAnalysis.response_id == 200)
        )
    ).scalar_one()
    marker = analysis.raw_analysis_json["canonical_alias_repairs"][0]
    assert marker["source"] == "canonical_alias_repair_v1"
    assert marker["inserted_by_repair"] is True
    assert marker["inserted_mention_id"] == mention.id

    owner_query = await session.get(Query, 100)
    assert owner_query is not None
    assert owner_query.brand_id == 2


@pytest.mark.asyncio
async def test_repair_extracts_owner_competitor_denominator_for_estee_path(
    session: AsyncSession,
):
    day = datetime(2026, 5, 12, 9, 30)
    session.add_all(
        [
            Brand(id=2, name="La Roche-Posay", aliases=["LRP"], industry="beauty"),
            Brand(id=12, name="Estee Lauder", aliases=["EL"], industry="beauty"),
        ]
    )
    await session.flush()
    session.add(Topic(id=120, brand_id=2, text="skincare", category="category"))
    await session.flush()
    session.add(
        Prompt(
            id=130,
            topic_id=120,
            text="best barrier repair serums",
            intent="non_brand",
            language="en",
        )
    )
    session.add(
        Query(
            id=140,
            prompt_id=130,
            brand_id=2,
            query_text="best barrier repair serums",
            target_llm="doubao",
            status=QueryStatus.DONE.value,
            created_at=day,
        )
    )
    session.add(
        LLMResponse(
            id=150,
            query_id=140,
            raw_text=(
                "Estee Lauder Advanced Night Repair is compared with "
                "La Roche-Posay Cicaplast in the same answer."
            ),
            citations_json=[],
            response_time_ms=1000,
            collected_at=day,
            analysis_status=AnalysisStatus.DONE.value,
        )
    )
    session.add(
        ResponseAnalysis(
            response_id=150,
            dimension_industry="beauty",
            dimension_category="category",
            target_brand_mentioned=False,
            total_brands_mentioned=0,
            raw_analysis_json={"source": "owner-brand-analysis"},
        )
    )
    await session.commit()

    stats = await repair_canonical_brand_mentions(
        session,
        brand_id=12,
        start_at=day.replace(hour=0, minute=0, second=0),
        end_at=day.replace(hour=23, minute=59, second=59),
        source_brand_id=2,
        competitive_brand_ids={2},
        dry_run=False,
    )

    assert stats["mentions_inserted"] == 1
    assert stats["competitive_mentions_inserted"] == 1
    mentions = (
        await session.execute(
            select(BrandMention).where(BrandMention.response_id == 150)
        )
    ).scalars().all()
    assert {(m.brand_id, m.brand_name) for m in mentions} == {
        (12, "Estee Lauder"),
        (2, "La Roche-Posay"),
    }
    assert all(m.sentiment_score is None for m in mentions)

    analysis = (
        await session.execute(
            select(ResponseAnalysis).where(ResponseAnalysis.response_id == 150)
        )
    ).scalar_one()
    sov_status = analysis.raw_analysis_json["metric_input_status"]["sov"]
    assert sov_status["state"] == "ok"
    assert sov_status["competitive_mentions"] == 2
    assert sov_status["non_target_competitive_mentions"] == 1

    await Aggregator(session).aggregate_daily(
        day,
        brand_id=12,
        competitive_brand_ids={12, 2},
    )
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
    assert geo.avg_sov == pytest.approx(0.5)
    assert geo.avg_sentiment_score is None
    assert geo.avg_geo_score is None


@pytest.mark.asyncio
async def test_repair_extracts_name_only_configured_competitor_without_brand_id(
    session: AsyncSession,
):
    day = datetime(2026, 5, 12, 9, 45)
    session.add_all(
        [
            Brand(id=2, name="Source Owner", aliases=[], industry="beauty"),
            Brand(id=12, name="Estee Lauder", aliases=["EL"], industry="beauty"),
            Competitor(
                brand_id=12,
                name="Clinique",
                aliases=["CLQ"],
                source="manual",
            ),
        ]
    )
    await session.flush()
    session.add(Topic(id=122, brand_id=2, text="skincare", category="category"))
    await session.flush()
    session.add(
        Prompt(
            id=132,
            topic_id=122,
            text="best hydrating products",
            intent="non_brand",
            language="en",
        )
    )
    session.add(
        Query(
            id=142,
            prompt_id=132,
            brand_id=2,
            query_text="best hydrating products",
            target_llm="doubao",
            status=QueryStatus.DONE.value,
            created_at=day,
        )
    )
    session.add(
        LLMResponse(
            id=152,
            query_id=142,
            raw_text="Estee Lauder is compared with Clinique.",
            citations_json=[],
            response_time_ms=1000,
            collected_at=day,
            analysis_status=AnalysisStatus.DONE.value,
        )
    )
    await session.commit()

    stats = await repair_canonical_brand_mentions(
        session,
        brand_id=12,
        start_at=day.replace(hour=0, minute=0, second=0),
        end_at=day.replace(hour=23, minute=59, second=59),
        source_brand_id=2,
        dry_run=False,
    )

    assert stats["competitive_mentions_inserted"] == 1
    clinique = (
        await session.execute(
            select(BrandMention).where(
                BrandMention.response_id == 152,
                BrandMention.brand_name == "Clinique",
            )
        )
    ).scalar_one()
    assert clinique.brand_id is None
    assert clinique.mention_count == 1

    await Aggregator(session).aggregate_daily(day, brand_id=12, competitive_brand_ids={12})
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
    assert geo.avg_sov == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_repair_records_machine_readable_missing_sources_for_partial_metrics(
    session: AsyncSession,
):
    day = datetime(2026, 5, 12, 10, 30)
    session.add_all(
        [
            Brand(id=2, name="Source Owner", aliases=[], industry="beauty"),
            Brand(id=12, name="Estee Lauder", aliases=["EL"], industry="beauty"),
        ]
    )
    await session.flush()
    session.add(Topic(id=121, brand_id=2, text="skincare", category="category"))
    await session.flush()
    session.add(
        Prompt(
            id=131,
            topic_id=121,
            text="best repair serum",
            intent="non_brand",
            language="en",
        )
    )
    session.add(
        Query(
            id=141,
            prompt_id=131,
            brand_id=2,
            query_text="best repair serum",
            target_llm="doubao",
            status=QueryStatus.DONE.value,
            created_at=day,
        )
    )
    session.add(
        LLMResponse(
            id=151,
            query_id=141,
            raw_text="Estee Lauder is mentioned, but no LLM position or sentiment is present.",
            citations_json=[
                {
                    "url": "https://research.example/skincare",
                    "title": "General skincare study",
                    "index": 1,
                }
            ],
            response_time_ms=1000,
            collected_at=day,
            analysis_status=AnalysisStatus.DONE.value,
        )
    )
    await session.commit()

    await repair_canonical_brand_mentions(
        session,
        brand_id=12,
        start_at=day.replace(hour=0, minute=0, second=0),
        end_at=day.replace(hour=23, minute=59, second=59),
        source_brand_id=2,
        dry_run=False,
    )

    mention = (
        await session.execute(select(BrandMention).where(BrandMention.response_id == 151))
    ).scalar_one()
    assert mention.sentiment is None
    assert mention.sentiment_score is None

    citation = (
        await session.execute(select(CitationSource).where(CitationSource.response_id == 151))
    ).scalar_one()
    assert citation.mention_id is None

    analysis = (
        await session.execute(
            select(ResponseAnalysis).where(ResponseAnalysis.response_id == 151)
        )
    ).scalar_one()
    assert analysis.sentiment_score is None
    assert analysis.sov_score is None
    assert analysis.citation_score is None
    assert analysis.geo_score is None

    status = analysis.raw_analysis_json["metric_input_status"]
    assert status["canonical_alias_repair"]["state"] == "partial"
    assert "canonical_alias_repair.partial" in status["canonical_alias_repair"]["missing_inputs"]
    assert status["sov"]["state"] == "partial"
    assert "brand_mentions.competitive_set" in status["sov"]["missing_inputs"]
    assert status["sentiment"]["state"] == "partial"
    assert "llm_brand_sentiment" in status["sentiment"]["missing_inputs"]
    assert "sentiment_drivers.source_quote" in status["sentiment"]["missing_inputs"]
    assert status["citation"]["state"] == "partial"
    assert "citation_sources.mention_id" in status["citation"]["missing_inputs"]
    assert status["pano_geo"]["state"] == "partial"
    assert "llm_brand_position" in status["pano_geo"]["missing_inputs"]


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

    stats = await Aggregator(session).aggregate_daily(
        day,
        brand_id=12,
        competitive_brand_ids={12},
    )

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
    assert geo.avg_sov is None
    assert geo.citation_rate == pytest.approx(1.0)
    assert geo.avg_position_rank is None
    assert geo.avg_geo_score is None

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


@pytest.mark.asyncio
async def test_aggregator_uses_prd_denominators_for_mention_rate_and_sov(
    session: AsyncSession,
):
    day = await _seed_cross_brand_fixture(session)
    await _add_response(
        session,
        query_id=102,
        response_id=202,
        prompt_id=32,
        brand_id=2,
        raw_text="兰蔻适合想看竞品的人群。",
        minutes=2,
    )
    await _add_response(
        session,
        query_id=103,
        response_id=203,
        prompt_id=33,
        brand_id=2,
        raw_text="无关品牌也可能被提到。",
        minutes=3,
    )
    await _add_response(
        session,
        query_id=104,
        response_id=204,
        prompt_id=34,
        brand_id=2,
        raw_text="品牌向问题里也出现雅诗兰黛，但不能进入默认提及率。",
        intent="brand",
        topic_category="品牌",
        minutes=4,
    )

    await repair_canonical_brand_mentions(
        session,
        brand_id=12,
        start_at=day.replace(hour=0, minute=0, second=0),
        end_at=day.replace(hour=23, minute=59, second=59),
        source_brand_id=2,
        dry_run=False,
    )
    session.add_all(
        [
            BrandMention(
                response_id=202,
                brand_id=77,
                brand_name="兰蔻",
                is_target=False,
                position_type="mentioned_only",
                sentiment="neutral",
                sentiment_score=0.0,
                mention_count=1,
            ),
            BrandMention(
                response_id=203,
                brand_id=99,
                brand_name="无关品牌",
                is_target=False,
                position_type="mentioned_only",
                sentiment="neutral",
                sentiment_score=0.0,
                mention_count=1,
            ),
        ]
    )
    await session.commit()

    await Aggregator(session).aggregate_daily(
        day,
        brand_id=12,
        competitive_brand_ids={12, 77},
    )

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
    assert geo.total_queries == 4
    assert geo.mention_count == 1
    assert geo.mention_rate == pytest.approx(0.25)
    assert geo.avg_sov == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_aggregator_skips_geo_when_default_denominator_evidence_is_missing(
    session: AsyncSession,
):
    day = await _add_response(
        session,
        query_id=120,
        response_id=220,
        prompt_id=50,
        brand_id=2,
        raw_text="canonical cross-owner fact",
        intent=None,
        topic_category=None,
    )
    await _add_response(
        session,
        query_id=121,
        response_id=221,
        prompt_id=51,
        brand_id=2,
        raw_text="same source owner but no canonical mention",
        intent=None,
        topic_category=None,
        minutes=1,
    )
    session.add_all(
        [
            Brand(id=12, name="canonical brand", aliases=["canonical"], industry="beauty"),
            BrandMention(
                response_id=220,
                brand_id=12,
                brand_name="canonical brand",
                is_target=False,
                position_type="mentioned_only",
                sentiment="neutral",
                sentiment_score=0.0,
                mention_count=1,
            ),
        ]
    )
    await session.commit()

    stats = await Aggregator(session).aggregate_daily(
        day,
        brand_id=12,
        competitive_brand_ids={12, 2},
    )

    assert stats["geo_score_daily"] == 0
    assert stats["topic_score"] == 2

    geo_rows = (
        await session.execute(
            select(GEOScoreDaily).where(GEOScoreDaily.brand_id == 12)
        )
    ).scalars().all()
    assert geo_rows == []

    await Aggregator(session).aggregate_daily(
        day,
        brand_id=12,
        competitive_brand_ids={12, 2},
    )
    rows = (
        await session.execute(
            select(GEOScoreDaily).where(GEOScoreDaily.brand_id == 12)
        )
    ).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_product_aggregation_only_writes_explicit_product_level_mentions(
    session: AsyncSession,
):
    day = await _add_response(
        session,
        query_id=130,
        response_id=230,
        prompt_id=60,
        brand_id=2,
        raw_text="brand-level canonical fact",
    )
    await _add_response(
        session,
        query_id=131,
        response_id=231,
        prompt_id=61,
        brand_id=2,
        raw_text="product-level canonical fact",
        minutes=1,
    )
    session.add_all(
        [
            Brand(id=12, name="canonical brand", aliases=["canonical"], industry="beauty"),
            BrandMention(
                response_id=230,
                brand_id=12,
                brand_name="canonical brand",
                is_target=False,
                position_type="mentioned_only",
                sentiment="neutral",
                sentiment_score=0.0,
                mention_count=1,
            ),
            BrandMention(
                response_id=231,
                brand_id=12,
                brand_name="canonical brand",
                product_name="Advanced Night Repair",
                is_target=False,
                position_type="first_recommendation",
                position_rank=1,
                sentiment="positive",
                sentiment_score=0.8,
                mention_count=1,
            ),
        ]
    )
    await session.commit()

    stats = await Aggregator(session).aggregate_daily(day, brand_id=12)

    assert stats["product_score"] == 1
    product = (
        await session.execute(
            select(ProductScoreDaily).where(ProductScoreDaily.brand_id == 12)
        )
    ).scalar_one()
    assert product.product_name == "Advanced Night Repair"
    assert product.total_queries == 1
    assert product.mention_count == 1
