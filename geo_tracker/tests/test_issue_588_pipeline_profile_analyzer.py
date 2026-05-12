from __future__ import annotations

import asyncio
import sys
import types
from collections.abc import AsyncGenerator
from datetime import datetime
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import geo_tracker.analyzer.cli as analyzer_cli
from geo_tracker.analyzer.prompts import ANALYSIS_USER
from geo_tracker.db.models import (
    AccountStatus,
    AnalysisStatus,
    Base,
    Brand,
    LLMAccount,
    LLMResponse,
    ProductFeatureMention,
    Profile,
    Query,
    QueryStatus,
    ResponseAnalysis,
    SentimentDriver,
)


def _install_fake_playwright(monkeypatch: pytest.MonkeyPatch) -> None:
    playwright = types.ModuleType("playwright")
    playwright_async = types.ModuleType("playwright.async_api")
    playwright_async.async_playwright = object
    playwright_async.BrowserContext = object
    playwright_async.ElementHandle = object
    playwright_async.Page = object
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.async_api", playwright_async)


class _TaskSessionContext:
    def __init__(self, maker):
        self.maker = maker
        self.session = None

    async def __aenter__(self):
        self.session = self.maker()
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        await self.session.close()
        return False


def test_execute_query_enqueues_analysis_and_preserves_account_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _install_fake_playwright(monkeypatch)

    from geo_tracker.tasks import celery_tasks

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'issue-588-query-success.db'}"
    query_id = 58801
    account_id = 588
    profile_id = 42

    async def seed_database() -> None:
        engine = create_async_engine(db_url, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            session.add_all(
                [
                    Profile(id=profile_id, name="Dry skin anti-aging"),
                    LLMAccount(
                        id=account_id,
                        llm_name="deepseek",
                        status=AccountStatus.ACTIVE.value,
                        cookies_json='[{"name":"session"}]',
                        profile_id=profile_id,
                        query_count_today=1,
                        daily_limit=20,
                    ),
                    Query(
                        id=query_id,
                        target_llm="deepseek",
                        query_text="best anti-aging serum for dry skin",
                        status=QueryStatus.PENDING.value,
                    ),
                ]
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(seed_database())

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    async def fake_acquire_query_account(db, query, pool=None):
        return LLMAccount(
            id=account_id,
            llm_name="deepseek",
            status=AccountStatus.ACTIVE.value,
            cookies_json='[{"name":"session"}]',
            profile_id=profile_id,
        )

    class FakeGuestQueryExecutor:
        def __init__(self, *args, **kwargs):
            self.last_error_reason = None

        async def execute(self, query):
            return LLMResponse(
                query_id=query.id,
                raw_text=(
                    "For dry skin anti-aging, look for barrier support, retinol "
                    "alternatives, peptides, and moisturizing serum textures."
                ),
                citations_json=[
                    {"url": "https://example.com/serum", "title": "Serum guide", "index": 1}
                ],
                response_time_ms=800,
            )

    analysis_calls: list[dict[str, object]] = []

    class FakeAnalyzeResponseTask:
        @staticmethod
        def apply_async(*, args, queue):
            analysis_calls.append({"args": args, "queue": queue})

    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(celery_tasks, "acquire_query_account", fake_acquire_query_account)
    monkeypatch.setattr(celery_tasks, "GuestQueryExecutor", FakeGuestQueryExecutor)
    monkeypatch.setattr(celery_tasks, "analyze_response", FakeAnalyzeResponseTask)

    result = celery_tasks.execute_query.run(query_id)

    async def load_state():
        engine = create_async_engine(db_url, future=True)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            query = await session.get(Query, query_id)
            response = (
                await session.execute(select(LLMResponse).where(LLMResponse.query_id == query_id))
            ).scalar_one()
            state = {
                "query_status": query.status,
                "query_profile_id": query.profile_id,
                "query_account_id": query.account_id,
                "response_id": response.id,
                "analysis_status": response.analysis_status,
            }
        await engine.dispose()
        return state

    state = asyncio.run(load_state())

    assert result == {
        "query_id": query_id,
        "status": "done",
        "mode": "guest",
        "analysis_enqueued": True,
    }
    assert state["query_status"] == QueryStatus.DONE.value
    assert state["query_profile_id"] == profile_id
    assert state["query_account_id"] == account_id
    assert state["analysis_status"] == AnalysisStatus.PENDING.value
    assert analysis_calls == [{"args": [state["response_id"]], "queue": "analysis"}]


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as db:
        yield db
    await engine.dispose()


class AnalyzerWithCurrentResponseFacts:
    model = "fake-issue-588"

    async def analyze(self, **_kwargs):
        return SimpleNamespace(
            brands=[
                SimpleNamespace(
                    brand_name="Curel",
                    product_name="Intensive Moisture Facial Cream",
                    position_type="first_recommendation",
                    position_rank=1,
                    detail_level="detailed",
                    sentiment="positive",
                    sentiment_score=0.8,
                    sentiment_drivers=[
                        SimpleNamespace(
                            driver_text="barrier repair is suitable for dry skin",
                            polarity="positive",
                            category="product_feature",
                            strength=0.9,
                            source_quote="Curel supports ceramide barrier repair for dry skin.",
                        )
                    ],
                    product_features=[
                        SimpleNamespace(
                            feature_name="ceramide barrier repair",
                            feature_sentiment="positive",
                            scenario="dry sensitive skin",
                            price_positioning="mid_range",
                            context_snippet="ceramide barrier repair for dry skin",
                        )
                    ],
                )
            ],
            dimension=SimpleNamespace(
                industry="beauty",
                company="",
                product="serum",
                category="skincare",
            ),
            raw_json={
                "response_relations": [
                    {
                        "entity_kind": "product",
                        "type": "recommended_for",
                        "a_name": "Intensive Moisture Facial Cream",
                        "b_name": "dry sensitive skin",
                        "confidence": 0.88,
                        "evidence": "recommended for dry sensitive skin",
                    }
                ]
            },
        )


@pytest.mark.asyncio
async def test_analyzer_persists_current_response_products_drivers_and_relations(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response_id = 58802
    query_id = 59802
    brand = Brand(id=88, name="Curel", aliases=["珂润"], industry="beauty")
    response = LLMResponse(
        id=response_id,
        query_id=query_id,
        raw_text=(
            "Curel Intensive Moisture Facial Cream supports ceramide barrier "
            "repair for dry sensitive skin."
        ),
        citations_json=[],
        response_time_ms=700,
        collected_at=datetime(2026, 5, 12, 12, 0),
        analysis_status=AnalysisStatus.PENDING.value,
    )
    session.add_all(
        [
            brand,
            Query(
                id=query_id,
                brand_id=brand.id,
                query_text="dry skin anti-aging product",
                target_llm="deepseek",
                status=QueryStatus.DONE.value,
            ),
            response,
        ]
    )
    await session.commit()

    monkeypatch.setattr(analyzer_cli, "LLMAnalyzer", AnalyzerWithCurrentResponseFacts)

    result = await analyzer_cli.analyze_single_response(
        session,
        response,
        brand,
        [],
        "non_brand",
    )

    assert result["status"] == "done"

    features = (
        await session.execute(select(ProductFeatureMention).where(ProductFeatureMention.brand_name == "Curel"))
    ).scalars().all()
    drivers = (
        await session.execute(select(SentimentDriver).where(SentimentDriver.response_id == response_id))
    ).scalars().all()
    analysis = (
        await session.execute(select(ResponseAnalysis).where(ResponseAnalysis.response_id == response_id))
    ).scalar_one()

    assert [feature.feature_name for feature in features] == ["ceramide barrier repair"]
    assert [driver.driver_text for driver in drivers] == [
        "barrier repair is suitable for dry skin"
    ]
    relation = analysis.raw_analysis_json["response_relations"][0]
    assert relation["response_id"] == response_id
    assert relation["query_id"] == query_id
    assert relation["source"] == "current_response_analyzer"


def test_analysis_prompt_requests_response_scoped_relations() -> None:
    assert "response_relations" in ANALYSIS_USER
    assert "current AI response" in ANALYSIS_USER
    assert "global inference" in ANALYSIS_USER
