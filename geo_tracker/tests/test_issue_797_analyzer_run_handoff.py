"""Issue #797 worker handoff for API-created analyzer runs."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from geo_tracker.analyzer import cli as analyzer_cli
from geo_tracker.db.models import (
    AnalysisStatus,
    AnalyzerRun,
    Base,
    BrandMention,
    ResponseAnalysis,
)
from geo_tracker.tests.test_issue_781_analyzer_v4 import (
    _legacy_projection,
    _patch_pipeline,
    _seed_response,
    _valid_v4_package,
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


@pytest.mark.asyncio
async def test_analyze_single_response_consumes_api_created_run_without_duplicate(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target, response = await _seed_response(session)
    queued_run = AnalyzerRun(
        response_id=response.id,
        status="queued",
        trigger_source="admin_single",
        idempotency_key="reanalyze-797",
    )
    session.add(queued_run)
    await session.commit()
    await session.refresh(queued_run)

    package = _valid_v4_package(response.id, response.query_id)
    _patch_pipeline(monkeypatch, _legacy_projection(package))

    result = await analyzer_cli.analyze_single_response(
        session,
        response,
        target,
        [],
        "non_brand",
        analyzer_run_id=queued_run.id,
        trigger_source="admin_submit",
    )

    assert result["status"] == "done"
    assert await session.scalar(select(func.count(AnalyzerRun.id))) == 1
    assert await session.scalar(select(func.count(ResponseAnalysis.id))) == 1
    assert await session.scalar(select(func.count(BrandMention.id))) == 1
    refreshed = await session.get(AnalyzerRun, queued_run.id)
    assert refreshed is not None
    assert refreshed.status in {"done", "partial"}
    assert refreshed.trigger_source == "admin_single"
    assert response.analysis_status == AnalysisStatus.DONE.value
