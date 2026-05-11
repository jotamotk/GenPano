from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from geo_tracker.db.models import (
    AccountStatus,
    Base,
    LLMAccount,
    LLMResponse,
    Query,
    QueryStatus,
)
from geo_tracker.tasks.quota_counter_repair import (
    RepairBlocked,
    build_quota_repair_report,
    apply_quota_repair_plan,
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


async def _account(
    session: AsyncSession,
    *,
    account_id: int,
    llm_name: str,
    query_count_today: int,
    daily_limit: int = 20,
) -> LLMAccount:
    account = LLMAccount(
        id=account_id,
        llm_name=llm_name,
        status=AccountStatus.ACTIVE.value,
        cookies_json='[{"name":"session","value":"ok"}]',
        query_count_today=query_count_today,
        daily_limit=daily_limit,
    )
    session.add(account)
    await session.commit()
    return account


def _query(
    query_id: int,
    *,
    account_id: int | None,
    target_llm: str,
    reason: str | None,
    event_at: datetime,
    status: str = QueryStatus.FAILED.value,
) -> Query:
    return Query(
        id=query_id,
        account_id=account_id,
        target_llm=target_llm,
        query_text=f"query {query_id}",
        status=status,
        retry_reason=reason,
        started_at=event_at,
        finished_at=event_at,
        created_at=event_at,
    )


@pytest.mark.asyncio
async def test_report_selects_only_current_day_non_consuming_unresponded_account_attempts(
    session: AsyncSession,
):
    day_start = datetime(2026, 5, 11)
    await _account(
        session,
        account_id=10,
        llm_name="chatgpt",
        query_count_today=5,
    )
    await _account(
        session,
        account_id=11,
        llm_name="deepseek",
        query_count_today=3,
    )

    included_1 = _query(
        101,
        account_id=10,
        target_llm="chatgpt",
        reason="no_response",
        event_at=day_start + timedelta(hours=1),
    )
    included_2 = _query(
        102,
        account_id=10,
        target_llm="chatgpt",
        reason="browser_timeout",
        event_at=day_start + timedelta(hours=2),
    )
    included_3 = _query(
        103,
        account_id=11,
        target_llm="deepseek",
        reason="soft_time_limit",
        event_at=day_start + timedelta(hours=3),
    )
    consuming_failure = _query(
        104,
        account_id=10,
        target_llm="chatgpt",
        reason="cookies_expired",
        event_at=day_start + timedelta(hours=4),
    )
    successful = _query(
        105,
        account_id=10,
        target_llm="chatgpt",
        reason=None,
        event_at=day_start + timedelta(hours=5),
        status=QueryStatus.DONE.value,
    )
    previous_day = _query(
        106,
        account_id=10,
        target_llm="chatgpt",
        reason="no_input",
        event_at=day_start - timedelta(minutes=1),
    )
    no_account = _query(
        107,
        account_id=None,
        target_llm="chatgpt",
        reason="page_load_failed",
        event_at=day_start + timedelta(hours=6),
    )
    has_response = _query(
        108,
        account_id=11,
        target_llm="deepseek",
        reason="exception",
        event_at=day_start + timedelta(hours=7),
    )
    session.add_all(
        [
            included_1,
            included_2,
            included_3,
            consuming_failure,
            successful,
            previous_day,
            no_account,
            has_response,
        ]
    )
    session.add(
        LLMResponse(
            query_id=108,
            raw_text="platform returned text before persistence failed",
            response_time_ms=1000,
        )
    )
    await session.commit()

    report = await build_quota_repair_report(
        session,
        service_day_start=day_start,
        service_day_end=day_start + timedelta(days=1),
    )

    assert report.candidate_query_ids == [101, 102, 103]
    assert report.total_refundable_attempts == 3
    assert [
        (item.engine, item.account_id, item.reason, item.refundable_attempts)
        for item in report.groups
    ] == [
        ("chatgpt", 10, "browser_timeout", 1),
        ("chatgpt", 10, "no_response", 1),
        ("deepseek", 11, "soft_time_limit", 1),
    ]
    assert [
        (
            item.engine,
            item.account_id,
            item.current_query_count_today,
            item.proposed_delta,
            item.after_query_count_today,
            item.safe_to_apply,
        )
        for item in report.account_plans
    ] == [
        ("chatgpt", 10, 5, 2, 3, True),
        ("deepseek", 11, 3, 1, 2, True),
    ]
    assert json.loads(json.dumps(report.to_dict()))["total_refundable_attempts"] == 3


@pytest.mark.asyncio
async def test_apply_guard_blocks_counter_underflow_and_exact_total_mismatch(
    session: AsyncSession,
):
    day_start = datetime(2026, 5, 11)
    account = await _account(
        session,
        account_id=20,
        llm_name="chatgpt",
        query_count_today=1,
    )
    session.add_all(
        [
            _query(
                201,
                account_id=20,
                target_llm="chatgpt",
                reason="no_response",
                event_at=day_start + timedelta(hours=1),
            ),
            _query(
                202,
                account_id=20,
                target_llm="chatgpt",
                reason="page_load_failed",
                event_at=day_start + timedelta(hours=2),
            ),
        ]
    )
    await session.commit()

    report = await build_quota_repair_report(
        session,
        service_day_start=day_start,
        service_day_end=day_start + timedelta(days=1),
    )

    assert report.account_plans[0].proposed_delta == 2
    assert report.account_plans[0].after_query_count_today == -1
    assert report.account_plans[0].safe_to_apply is False

    with pytest.raises(RepairBlocked, match="would drop below zero"):
        await apply_quota_repair_plan(session, report, expected_total_delta=2)
    await session.refresh(account)
    assert account.query_count_today == 1

    account.query_count_today = 3
    await session.commit()
    report = await build_quota_repair_report(
        session,
        service_day_start=day_start,
        service_day_end=day_start + timedelta(days=1),
    )

    with pytest.raises(RepairBlocked, match="expected_total_delta"):
        await apply_quota_repair_plan(session, report, expected_total_delta=1)
    await session.refresh(account)
    assert account.query_count_today == 3

    applied = await apply_quota_repair_plan(session, report, expected_total_delta=2)
    await session.refresh(account)

    assert applied.total_delta == 2
    assert account.query_count_today == 1
