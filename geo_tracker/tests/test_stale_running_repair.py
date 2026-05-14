from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from geo_tracker.db.models import Base, LLMResponse, Query, QueryStatus
from geo_tracker.tasks.stale_running_repair import (
    repair_stale_pending_dispatch_queries,
    repair_stale_running_queries,
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


def _query(
    query_id: int,
    *,
    brand_id: int = 24,
    target_llm: str = "deepseek",
    status: str = QueryStatus.RUNNING.value,
    event_at: datetime,
) -> Query:
    return Query(
        id=query_id,
        brand_id=brand_id,
        target_llm=target_llm,
        query_text=f"bestCoffer validation query {query_id}",
        status=status,
        queued_at=event_at,
        started_at=event_at,
        executed_at=event_at,
        created_at=event_at,
    )


@pytest.mark.asyncio
async def test_stale_running_no_response_becomes_failed_with_auditable_reason(
    session: AsyncSession,
) -> None:
    now = datetime(2026, 5, 12, 12, 0, 0)
    stale_no_response = _query(184555, event_at=now - timedelta(hours=2))
    fresh_no_response = _query(184556, event_at=now - timedelta(minutes=5))
    other_brand = _query(184557, brand_id=25, event_at=now - timedelta(hours=2))
    session.add_all([stale_no_response, fresh_no_response, other_brand])
    await session.commit()

    dry_run = await repair_stale_running_queries(
        session,
        brand_id=24,
        max_age_seconds=3600,
        now=now,
        dry_run=True,
    )

    assert dry_run.matched == 1
    assert dry_run.repaired == 0
    assert dry_run.query_ids == [184555]

    applied = await repair_stale_running_queries(
        session,
        brand_id=24,
        max_age_seconds=3600,
        now=now,
    )

    assert applied.matched == 1
    assert applied.repaired == 1
    assert applied.by_engine == {"deepseek": 1}

    await session.refresh(stale_no_response)
    await session.refresh(fresh_no_response)
    await session.refresh(other_brand)
    assert stale_no_response.status == QueryStatus.FAILED.value
    assert stale_no_response.retry_reason == "stale_running_timeout"
    assert stale_no_response.finished_at == now
    assert stale_no_response.latency_ms == 7_200_000
    assert fresh_no_response.status == QueryStatus.RUNNING.value
    assert other_brand.status == QueryStatus.RUNNING.value

    candidate_ids = (
        await session.execute(
            select(Query.id)
            .where(Query.brand_id == 24)
            .where(Query.status.in_([QueryStatus.PENDING.value, QueryStatus.FAILED.value]))
            .where(~exists().where(LLMResponse.query_id == Query.id))
        )
    ).scalars().all()
    assert candidate_ids == [184555]


@pytest.mark.asyncio
async def test_stale_running_with_existing_response_is_not_destroyed(
    session: AsyncSession,
) -> None:
    now = datetime(2026, 5, 12, 12, 0, 0)
    responded = _query(184600, target_llm="chatgpt", event_at=now - timedelta(hours=3))
    no_response = _query(184601, target_llm="chatgpt", event_at=now - timedelta(hours=3))
    response = LLMResponse(
        query_id=184600,
        raw_text="This is a valid saved response that must not be overwritten.",
        response_time_ms=1234,
        llm_version="test",
    )
    session.add_all([responded, no_response, response])
    await session.commit()

    applied = await repair_stale_running_queries(
        session,
        brand_id=24,
        target_llm="chatgpt",
        max_age_seconds=3600,
        now=now,
    )

    assert applied.query_ids == [184601]

    await session.refresh(responded)
    await session.refresh(no_response)
    await session.refresh(response)
    assert responded.status == QueryStatus.RUNNING.value
    assert responded.retry_reason is None
    assert response.raw_text == "This is a valid saved response that must not be overwritten."
    assert no_response.status == QueryStatus.FAILED.value
    assert no_response.retry_reason == "stale_running_timeout"


@pytest.mark.asyncio
async def test_stale_queued_pending_no_response_becomes_failed_dispatch_timeout(
    session: AsyncSession,
) -> None:
    now = datetime(2026, 5, 14, 4, 45, 0)
    stale_queued = _query(
        184974,
        target_llm="doubao",
        status=QueryStatus.PENDING.value,
        event_at=now - timedelta(hours=2),
    )
    stale_queued.started_at = None
    stale_queued.executed_at = None
    fresh_queued = _query(
        184975,
        target_llm="doubao",
        status=QueryStatus.PENDING.value,
        event_at=now - timedelta(minutes=5),
    )
    fresh_queued.started_at = None
    fresh_queued.executed_at = None
    unqueued = _query(
        184976,
        target_llm="doubao",
        status=QueryStatus.PENDING.value,
        event_at=now - timedelta(hours=2),
    )
    unqueued.queued_at = None
    unqueued.started_at = None
    unqueued.executed_at = None
    session.add_all([stale_queued, fresh_queued, unqueued])
    await session.commit()

    applied = await repair_stale_pending_dispatch_queries(
        session,
        brand_id=24,
        target_llm="doubao",
        max_age_seconds=3600,
        now=now,
    )

    assert applied.matched == 1
    assert applied.repaired == 1
    assert applied.query_ids == [184974]
    assert applied.by_engine == {"doubao": 1}

    await session.refresh(stale_queued)
    await session.refresh(fresh_queued)
    await session.refresh(unqueued)
    assert stale_queued.status == QueryStatus.FAILED.value
    assert stale_queued.retry_reason == "pending_dispatch_timeout"
    assert stale_queued.finished_at == now
    assert stale_queued.latency_ms is None
    assert fresh_queued.status == QueryStatus.PENDING.value
    assert unqueued.status == QueryStatus.PENDING.value
