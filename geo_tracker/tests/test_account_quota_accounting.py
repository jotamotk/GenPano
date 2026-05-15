from __future__ import annotations

import importlib
import logging
import sys
import types
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from geo_tracker.db.models import (
    AccountRotationLog,
    AccountStatus,
    Base,
    LLMAccount,
    LLMResponse,
    Query,
)
from geo_tracker.pool.account_pool import (
    AccountPool,
)
from geo_tracker.tasks.account_quota_settlement import AccountQuotaSettlement
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
    status: str = AccountStatus.ACTIVE.value,
    cookies_json: str = '[{"name":"session","value":"ok"}]',
) -> LLMAccount:
    account = LLMAccount(
        llm_name=llm_name,
        status=status,
        cookies_json=cookies_json,
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

    settlement = AccountQuotaSettlement(acquired.id)
    refunded = await settlement.settle_failure(
        session,
        AccountPool(session),
        reason="no_input",
    )
    await session.refresh(account)

    assert refunded is True
    assert settlement.settled is True
    assert account.query_count_today == 0


@pytest.mark.asyncio
async def test_fallback_acquire_non_consuming_failure_refunds_quota(session: AsyncSession):
    account = await _create_account(session)
    pool = AccountPool(session)

    acquired = await pool.acquire("chatgpt")
    await session.refresh(account)

    assert acquired.id == account.id
    assert account.query_count_today == 1

    settlement = AccountQuotaSettlement(acquired.id)
    refunded = await settlement.settle_failure(
        session,
        pool,
        reason="page_load_failed",
    )
    await session.refresh(account)

    assert refunded is True
    assert settlement.settled is True
    assert account.query_count_today == 0


@pytest.mark.asyncio
async def test_consuming_execution_keeps_single_reserved_quota(session: AsyncSession):
    account = await _create_account(session)
    pool = AccountPool(session)

    acquired = await pool.acquire("chatgpt")
    settlement = AccountQuotaSettlement(acquired.id)
    await settlement.settle_success(pool)
    await session.refresh(account)

    assert account.query_count_today == 1

    refunded = await settlement.settle_failure(
        session,
        pool,
        reason="response_too_short",
    )
    await session.refresh(account)

    assert refunded is False
    assert settlement.settled is True
    assert account.query_count_today == 1


@pytest.mark.asyncio
async def test_post_response_exception_keeps_reserved_quota(session: AsyncSession):
    account = await _create_account(session)
    pool = AccountPool(session)

    acquired = await pool.acquire("chatgpt")
    settlement = AccountQuotaSettlement(acquired.id)
    settlement.mark_platform_consumed()

    await settlement.settle_failure(session, pool, reason="exception")
    await session.refresh(account)

    assert settlement.settled is True
    assert account.query_count_today == 1


@pytest.mark.asyncio
async def test_duplicate_non_consuming_settlement_refunds_once(session: AsyncSession):
    account = await _create_account(session, daily_limit=2)
    pool = AccountPool(session)

    acquired = await pool.acquire("chatgpt")
    settlement = AccountQuotaSettlement(acquired.id)
    await session.refresh(account)
    assert account.query_count_today == 1

    await settlement.settle_failure(session, pool, reason="no_response")
    await settlement.settle_failure(session, pool, reason="no_response")
    await session.refresh(account)

    assert settlement.settled is True
    assert account.query_count_today == 0


@pytest.mark.asyncio
async def test_consuming_failure_followed_by_exception_does_not_refund(
    session: AsyncSession,
):
    account = await _create_account(session)
    pool = AccountPool(session)

    acquired = await pool.acquire("chatgpt")
    settlement = AccountQuotaSettlement(acquired.id)

    await settlement.settle_failure(session, pool, reason="cookies_expired")
    await settlement.settle_failure(session, pool, reason="exception")
    await session.refresh(account)

    assert settlement.settled is True
    assert account.query_count_today == 1
    assert account.status == AccountStatus.EXPIRED.value
    assert account.cooldown_until is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("llm_name", "reason"),
    [
        ("chatgpt", "cookies_expired"),
        ("chatgpt", "token_invalidated"),
        ("chatgpt", "chatgpt_login_page"),
        ("chatgpt", "chatgpt_not_logged_in"),
        ("chatgpt", "chatgpt_auth_redirect"),
        ("deepseek", "cookies_expired"),
        ("doubao", "doubao_not_logged_in"),
        ("doubao", "doubao_auth_state_missing"),
    ],
)
async def test_expired_login_failures_mark_account_expired_across_llms(
    session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
    llm_name: str,
    reason: str,
):
    account = await _create_account(
        session,
        llm_name=llm_name,
        daily_limit=3,
        cookies_json='[{"name":"session","value":"fixture-cookie-value"}]',
    )
    account.phone_number = "fixture-phone-1234"
    account.cooldown_until = datetime.utcnow() + timedelta(hours=1)
    await session.commit()

    pool = AccountPool(session)
    caplog.set_level(logging.INFO, logger="geo_tracker.pool.account_pool")

    await pool.report_failure(account.id, reason=reason)
    await session.refresh(account)
    rotation = (
        await session.execute(
            select(AccountRotationLog).where(AccountRotationLog.account_id == account.id)
        )
    ).scalar_one()

    assert account.status == AccountStatus.EXPIRED.value
    assert account.cooldown_until is None
    assert account.consecutive_fails == 0
    assert rotation.reason == reason
    assert "previous_status=active" in caplog.text
    assert "new_status=expired" in caplog.text
    assert f"reason={reason}" in caplog.text
    assert f"engine={llm_name}" in caplog.text
    assert "fixture-cookie-value" not in caplog.text
    assert "fixture-phone-1234" not in caplog.text


