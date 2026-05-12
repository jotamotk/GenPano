from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from geo_tracker.db.models import (
    AnalysisStatus,
    Base,
    Brand,
    BrandMention,
    GEOScoreDaily,
    LLMResponse,
    Prompt,
    Query,
    QueryStatus,
    ResponseAnalysis,
    Topic,
    TopicScoreDaily,
)
from geo_tracker.tasks.bestcoffer_analyzer_backfill import (
    AnalyzerBackfillApplyError,
    BestCofferAnalyzerBackfillScope,
    build_bestcoffer_analyzer_backfill_report,
    validate_approval_ref,
)

EXPLICIT_PROD_APPROVAL_REF = (
    "https://github.com/jotamotk/trash_test/issues/686#issuecomment-4433999999 "
    "explicit production-write-approved evidence for BestCoffer analyzer backfill apply"
)
DISPATCH_ONLY_REF = (
    "https://github.com/jotamotk/trash_test/issues/686#issuecomment-4433719761"
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


async def _seed_bestcoffer_scope(session: AsyncSession) -> datetime:
    day = datetime(2026, 4, 24, 10, 0)
    session.add_all(
        [
            Brand(id=2, name="La Roche-Posay", aliases=["LRP"], industry="beauty"),
            Brand(id=24, name="bestCoffer", aliases=["BestCoffer"], industry="coffee"),
        ]
    )
    await session.flush()
    session.add_all(
        [
            Topic(id=2401, brand_id=24, text="BestCoffer discovery", category="category"),
            Prompt(
                id=2402,
                topic_id=2401,
                text="best coffee grinders",
                intent="non_brand",
                language="en",
                tags={"prompt_scope": "nonbrand", "topic_dimension": "category"},
            ),
        ]
    )
    await session.flush()
    session.add_all(
        [
            Query(
                id=2403,
                prompt_id=2402,
                brand_id=24,
                query_text="best coffee grinders for office",
                target_llm="chatgpt",
                status=QueryStatus.DONE.value,
                created_at=day,
            ),
            Query(
                id=2404,
                prompt_id=2402,
                brand_id=24,
                query_text="login shell should be excluded",
                target_llm="chatgpt",
                status=QueryStatus.DONE.value,
                created_at=day,
            ),
            Query(
                id=2405,
                prompt_id=2402,
                brand_id=24,
                query_text="failed query should be ignored",
                target_llm="deepseek",
                status=QueryStatus.FAILED.value,
                created_at=day,
            ),
        ]
    )
    await session.flush()
    session.add_all(
        [
            LLMResponse(
                id=2410,
                query_id=2403,
                raw_text="BestCoffer is recommended for office coffee grinder workflows.",
                citations_json=[],
                response_time_ms=900,
                collected_at=day,
                analysis_status=AnalysisStatus.PENDING.value,
            ),
            LLMResponse(
                id=2411,
                query_id=2404,
                raw_text="Sign in to ChatGPT Continue with Google Continue with Microsoft",
                citations_json=[],
                response_time_ms=300,
                collected_at=day,
                analysis_status=AnalysisStatus.PENDING.value,
            ),
            LLMResponse(
                id=2412,
                query_id=2405,
                raw_text="BestCoffer failed query artifact",
                citations_json=[],
                response_time_ms=300,
                collected_at=day,
                analysis_status=AnalysisStatus.PENDING.value,
            ),
        ]
    )
    await session.commit()
    return day


async def _seed_unrelated_response(session: AsyncSession) -> None:
    day = datetime(2026, 4, 24, 11, 0)
    session.add(
        Topic(id=2201, brand_id=2, text="Unrelated beauty discovery", category="category")
    )
    await session.flush()
    session.add(
        Prompt(
            id=2202,
            topic_id=2201,
            text="best sunscreen",
            intent="non_brand",
            language="en",
            tags={"prompt_scope": "nonbrand", "topic_dimension": "category"},
        )
    )
    await session.flush()
    session.add(
        Query(
            id=2203,
            prompt_id=2202,
            brand_id=2,
            query_text="best sunscreen for sensitive skin",
            target_llm="chatgpt",
            status=QueryStatus.DONE.value,
            created_at=day,
        )
    )
    await session.flush()
    session.add(
        LLMResponse(
            id=2210,
            query_id=2203,
            raw_text="La Roche-Posay is recommended for sensitive skin sunscreen.",
            citations_json=[],
            response_time_ms=800,
            collected_at=day,
            analysis_status=AnalysisStatus.PENDING.value,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_dry_run_selects_successful_bestcoffer_responses_and_excludes_invalid_artifacts(
    session: AsyncSession,
) -> None:
    day = await _seed_bestcoffer_scope(session)

    report = await build_bestcoffer_analyzer_backfill_report(
        session,
        BestCofferAnalyzerBackfillScope(
            brand_id=24,
            date_from="2026-04-24",
            date_to="2026-04-24",
            limit=10,
        ),
        apply=False,
    )

    assert report["issue"] == 686
    assert report["mode"] == "dry_run"
    assert report["write_performed"] is False
    assert report["safe_selection"]["successful_responses_only"] is True
    assert report["safe_selection"]["invalid_artifacts_excluded"] is True
    assert report["selected_response_ids"] == [2410]
    assert report["before"]["candidate_count"] == 2
    assert report["before"]["selected_count"] == 1
    assert report["before"]["excluded_invalid_count"] == 1
    assert report["before"]["analyzer_state_counts"] == {"missing_analysis": 1}
    assert report["before"]["excluded_rows"][0]["invalid_reason"] == "chatgpt_auth_redirect"

    mentions = (
        await session.execute(select(BrandMention).where(BrandMention.brand_id == 24))
    ).scalars().all()
    assert mentions == []


@pytest.mark.asyncio
async def test_apply_uses_requested_brand_target_and_aggregates_selected_days(
    session: AsyncSession,
) -> None:
    day = await _seed_bestcoffer_scope(session)
    source_query = await session.get(Query, 2403)
    assert source_query is not None
    source_query.brand_id = 2
    await session.commit()
    analyzed: list[tuple[int, int]] = []

    async def fake_analyze(session, response, brand, competitors, intent):
        analyzed.append((response.id, brand.id))
        response.analysis_status = AnalysisStatus.DONE.value
        session.add(
            ResponseAnalysis(
                response_id=response.id,
                dimension_industry="coffee",
                dimension_category="category",
                target_brand_mentioned=True,
                raw_analysis_json={"source": "issue-686-test"},
            )
        )
        session.add(
            BrandMention(
                response_id=response.id,
                brand_id=brand.id,
                brand_name=brand.name,
                is_target=True,
                position_type="mentioned_only",
                sentiment=None,
                sentiment_score=None,
                mention_count=1,
            )
        )
        await session.commit()
        return {"response_id": response.id, "status": "done"}

    report = await build_bestcoffer_analyzer_backfill_report(
        session,
        BestCofferAnalyzerBackfillScope(
            brand_id=24,
            date_from="2026-04-24",
            date_to="2026-04-24",
            limit=10,
            competitive_brand_ids=(2,),
        ),
        apply=True,
        aggregate=True,
        approval_ref=EXPLICIT_PROD_APPROVAL_REF,
        analyze_func=fake_analyze,
    )

    assert analyzed == [(2410, 24)]
    assert report["write_performed"] is True
    assert report["apply_results"] == [{"response_id": 2410, "status": "done"}]
    assert report["aggregate_results"] == [
        {
            "date": "2026-04-24",
            "brand_id": 24,
            "stats": {
                "geo_score_daily": 2,
                "industry_benchmark": 0,
                "product_score": 0,
                "topic_score": 1,
                "geo_score_daily_removed": 0,
                "product_score_removed": 0,
                "topic_score_removed": 0,
            },
        }
    ]

    geo = (
        await session.execute(select(GEOScoreDaily).where(GEOScoreDaily.brand_id == 24))
    ).scalars().all()
    topics = (
        await session.execute(select(TopicScoreDaily).where(TopicScoreDaily.brand_id == 24))
    ).scalars().all()
    assert len(geo) == 2
    assert len(topics) == 1
    assert topics[0].total_responses == 1


@pytest.mark.asyncio
async def test_apply_requires_issue_686_approval_ref(session: AsyncSession) -> None:
    await _seed_bestcoffer_scope(session)

    with pytest.raises(ValueError, match="approval_ref"):
        await build_bestcoffer_analyzer_backfill_report(
            session,
            BestCofferAnalyzerBackfillScope(
                brand_id=24,
                date_from="2026-04-24",
                date_to="2026-04-24",
            ),
            apply=True,
        )


@pytest.mark.parametrize(
    "approval_ref",
    [
        "https://github.com/jotamotk/trash_test/issues/686",
        DISPATCH_ONLY_REF,
    ],
)
def test_approval_ref_rejects_non_production_write_evidence(approval_ref: str) -> None:
    with pytest.raises(ValueError, match="production-write approval"):
        validate_approval_ref(approval_ref)


def test_approval_ref_accepts_explicit_production_write_evidence() -> None:
    assert validate_approval_ref(EXPLICIT_PROD_APPROVAL_REF) == EXPLICIT_PROD_APPROVAL_REF


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope_kwargs",
    [
        {"response_ids": (2210,)},
        {"query_ids": (2203,)},
    ],
)
async def test_apply_excludes_explicit_ids_outside_bestcoffer_scope(
    session: AsyncSession,
    scope_kwargs: dict,
) -> None:
    await _seed_bestcoffer_scope(session)
    await _seed_unrelated_response(session)
    analyzed: list[int] = []

    async def fake_analyze(session, response, brand, competitors, intent):
        analyzed.append(response.id)
        response.analysis_status = AnalysisStatus.DONE.value
        await session.commit()
        return {"response_id": response.id, "status": "done"}

    report = await build_bestcoffer_analyzer_backfill_report(
        session,
        BestCofferAnalyzerBackfillScope(
            brand_id=24,
            limit=10,
            **scope_kwargs,
        ),
        apply=True,
        approval_ref=EXPLICIT_PROD_APPROVAL_REF,
        analyze_func=fake_analyze,
    )

    assert analyzed == []
    assert report["write_performed"] is False
    assert report["selected_response_ids"] == []
    assert report["selected_query_ids"] == []
    assert report["before"]["candidate_count"] == 1
    assert report["before"]["selected_count"] == 0
    assert report["before"]["excluded_invalid_count"] == 1
    assert (
        report["before"]["excluded_rows"][0]["invalid_reason"]
        == "outside_target_brand_scope"
    )


@pytest.mark.asyncio
async def test_apply_failure_preserves_report_and_stops_before_aggregate(
    session: AsyncSession,
) -> None:
    await _seed_bestcoffer_scope(session)

    async def fake_analyze(session, response, brand, competitors, intent):
        return {"response_id": response.id, "status": "failed", "error": "llm_timeout"}

    with pytest.raises(AnalyzerBackfillApplyError) as exc:
        await build_bestcoffer_analyzer_backfill_report(
            session,
            BestCofferAnalyzerBackfillScope(
                brand_id=24,
                date_from="2026-04-24",
                date_to="2026-04-24",
            ),
            apply=True,
            aggregate=True,
            approval_ref=EXPLICIT_PROD_APPROVAL_REF,
            analyze_func=fake_analyze,
        )

    report = exc.value.report
    assert report["write_attempted"] is True
    assert report["apply_failed"] is True
    assert report["failed_response_id"] == 2410
    assert report["apply_results"] == [
        {"response_id": 2410, "status": "failed", "error": "llm_timeout"}
    ]
    assert "aggregate_results" not in report
