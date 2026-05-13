from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import geo_tracker.analyzer.cli as analyzer_cli
from geo_tracker.analyzer.aggregator import Aggregator
from geo_tracker.db.models import (
    AnalysisStatus,
    Base,
    Brand,
    BrandMention,
    CitationSource,
    GEOScoreDaily,
    LLMResponse,
    ProductScoreDaily,
    Prompt,
    Query,
    QueryStatus,
    ResponseAnalysis,
    SentimentDriver,
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


class FakeLLMAnalyzer:
    model = "fake-no-fallback"

    async def analyze(self, **_kwargs):
        return SimpleNamespace(
            brands=[
                SimpleNamespace(
                    brand_name="Estee Lauder",
                    product_name=None,
                    position_type="listed",
                    position_rank=2,
                    detail_level="brief",
                    sentiment="positive",
                    sentiment_score=0.6,
                    sentiment_drivers=[
                        SimpleNamespace(
                            driver_text="strong serum reputation",
                            polarity="positive",
                            category="brand_image",
                            strength=0.8,
                            source_quote="Estee Lauder is praised for serum authority.",
                        )
                    ],
                    product_features=[],
                ),
                SimpleNamespace(
                    brand_name="Clinique",
                    product_name="Moisture Surge",
                    position_type="comparison_winner",
                    position_rank=1,
                    detail_level="detailed",
                    sentiment="negative",
                    sentiment_score=-0.4,
                    sentiment_drivers=[
                        SimpleNamespace(
                            driver_text="sticky finish",
                            polarity="negative",
                            category="product_feature",
                            strength=0.7,
                            source_quote="Clinique Moisture Surge can feel sticky.",
                        )
                    ],
                    product_features=[],
                ),
            ],
            dimension=SimpleNamespace(
                industry="beauty",
                company="",
                product="serum",
                category="skincare",
            ),
            raw_json={"source": "fake-llm"},
        )


class AliasLLMAnalyzer:
    model = "fake-alias"

    async def analyze(self, **_kwargs):
        return SimpleNamespace(
            brands=[
                SimpleNamespace(
                    brand_name="Estee Lauder",
                    product_name=None,
                    position_type="listed",
                    position_rank=1,
                    detail_level="detailed",
                    sentiment="positive",
                    sentiment_score=0.8,
                    sentiment_drivers=[
                        SimpleNamespace(
                            driver_text="strong repair serum evidence",
                            polarity="positive",
                            category="brand_image",
                            strength=0.9,
                            source_quote="Estee Lauder is praised for repair serum authority.",
                        )
                    ],
                    product_features=[],
                )
            ],
            dimension=SimpleNamespace(
                industry="beauty",
                company="",
                product="serum",
                category="skincare",
            ),
            raw_json={"source": "fake-alias"},
        )


class CitationAliasLLMAnalyzer:
    model = "fake-citation-alias"

    async def analyze(self, **_kwargs):
        return SimpleNamespace(
            brands=[
                SimpleNamespace(
                    brand_name="雅诗兰黛",
                    product_name=None,
                    position_type="listed",
                    position_rank=1,
                    detail_level="detailed",
                    sentiment="positive",
                    sentiment_score=0.8,
                    sentiment_drivers=[
                        SimpleNamespace(
                            driver_text="repair serum authority",
                            polarity="positive",
                            category="brand_image",
                            strength=0.9,
                            source_quote="Estee Lauder has strong repair serum authority.",
                        )
                    ],
                    product_features=[],
                )
            ],
            dimension=SimpleNamespace(
                industry="beauty",
                company="",
                product="serum",
                category="skincare",
            ),
            raw_json={"source": "fake-citation-alias"},
        )


class DuplicateCanonicalLLMAnalyzer:
    model = "fake-duplicate-canonical"

    async def analyze(self, **_kwargs):
        return SimpleNamespace(
            brands=[
                SimpleNamespace(
                    brand_name="ONLYOFFICE",
                    product_name="DocSpace",
                    position_type="listed",
                    position_rank=4,
                    detail_level="brief",
                    sentiment="positive",
                    sentiment_score=0.6,
                    sentiment_drivers=[
                        SimpleNamespace(
                            driver_text="low-cost collaboration",
                            polarity="positive",
                            category="pricing",
                            strength=0.7,
                            source_quote="ONLYOFFICE DocSpace is low cost.",
                        )
                    ],
                    product_features=[],
                ),
                SimpleNamespace(
                    brand_name="ONLYOFFICE ",
                    product_name="DocSpace",
                    position_type="listed",
                    position_rank=4,
                    detail_level="brief",
                    sentiment="positive",
                    sentiment_score=0.6,
                    sentiment_drivers=[
                        SimpleNamespace(
                            driver_text="team editing",
                            polarity="positive",
                            category="product_feature",
                            strength=0.6,
                            source_quote="ONLYOFFICE DocSpace supports team editing.",
                        )
                    ],
                    product_features=[],
                ),
            ],
            dimension=SimpleNamespace(
                industry="enterprise SaaS",
                company="",
                product="collaboration",
                category="document workspace",
            ),
            raw_json={"source": "fake-duplicate-canonical"},
        )


async def _seed_response(
    session: AsyncSession,
    *,
    response_id: int = 300,
    brand_id: int = 12,
    raw_text: str = (
        "Estee Lauder Advanced Night Repair is visible, while Clinique "
        "Moisture Surge can feel sticky in comparison."
    ),
    citations_json: list[dict] | None = None,
    prompt_id: int | None = 30,
    topic_id: int | None = 20,
    minutes: int = 0,
) -> tuple[datetime, Brand, LLMResponse]:
    day = datetime(2026, 5, 12, 10, 30) + timedelta(minutes=minutes)
    brand = Brand(
        id=brand_id,
        name="Estee Lauder",
        website="https://www.esteelauder.com",
        aliases=["EL"],
        industry="beauty",
    )
    session.add(brand)
    await session.flush()

    if topic_id is not None:
        session.add(Topic(id=topic_id, brand_id=brand_id, text="skincare", category="category"))
        await session.flush()
    if prompt_id is not None:
        session.add(
            Prompt(
                id=prompt_id,
                topic_id=topic_id,
                text="best hydrating skincare",
                intent="non_brand",
                language="en",
            )
        )
        await session.flush()

    query = Query(
        id=response_id + 1000,
        prompt_id=prompt_id,
        brand_id=brand_id,
        query_text="best hydrating skincare",
        target_llm="doubao",
        status=QueryStatus.DONE.value,
        created_at=day,
    )
    response = LLMResponse(
        id=response_id,
        query_id=query.id,
        raw_text=raw_text,
        citations_json=(
            citations_json
            if citations_json is not None
            else [
                {
                    "url": "https://reviews.example/clinique-moisture",
                    "title": "Clinique Moisture Surge review",
                    "index": 1,
                }
            ]
        ),
        response_time_ms=900,
        collected_at=day,
        analysis_status=AnalysisStatus.PENDING.value,
    )
    session.add_all([query, response])
    await session.commit()
    return day, brand, response


@pytest.mark.asyncio
async def test_analyzer_deduplicates_llm_only_mentions_after_canonicalization(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _day, brand, response = await _seed_response(
        session,
        brand_id=24,
        raw_text=(
            "ONLYOFFICE DocSpace is low cost. "
            "ONLYOFFICE DocSpace supports team editing."
        ),
        citations_json=[],
    )
    brand.name = "bestCoffer"
    session.add(
        Brand(
            id=88,
            name="ONLYOFFICE",
            aliases=["ONLYOFFICE "],
            industry="enterprise SaaS",
        )
    )
    await session.commit()
    monkeypatch.setattr(analyzer_cli, "LLMAnalyzer", DuplicateCanonicalLLMAnalyzer)

    result = await analyzer_cli.analyze_single_response(
        session,
        response,
        brand,
        competitors=[],
        intent="non_brand",
    )

    assert result["status"] == "done"
    mentions = (
        await session.execute(
            select(BrandMention).where(
                BrandMention.response_id == response.id,
                BrandMention.brand_name == "ONLYOFFICE",
                BrandMention.product_name == "DocSpace",
            )
        )
    ).scalars().all()
    assert len(mentions) == 1
    assert mentions[0].mention_count == 4

    drivers = (
        await session.execute(
            select(SentimentDriver).where(SentimentDriver.mention_id == mentions[0].id)
        )
    ).scalars().all()
    assert {driver.driver_text for driver in drivers} == {
        "low-cost collaboration",
        "team editing",
    }


@pytest.mark.asyncio
async def test_analyzer_merges_alias_llm_result_into_rule_detected_canonical_mention(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _day, brand, response = await _seed_response(
        session,
        brand_id=12,
        raw_text="Estee Lauder is repeatedly recommended for repair serum.",
        citations_json=[],
    )
    brand.name = "雅诗兰黛"
    brand.aliases = ["Estee Lauder", "EL"]
    await session.commit()
    monkeypatch.setattr(analyzer_cli, "LLMAnalyzer", AliasLLMAnalyzer)

    result = await analyzer_cli.analyze_single_response(
        session,
        response,
        brand,
        competitors=[],
        intent="non_brand",
    )

    assert result["status"] == "done"
    mentions = (
        await session.execute(
            select(BrandMention).where(BrandMention.response_id == response.id)
        )
    ).scalars().all()
    assert len(mentions) == 1
    mention = mentions[0]
    assert mention.brand_id == 12
    assert mention.brand_name == "雅诗兰黛"
    assert mention.is_target is True
    assert mention.sentiment == "positive"
    assert mention.sentiment_score == pytest.approx(0.8)

    analysis = (
        await session.execute(
            select(ResponseAnalysis).where(ResponseAnalysis.response_id == response.id)
        )
    ).scalar_one()
    facts = analysis.raw_analysis_json["brand_mention_facts"]
    assert len(facts) == 1
    assert facts[0]["provenance"] == "detector_llm"
    assert facts[0]["raw_brand_name"] == "Estee Lauder"


@pytest.mark.asyncio
async def test_analyzer_persists_llm_only_brand_sentiment_provenance_and_citation_attribution(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _day, brand, response = await _seed_response(session)
    monkeypatch.setattr(analyzer_cli, "LLMAnalyzer", FakeLLMAnalyzer)

    result = await analyzer_cli.analyze_single_response(
        session,
        response,
        brand,
        competitors=[],
        intent="non_brand",
    )

    assert result["status"] == "done"

    clinique = (
        await session.execute(
            select(BrandMention).where(
                BrandMention.response_id == response.id,
                BrandMention.brand_name == "Clinique",
            )
        )
    ).scalar_one()
    assert clinique.brand_id is None
    assert clinique.is_target is False
    assert clinique.product_name == "Moisture Surge"
    assert clinique.position_rank == 1
    assert clinique.sentiment == "negative"
    assert clinique.sentiment_score == pytest.approx(-0.4)
    assert "Clinique" in (clinique.context_snippet or "")

    driver = (
        await session.execute(
            select(SentimentDriver).where(SentimentDriver.mention_id == clinique.id)
        )
    ).scalar_one()
    assert driver.source_quote == "Clinique Moisture Surge can feel sticky."

    citation = (
        await session.execute(
            select(CitationSource).where(CitationSource.response_id == response.id)
        )
    ).scalar_one()
    assert citation.mention_id == clinique.id
    assert citation.domain == "reviews.example"

    analysis = (
        await session.execute(
            select(ResponseAnalysis).where(ResponseAnalysis.response_id == response.id)
        )
    ).scalar_one()
    facts = analysis.raw_analysis_json["brand_mention_facts"]
    clinique_fact = next(fact for fact in facts if fact["mention_id"] == clinique.id)
    assert clinique_fact["provenance"] == "llm_extraction"
    assert clinique_fact["canonical_brand_id"] is None
    assert clinique_fact["query_id"] == response.query_id
    assert clinique_fact["prompt_id"] == 30
    assert clinique_fact["topic_id"] == 20
    assert "Clinique" in clinique_fact["evidence_snippet"]
    assert analysis.raw_analysis_json["metric_input_status"]["sov"]["state"] == "ok"


@pytest.mark.asyncio
async def test_analyzer_attributes_citation_by_alias_to_canonical_persisted_mention(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _day, brand, response = await _seed_response(
        session,
        raw_text="Estee Lauder has strong repair serum authority.",
        citations_json=[
            {
                "url": "https://reviews.example/estee-repair",
                "title": "雅诗兰黛 小棕瓶 review",
                "index": 1,
            }
        ],
    )
    brand.name = "Estee Lauder"
    brand.aliases = ["雅诗兰黛", "EL"]
    await session.commit()
    monkeypatch.setattr(analyzer_cli, "LLMAnalyzer", CitationAliasLLMAnalyzer)

    result = await analyzer_cli.analyze_single_response(
        session,
        response,
        brand,
        competitors=[],
        intent="non_brand",
    )

    assert result["status"] == "done"
    mention = (
        await session.execute(
            select(BrandMention).where(BrandMention.response_id == response.id)
        )
    ).scalar_one()
    assert mention.brand_name == "Estee Lauder"
    assert mention.brand_id == 12

    citation = (
        await session.execute(
            select(CitationSource).where(CitationSource.response_id == response.id)
        )
    ).scalar_one()
    assert citation.mention_id == mention.id

    analysis = (
        await session.execute(
            select(ResponseAnalysis).where(ResponseAnalysis.response_id == response.id)
        )
    ).scalar_one()
    citation_status = analysis.raw_analysis_json["metric_input_status"]["citation"]
    assert citation_status["state"] == "ok"
    assert citation_status["missing_inputs"] == []
    assert citation_status["attributed_citation_count"] == 1


@pytest.mark.asyncio
async def test_analyzer_marks_citation_status_partial_when_mappings_are_unattributed(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _day, brand, response = await _seed_response(
        session,
        citations_json=[
            {
                "url": "https://research.example/skincare",
                "title": "Hydration study with no brand title",
                "index": 1,
            }
        ],
    )
    monkeypatch.setattr(analyzer_cli, "LLMAnalyzer", FakeLLMAnalyzer)

    result = await analyzer_cli.analyze_single_response(
        session,
        response,
        brand,
        competitors=[],
        intent="non_brand",
    )

    assert result["status"] == "done"
    citation = (
        await session.execute(
            select(CitationSource).where(CitationSource.response_id == response.id)
        )
    ).scalar_one()
    assert citation.mention_id is None

    analysis = (
        await session.execute(
            select(ResponseAnalysis).where(ResponseAnalysis.response_id == response.id)
        )
    ).scalar_one()
    citation_status = analysis.raw_analysis_json["metric_input_status"]["citation"]
    assert citation_status["state"] == "partial"
    assert "citation_sources.mention_id" in citation_status["missing_inputs"]
    assert citation_status["citation_count"] == 1
    assert citation_status["attributed_citation_count"] == 0


@pytest.mark.asyncio
async def test_aggregator_does_not_emit_target_only_sov_when_competitors_are_missing(
    session: AsyncSession,
) -> None:
    day, _brand, response = await _seed_response(
        session,
        response_id=320,
        citations_json=[],
        raw_text="Estee Lauder is the only brand extracted.",
    )
    response.analysis_status = AnalysisStatus.DONE.value
    session.add_all(
        [
            ResponseAnalysis(
                response_id=response.id,
                dimension_industry="beauty",
                target_brand_mentioned=True,
                raw_analysis_json={"source": "test"},
            ),
            BrandMention(
                response_id=response.id,
                brand_id=12,
                brand_name="Estee Lauder",
                is_target=True,
                position_type="mentioned_only",
                sentiment="positive",
                sentiment_score=0.7,
                mention_count=1,
            ),
        ]
    )
    await session.commit()

    await Aggregator(session).aggregate_daily(day, brand_id=12, competitive_brand_ids={12, 77})

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
    assert geo.mention_rate == pytest.approx(1.0)
    assert geo.avg_sov is None
    assert geo.avg_sov_score is None
    assert geo.avg_geo_score is None


@pytest.mark.asyncio
async def test_aggregator_surfaces_missing_citation_and_sentiment_inputs_as_null_components(
    session: AsyncSession,
) -> None:
    day, _brand, response = await _seed_response(
        session,
        response_id=330,
        citations_json=[],
        raw_text="Estee Lauder is mentioned without citation or sentiment evidence.",
    )
    response.analysis_status = AnalysisStatus.DONE.value
    session.add_all(
        [
            ResponseAnalysis(
                response_id=response.id,
                dimension_industry="beauty",
                target_brand_mentioned=True,
                raw_analysis_json={"source": "test"},
            ),
            BrandMention(
                response_id=response.id,
                brand_id=12,
                brand_name="Estee Lauder",
                is_target=True,
                position_type="listed",
                position_rank=2,
                sentiment=None,
                sentiment_score=None,
                mention_count=1,
            ),
            BrandMention(
                response_id=response.id,
                brand_id=77,
                brand_name="Lancome",
                is_target=False,
                position_type="mentioned_only",
                sentiment="neutral",
                sentiment_score=0.0,
                mention_count=1,
            ),
        ]
    )
    await session.commit()

    await Aggregator(session).aggregate_daily(day, brand_id=12, competitive_brand_ids={12, 77})

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
    assert geo.citation_rate is None
    assert geo.avg_citation_score is None
    assert geo.avg_sentiment_score is None
    assert geo.avg_sentiment is None
    assert geo.avg_geo_score is None


@pytest.mark.asyncio
async def test_aggregator_uses_target_mention_citation_attribution_not_response_level_citation(
    session: AsyncSession,
) -> None:
    day, _brand, response = await _seed_response(
        session,
        response_id=335,
        citations_json=[],
        raw_text="Estee Lauder and Lancome are both mentioned, but only Lancome is cited.",
    )
    response.analysis_status = AnalysisStatus.DONE.value
    session.add(
        ResponseAnalysis(
            response_id=response.id,
            dimension_industry="beauty",
            target_brand_mentioned=True,
            raw_analysis_json={"source": "test"},
        )
    )
    target = BrandMention(
        response_id=response.id,
        brand_id=12,
        brand_name="Estee Lauder",
        is_target=True,
        position_type="listed",
        position_rank=1,
        sentiment="positive",
        sentiment_score=0.7,
        mention_count=1,
    )
    competitor = BrandMention(
        response_id=response.id,
        brand_id=77,
        brand_name="Lancome",
        is_target=False,
        position_type="mentioned_only",
        sentiment="neutral",
        sentiment_score=0.0,
        mention_count=1,
    )
    session.add_all([target, competitor])
    await session.flush()
    session.add(
        CitationSource(
            response_id=response.id,
            mention_id=competitor.id,
            url="https://example.com/lancome-review",
            domain="example.com",
            title="Lancome review",
            citation_index=1,
            source_type="review_site",
        )
    )
    await session.commit()

    await Aggregator(session).aggregate_daily(day, brand_id=12, competitive_brand_ids={12, 77})

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
    assert geo.citation_rate is None
    assert geo.avg_citation_score is None
    assert geo.avg_geo_score is None


@pytest.mark.asyncio
async def test_aggregator_does_not_use_cross_owner_mentions_as_missing_denominator_fallback(
    session: AsyncSession,
) -> None:
    day, owner_brand, response = await _seed_response(
        session,
        response_id=338,
        brand_id=77,
        prompt_id=None,
        topic_id=None,
        citations_json=[],
        raw_text="A cross-owner response mentions Estee Lauder without default prompt evidence.",
    )
    owner_brand.name = "Source Owner"
    response.analysis_status = AnalysisStatus.DONE.value
    session.add_all(
        [
            Brand(id=12, name="Estee Lauder", aliases=["EL"], industry="beauty"),
            ResponseAnalysis(
                response_id=response.id,
                dimension_industry="beauty",
                target_brand_mentioned=True,
                raw_analysis_json={"source": "test"},
            ),
            BrandMention(
                response_id=response.id,
                brand_id=12,
                brand_name="Estee Lauder",
                is_target=False,
                position_type="mentioned_only",
                sentiment="neutral",
                sentiment_score=0.0,
                mention_count=1,
            ),
        ]
    )
    await session.commit()

    stats = await Aggregator(session).aggregate_daily(day, brand_id=12)

    assert stats["geo_score_daily"] == 0
    geo_rows = (await session.execute(select(GEOScoreDaily))).scalars().all()
    assert geo_rows == []


@pytest.mark.asyncio
async def test_product_aggregation_preserves_missing_sentiment_and_comparison_as_null(
    session: AsyncSession,
) -> None:
    day, _brand, response = await _seed_response(
        session,
        response_id=339,
        citations_json=[],
        raw_text="Estee Lauder Advanced Night Repair is mentioned without evidence details.",
    )
    response.analysis_status = AnalysisStatus.DONE.value
    session.add_all(
        [
            ResponseAnalysis(
                response_id=response.id,
                dimension_industry="beauty",
                target_brand_mentioned=True,
                raw_analysis_json={"source": "test"},
            ),
            BrandMention(
                response_id=response.id,
                brand_id=12,
                brand_name="Estee Lauder",
                product_name="Advanced Night Repair",
                is_target=True,
                position_type="mentioned_only",
                sentiment=None,
                sentiment_score=None,
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
    assert product.avg_sentiment_score is None
    assert product.comparison_total == 0
    assert product.win_rate is None


@pytest.mark.asyncio
async def test_aggregator_does_not_fabricate_topic_rows_without_prompt_topic_links(
    session: AsyncSession,
) -> None:
    day, _brand, response = await _seed_response(
        session,
        response_id=340,
        prompt_id=None,
        topic_id=None,
        citations_json=[],
        raw_text="Estee Lauder appears in a response whose query has no prompt link.",
    )
    response.analysis_status = AnalysisStatus.DONE.value
    session.add_all(
        [
            ResponseAnalysis(
                response_id=response.id,
                dimension_industry="beauty",
                target_brand_mentioned=True,
                raw_analysis_json={"source": "test"},
            ),
            BrandMention(
                response_id=response.id,
                brand_id=12,
                brand_name="Estee Lauder",
                is_target=True,
                position_type="mentioned_only",
                sentiment="neutral",
                sentiment_score=0.0,
                mention_count=1,
            ),
        ]
    )
    await session.commit()

    stats = await Aggregator(session).aggregate_daily(day, brand_id=12)

    assert stats["topic_score"] == 0
    topic_rows = (await session.execute(select(TopicScoreDaily))).scalars().all()
    assert topic_rows == []
