from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from geo_tracker.db.models import (
    AnalysisFactLink,
    AnalysisStatus,
    AnalyzerRun,
    Base,
    Brand,
    LLMResponse,
    Prompt,
    Query,
    QueryStatus,
    ResponseAnalysis,
    ResponseEntity,
    ResponseRelationFact,
    Topic,
)
from geo_tracker.tasks import bestcoffer_v4_coverage_repair as v4_repair
from geo_tracker.tasks.bestcoffer_v4_coverage_repair import (
    APPROVAL_REF_HELP,
    BestCofferV4CoverageScope,
    build_bestcoffer_v4_coverage_report,
    validate_approval_ref,
)
from geo_tracker.tests.test_issue_781_analyzer_v4 import _valid_v4_package


PROJECT_ID = "7380c0e0-8798-4a5f-998f-42010a7d9caa"
APPROVAL_REF = "https://github.com/jotamotk/trash_test/issues/827#issuecomment-4449999999"
KICKOFF_REF = "https://github.com/jotamotk/trash_test/issues/827#issuecomment-4444681353"


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                """
                CREATE TABLE project_topic_pins (
                    project_id TEXT NOT NULL,
                    topic_id INTEGER NOT NULL,
                    state TEXT
                )
                """
            )
        )
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as db:
        yield db
    await engine.dispose()


def _approval_fetcher(comment_id: int) -> dict:
    comments = {
        4449999999: {
            "html_url": APPROVAL_REF,
            "issue_url": "https://api.github.com/repos/jotamotk/trash_test/issues/827",
            "author_association": "OWNER",
            "user": {"login": "jotamotk"},
            "body": (
                "AI Lead trusted approval for BestCoffer analyzer v4 run coverage "
                "repair apply. Approved exact response_ids: 82710,82711. "
                "Migrate existing raw analyzer_v4 packages only; reanalysis is not "
                "approved in this comment."
            ),
        },
        4444681353: {
            "html_url": KICKOFF_REF,
            "issue_url": "https://api.github.com/repos/jotamotk/trash_test/issues/827",
            "author_association": "COLLABORATOR",
            "user": {"login": "jotamotk"},
            "body": "Worker assignment for #827. This is not production-write approval.",
        },
    }
    return comments[comment_id]


@pytest.mark.asyncio
async def test_run_cli_opens_task_session_context_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeEngine:
        disposed = False

        async def dispose(self) -> None:
            self.disposed = True

    engine = FakeEngine()
    session_seen = object()

    monkeypatch.setattr(v4_repair, "create_task_engine", lambda: engine)

    @asynccontextmanager
    async def fake_task_session(passed_engine: object):
        assert passed_engine is engine
        yield session_seen

    async def fake_build_report(
        session: object,
        scope: BestCofferV4CoverageScope,
        *,
        mode: str,
        approval_ref: str | None = None,
    ) -> dict:
        assert session is session_seen
        assert scope.project_id == PROJECT_ID
        assert scope.brand_id == 24
        assert scope.competitor_brand_ids == (2,)
        assert scope.response_ids == tuple()
        assert scope.query_ids == tuple()
        assert scope.limit == 500
        assert mode == "export"
        assert approval_ref is None
        return {"ok": True, "mode": mode}

    monkeypatch.setattr(v4_repair, "get_task_async_session", fake_task_session)
    monkeypatch.setattr(v4_repair, "build_bestcoffer_v4_coverage_report", fake_build_report)

    report = await v4_repair._run_cli(
        SimpleNamespace(
            mode="export",
            project_id=PROJECT_ID,
            brand_id="24",
            competitor_brand_ids="2",
            date_from="2026-05-06",
            date_to="2026-05-13",
            response_ids="",
            query_ids="",
            limit="500",
            approval_ref="",
        )
    )

    assert report == {"ok": True, "mode": "export"}
    assert engine.disposed is True


