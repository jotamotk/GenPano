from __future__ import annotations

import sys
import types
from collections.abc import AsyncGenerator
from datetime import datetime
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select
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
            ]
        }
    )

    assert [brand.position_type for brand in result.brands] == [
        "first_recommendation",
        "listed",
        "mentioned_only",
        "mentioned_only",
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
