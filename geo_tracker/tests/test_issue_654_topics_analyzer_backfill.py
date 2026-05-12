from __future__ import annotations

from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from geo_tracker.db.models import (
    AnalysisStatus,
    Base,
    Brand,
    BrandMention,
    LLMResponse,
    ProductFeatureMention,
    Profile,
    Prompt,
    Query,
    QueryStatus,
    ResponseAnalysis,
    Topic,
)
from geo_tracker.tasks.topics_analyzer_backfill import (
    TopicsAnalyzerBackfillScope,
    build_topics_analyzer_backfill_report,
)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as db:
        yield db
    await engine.dispose()


async def _seed_scope(session: AsyncSession) -> None:
    brand = Brand(id=12, name="Estee Lauder", aliases=["Estee Lauder"])
    topic = Topic(
        id=11,
        brand_id=12,
        text="Anti-aging serum commercial topic",
        category="commercial",
        generated_by="test",
    )
    prompt = Prompt(
        id=36,
        topic_id=11,
        text="Which anti-aging serum should I buy?",
        intent="commercial",
        language="zh",
    )
    other_prompt = Prompt(
        id=37,
        topic_id=11,
        text="Other prompt",
        intent="commercial",
        language="zh",
    )
    profile = Profile(id=42, name="Urban skincare buyer")
    session.add_all([brand, topic, prompt, other_prompt, profile])
    session.add_all(
        [
            Query(
                id=65401,
                brand_id=12,
                prompt_id=36,
                profile_id=42,
                query_text="Which anti-aging serum should I buy?",
                target_llm="deepseek",
                status=QueryStatus.DONE.value,
            ),
            Query(
                id=65402,
                brand_id=12,
                prompt_id=36,
                profile_id=None,
                query_text="Which anti-aging serum should I buy?",
                target_llm="deepseek",
                status=QueryStatus.DONE.value,
            ),
            Query(
                id=65403,
                brand_id=12,
                prompt_id=36,
                query_text="failed query",
                target_llm="deepseek",
                status=QueryStatus.FAILED.value,
            ),
            Query(
                id=65404,
                brand_id=12,
                prompt_id=37,
                query_text="other prompt",
                target_llm="deepseek",
                status=QueryStatus.DONE.value,
            ),
            Query(
                id=65405,
                brand_id=12,
                prompt_id=36,
                query_text="outside window",
                target_llm="deepseek",
                status=QueryStatus.DONE.value,
            ),
        ]
    )
    session.add_all(
        [
            LLMResponse(
                id=75401,
                query_id=65401,
                raw_text="Estee Lauder Advanced Night Repair has serum benefits.",
                citations_json=[],
                collected_at=datetime(2026, 5, 1, 8, 0, 0),
                analysis_status=AnalysisStatus.DONE.value,
            ),
            LLMResponse(
                id=75402,
                query_id=65402,
                raw_text="Estee Lauder is mentioned without an assigned profile.",
                citations_json=[],
                collected_at=datetime(2026, 5, 2, 8, 0, 0),
                analysis_status=AnalysisStatus.DONE.value,
            ),
            LLMResponse(
                id=75403,
                query_id=65403,
                raw_text="failed query should not be selected",
                citations_json=[],
                collected_at=datetime(2026, 5, 3, 8, 0, 0),
                analysis_status=AnalysisStatus.DONE.value,
            ),
            LLMResponse(
                id=75404,
                query_id=65404,
                raw_text="other prompt should not be selected",
                citations_json=[],
                collected_at=datetime(2026, 5, 4, 8, 0, 0),
                analysis_status=AnalysisStatus.DONE.value,
            ),
            LLMResponse(
                id=75405,
                query_id=65405,
                raw_text="outside window should not be selected",
                citations_json=[],
                collected_at=datetime(2026, 4, 1, 8, 0, 0),
                analysis_status=AnalysisStatus.DONE.value,
            ),
        ]
    )
    session.add_all(
        [
            BrandMention(
                response_id=75401,
                brand_id=12,
                brand_name="Estee Lauder",
                product_name=None,
                is_target=True,
                mention_count=1,
            ),
            ResponseAnalysis(
                id=86401,
                response_id=75401,
                raw_analysis_json={"legacy": True},
            ),
            ResponseAnalysis(
                id=86402,
                response_id=75402,
                raw_analysis_json={"legacy": True},
            ),
            ProductFeatureMention(
                analysis_id=86401,
                brand_name="Estee Lauder",
                product_name="Advanced Night Repair",
                feature_name="repair serum",
            ),
        ]
    )
    await session.commit()


@pytest.mark.asyncio
async def test_dry_run_selects_only_successful_prompt_topic_responses_and_reports_profiles(
    session: AsyncSession,
) -> None:
    await _seed_scope(session)

    report = await build_topics_analyzer_backfill_report(
        session,
        TopicsAnalyzerBackfillScope(
            topic_id=11,
            prompt_id=36,
            date_from="2026-04-12",
            date_to="2026-05-12",
            prompt_intent="commercial",
            prompt_language="zh",
        ),
        apply=False,
    )

    assert report["mode"] == "dry_run"
    assert report["write_performed"] is False
    assert report["selected_response_ids"] == [75401, 75402]
    assert report["selected_query_ids"] == [65401, 65402]
    assert report["scope"]["topic_id"] == 11
    assert report["scope"]["prompt_id"] == 36
    assert report["before"]["selected_count"] == 2
    assert report["before"]["profile_state_counts"] == {
        "profile_found": 1,
        "query_profile_id_null": 1,
    }
    assert report["before"]["analyzer_state_counts"]["missing_fact_packages"] == 2
    assert report["before"]["rows"][0]["profile_name"] == "Urban skincare buyer"
    assert report["before"]["rows"][1]["profile_name"] == "Unknown profile"
    assert report["before"]["rows"][1]["upstream_null_reason"] == "query.profile_id is NULL"
    assert report["safe_selection"]["successful_responses_only"] is True
    assert "response_ids" in report["apply_plan"]


@pytest.mark.asyncio
async def test_apply_reanalyzes_only_selected_response_ids(
    session: AsyncSession,
) -> None:
    await _seed_scope(session)
    analyzed: list[int] = []

    async def fake_analyze(session, response, brand, competitors, intent):
        analyzed.append(response.id)
        response.analysis_status = AnalysisStatus.DONE.value
        await session.commit()
        return {"response_id": response.id, "status": "done"}

    report = await build_topics_analyzer_backfill_report(
        session,
        TopicsAnalyzerBackfillScope(
            topic_id=11,
            prompt_id=36,
            date_from="2026-04-12",
            date_to="2026-05-12",
            prompt_intent="commercial",
            prompt_language="zh",
        ),
        apply=True,
        approval_ref="https://github.com/jotamotk/trash_test/issues/654",
        analyze_func=fake_analyze,
    )

    assert report["mode"] == "apply"
    assert report["write_performed"] is True
    assert analyzed == [75401, 75402]
    assert report["apply_results"] == [
        {"response_id": 75401, "status": "done"},
        {"response_id": 75402, "status": "done"},
    ]


@pytest.mark.asyncio
async def test_apply_requires_github_approval_ref(session: AsyncSession) -> None:
    await _seed_scope(session)

    with pytest.raises(ValueError, match="approval_ref"):
        await build_topics_analyzer_backfill_report(
            session,
            TopicsAnalyzerBackfillScope(
                topic_id=11,
                prompt_id=36,
                date_from="2026-04-12",
                date_to="2026-05-12",
            ),
            apply=True,
        )
