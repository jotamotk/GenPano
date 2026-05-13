from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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
    Topic,
)
from geo_tracker.tasks.bestcoffer_citation_geo_followup import (
    APPROVAL_REF_HELP,
    BestCofferCitationGeoScope,
    build_bestcoffer_citation_geo_followup_report,
    validate_approval_ref,
)

APPROVAL_REF = (
    "https://github.com/jotamotk/trash_test/issues/760#issuecomment-4439999999"
)
CITATION_ONLY_APPROVAL_REF = (
    "https://github.com/jotamotk/trash_test/issues/760#issuecomment-4439999998"
)
KICKOFF_REF = (
    "https://github.com/jotamotk/trash_test/issues/760#issuecomment-4439507284"
)
WRONG_ISSUE_REF = (
    "https://github.com/jotamotk/trash_test/issues/711#issuecomment-4436999999"
)
APPROVAL_BODY = (
    "AI Lead approved production writes for BestCoffer citation GEO materialization "
    "apply for response_ids=7610. Aggregate recompute approved for brand_id=24, "
    "dates=2026-05-12."
)
CITATION_ONLY_APPROVAL_BODY = (
    "AI Lead approved production writes for BestCoffer citation GEO materialization "
    "apply for response_ids=7610. Daily rollup permission is outside this approval."
)
KICKOFF_BODY = (
    "Owner Agent: pipeline-data-agent. Goal: implement #760 pipeline/data fix. "
    "This is a dispatch/kickoff comment, not production-write approval."
)


