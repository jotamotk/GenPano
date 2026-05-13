from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from geo_tracker.analyzer import cli as analyzer_cli
from geo_tracker.analyzer.brand_detector import DetectedBrand
from geo_tracker.analyzer.llm_analyzer import (
    BrandAnalysis,
    DimensionResult,
    DriverResult,
    LLMAnalysisResult,
    ProductFeatureResult,
)
from geo_tracker.db.models import (
    AnalysisStatus,
    Base,
    Brand,
    BrandMention,
    CitationSource,
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


async def _seed_response(session: AsyncSession) -> tuple[Brand, LLMResponse]:
    day = datetime(2026, 5, 13, 8, 0)
    target = Brand(id=24, name="BestCoffer", aliases=["Best Coffer"], industry="coffee")
    duplicate_brand = Brand(
        id=88,
        name="ONLYOFFICE",
        aliases=["OnlyOffice", "ONLYOFFICE "],
        industry="collaboration",
    )
    session.add_all(
        [
            target,
            duplicate_brand,
            Topic(id=7431, brand_id=24, text="BestCoffer VDR alternatives", category="category"),
            Prompt(
                id=7432,
                topic_id=7431,
                text="Best VDR options for early-stage teams",
                intent="non_brand",
                language="zh",
            ),
        ]
    )
    await session.flush()
    session.add(
        Query(
            id=7433,
            prompt_id=7432,
            brand_id=24,
            query_text="Best VDR options",
            target_llm="deepseek",
            status=QueryStatus.DONE.value,
            created_at=day,
        )
    )
    await session.flush()
    response = LLMResponse(
        id=550,
        query_id=7433,
        raw_text=(
            "ONLYOFFICE DocSpace is an entry-level collaboration option. "
            "ONLYOFFICE DocSpace also has a free startup plan."
        ),
        citations_json=[],
        collected_at=day,
        analysis_status=AnalysisStatus.RUNNING.value,
    )
    session.add(response)
    await session.commit()
    return target, response


def _duplicate_llm_result() -> LLMAnalysisResult:
    return LLMAnalysisResult(
        brands=[
            BrandAnalysis(
                brand_name="ONLYOFFICE",
                product_name="DocSpace",
                position_type="listed",
                position_rank=4,
                detail_level="brief",
                sentiment="positive",
                sentiment_score=0.6,
                sentiment_drivers=[
                    DriverResult(
                        driver_text="low monthly price",
                        polarity="positive",
                        category="pricing",
                        strength=0.8,
                        source_quote="20 dollars per admin per month",
                    )
                ],
                product_features=[
                    ProductFeatureResult(
                        feature_name="co-editing",
                        feature_sentiment="positive",
                        context_snippet="co-editing evidence",
                    )
                ],
            ),
            BrandAnalysis(
                brand_name="ONLYOFFICE ",
                product_name="DocSpace",
                position_type="listed",
                position_rank=4,
                detail_level="brief",
                sentiment="positive",
                sentiment_score=0.6,
                sentiment_drivers=[
                    DriverResult(
                        driver_text="free startup plan",
                        polarity="positive",
                        category="pricing",
                        strength=0.7,
                        source_quote="free startup plan",
                    )
                ],
                product_features=[
                    ProductFeatureResult(
                        feature_name="startup plan",
                        feature_sentiment="positive",
                        context_snippet="free startup plan evidence",
                    )
                ],
            ),
        ],
        dimension=DimensionResult(industry="software", product="VDR", category="collaboration"),
        raw_json={
            "brands": [
                {"brand_name": "ONLYOFFICE", "product_name": "DocSpace"},
                {"brand_name": "ONLYOFFICE ", "product_name": "DocSpace"},
            ]
        },
    )


class _FakeDetector:
    def detect(self, *_args, **_kwargs):
        return [
            DetectedBrand(
                brand_name="ONLYOFFICE",
                brand_id=88,
                is_target=False,
                mention_count=3,
                context_snippets=["ONLYOFFICE DocSpace evidence"],
            )
        ]


class _FakeLLMAnalyzer:
    provider = "test-provider"
    model = "test-model"
    prompt_version = "issue-743-test"

    async def analyze(self, *_args, **_kwargs):
        return _duplicate_llm_result()


class _FakeCitationMapper:
    def map_citations(self, *_args, **_kwargs):
        return []


def _patch_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analyzer_cli, "BrandDetector", lambda: _FakeDetector())
    monkeypatch.setattr(analyzer_cli, "LLMAnalyzer", lambda: _FakeLLMAnalyzer())
    monkeypatch.setattr(analyzer_cli, "CitationMapper", lambda: _FakeCitationMapper())