async def _seed_scope(session: AsyncSession, *, pin_topic: bool = True) -> None:
    day = datetime(2026, 5, 12, 10, 0)
    session.add_all(
        [
            Brand(id=24, name="BestCoffer", aliases=["Best Coffer"], industry="coffee"),
            Topic(id=82701, brand_id=24, text="BestCoffer analyzer coverage"),
            Prompt(id=82702, topic_id=82701, text="compare BestCoffer", intent="non_brand"),
        ]
    )
    await session.flush()
    if pin_topic:
        await session.execute(
            text(
                """
                INSERT INTO project_topic_pins (project_id, topic_id, state)
                VALUES (:project_id, :topic_id, 'tracked')
                """
            ),
            {"project_id": PROJECT_ID, "topic_id": 82701},
        )
    session.add_all(
        [
            Query(
                id=82703,
                prompt_id=82702,
                brand_id=24,
                query_text="missing v4 run",
                target_llm="chatgpt",
                status=QueryStatus.DONE.value,
                created_at=day,
            ),
            Query(
                id=82704,
                prompt_id=82702,
                brand_id=24,
                query_text="failed v4 run",
                target_llm="deepseek",
                status=QueryStatus.DONE.value,
                created_at=day,
            ),
            Query(
                id=82705,
                prompt_id=82702,
                brand_id=24,
                query_text="queued v4 run",
                target_llm="chatgpt",
                status=QueryStatus.DONE.value,
                created_at=day,
            ),
            Query(
                id=82706,
                prompt_id=82702,
                brand_id=24,
                query_text="analyzed v4 run",
                target_llm="deepseek",
                status=QueryStatus.DONE.value,
                created_at=day,
            ),
        ]
    )
    await session.flush()
    responses = [
        LLMResponse(
            id=82710,
            query_id=82703,
            raw_text="BestCoffer is mentioned with official support.",
            citations_json=[],
            collected_at=day,
            analysis_status=AnalysisStatus.DONE.value,
        ),
        LLMResponse(
            id=82711,
            query_id=82704,
            raw_text="BestCoffer has a failed latest analyzer run.",
            citations_json=[],
            collected_at=day,
            analysis_status=AnalysisStatus.DONE.value,
        ),
        LLMResponse(
            id=82712,
            query_id=82705,
            raw_text="BestCoffer has a queued latest analyzer run.",
            citations_json=[],
            collected_at=day,
            analysis_status=AnalysisStatus.DONE.value,
        ),
        LLMResponse(
            id=82713,
            query_id=82706,
            raw_text="BestCoffer already has analyzed v4 facts.",
            citations_json=[],
            collected_at=day,
            analysis_status=AnalysisStatus.DONE.value,
        ),
    ]
    session.add_all(responses)
    await session.flush()
    session.add_all(
        [
            ResponseAnalysis(
                id=82720,
                response_id=82710,
                raw_analysis_json=_valid_v4_package(82710, 82703),
            ),
            ResponseAnalysis(
                id=82721,
                response_id=82711,
                raw_analysis_json={"analyzer_fact_package_v3": {"analyzer_version": "v3"}},
            ),
            ResponseAnalysis(
                id=82722,
                response_id=82712,
                raw_analysis_json={},
            ),
            ResponseAnalysis(
                id=82723,
                response_id=82713,
                raw_analysis_json=_valid_v4_package(82713, 82706),
            ),
        ]
    )
    session.add_all(
        [
            AnalyzerRun(
                id=82731,
                response_id=82711,
                schema_version="analyzer_v4",
                status="failed",
                started_at=day,
                completed_at=day,
                failure_code="schema_validation_failed",
                failure_message="legacy failure",
            ),
            AnalyzerRun(
                id=82732,
                response_id=82712,
                schema_version="analyzer_v4",
                status="queued",
                started_at=day,
            ),
            AnalyzerRun(
                id=82733,
                response_id=82713,
                schema_version="analyzer_v4",
                status="done",
                started_at=day,
                completed_at=day,
            ),
            ResponseEntity(
                run_id=82733,
                response_id=82713,
                entity_key="ent_bestcoffer",
                entity_type="brand",
                raw_name="BestCoffer",
                canonicalization_status="matched",
            ),
        ]
    )
    await session.commit()


