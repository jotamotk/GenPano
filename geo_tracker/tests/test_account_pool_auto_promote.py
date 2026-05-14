"""Tests for cooldown auto-promotion and pool health snapshot (issue #917 / #908)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from geo_tracker.db.models import AccountStatus, Base, LLMAccount
from geo_tracker.pool.account_pool import (
    AccountPool,
    promote_expired_cooldowns,
    snapshot_pool_health,
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


def _account(
    account_id: int,
    *,
    status: str,
    cooldown_until: datetime | None = None,
    cookies: str | None = '[{"name": "a", "value": "b"}]',
    daily_limit: int = 20,
) -> LLMAccount:
    return LLMAccount(
        id=account_id,
        llm_name="doubao",
        email=f"acc{account_id}@local",
        phone_number=f"100000{account_id}",
        cookies_json=cookies,
        cookies_updated_at=datetime(2026, 5, 1, 0, 0, 0),
        daily_limit=daily_limit,
        query_count_today=0,
        consecutive_fails=0,
        status=status,
        cooldown_until=cooldown_until,
    )


@pytest.mark.asyncio
async def test_promote_only_past_cooldown(session: AsyncSession) -> None:
    now = datetime(2026, 5, 14, 12, 0, 0)
    elapsed = _account(1, status=AccountStatus.COOLDOWN.value, cooldown_until=now - timedelta(minutes=10))
    future = _account(2, status=AccountStatus.COOLDOWN.value, cooldown_until=now + timedelta(hours=2))
    banned = _account(3, status=AccountStatus.BANNED.value, cooldown_until=now - timedelta(hours=5))
    expired_status = _account(4, status=AccountStatus.EXPIRED.value, cooldown_until=None)
    session.add_all([elapsed, future, banned, expired_status])
    await session.commit()

    promoted = await promote_expired_cooldowns(session, "doubao", now=now)

    assert promoted == [1]
    await session.refresh(elapsed)
    await session.refresh(future)
    await session.refresh(banned)
    await session.refresh(expired_status)
    assert elapsed.status == AccountStatus.ACTIVE.value
    assert elapsed.cooldown_until is None
    assert future.status == AccountStatus.COOLDOWN.value, "未到点的 cooldown 不应被提升"
    assert banned.status == AccountStatus.BANNED.value, "banned 不应被自动提升"
    assert expired_status.status == AccountStatus.EXPIRED.value, "expired 不应被自动提升"


@pytest.mark.asyncio
async def test_promote_dry_run_no_writes(session: AsyncSession) -> None:
    now = datetime(2026, 5, 14, 12, 0, 0)
    acc = _account(
        1,
        status=AccountStatus.COOLDOWN.value,
        cooldown_until=now - timedelta(minutes=10),
    )
    session.add(acc)
    await session.commit()

    promoted = await promote_expired_cooldowns(session, "doubao", now=now, dry_run=True)

    assert promoted == [1]
    await session.refresh(acc)
    assert acc.status == AccountStatus.COOLDOWN.value
    assert acc.cooldown_until is not None


@pytest.mark.asyncio
async def test_promote_filters_by_llm_when_provided(session: AsyncSession) -> None:
    now = datetime(2026, 5, 14, 12, 0, 0)
    doubao = _account(1, status=AccountStatus.COOLDOWN.value, cooldown_until=now - timedelta(minutes=10))
    other = LLMAccount(
        id=2,
        llm_name="deepseek",
        email="x@local",
        phone_number="100000002",
        cookies_json='[{"name": "a", "value": "b"}]',
        cookies_updated_at=datetime(2026, 5, 1, 0, 0, 0),
        daily_limit=20,
        query_count_today=0,
        consecutive_fails=0,
        status=AccountStatus.COOLDOWN.value,
        cooldown_until=now - timedelta(hours=1),
    )
    session.add_all([doubao, other])
    await session.commit()

    promoted = await promote_expired_cooldowns(session, "doubao", now=now)

    assert promoted == [1]
    await session.refresh(other)
    assert other.status == AccountStatus.COOLDOWN.value, "其他 LLM 不应被影响"


@pytest.mark.asyncio
async def test_snapshot_counts_each_status(session: AsyncSession) -> None:
    now = datetime(2026, 5, 14, 12, 0, 0)
    session.add_all(
        [
            _account(1, status=AccountStatus.ACTIVE.value),
            _account(2, status=AccountStatus.COOLDOWN.value, cooldown_until=now - timedelta(minutes=10)),
            _account(3, status=AccountStatus.COOLDOWN.value, cooldown_until=now + timedelta(hours=2)),
            _account(4, status=AccountStatus.EXPIRED.value),
            _account(5, status=AccountStatus.BANNED.value),
            _account(6, status=AccountStatus.ACTIVE.value, cookies=None),
        ]
    )
    await session.commit()

    snap = await snapshot_pool_health(session, "doubao", now=now)

    assert snap.llm_name == "doubao"
    assert snap.active == 2
    assert snap.cooldown == 2
    assert snap.cooldown_expired == 1
    assert snap.expired == 1
    assert snap.banned == 1
    assert snap.with_cookies == 5

    data = snap.to_dict()
    assert data["active"] == 2
    assert data["cooldown_expired"] == 1


@pytest.mark.asyncio
async def test_acquire_promotes_then_selects(session: AsyncSession) -> None:
    far_past = datetime(2020, 1, 1, 0, 0, 0)
    session.add(
        _account(
            1,
            status=AccountStatus.COOLDOWN.value,
            cooldown_until=far_past,
        )
    )
    await session.commit()

    pool = AccountPool(session)
    account = await pool.acquire("doubao")

    assert account is not None
    assert account.id == 1
    assert account.status == AccountStatus.ACTIVE.value
    assert account.cooldown_until is None


@pytest.mark.asyncio
async def test_acquire_returns_none_when_only_banned(session: AsyncSession) -> None:
    session.add_all(
        [
            _account(1, status=AccountStatus.BANNED.value),
            _account(2, status=AccountStatus.EXPIRED.value),
        ]
    )
    await session.commit()

    pool = AccountPool(session)
    account = await pool.acquire("doubao")

    assert account is None