@pytest.mark.asyncio
async def test_expired_accounts_are_not_acquired(session: AsyncSession):
    expired = await _create_account(
        session,
        llm_name="deepseek",
        status=AccountStatus.EXPIRED.value,
        daily_limit=5,
    )
    active = await _create_account(
        session,
        llm_name="deepseek",
        daily_limit=5,
    )

    acquired = await AccountPool(session).acquire("deepseek")

    assert acquired.id == active.id
    assert acquired.id != expired.id


@pytest.mark.asyncio
async def test_save_cookies_reactivates_expired_account(session: AsyncSession):
    account = await _create_account(
        session,
        status=AccountStatus.EXPIRED.value,
        daily_limit=5,
    )
    account.consecutive_fails = 2
    account.cooldown_until = datetime.utcnow() + timedelta(hours=2)
    await session.commit()

    await AccountPool(session).save_cookies(
        account.id,
        '[{"name":"session","value":"fresh"}]',
    )
    await session.refresh(account)

    assert account.status == AccountStatus.ACTIVE.value
    assert account.cooldown_until is None
    assert account.consecutive_fails == 0


@pytest.mark.asyncio
async def test_chatgpt_logged_out_auth_failure_marks_account_expired(
    session: AsyncSession,
):
    account = await _create_account(session)
    pool = AccountPool(session)

    acquired = await pool.acquire("chatgpt")
    settlement = AccountQuotaSettlement(acquired.id)

    refunded = await settlement.settle_failure(
        session,
        pool,
        reason="chatgpt_not_logged_in",
    )
    await session.refresh(account)

    assert refunded is False
    assert settlement.settled is True
    assert account.query_count_today == 1
    assert account.status == AccountStatus.EXPIRED.value
    assert account.cooldown_until is None


@pytest.mark.asyncio
async def test_unreserved_abort_cleanup_does_not_refund_assigned_account(
    session: AsyncSession,
):
    account = await _create_account(session, query_count_today=1, daily_limit=2)
    settlement = AccountQuotaSettlement(None)

    refunded = await settlement.settle_failure(
        session,
        AccountPool(session),
        reason="soft_time_limit",
    )
    await session.refresh(account)

    assert refunded is False
    assert settlement.settled is False
    assert account.query_count_today == 1


def _import_celery_tasks_with_fake_playwright(monkeypatch):
    playwright = types.ModuleType("playwright")
    playwright_async = types.ModuleType("playwright.async_api")
    playwright_async.async_playwright = object
    playwright_async.BrowserContext = object
    playwright_async.ElementHandle = object
    playwright_async.Page = object
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.async_api", playwright_async)
    return importlib.import_module("geo_tracker.tasks.celery_tasks")


class _ExistingSessionContext:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _NoopEngine:
    async def dispose(self):
        return None


@pytest.mark.asyncio
async def test_reserved_soft_timeout_abort_cleanup_refunds_quota(
    session: AsyncSession,
    monkeypatch,
):
    celery_tasks = _import_celery_tasks_with_fake_playwright(monkeypatch)
    account = await _create_account(session, query_count_today=1, daily_limit=2)
    query = Query(
        id=501,
        account_id=account.id,
        target_llm="chatgpt",
        query_text="hello",
        status="running",
    )
    session.add(query)
    await session.commit()
    settlement = AccountQuotaSettlement(account.id)

    monkeypatch.setattr(celery_tasks, "create_task_engine", lambda: _NoopEngine())
    monkeypatch.setattr(
        celery_tasks,
        "get_task_async_session",
        lambda engine: _ExistingSessionContext(session),
    )

    await celery_tasks._mark_query_failed_after_task_abort_async(
        query.id,
        "soft_time_limit",
        quota_settlement=settlement,
    )
    await session.refresh(account)
    await session.refresh(query)

    assert settlement.settled is True
    assert account.query_count_today == 0
    assert query.status == "failed"
    assert query.retry_reason == "soft_time_limit"