@pytest.mark.asyncio
async def test_export_buckets_latest_v4_run_state_and_raw_package_flags(
    session: AsyncSession,
) -> None:
    await _seed_scope(session)

    report = await build_bestcoffer_v4_coverage_report(
        session,
        BestCofferV4CoverageScope(
            project_id=PROJECT_ID,
            brand_id=24,
            date_from="2026-05-06",
            date_to="2026-05-13",
        ),
        mode="export",
    )

    assert report["mode"] == "export"
    assert report["write_performed"] is False
    assert report["project_topic_scope_status"] == "tracked_topic_scope"
    assert report["project_topic_ids_count"] == 1
    assert report["bucket_counts"] == {
        "missing_v4_run": 1,
        "latest_v4_failed": 1,
        "latest_v4_other": 1,
        "latest_v4_analyzed": 1,
    }
    rows = {row["response_id"]: row for row in report["rows"]}
    assert rows[82710]["repair_bucket"] == "missing_v4_run"
    assert rows[82710]["raw_packages"]["has_raw_analysis_json"] is True
    assert rows[82710]["raw_packages"]["has_raw_analyzer_v4_package"] is True
    assert rows[82710]["raw_packages"]["has_raw_analyzer_v3_package"] is False
    assert rows[82710]["raw_packages"]["raw_v4_package_valid"] is True
    assert rows[82711]["repair_bucket"] == "latest_v4_failed"
    assert rows[82711]["raw_packages"]["has_raw_analyzer_v3_package"] is True
    assert rows[82712]["repair_bucket"] == "latest_v4_other"
    assert rows[82713]["repair_bucket"] == "latest_v4_analyzed"
    assert rows[82713]["first_class_fact_counts"]["response_entities"] == 1


@pytest.mark.asyncio
async def test_empty_project_topic_pins_export_and_dry_run_use_brand_scope_fallback(
    session: AsyncSession,
) -> None:
    await _seed_scope(session, pin_topic=False)

    report = await build_bestcoffer_v4_coverage_report(
        session,
        BestCofferV4CoverageScope(
            project_id=PROJECT_ID,
            brand_id=24,
            date_from="2026-05-06",
            date_to="2026-05-13",
        ),
        mode="export",
    )

    assert report["project_topic_scope_status"] == "empty_fallback_to_brand_scope"
    assert report["project_topic_ids_count"] == 0
    assert report["selected_response_ids"] == [82710, 82711, 82712, 82713]

    dry_run = await build_bestcoffer_v4_coverage_report(
        session,
        BestCofferV4CoverageScope(
            project_id=PROJECT_ID,
            brand_id=24,
            response_ids=(82710,),
        ),
        mode="dry_run",
    )

    assert dry_run["project_topic_scope_status"] == "empty_fallback_to_brand_scope"
    assert dry_run["project_topic_ids_count"] == 0
    assert dry_run["repair_plan"]["migrate_raw_v4_response_ids"] == [82710]


@pytest.mark.asyncio
async def test_dry_run_reports_migration_vs_reanalysis_without_writes(
    session: AsyncSession,
) -> None:
    await _seed_scope(session)

    report = await build_bestcoffer_v4_coverage_report(
        session,
        BestCofferV4CoverageScope(
            project_id=PROJECT_ID,
            brand_id=24,
            response_ids=(82710, 82711),
        ),
        mode="dry_run",
    )

    assert report["mode"] == "dry_run"
    assert report["write_performed"] is False
    assert report["repair_plan"]["migrate_raw_v4_response_ids"] == [82710]
    assert report["repair_plan"]["reanalysis_required_response_ids"] == [82711]
    assert report["repair_plan"]["actions_by_response"][82710]["action"] == "migrate_raw_v4_package"
    assert report["repair_plan"]["actions_by_response"][82711]["action"] == "reanalysis_required"
    assert await session.scalar(select(func.count(AnalyzerRun.id))) == 3


