from __future__ import annotations

import sys
import types
from collections.abc import AsyncGenerator
from datetime import datetime
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


class _FakeAsyncOpenAI:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass


openai = types.ModuleType("openai")
openai.AsyncOpenAI = _FakeAsyncOpenAI
sys.modules.setdefault("openai", openai)

import geo_tracker.analyzer.cli as analyzer_cli  # noqa: E402
from geo_tracker.analyzer.llm_analyzer import LLMAnalyzer  # noqa: E402
from geo_tracker.db.models import (  # noqa: E402
    AnalysisStatus,
    Base,
    Brand,
    BrandMention,
    LLMResponse,
    Query,
    QueryStatus,
    ResponseAnalysis,
    SentimentDriver,
)


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as db:
        yield db
    await engine.dispose()


def test_parser_normalizes_multilabel_position_types_to_canonical_values() -> None:
    analyzer = object.__new__(LLMAnalyzer)

    result = analyzer._parse_result(
        {
            "brands": [
                {
                    "brand_name": "A",
                    "position_type": "first_recommendation,comparison_winner",
                },
                {
                    "brand_name": "B",
                    "position_type": "comparison_loser|listed",
                },
                {
                    "brand_name": "C",
                    "position_type": "unexpected_position",
                },
                {
                    "brand_name": "D",
                    "position_type": "",
                },
                {
                    "brand_name": "E",
                    "position_type": "comparison_loser/listed",
                },
                {
                    "brand_name": "F",
                    "position_type": "comparison_loser;comparison_winner",
                },
                {
                    "brand_name": "G",
                    "position_type": "comparison_loser listed",
                },
            ]
        }
    )

    assert [brand.position_type for brand in result.brands] == [
        "first_recommendation",
        "listed",
        "mentioned_only",
        "mentioned_only",
        "listed",
        "comparison_winner",
        "listed",
    ]
    assert all(len(brand.position_type) <= 32 for brand in result.brands)


class AnalyzerWithMultilabelPosition:
    model = "fake-issue-660"

    async def analyze(self, **_kwargs):
        return SimpleNamespace(
            brands=[
                SimpleNamespace(
                    brand_name="Estee Lauder",
                    product_name=None,
                    position_type="first_recommendation,comparison_winner",
                    position_rank=1,
                    detail_level="detailed",
                    sentiment="positive",
                    sentiment_score=0.8,
                    sentiment_drivers=[],
                    product_features=[],
                )
            ],
            dimension=SimpleNamespace(
                industry="beauty",
                company="",
                product="serum",
                category="skincare",
            ),
            raw_json={"source": "fake-issue-660"},
        )


class AnalyzerWithFreshDriver:
    model = "fake-issue-666"

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
                    sentiment_score=0.7,
                    sentiment_drivers=[
                        SimpleNamespace(
                            driver_text="fresh reanalysis driver",
                            polarity="positive",
                            category="brand_image",
                            strength=0.8,
                            source_quote="Estee Lauder is recommended.",
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
            raw_json={"source": "fake-issue-666"},
        )


@pytest.mark.asyncio
async def test_analyzer_persists_and_scores_canonical_position_type(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brand = Brand(id=12, name="Estee Lauder", aliases=["Estee Lauder"])
    response = LLMResponse(
        id=360,
        query_id=66001,
        raw_text="Estee Lauder is the first recommendation for anti-aging serum.",
        citations_json=[],
        collected_at=datetime(2026, 5, 12, 12, 0),
        analysis_status=AnalysisStatus.PENDING.value,
    )
    session.add_all(
        [
            brand,
            Query(
                id=66001,
                brand_id=brand.id,
                query_text="Which anti-aging serum should I buy?",
                target_llm="deepseek",
                status=QueryStatus.DONE.value,
            ),
            response,
        ]
    )
    await session.commit()

    monkeypatch.setattr(analyzer_cli, "LLMAnalyzer", AnalyzerWithMultilabelPosition)

    result = await analyzer_cli.analyze_single_response(
        session,
        response,
        brand,
        [],
        "commercial",
    )

    assert result["status"] == "done"
    mention = (
        await session.execute(select(BrandMention).where(BrandMention.response_id == 360))
    ).scalar_one()
    analysis = (
        await session.execute(select(ResponseAnalysis).where(ResponseAnalysis.response_id == 360))
    ).scalar_one()

    assert mention.position_type == "first_recommendation"
    assert analysis.target_brand_position == "first_recommendation"
    assert analysis.visibility_score == 100.0
    assert analysis.raw_analysis_json["brand_mention_facts"][0]["position_type"] == (
        "first_recommendation"
    )


@pytest.mark.asyncio
async def test_reanalysis_deletes_old_sentiment_drivers_before_old_mentions(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brand = Brand(id=13, name="Estee Lauder", aliases=["Estee Lauder"])
    response = LLMResponse(
        id=359,
        query_id=66601,
        raw_text="Estee Lauder is recommended for anti-aging serum.",
        citations_json=[],
        collected_at=datetime(2026, 5, 12, 12, 0),
        analysis_status=AnalysisStatus.DONE.value,
    )
    session.add_all(
        [
            brand,
            Query(
                id=66601,
                brand_id=brand.id,
                query_text="Which anti-aging serum should I buy?",
                target_llm="deepseek",
                status=QueryStatus.DONE.value,
            ),
            response,
        ]
    )
    await session.flush()

    old_mention = BrandMention(
        id=100,
        response_id=response.id,
        brand_id=brand.id,
        brand_name=brand.name,
        is_target=True,
        position_type="listed",
        position_rank=2,
        detail_level="brief",
        sentiment="negative",
        sentiment_score=-0.5,
        mention_count=1,
    )
    session.add(old_mention)
    await session.flush()
    old_mention_id = old_mention.id
    session.add(
        SentimentDriver(
            mention_id=old_mention_id,
            response_id=response.id,
            brand_name=brand.name,
            driver_text="stale driver from previous failed apply",
            polarity="negative",
            category="old_analysis",
            strength=0.4,
            source_quote="stale quote",
        )
    )
    await session.commit()

    monkeypatch.setattr(analyzer_cli, "LLMAnalyzer", AnalyzerWithFreshDriver)

    result = await analyzer_cli.analyze_single_response(
        session,
        response,
        brand,
        [],
        "commercial",
    )

    assert result["status"] == "done"
    mentions = (
        (await session.execute(select(BrandMention).where(BrandMention.response_id == 359)))
        .scalars()
        .all()
    )
    drivers = (
        (
            await session.execute(
                select(SentimentDriver).where(SentimentDriver.response_id == 359)
            )
        )
        .scalars()
        .all()
    )

    assert [mention.id for mention in mentions] != [old_mention_id]
    assert [driver.driver_text for driver in drivers] == ["fresh reanalysis driver"]
    assert all(driver.mention_id != old_mention_id for driver in drivers)
