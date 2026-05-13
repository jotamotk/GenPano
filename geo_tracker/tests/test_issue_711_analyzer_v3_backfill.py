from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from geo_tracker.tasks import analyzer_v3_backfill
from geo_tracker.db.models import (
    AnalysisStatus,
    Base,
    Brand,
    BrandMention,
    CitationSource,
    GEOScoreDaily,
    LLMResponse,
    ProductFeatureMention,
    Prompt,
    Query,
    QueryStatus,
    ResponseAnalysis,
    SentimentDriver,
    Topic,
    TopicScoreDaily,
)
from geo_tracker.tasks.analyzer_v3_backfill import (
    AnalyzerV3BackfillApplyError,
    AnalyzerV3BackfillScope,
    build_analyzer_v3_backfill_report,
    validate_approval_ref,
)

APPROVAL_REF = (
    "https://github.com/jotamotk/trash_test/issues/711#issuecomment-4436999999 "
    "AI Lead approved production-write analyzer v3 backfill apply after dry-run evidence"
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


async def _seed_scope(session: AsyncSession) -> None:
    day = datetime(2026, 5, 12, 10, 0)
    session.add_all(
        [
            Brand(id=24, name="BestCoffer", aliases=["Best Coffer"], industry="coffee"),
            Topic(id=7111, brand_id=24, text="Office coffee", category="category"),
            Prompt(
                id=7112,
                topic_id=7111,
                text="best office coffee machines",
                intent="non_brand",
                language="en",
            ),
        ]
    )
    await session.flush()
    session.add_all(
        [
            Query(
                id=7113,
                prompt_id=7112,
                brand_id=24,
                query_text="best office coffee machines",
                target_llm="chatgpt",
                status=QueryStatus.DONE.value,
                created_at=day,
            ),
            Query(
                id=7114,
                prompt_id=7112,
                brand_id=24,
                query_text="best office grinder",
                target_llm="deepseek",
                status=QueryStatus.DONE.value,
                created_at=day,
            ),
            Query(
                id=7115,
                prompt_id=7112,
                brand_id=24,
                query_text="pending response should not be selected",
                target_llm="chatgpt",
                status=QueryStatus.PENDING.value,
                created_at=day,
            ),
        ]
    )
    await session.flush()
    session.add_all(
        [
            LLMResponse(
                id=7120,
                query_id=7113,
                raw_text="BestCoffer is recommended with AcmeGrind.",
                citations_json=[],
                collected_at=day,
                analysis_status=AnalysisStatus.PENDING.value,
            ),
            LLMResponse(
                id=7121,
                query_id=7114,
                raw_text="BestCoffer and AcmeGrind are both mentioned.",
                citations_json=[],
                collected_at=day,
                analysis_status=AnalysisStatus.DONE.value,
            ),
            LLMResponse(
                id=7122,
                query_id=7115,
                raw_text="Not eligible because query is pending.",
                citations_json=[],
                collected_at=day,
                analysis_status=AnalysisStatus.PENDING.value,
            ),
        ]
    )
    await session.flush()
    session.add(
        ResponseAnalysis(
            response_id=7121,
            dimension_industry="coffee",
            raw_analysis_json={
                "analyzer_fact_package_v3": {
                    "analyzer_version": "v3",
                    "idempotency_key": "7121:v3:existing",
                }
            },
        )
    )
    await session.commit()


async def _seed_legacy_evidence(
    session: AsyncSession,
    *,
    response_id: int = 7120,
    target_mentioned: bool = True,
) -> None:
    response = await session.get(LLMResponse, response_id)
    assert response is not None
    response.analysis_status = AnalysisStatus.DONE.value
    old_analysis = ResponseAnalysis(
        response_id=response_id,
        dimension_industry="coffee",
        dimension_category="category",
        target_brand_mentioned=target_mentioned,
        raw_analysis_json={"legacy": "evidence"},
    )
    brand_name = "BestCoffer" if target_mentioned else "AcmeGrind"
    brand_id = 24 if target_mentioned else None
    old_mention = BrandMention(
        response_id=response_id,
        brand_id=brand_id,
        brand_name=brand_name,
        product_name="Legacy Brew" if target_mentioned else None,
        is_target=target_mentioned,
        position_type="ranked" if target_mentioned else None,
        position_rank=2 if target_mentioned else None,
        sentiment="positive" if target_mentioned else None,
        sentiment_score=0.8 if target_mentioned else None,
        context_snippet=f"{brand_name} legacy evidence",
        mention_count=1,
    )
    session.add_all([old_analysis, old_mention])
    await session.flush()
    if target_mentioned:
        session.add(
            SentimentDriver(
                mention_id=old_mention.id,
                response_id=response_id,
                brand_name="BestCoffer",
                driver_text="quiet grinder",
                polarity="positive",
                category="quality",
                strength=0.8,
                source_quote="BestCoffer is a quiet grinder",
            )
        )
    session.add(
        CitationSource(
            response_id=response_id,
            mention_id=old_mention.id if target_mentioned else None,
            url="https://legacy.example/review",
            domain="legacy.example",
            title="Legacy review",
        )
    )
    session.add(
        ProductFeatureMention(
            analysis_id=old_analysis.id,
            brand_name=brand_name,
            product_name="Legacy Brew",
            feature_name="quiet",
        )
    )
    await session.commit()


def test_approval_ref_accepts_issue_711_ai_lead_apply_evidence() -> None:
    assert validate_approval_ref(APPROVAL_REF) == APPROVAL_REF


@pytest.mark.parametrize(
    "approval_ref",
    [
        "",
        "https://github.com/jotamotk/trash_test/issues/710#issuecomment-4436825899",
        "https://github.com/jotamotk/trash_test/issues/711#issuecomment-4436999999 dry-run only",
    ],
)
def test_approval_ref_rejects_missing_issue_711_write_approval(
    approval_ref: str,
) -> None:
    with pytest.raises(ValueError, match="approval_ref"):
        validate_approval_ref(approval_ref)


@pytest.mark.asyncio
async def test_dry_run_reports_missing_existing_and_resume_cursor(
    session: AsyncSession,
) -> None:
    await _seed_scope(session)

    report = await build_analyzer_v3_backfill_report(
        session,
        AnalyzerV3BackfillScope(
            response_ids=(7120, 7121),
            brand_id=24,
            topic_id=7111,
            date_from="2026-05-12",
            date_to="2026-05-12",
            batch_size=1,
        ),
    )

    assert report["issue"] == 711
    assert report["mode"] == "dry_run"
    assert report["write_performed"] is False
    assert report["selected_response_ids"] == [7120]
    assert report["skipped_response_ids"] == [7121]
    assert report["before"]["state_counts"] == {"DONE": 1, "PENDING": 1}
    assert report["before"]["partial_state"]["completed_response_ids"] == [7121]
    assert report["before"]["partial_state"]["pending_response_ids"] == [7120]
    assert report["resume"]["next_resume_cursor"] == 7120
    assert report["resume"]["has_more"] is True


@pytest.mark.asyncio
async def test_dry_run_reports_project_scope_is_not_apply_boundary(
    session: AsyncSession,
) -> None:
    await _seed_scope(session)

    report = await build_analyzer_v3_backfill_report(
        session,
        AnalyzerV3BackfillScope(
            project_id="95d43022-a5c8-5944-b6d6-34b29faa18b5",
            brand_id=24,
            topic_id=7111,
            date_from="2026-05-12",
            date_to="2026-05-12",
            batch_size=10,
        ),
    )

    assert report["mode"] == "dry_run"
    assert report["selected_response_ids"] == [7120]
    assert report.get("apply_blocked") is None
    assert report["safe_selection"]["project_scope_enforced"] is False
    assert "not an apply boundary" in report["safe_selection"]["project_filter_note"]


@pytest.mark.asyncio
async def test_apply_is_idempotent_and_resumable_after_interruption(
    session: AsyncSession,
) -> None:
    await _seed_scope(session)
    await _seed_legacy_evidence(session)

    report = await build_analyzer_v3_backfill_report(
        session,
        AnalyzerV3BackfillScope(response_ids=(7120, 7121), brand_id=24, batch_size=10),
        apply=True,
        approval_ref=APPROVAL_REF,
    )

    assert report["write_performed"] is True
    assert report["apply_results"][0]["status"] == "done"
    assert report["apply_results"][0]["idempotency_key"].startswith("7120:v3:")
    assert report["after"]["state_counts"] == {"DONE": 2}
    assert report["after"]["partial_state"]["completed_response_ids"] == [7120, 7121]
    analysis = await session.scalar(
        select(ResponseAnalysis).where(ResponseAnalysis.response_id == 7120)
    )
    assert analysis is not None
    raw = analysis.raw_analysis_json
    assert raw["legacy"] == "evidence"
    package = raw["analyzer_fact_package_v3"]
    assert package["analyzer_version"] == "v3"
    assert package["entities"]["target"]["mentioned"] is True
    assert package["topic_metrics"]["visible"] is True

    second = await build_analyzer_v3_backfill_report(
        session,
        AnalyzerV3BackfillScope(response_ids=(7120, 7121), brand_id=24, batch_size=10),
        apply=True,
        approval_ref=APPROVAL_REF,
    )
    assert second["selected_response_ids"] == []
    assert second["skipped_response_ids"] == [7120, 7121]


@pytest.mark.asyncio
async def test_apply_rejects_project_scope_without_explicit_response_or_query_ids(
    session: AsyncSession,
) -> None:
    await _seed_scope(session)

    report = await build_analyzer_v3_backfill_report(
        session,
        AnalyzerV3BackfillScope(
            project_id="95d43022-a5c8-5944-b6d6-34b29faa18b5",
            brand_id=24,
            topic_id=7111,
            date_from="2026-05-12",
            date_to="2026-05-12",
            batch_size=10,
        ),
        apply=True,
        approval_ref=APPROVAL_REF,
    )

    assert report["write_performed"] is False
    assert report["apply_blocked"] is True
    assert (
        report["block_reason"]
        == "project_scope_requires_explicit_response_or_query_ids"
    )
    assert report["selected_response_ids"] == []
    assert report["safe_selection"]["project_scope_enforced"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope_kwargs", [{"response_ids": (7120,)}, {"query_ids": (7113,)}]
)
async def test_apply_allows_project_scope_with_explicit_response_or_query_ids(
    session: AsyncSession,
    scope_kwargs: dict,
) -> None:
    await _seed_scope(session)
    await _seed_legacy_evidence(session)

    report = await build_analyzer_v3_backfill_report(
        session,
        AnalyzerV3BackfillScope(
            project_id="95d43022-a5c8-5944-b6d6-34b29faa18b5",
            brand_id=24,
            batch_size=10,
            **scope_kwargs,
        ),
        apply=True,
        approval_ref=APPROVAL_REF,
    )

    assert report["write_performed"] is True
    assert report["apply_results"][0]["status"] == "done"
    assert report.get("apply_blocked") is None
    assert report["safe_selection"]["project_scope_enforced"] is False


@pytest.mark.asyncio
async def test_apply_failure_reports_partial_state_before_retry(
    session: AsyncSession,
) -> None:
    await _seed_scope(session)
    await _seed_legacy_evidence(session)

    def broken_builder(*args, **kwargs):
        raise RuntimeError("package_timeout")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        analyzer_v3_backfill,
        "build_response_fact_package_v3",
        broken_builder,
    )
    try:
        with pytest.raises(AnalyzerV3BackfillApplyError) as exc:
            await build_analyzer_v3_backfill_report(
                session,
                AnalyzerV3BackfillScope(
                    response_ids=(7120, 7121), brand_id=24, batch_size=10
                ),
                apply=True,
                approval_ref=APPROVAL_REF,
            )
    finally:
        monkeypatch.undo()

    report = exc.value.report
    assert report["apply_failed"] is True
    assert report["failed_response_id"] == 7120
    assert report["failure_reason"] == "package_timeout"
    assert report["partial_writes_possible"] is False
    assert report["after"]["state_counts"] == {"DONE": 1, "PENDING": 1}
    assert report["after"]["partial_state"]["completed_response_ids"] == [7121]
    assert report["after"]["partial_state"]["pending_response_ids"] == [7120]
    analysis = await session.scalar(
        select(ResponseAnalysis).where(ResponseAnalysis.response_id == 7120)
    )
    assert analysis is not None
    assert analysis.raw_analysis_json == {"legacy": "evidence"}