@pytest.mark.asyncio
async def test_apply_migrates_raw_v4_package_idempotently_and_requires_trusted_approval(
    session: AsyncSession,
) -> None:
    await _seed_scope(session)

    with pytest.raises(ValueError, match="production-write approval"):
        validate_approval_ref(KICKOFF_REF, approval_comment_fetcher=_approval_fetcher)

    first = await build_bestcoffer_v4_coverage_report(
        session,
        BestCofferV4CoverageScope(
            project_id=PROJECT_ID,
            brand_id=24,
            response_ids=(82710,),
        ),
        mode="apply",
        approval_ref=APPROVAL_REF,
        approval_comment_fetcher=_approval_fetcher,
    )
    second = await build_bestcoffer_v4_coverage_report(
        session,
        BestCofferV4CoverageScope(
            project_id=PROJECT_ID,
            brand_id=24,
            response_ids=(82710,),
        ),
        mode="apply",
        approval_ref=APPROVAL_REF,
        approval_comment_fetcher=_approval_fetcher,
    )

    assert first["write_performed"] is True
    assert first["repair_plan"]["migrated_response_ids"] == [82710]
    assert second["write_performed"] is False
    assert second["repair_plan"]["already_satisfied_response_ids"] == [82710]
    assert await session.scalar(select(func.count(AnalyzerRun.id))) == 4
    assert await session.scalar(select(func.count(ResponseEntity.id))) == 3
    assert await session.scalar(select(func.count(ResponseRelationFact.id))) == 1
    assert await session.scalar(select(func.count(AnalysisFactLink.id))) == 2


def test_apply_requires_exact_ids_and_approval() -> None:
    scope = BestCofferV4CoverageScope(
        project_id=PROJECT_ID,
        brand_id=24,
        date_from="2026-05-06",
        date_to="2026-05-13",
    )
    assert "exact response_ids" in APPROVAL_REF_HELP
    with pytest.raises(ValueError, match="apply mode requires explicit response_ids"):
        scope.validate(mode="apply")


def test_approval_ref_matches_exact_numeric_response_id_tokens() -> None:
    def fetcher(comment_id: int) -> dict:
        bodies = {
            4449000001: (
                "AI Lead trusted approval for BestCoffer analyzer v4 run coverage "
                "repair apply. Approved exact response_ids: 82710."
            ),
            4449000002: (
                "AI Lead trusted approval for BestCoffer analyzer v4 run coverage "
                "repair apply. Approved exact response_ids: 827101."
            ),
            4449000003: (
                "AI Lead trusted approval for BestCoffer analyzer v4 run coverage "
                "repair apply. Approved exact response_ids:\n82710, 82711\n82712"
            ),
        }
        ref = f"https://github.com/jotamotk/trash_test/issues/827#issuecomment-{comment_id}"
        return {
            "html_url": ref,
            "issue_url": "https://api.github.com/repos/jotamotk/trash_test/issues/827",
            "author_association": "OWNER",
            "user": {"login": "jotamotk"},
            "body": bodies[comment_id],
        }

    with pytest.raises(ValueError, match="missing=\\[8271\\]"):
        validate_approval_ref(
            "https://github.com/jotamotk/trash_test/issues/827#issuecomment-4449000001",
            approval_comment_fetcher=fetcher,
            response_ids=(8271,),
        )
    with pytest.raises(ValueError, match="missing=\\[82710\\]"):
        validate_approval_ref(
            "https://github.com/jotamotk/trash_test/issues/827#issuecomment-4449000002",
            approval_comment_fetcher=fetcher,
            response_ids=(82710,),
        )

    approved = validate_approval_ref(
        "https://github.com/jotamotk/trash_test/issues/827#issuecomment-4449000003",
        approval_comment_fetcher=fetcher,
        response_ids=(82710, 82711, 82712),
    )
    assert approved.endswith("4449000003")


