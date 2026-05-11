from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from geo_tracker.db.models import AccountStatus, Base, LLMAccount, Query
from geo_tracker.pool.account_pool import (
    AccountPool,
    refund_account_quota_reservation,
)
from geo_tracker.tasks.account_assignment import acquire_query_account


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as db:
        yield db

    await engine.dispose()


async def _create_account(
    session: AsyncSession,
    *,
    llm_name: str = "chatgpt",
    query_count_today: int = 0,
    daily_limit: int = 1,
) -> LLMAccount:
    account = LLMAccount(
        llm_name=llm_name,
        status=AccountStatus.ACTIVE.value,
        cookies_json='[{"name":"session","value":"ok"}]',
        query_count_today=query_count_today,
        daily_limit=daily_limit,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


@pytest.mark.asyncio
async def test_scheduler_assigned_non_consuming_failure_refunds_quota(session: AsyncSession):
    account = await _create_account(session)
    query = Query(account_id=account.id, target_llm="chatgpt", query_text="hello")

    acquired = await acquire_query_account(session, query)
    await session.refresh(account)

    assert acquired.id == account.id
    assert account.query_count_today == 1

    refunded = await refund_account_quota_reservation(
        session,
        account.id,
        reason="no_input",
    )
    await session.refresh(account)

    assert refunded is True
    assert account.query_count_today == 0


@pytest.mark.asyncio
async def test_fallback_acquire_non_consuming_failure_refunds_quota(session: AsyncSession):
    account = await _create_account(session)
    pool = AccountPool(session)

    acquired = await pool.acquire("chatgpt")
    await session.refresh(account)

    assert acquired.id == account.id
    assert account.query_count_today == 1

    refunded = await refund_account_quota_reservation(
        session,
        account.id,
        reason="page_load_failed",
    )
    await session.refresh(account)

    assert refunded is True
    assert account.query_count_today == 0


@pytest.mark.asyncio
async def test_consuming_execution_keeps_single_reserved_quota(session: AsyncSession):
    account = await _create_account(session)
    pool = AccountPool(session)

    acquired = await pool.acquire("chatgpt")
    await pool.report_success(acquired.id)
    await session.refresh(account)

    assert account.query_count_today == 1

    refunded = await refund_account_quota_reservation(
        session,
        account.id,
        reason="response_too_short",
    )
    await session.refresh(account)

    assert refunded is False
    assert account.query_count_today == 1


@pytest.mark.asyncio
async def test_true_daily_limit_exhaustion_still_blocks_acquisition(session: AsyncSession):
    account = await _create_account(session)
    pool = AccountPool(session)

    first = await pool.acquire("chatgpt")
    second = await pool.acquire("chatgpt")
    await session.refresh(account)

    assert first.id == account.id
    assert second is None
    assert account.query_count_today == 1


@pytest.mark.asyncio
async def test_retry_after_non_consuming_failure_can_reacquire_account(session: AsyncSession):
    account = await _create_account(session)
    pool = AccountPool(session)

    first = await pool.acquire("chatgpt")
    assert first.id == account.id

    assert await refund_account_quota_reservation(
        session,
        account.id,
        reason="no_response",
    )

    second = await pool.acquire("chatgpt")
    await session.refresh(account)

    assert second.id == account.id
    assert account.query_count_today == 1