@pytest.mark.asyncio
async def test_doubao_soft_timeout_abort_cleanup_records_no_response_stage_reason(
    session: AsyncSession,
    monkeypatch,
):
    celery_tasks = _import_celery_tasks_with_fake_playwright(monkeypatch)
    account = await _create_account(
        session,
        llm_name="doubao",
        query_count_today=1,
        daily_limit=2,
    )
    query = Query(
        id=96301,
        account_id=account.id,
        target_llm="doubao",
        query_text="hello",
        status="running",
    )
    session.add(query)
    await session.commit()
    settlement = AccountQuotaSettlement(account.id)

    monkeypatch.setattr(celery_tasks, "create_task_engine", lambda: _NoopEngine())
    monkeypatch.setattr(
        celery_tasks,
        "get_task_async_session",
        lambda engine: _ExistingSessionContext(session),
    )

    await celery_tasks._mark_query_failed_after_task_abort_async(
        query.id,
        "soft_time_limit",
        quota_settlement=settlement,
    )
    await session.refresh(account)
    await session.refresh(query)

    assert settlement.settled is True
    assert account.query_count_today == 0
    assert query.status == "failed"
    assert query.retry_reason == "doubao_browser_timeout:task_soft_limit"


@pytest.mark.asyncio
async def test_doubao_soft_timeout_abort_cleanup_preserves_existing_response_contract(
    session: AsyncSession,
    monkeypatch,
):
    celery_tasks = _import_celery_tasks_with_fake_playwright(monkeypatch)
    account = await _create_account(
        session,
        llm_name="doubao",
        query_count_today=1,
        daily_limit=2,
    )
    query = Query(
        id=96302,
        account_id=account.id,
        target_llm="doubao",
        query_text="hello",
        status="running",
    )
    response = LLMResponse(
        id=9630201,
        query_id=query.id,
        raw_text="Existing Doubao answer retained from an earlier attempt.",
        response_time_ms=123,
        screenshot_path="/data/screenshots/query_96302_doubao.png",
        analysis_status="done",
    )
    session.add_all([query, response])
    await session.commit()
    settlement = AccountQuotaSettlement(account.id)

    monkeypatch.setattr(celery_tasks, "create_task_engine", lambda: _NoopEngine())
    monkeypatch.setattr(
        celery_tasks,
        "get_task_async_session",
        lambda engine: _ExistingSessionContext(session),
    )

    await celery_tasks._mark_query_failed_after_task_abort_async(
        query.id,
        "soft_time_limit",
        quota_settlement=settlement,
    )
    await session.refresh(account)
    await session.refresh(query)
    response_result = await session.execute(
        select(LLMResponse).where(LLMResponse.query_id == query.id)
    )

    assert settlement.settled is True
    assert account.query_count_today == 0
    assert query.status == "failed"
    assert query.retry_reason == "doubao_browser_timeout:existing_response"
    assert response_result.scalar_one().screenshot_path.endswith("query_96302_doubao.png")


@pytest.mark.asyncio
async def test_consumed_soft_timeout_abort_cleanup_keeps_quota(
    session: AsyncSession,
    monkeypatch,
):
    celery_tasks = _import_celery_tasks_with_fake_playwright(monkeypatch)
    account = await _create_account(session, query_count_today=1, daily_limit=2)
    query = Query(
        id=502,
        account_id=account.id,
        target_llm="chatgpt",
        query_text="hello",
        status="running",
    )
    session.add(query)
    await session.commit()
    settlement = AccountQuotaSettlement(account.id)
    settlement.mark_platform_consumed()

    monkeypatch.setattr(celery_tasks, "create_task_engine", lambda: _NoopEngine())
    monkeypatch.setattr(
        celery_tasks,
        "get_task_async_session",
        lambda engine: _ExistingSessionContext(session),
    )

    await celery_tasks._mark_query_failed_after_task_abort_async(
        query.id,
        "soft_time_limit",
        quota_settlement=settlement,
    )
    await session.refresh(account)

    assert settlement.settled is True
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

    settlement = AccountQuotaSettlement(first.id)
    assert await settlement.settle_failure(session, pool, reason="no_response")

    second = await pool.acquire("chatgpt")
    await session.refresh(account)

    assert second.id == account.id
    assert account.query_count_today == 1