def test_approval_ref_ignores_unrelated_numeric_tokens_outside_response_ids_block() -> None:
    def fetcher(comment_id: int) -> dict:
        ref = f"https://github.com/jotamotk/trash_test/issues/827#issuecomment-{comment_id}"
        return {
            "html_url": ref,
            "issue_url": "https://api.github.com/repos/jotamotk/trash_test/issues/827",
            "author_association": "OWNER",
            "user": {"login": "jotamotk"},
            "body": (
                "AI Lead trusted approval for BestCoffer analyzer v4 run coverage "
                "repair apply.\n"
                "Refs #827 #760 #753 #752 #714.\n"
                "Dry-run evidence date 2026-05-13, run 25821941549, "
                "selected_count=82710.\n"
                "Approved exact response_ids: 82711, 82712"
            ),
        }

    with pytest.raises(ValueError, match="missing=\\[82710\\]"):
        validate_approval_ref(
            "https://github.com/jotamotk/trash_test/issues/827#issuecomment-4449000004",
            approval_comment_fetcher=fetcher,
            response_ids=(82710,),
        )

    approved = validate_approval_ref(
        "https://github.com/jotamotk/trash_test/issues/827#issuecomment-4449000004",
        approval_comment_fetcher=fetcher,
        response_ids=(82711, 82712),
    )
    assert approved.endswith("4449000004")