def _approval_fetcher(comment_id: int) -> dict:
    comments = {
        4439999999: {
            "html_url": APPROVAL_REF,
            "issue_url": "https://api.github.com/repos/jotamotk/trash_test/issues/760",
            "body": APPROVAL_BODY,
            "user": {"login": "jotamotk"},
        },
        4439999998: {
            "html_url": CITATION_ONLY_APPROVAL_REF,
            "issue_url": "https://api.github.com/repos/jotamotk/trash_test/issues/760",
            "body": CITATION_ONLY_APPROVAL_BODY,
            "user": {"login": "jotamotk"},
        },
        4439507284: {
            "html_url": KICKOFF_REF,
            "issue_url": "https://api.github.com/repos/jotamotk/trash_test/issues/760",
            "body": KICKOFF_BODY,
            "user": {"login": "jotamotk"},
        },
    }
    return comments[comment_id]


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
            Brand(id=2, name="AcmeGrind", aliases=["Acme Grind"], industry="coffee"),
            Brand(id=24, name="BestCoffer", aliases=["Best Coffer"], industry="coffee"),
            Topic(id=7601, brand_id=24, text="Office coffee", category="category"),
            Prompt(
                id=7602,
                topic_id=7601,
                text="best office coffee machines",
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
                id=7603,
                prompt_id=7602,
                brand_id=24,
                query_text="best office coffee machine",
                target_llm="chatgpt",
                status=QueryStatus.DONE.value,
                created_at=day,
            ),
            Query(
                id=7604,
                prompt_id=7602,
                brand_id=24,
                query_text="missing analyzer row",
                target_llm="deepseek",
                status=QueryStatus.DONE.value,
                created_at=day,
            ),
            Query(
                id=7605,
                prompt_id=7602,
                brand_id=24,
                query_text="invalid login shell",
                target_llm="chatgpt",
                status=QueryStatus.DONE.value,
                created_at=day,
            ),
            Query(
                id=7606,
                prompt_id=7602,
                brand_id=24,
                query_text="failed query excluded",
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
                id=7610,
                query_id=7603,
                raw_text="BestCoffer and AcmeGrind are compared for office coffee.",
                citations_json=[],
                response_time_ms=900,
                collected_at=day,
                analysis_status=AnalysisStatus.DONE.value,
            ),
            LLMResponse(
                id=7611,
                query_id=7604,
                raw_text="BestCoffer has a compact office setup.",
                citations_json=[],
                response_time_ms=800,
                collected_at=day,
                analysis_status=AnalysisStatus.DONE.value,
            ),
            LLMResponse(
                id=7612,
                query_id=7605,
                raw_text="Sign in to ChatGPT Continue with Google Continue with Microsoft",
                citations_json=[],
                response_time_ms=200,
                collected_at=day,
                analysis_status=AnalysisStatus.PENDING.value,
            ),
            LLMResponse(
                id=7613,
                query_id=7606,
                raw_text="BestCoffer failed query artifact",
                citations_json=[],
                response_time_ms=200,
                collected_at=day,
                analysis_status=AnalysisStatus.PENDING.value,
            ),
        ]
    )
    await session.flush()
    session.add_all(
        [
            BrandMention(
                id=7620,
                response_id=7610,
                brand_id=24,
                brand_name="BestCoffer",
                is_target=True,
                position_type="first_recommendation",
                position_rank=1,
                detail_level="detailed",
                sentiment="positive",
                sentiment_score=0.9,
                mention_count=1,
            ),
            BrandMention(
                id=7621,
                response_id=7610,
                brand_id=2,
                brand_name="AcmeGrind",
                is_target=False,
                position_type="ranked",
                position_rank=2,
                detail_level="brief",
                sentiment="neutral",
                sentiment_score=0.5,
                mention_count=1,
            ),
        ]
    )
    await session.flush()
    session.add(
        ResponseAnalysis(
            id=7630,
            response_id=7610,
            dimension_industry="coffee",
            dimension_category="category",
            target_brand_mentioned=True,
            target_brand_sentiment="positive",
            visibility_score=80,
            sentiment_score=90,
            sov_score=50,
            citation_score=0,
            geo_score=0,
            analyzed_at=day,
            raw_analysis_json={
                "analyzer_fact_package_v3": {
                    "analyzer_version": "v3",
                    "response_id": 7610,
                    "query_id": 7603,
                    "target_brand_id": 24,
                    "citations": {
                        "total_citations": 2,
                        "attributed_citations": [],
                        "unresolved_citations": [
                            {
                                "url": "https://coffee.example/bestcoffer-review",
                                "domain": "coffee.example",
                                "title": "BestCoffer review",
                                "citation_index": 1,
                                "source_type": "article",
                                "brand_name": "BestCoffer",
                                "mention_id": None,
                            },
                            {
                                "url": "https://coffee.example/general-guide",
                                "domain": "coffee.example",
                                "title": "General guide",
                                "citation_index": 2,
                                "source_type": "article",
                                "brand_name": None,
                                "mention_id": None,
                            },
                        ],
                        "formula_status": "partial",
                        "reason_codes": ["citation_sources.mention_id"],
                    },
                    "citation_facts": [
                        {
                            "url": "https://coffee.example/bestcoffer-review",
                            "domain": "coffee.example",
                            "title": "BestCoffer review",
                            "brand_name": "BestCoffer",
                            "mention_id": None,
                            "missing_inputs": ["citation_sources.mention_id"],
                        }
                    ],
                }
            },
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_dry_run_reports_exact_missing_analyzer_rows_and_safety(
    session: AsyncSession,
) -> None:
    await _seed_scope(session)

    report = await build_bestcoffer_citation_geo_followup_report(
        session,
        BestCofferCitationGeoScope(
            project_id="7380c0e0-8798-4a5f-998f-42010a7d9caa",
            brand_id=24,
            competitor_brand_ids=(2,),
            date_from="2026-05-12",
            date_to="2026-05-12",
            limit=10,
        ),
    )

    assert report["issue"] == 760
    assert report["mode"] == "dry_run"
    assert report["write_performed"] is False
    assert report["safe_selection"]["successful_responses_only"] is True
    assert report["safe_selection"]["invalid_artifacts_excluded"] is True
    assert report["selected_response_ids"] == [7610, 7611]
    assert report["missing_analyzer_response_ids"] == [7611]
    assert report["before"]["candidate_count"] == 3
    assert report["before"]["excluded_invalid_count"] == 1
    assert report["before"]["excluded_rows"][0]["invalid_reason"] == "chatgpt_auth_redirect"
    assert report["citation_plan"]["candidate_citation_count"] == 2
    assert report["citation_plan"]["resolvable_citation_count"] == 1
    assert report["citation_plan"]["unresolved_citation_count"] == 1
    assert report["aggregate_plan"]["dates"] == ["2026-05-12"]
    assert report["aggregate_plan"]["full_brand_date_side_effects"] is True
    assert report["aggregate_plan"]["requires_separate_aggregate_approval"] is True

    citation_count = (
        await session.execute(select(func.count()).select_from(CitationSource))
    ).scalar_one()
    assert citation_count == 0


@pytest.mark.asyncio
async def test_apply_materializes_attributable_citations_and_geo_rows_idempotently(
    session: AsyncSession,
) -> None:
    await _seed_scope(session)

    report = await build_bestcoffer_citation_geo_followup_report(
        session,
        BestCofferCitationGeoScope(
            project_id="7380c0e0-8798-4a5f-998f-42010a7d9caa",
            brand_id=24,
            competitor_brand_ids=(2,),
            response_ids=(7610,),
            date_from="2026-05-12",
            date_to="2026-05-12",
            limit=10,
        ),
        apply=True,
        aggregate=True,
        approval_ref=APPROVAL_REF,
        approval_comment_fetcher=_approval_fetcher,
        aggregate_approval_ref=APPROVAL_REF,
    )

    assert report["write_performed"] is True
    assert report["citation_plan"]["insert_citation_source_count"] == 2
    assert report["citation_plan"]["resolved_existing_citation_source_count"] == 0
    assert report["citation_plan"]["patched_response_analysis_count"] == 1
    assert report["aggregate_results"][0]["stats"]["geo_score_daily"] == 2
    assert report["aggregate_approval_ref"] == APPROVAL_REF
    assert report["aggregate_plan"]["approved_dates"] == ["2026-05-12"]
    assert report["no_fallback_values"] is True

    citations = (
        await session.execute(
            select(CitationSource).order_by(CitationSource.citation_index.asc())
        )
    ).scalars().all()
    assert len(citations) == 2
    assert citations[0].mention_id == 7620
    assert citations[1].mention_id is None

    analysis = (
        await session.execute(
            select(ResponseAnalysis).where(ResponseAnalysis.response_id == 7610)
        )
    ).scalar_one()
    package = analysis.raw_analysis_json["analyzer_fact_package_v3"]
    assert package["citations"]["attributed_citations"][0]["mention_id"] == 7620
    assert package["citations"]["attributed_citations"][0]["citation_id"] == citations[0].id
    assert package["citations"]["unresolved_citations"][0]["url"].endswith("general-guide")
    assert package["citations"]["formula_status"] == "partial"
    assert package["citation_facts"][0]["mention_id"] == 7620
    assert package["citation_facts"][0]["missing_inputs"] == []

    geo_rows = (
        await session.execute(select(GEOScoreDaily).where(GEOScoreDaily.brand_id == 24))
    ).scalars().all()
    assert len(geo_rows) == 2
    assert any(row.citation_rate == 1.0 for row in geo_rows)

    second = await build_bestcoffer_citation_geo_followup_report(
        session,
        BestCofferCitationGeoScope(
            project_id="7380c0e0-8798-4a5f-998f-42010a7d9caa",
            brand_id=24,
            competitor_brand_ids=(2,),
            response_ids=(7610,),
            date_from="2026-05-12",
            date_to="2026-05-12",
            limit=10,
        ),
        apply=True,
        aggregate=True,
        approval_ref=APPROVAL_REF,
        approval_comment_fetcher=_approval_fetcher,
        aggregate_approval_ref=APPROVAL_REF,
    )
    assert second["citation_plan"]["insert_citation_source_count"] == 0
    assert (
        await session.execute(select(func.count()).select_from(CitationSource))
    ).scalar_one() == 2


@pytest.mark.asyncio
async def test_apply_resolves_existing_unattributed_citation_rows_without_duplicates(
    session: AsyncSession,
) -> None:
    await _seed_scope(session)
    session.add_all(
        [
            CitationSource(
                response_id=7610,
                mention_id=None,
                url="https://coffee.example/bestcoffer-review",
                domain="coffee.example",
                title="BestCoffer review",
                citation_index=1,
                source_type="article",
            ),
            CitationSource(
                response_id=7610,
                mention_id=None,
                url="https://coffee.example/general-guide",
                domain="coffee.example",
                title="General guide",
                citation_index=2,
                source_type="article",
            ),
        ]
    )
    await session.commit()

    report = await build_bestcoffer_citation_geo_followup_report(
        session,
        BestCofferCitationGeoScope(
            project_id="7380c0e0-8798-4a5f-998f-42010a7d9caa",
            brand_id=24,
            competitor_brand_ids=(2,),
            response_ids=(7610,),
            date_from="2026-05-12",
            date_to="2026-05-12",
            limit=10,
        ),
        apply=True,
        approval_ref=APPROVAL_REF,
        approval_comment_fetcher=_approval_fetcher,
    )

    assert report["citation_plan"]["insert_citation_source_count"] == 0
    assert report["citation_plan"]["resolved_existing_citation_source_count"] == 1
    assert report["citation_plan"]["patched_response_analysis_count"] == 1
    assert (
        await session.execute(select(func.count()).select_from(CitationSource))
    ).scalar_one() == 2

    citations = (
        await session.execute(
            select(CitationSource).order_by(CitationSource.citation_index.asc())
        )
    ).scalars().all()
    assert citations[0].mention_id == 7620
    assert citations[1].mention_id is None


@pytest.mark.asyncio
async def test_apply_preserves_unresolved_fact_when_existing_citation_row_conflicts(
    session: AsyncSession,
) -> None:
    await _seed_scope(session)
    session.add(
        CitationSource(
            response_id=7610,
            mention_id=7621,
            url="https://coffee.example/bestcoffer-review",
            domain="coffee.example",
            title="BestCoffer review",
            citation_index=1,
            source_type="article",
        )
    )
    await session.commit()

    report = await build_bestcoffer_citation_geo_followup_report(
        session,
        BestCofferCitationGeoScope(
            project_id="7380c0e0-8798-4a5f-998f-42010a7d9caa",
            brand_id=24,
            competitor_brand_ids=(2,),
            response_ids=(7610,),
            date_from="2026-05-12",
            date_to="2026-05-12",
            limit=10,
        ),
        apply=True,
        approval_ref=APPROVAL_REF,
        approval_comment_fetcher=_approval_fetcher,
    )

    assert report["citation_plan"]["conflicting_existing_citation_source_count"] == 1
    analysis = (
        await session.execute(
            select(ResponseAnalysis).where(ResponseAnalysis.response_id == 7610)
        )
    ).scalar_one()
    package = analysis.raw_analysis_json["analyzer_fact_package_v3"]
    assert package["citations"]["attributed_citations"] == []
    bestcoffer_citation = [
        row
        for row in package["citations"]["unresolved_citations"]
        if row["url"].endswith("bestcoffer-review")
    ][0]
    assert bestcoffer_citation["mention_id"] is None
    assert bestcoffer_citation.get("citation_id") is None


@pytest.mark.asyncio
async def test_apply_requires_explicit_ids_and_issue_760_approval(
    session: AsyncSession,
) -> None:
    await _seed_scope(session)

    with pytest.raises(ValueError, match="explicit response_ids or query_ids"):
        await build_bestcoffer_citation_geo_followup_report(
            session,
            BestCofferCitationGeoScope(
                project_id="7380c0e0-8798-4a5f-998f-42010a7d9caa",
                brand_id=24,
                competitor_brand_ids=(2,),
                date_from="2026-05-12",
                date_to="2026-05-12",
            ),
            apply=True,
            approval_ref=APPROVAL_REF,
            approval_comment_fetcher=_approval_fetcher,
        )

    with pytest.raises(ValueError, match="approval_ref"):
        await build_bestcoffer_citation_geo_followup_report(
            session,
            BestCofferCitationGeoScope(
                project_id="7380c0e0-8798-4a5f-998f-42010a7d9caa",
                brand_id=24,
                competitor_brand_ids=(2,),
                response_ids=(7610,),
                date_from="2026-05-12",
                date_to="2026-05-12",
            ),
            apply=True,
            approval_ref=None,
            approval_comment_fetcher=_approval_fetcher,
        )


@pytest.mark.asyncio
async def test_aggregate_apply_requires_date_scoped_approval(
    session: AsyncSession,
) -> None:
    await _seed_scope(session)

    with pytest.raises(ValueError, match="aggregate_approval_ref"):
        await build_bestcoffer_citation_geo_followup_report(
            session,
            BestCofferCitationGeoScope(
                project_id="7380c0e0-8798-4a5f-998f-42010a7d9caa",
                brand_id=24,
                competitor_brand_ids=(2,),
                response_ids=(7610,),
                date_from="2026-05-12",
                date_to="2026-05-12",
            ),
            apply=True,
            aggregate=True,
            approval_ref=CITATION_ONLY_APPROVAL_REF,
            approval_comment_fetcher=_approval_fetcher,
        )


def test_approval_ref_accepts_issue_760_production_write_evidence() -> None:
    assert (
        validate_approval_ref(APPROVAL_REF, approval_comment_fetcher=_approval_fetcher)
        == APPROVAL_REF
    )


@pytest.mark.parametrize(
    "approval_ref",
    [
        "",
        f"{KICKOFF_REF} AI Lead approved production writes for BestCoffer citation GEO materialization apply",
        KICKOFF_REF,
        WRONG_ISSUE_REF,
    ],
)
def test_approval_ref_rejects_missing_issue_760_write_evidence(
    approval_ref: str,
) -> None:
    with pytest.raises(ValueError, match="approval_ref"):
        validate_approval_ref(approval_ref, approval_comment_fetcher=_approval_fetcher)


def test_approval_help_mentions_dry_run_first() -> None:
    assert "Dry-run first" in APPROVAL_REF_HELP