@pytest.mark.asyncio
async def test_analyzer_merges_duplicate_brand_product_mentions_before_insert(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_pipeline(monkeypatch)
    target, response = await _seed_response(session)

    result = await analyzer_cli.analyze_single_response(
        session,
        response,
        target,
        [],
        "non_brand",
    )

    assert result["status"] == "done"
    mentions = (
        await session.execute(
            select(BrandMention).where(BrandMention.response_id == response.id)
        )
    ).scalars().all()
    assert [(m.brand_name, m.product_name, m.mention_count) for m in mentions] == [
        ("ONLYOFFICE", "DocSpace", 3)
    ]
    assert (
        await session.scalar(
            select(func.count(SentimentDriver.id)).where(
                SentimentDriver.response_id == response.id
            )
        )
        == 2
    )
    analysis = await session.scalar(
        select(ResponseAnalysis).where(ResponseAnalysis.response_id == response.id)
    )
    assert analysis is not None
    facts = analysis.raw_analysis_json["brand_mention_facts"]
    assert facts[0]["merged_duplicate_count"] == 2
    assert analysis.raw_analysis_json["dedupe_facts"] == {
        "llm_brand_product_duplicates_merged": 1,
        "keys": ["ONLYOFFICE|DocSpace"],
    }
    package = analysis.raw_analysis_json["analyzer_fact_package_v3"]
    assert package["entities"]["response_named_brands"][0]["mention_count"] == 3
    assert package["products"] == [
        {
            "product_name": "DocSpace",
            "brand_id": 88,
            "feature_name": None,
            "sentiment": None,
            "snippets": ["ONLYOFFICE DocSpace evidence"],
            "formula_status": "ok",
        }
    ]


@pytest.mark.asyncio
async def test_analyzer_retry_is_idempotent_after_partial_duplicate_artifacts(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_pipeline(monkeypatch)
    target, response = await _seed_response(session)
    stale = BrandMention(
        response_id=response.id,
        brand_id=88,
        brand_name="ONLYOFFICE",
        product_name="DocSpace",
        is_target=False,
        mention_count=1,
    )
    session.add(stale)
    await session.flush()
    session.add_all(
        [
            SentimentDriver(
                mention_id=stale.id,
                response_id=response.id,
                brand_name="ONLYOFFICE",
                driver_text="stale driver",
                polarity="positive",
            ),
            CitationSource(
                response_id=response.id,
                mention_id=stale.id,
                url="https://stale.example/docspace",
            ),
        ]
    )
    await session.commit()

    first = await analyzer_cli.analyze_single_response(
        session,
        response,
        target,
        [],
        "non_brand",
    )
    second = await analyzer_cli.analyze_single_response(
        session,
        response,
        target,
        [],
        "non_brand",
    )

    assert first["status"] == "done"
    assert second["status"] == "done"
    assert await session.scalar(select(func.count(ResponseAnalysis.id))) == 1
    assert await session.scalar(select(func.count(BrandMention.id))) == 1
    assert await session.scalar(select(func.count(SentimentDriver.id))) == 2
    assert await session.scalar(select(func.count(CitationSource.id))) == 0
    await session.refresh(response)
    assert response.analysis_status == AnalysisStatus.DONE.value


@pytest.mark.asyncio
async def test_analyzer_transaction_error_marks_failed_without_pending_rollback_mask(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_pipeline(monkeypatch)
    target, response = await _seed_response(session)
    response_id = response.id

    def _bypass_dedupe(llm_brands, _brand_index):
        rows = {}
        duplicate_counts = {}
        display_keys = {}
        raw_names = {}
        for llm_brand in llm_brands:
            key = (llm_brand.brand_name.lower(), (llm_brand.product_name or "").lower())
            rows[key] = llm_brand
            duplicate_counts[key] = 1
            display_keys[key] = f"{llm_brand.brand_name}|{llm_brand.product_name or ''}"
            raw_names[key] = [llm_brand.brand_name]
        return rows, duplicate_counts, display_keys, raw_names

    monkeypatch.setattr(analyzer_cli, "_dedupe_llm_brand_products", _bypass_dedupe)

    result = await analyzer_cli.analyze_single_response(
        session,
        response,
        target,
        [],
        "non_brand",
    )

    assert result["status"] == "failed"
    assert "UNIQUE constraint failed" in result["error"]
    assert "PendingRollbackError" not in result["error"]
    status = await session.scalar(
        select(LLMResponse.analysis_status).where(LLMResponse.id == response_id)
    )
    assert status == AnalysisStatus.FAILED.value