@pytest.mark.asyncio
async def test_project_topic_scope_sql_error_fails_closed() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as db:
        await _seed_scope(db, pin_topic=False)

        with pytest.raises(ValueError, match="project topic scope"):
            await build_bestcoffer_v4_coverage_report(
                db,
                BestCofferV4CoverageScope(
                    project_id=PROJECT_ID,
                    brand_id=24,
                    date_from="2026-05-06",
                    date_to="2026-05-13",
                ),
                mode="export",
            )

        with pytest.raises(ValueError, match="project topic scope"):
            await build_bestcoffer_v4_coverage_report(
                db,
                BestCofferV4CoverageScope(
                    project_id=PROJECT_ID,
                    brand_id=24,
                    response_ids=(82710,),
                ),
                mode="apply",
                approval_ref=APPROVAL_REF,
                approval_comment_fetcher=_approval_fetcher,
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_empty_pins_exact_ids_outside_brand_scope_are_blocked(
    session: AsyncSession,
) -> None:
    await _seed_scope(session, pin_topic=False)
    day = datetime(2026, 5, 12, 11, 0)
    session.add_all(
        [
            Brand(id=99, name="Outside Brand", aliases=[], industry="coffee"),
            Topic(id=82790, brand_id=99, text="Outside brand topic"),
            Prompt(id=82791, topic_id=82790, text="outside prompt", intent="non_brand"),
            Query(
                id=82792,
                prompt_id=82791,
                brand_id=99,
                query_text="outside brand response",
                target_llm="chatgpt",
                status=QueryStatus.DONE.value,
                created_at=day,
            ),
            LLMResponse(
                id=82714,
                query_id=82792,
                raw_text="Outside brand appears without BestCoffer scope.",
                citations_json=[],
                collected_at=day,
                analysis_status=AnalysisStatus.DONE.value,
            ),
            ResponseAnalysis(
                id=82724,
                response_id=82714,
                raw_analysis_json=_valid_v4_package(82714, 82792),
            ),
        ]
    )
    await session.commit()

    with pytest.raises(ValueError, match="blocked response_ids=\\[82714\\]"):
        await build_bestcoffer_v4_coverage_report(
            session,
            BestCofferV4CoverageScope(
                project_id=PROJECT_ID,
                brand_id=24,
                response_ids=(82714,),
            ),
            mode="dry_run",
        )

    def fetcher(comment_id: int) -> dict:
        ref = f"https://github.com/jotamotk/trash_test/issues/827#issuecomment-{comment_id}"
        return {
            "html_url": ref,
            "issue_url": "https://api.github.com/repos/jotamotk/trash_test/issues/827",
            "author_association": "OWNER",
            "user": {"login": "jotamotk"},
            "body": (
                "AI Lead trusted approval for BestCoffer analyzer v4 run coverage "
                "repair apply. Approved exact response_ids: 82714."
            ),
        }

    with pytest.raises(ValueError, match="blocked response_ids=\\[82714\\]"):
        await build_bestcoffer_v4_coverage_report(
            session,
            BestCofferV4CoverageScope(
                project_id=PROJECT_ID,
                brand_id=24,
                response_ids=(82714,),
            ),
            mode="apply",
            approval_ref="https://github.com/jotamotk/trash_test/issues/827#issuecomment-4449000006",
            approval_comment_fetcher=fetcher,
        )


@pytest.mark.asyncio
async def test_exact_response_apply_blocks_ids_outside_verified_project_topics(
    session: AsyncSession,
) -> None:
    await _seed_scope(session)
    day = datetime(2026, 5, 12, 11, 0)
    session.add_all(
        [
            Topic(id=82790, brand_id=24, text="Unpinned BestCoffer topic"),
            Prompt(id=82791, topic_id=82790, text="unpinned prompt", intent="non_brand"),
            Query(
                id=82792,
                prompt_id=82791,
                brand_id=24,
                query_text="unpinned response",
                target_llm="chatgpt",
                status=QueryStatus.DONE.value,
                created_at=day,
            ),
            LLMResponse(
                id=82714,
                query_id=82792,
                raw_text="BestCoffer appears outside the pinned project topic scope.",
                citations_json=[],
                collected_at=day,
                analysis_status=AnalysisStatus.DONE.value,
            ),
            ResponseAnalysis(
                id=82724,
                response_id=82714,
                raw_analysis_json=_valid_v4_package(82714, 82792),
            ),
        ]
    )
    await session.commit()

    with pytest.raises(ValueError, match="blocked response_ids=\\[82714\\]"):
        await build_bestcoffer_v4_coverage_report(
            session,
            BestCofferV4CoverageScope(
                project_id=PROJECT_ID,
                brand_id=24,
                response_ids=(82714,),
            ),
            mode="dry_run",
        )

    def fetcher(comment_id: int) -> dict:
        ref = f"https://github.com/jotamotk/trash_test/issues/827#issuecomment-{comment_id}"
        return {
            "html_url": ref,
            "issue_url": "https://api.github.com/repos/jotamotk/trash_test/issues/827",
            "author_association": "OWNER",
            "user": {"login": "jotamotk"},
            "body": (
                "AI Lead trusted approval for BestCoffer analyzer v4 run coverage "
                "repair apply. Approved exact response_ids: 82714."
            ),
        }

    with pytest.raises(ValueError, match="blocked response_ids=\\[82714\\]"):
        await build_bestcoffer_v4_coverage_report(
            session,
            BestCofferV4CoverageScope(
                project_id=PROJECT_ID,
                brand_id=24,
                response_ids=(82714,),
            ),
            mode="apply",
            approval_ref="https://github.com/jotamotk/trash_test/issues/827#issuecomment-4449000005",
            approval_comment_fetcher=fetcher,
        )


@pytest.mark.asyncio
async def test_apply_rebuilds_partial_existing_migration_run_without_duplicate_facts(
    session: AsyncSession,
) -> None:
    await _seed_scope(session)

    first = await build_bestcoffer_v4_coverage_report(
        session,
        BestCofferV4CoverageScope(
            project_id=PROJECT_ID,
            brand_id=24,
            response_ids=(82710,),
        ),
        mode="apply",
        approval_ref=APPROVAL_REF,
        approval_comment_fetcher=_approval_fetcher,
    )
    run_id = first["repair_plan"]["created_analyzer_run_ids"][0]
    await session.execute(delete(AnalysisFactLink).where(AnalysisFactLink.run_id == run_id))
    await session.commit()

    second = await build_bestcoffer_v4_coverage_report(
        session,
        BestCofferV4CoverageScope(
            project_id=PROJECT_ID,
            brand_id=24,
            response_ids=(82710,),
        ),
        mode="apply",
        approval_ref=APPROVAL_REF,
        approval_comment_fetcher=_approval_fetcher,
    )

    assert second["write_performed"] is True
    assert second["repair_plan"]["rebuilt_existing_run_ids"] == [run_id]
    assert await session.scalar(select(func.count(AnalyzerRun.id))) == 4
    assert await session.scalar(
        select(func.count(AnalysisFactLink.id)).where(AnalysisFactLink.run_id == run_id)
    ) == 2
    assert await session.scalar(
        select(func.count(ResponseEntity.id)).where(ResponseEntity.run_id == run_id)
    ) == 2
