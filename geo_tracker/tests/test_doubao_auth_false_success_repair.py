from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from geo_tracker.db.models import AnalysisStatus, Base, LLMResponse, Query, QueryStatus


async def _session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return maker()


async def test_known_doubao_false_success_repair_dry_run_does_not_write():
    from geo_tracker.tasks.doubao_auth_false_success_repair import (
        repair_known_doubao_auth_false_successes,
    )

    async with await _session() as session:
        finished_at = datetime(2026, 5, 12, 9, 42, 11, 123456)
        query = Query(
            id=184409,
            target_llm="doubao",
            query_text="bestCoffer",
            status=QueryStatus.DONE.value,
            finished_at=finished_at,
        )
        response = LLMResponse(
            id=532,
            query_id=184409,
            raw_text="answer-like unauthenticated text",
            response_html="<header><div>登录</div></header>",
            analysis_status=AnalysisStatus.DONE.value,
        )
        session.add_all([query, response])
        await session.commit()

        report = await repair_known_doubao_auth_false_successes(
            session,
            apply=False,
            approval_ref="Refs #594 dry-run",
        )
        await session.refresh(query)
        await session.refresh(response)

        assert report.candidate_query_ids == [184409]
        assert report.repaired_query_ids == []
        assert query.status == QueryStatus.DONE.value
        assert query.finished_at == finished_at
        assert response.analysis_status == AnalysisStatus.DONE.value
        assert "rollback_doubao_auth_false_success" in report.rollback_sql[0]
        assert "finished_at = '2026-05-12 09:42:11.123456'" in report.rollback_sql[0]


async def test_known_doubao_false_success_repair_marks_failed_without_deleting_response():
    from geo_tracker.tasks.doubao_auth_false_success_repair import (
        repair_known_doubao_auth_false_successes,
    )

    async with await _session() as session:
        query = Query(
            id=184518,
            target_llm="doubao",
            query_text="bestCoffer",
            status=QueryStatus.DONE.value,
        )
        response = LLMResponse(
            id=900,
            query_id=184518,
            raw_text="answer-like unauthenticated text",
            response_html="<header><div>登录</div></header>",
            analysis_status=AnalysisStatus.DONE.value,
        )
        session.add_all([query, response])
        await session.commit()

        report = await repair_known_doubao_auth_false_successes(
            session,
            apply=True,
            approval_ref="Refs #594",
        )
        await session.refresh(query)
        await session.refresh(response)

        assert report.repaired_query_ids == [184518]
        assert "finished_at = NULL" in report.rollback_sql[0]
        assert query.status == QueryStatus.FAILED.value
        assert query.retry_reason == "doubao_not_logged_in:false_success_repair:#594"
        assert response.analysis_status == AnalysisStatus.FAILED.value
        assert response.raw_text == "answer-like unauthenticated text"


async def test_repair_rejects_unknown_query_id_override_without_writing():
    from geo_tracker.tasks.doubao_auth_false_success_repair import (
        repair_known_doubao_auth_false_successes,
    )

    async with await _session() as session:
        query = Query(
            id=999999,
            target_llm="doubao",
            query_text="unreviewed query",
            status=QueryStatus.DONE.value,
        )
        response = LLMResponse(
            id=999001,
            query_id=999999,
            raw_text="answer-like text from a query that is not in #594 evidence",
            response_html="<header><div>\u767b\u5f55</div></header>",
            analysis_status=AnalysisStatus.DONE.value,
        )
        session.add_all([query, response])
        await session.commit()

        with pytest.raises(ValueError, match="unsupported query_id"):
            await repair_known_doubao_auth_false_successes(
                session,
                apply=True,
                approval_ref="Refs #594",
                query_ids=[999999],
            )

        await session.refresh(query)
        await session.refresh(response)

        assert query.status == QueryStatus.DONE.value
        assert query.retry_reason is None
        assert response.analysis_status == AnalysisStatus.DONE.value