@pytest.mark.asyncio
async def test_global_unrelated_aggregate_rows_do_not_satisfy_selected_scope(
    session: AsyncSession,
) -> None:
    await _seed_scope(session)
    session.add_all(
        [
            GEOScoreDaily(
                brand_id=999,
                date=datetime(2026, 5, 12),
                target_llm="chatgpt",
                total_queries=9,
            ),
            TopicScoreDaily(
                brand_id=999,
                topic_id=9991,
                date=datetime(2026, 5, 12),
                total_responses=9,
            ),
        ]
    )
    await session.commit()

    report = await build_analyzer_v3_backfill_report(
        session,
        AnalyzerV3BackfillScope(
            response_ids=(7120, 7121),
            brand_id=24,
            topic_id=7111,
            date_from="2026-05-12",
            date_to="2026-05-12",
        ),
    )

    aggregate_rows = report["before"]["artifact_counts"]["aggregate_rows"]
    assert aggregate_rows["scoped"] is True
    assert aggregate_rows["geo_score_daily"] == 0
    assert aggregate_rows["topic_score_daily"] == 0
    assert aggregate_rows["total"] == 0


@pytest.mark.asyncio
async def test_apply_without_existing_analysis_preserves_rows_and_reports_missing_evidence(
    session: AsyncSession,
) -> None:
    await _seed_scope(session)
    response = await session.get(LLMResponse, 7120)
    assert response is not None

    with pytest.raises(AnalyzerV3BackfillApplyError) as exc:
        await build_analyzer_v3_backfill_report(
            session,
            AnalyzerV3BackfillScope(
                response_ids=(7120,),
                brand_id=24,
                batch_size=10,
            ),
            apply=True,
            approval_ref=APPROVAL_REF,
        )

    report = exc.value.report
    assert report["apply_failed"] is True
    assert report["failure_reason"] == "missing_response_analysis"
    assert report["write_performed"] is False
    assert report["write_attempted"] is True
    assert report["partial_writes_possible"] is False
    await session.refresh(response)
    assert response.analysis_status == AnalysisStatus.PENDING.value
    assert (
        await session.scalar(
            select(func.count(ResponseAnalysis.id)).where(
                ResponseAnalysis.response_id == 7120
            )
        )
        == 0
    )
    assert (
        await session.scalar(
            select(func.count(BrandMention.id)).where(BrandMention.response_id == 7120)
        )
        == 0
    )
    assert (
        await session.scalar(
            select(func.count(SentimentDriver.id)).where(
                SentimentDriver.response_id == 7120
            )
        )
        == 0
    )
    assert (
        await session.scalar(
            select(func.count(CitationSource.id)).where(
                CitationSource.response_id == 7120
            )
        )
        == 0
    )
    assert await session.scalar(select(func.count(ProductFeatureMention.id))) == 0


@pytest.mark.asyncio
async def test_apply_competitor_only_topic_evidence_does_not_create_target_visibility(
    session: AsyncSession,
) -> None:
    await _seed_scope(session)
    response = await session.get(LLMResponse, 7120)
    assert response is not None
    response.raw_text = "AcmeGrind is mentioned without the target brand."
    await session.commit()
    await _seed_legacy_evidence(session, target_mentioned=False)

    report = await build_analyzer_v3_backfill_report(
        session,
        AnalyzerV3BackfillScope(response_ids=(7120,), brand_id=24, batch_size=10),
        apply=True,
        approval_ref=APPROVAL_REF,
    )

    assert report["apply_results"][0]["status"] == "done"
    analysis = await session.scalar(
        select(ResponseAnalysis).where(ResponseAnalysis.response_id == 7120)
    )
    assert analysis is not None
    package = analysis.raw_analysis_json["analyzer_fact_package_v3"]
    assert package["visibility"]["is_visible"] is False
    assert package["topic_metrics"]["visible"] is False
    assert package["topic_metrics"]["rank_basis"] == 0
    assert (
        "missing_target_visibility_evidence" in package["topic_metrics"]["reason_codes"]
    )
