"""Refs Epic #1110 / Issue #1114.

Verify that ``AccountPool.report_failure`` treats ``execution_mode='vm_session'``
accounts differently from the legacy ``local_cookie`` accounts:

  - On ``PROXY_DEAD``, set a VM-local cooldown (30 min) WITHOUT
    incrementing ``expired_transition_count``. The 3-strike ricochet ban
    gate must not fire for VM infra blips.
  - On any other failure reason, pass through (log only) — login
    liveness for vm_session is owned by the watchdog from Issue #1115,
    and CAPTCHA goes through docs/ADAPTER_CONTRACT.md §9.

Regression test for the existing ``local_cookie`` path: a doubao
account with an EXPIRED_ACCOUNT_REASONS failure still bumps
``expired_transition_count`` exactly as it did before this PR. The
local_cookie branch is the production path and we must not change it
while the dead-code deploy validates.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from geo_tracker.db.models import AccountStatus, Base, LLMAccount
from geo_tracker.pool.account_pool import AccountPool


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as db:
        yield db
    await engine.dispose()


def _vm_account(account_id: int) -> LLMAccount:
    """A vm_session account: NO cookies_json (DB constraint
    ``chk_exec_mode_cookies`` forbids it). ``vm_id`` populated."""
    return LLMAccount(
        id=account_id,
        llm_name="doubao",
        email=f"vm{account_id}@local",
        phone_number=f"200000{account_id}",
        cookies_json=None,
        cookies_updated_at=None,
        daily_limit=20,
        query_count_today=0,
        consecutive_fails=0,
        status=AccountStatus.ACTIVE.value,
        cooldown_until=None,
        execution_mode="vm_session",
        vm_id=f"vm-{account_id:03d}",
        expired_transition_count=0,
    )


def _local_account(account_id: int) -> LLMAccount:
    """A legacy local_cookie account — current production shape.
    Cookies present, no vm_id."""
    return LLMAccount(
        id=account_id,
        llm_name="doubao",
        email=f"local{account_id}@local",
        phone_number=f"300000{account_id}",
        cookies_json='[{"name":"a","value":"b","domain":".doubao.com"}]',
        cookies_updated_at=datetime(2026, 5, 15, 0, 0, 0),
        daily_limit=20,
        query_count_today=0,
        consecutive_fails=0,
        status=AccountStatus.ACTIVE.value,
        cooldown_until=None,
        execution_mode="local_cookie",
        vm_id=None,
        expired_transition_count=0,
    )


# --- vm_session-specific behavior ------------------------------------------

@pytest.mark.asyncio
async def test_vm_session_proxy_dead_sets_cooldown_without_bumping_strike(
    session: AsyncSession,
) -> None:
    """The headline guarantee: PROXY_DEAD on a vm_session account
    → status=COOLDOWN with cooldown_until ~30 min in the future, and
    expired_transition_count stays at 0. If this regressed, a VM
    heartbeat blip would burn a Doubao account toward the 3-strike
    permanent ban — exactly the failure mode #1114 exists to prevent.
    """
    acc = _vm_account(1)
    session.add(acc)
    await session.commit()

    before = datetime.utcnow()
    pool = AccountPool(session)
    await pool.report_failure(account_id=1, reason="PROXY_DEAD")
    after = datetime.utcnow()

    await session.refresh(acc)
    assert acc.status == AccountStatus.COOLDOWN.value
    assert acc.cooldown_until is not None
    # 30-min window, with a bit of slack to absorb fixture clock skew.
    expected_low = before + timedelta(minutes=29)
    expected_high = after + timedelta(minutes=31)
    assert expected_low <= acc.cooldown_until <= expected_high
    # The load-bearing assertion: strike counter UNCHANGED.
    assert acc.expired_transition_count == 0


@pytest.mark.asyncio
async def test_vm_session_other_reason_is_passthrough(
    session: AsyncSession,
) -> None:
    """Any non-PROXY_DEAD reason on a vm_session account is a
    pass-through: no status change, no strike, no cooldown. The
    watchdog / CAPTCHA pipeline owns these flows."""
    acc = _vm_account(2)
    session.add(acc)
    await session.commit()

    pool = AccountPool(session)
    await pool.report_failure(account_id=2, reason="login_redirect")

    await session.refresh(acc)
    assert acc.status == AccountStatus.ACTIVE.value
    assert acc.cooldown_until is None
    assert acc.expired_transition_count == 0
    assert acc.consecutive_fails == 0


@pytest.mark.asyncio
async def test_vm_session_writes_rotation_log_row(session: AsyncSession) -> None:
    """Even on the pass-through path we still write the audit row so
    the operator can grep ``account_rotation_log`` and see what
    happened. Skipping the log would make incident triage impossible."""
    from geo_tracker.db.models import AccountRotationLog
    from sqlalchemy import select

    acc = _vm_account(3)
    session.add(acc)
    await session.commit()

    pool = AccountPool(session)
    await pool.report_failure(account_id=3, reason="PROXY_DEAD")
    await pool.report_failure(account_id=3, reason="login_redirect")

    rows = (
        await session.execute(
            select(AccountRotationLog).where(AccountRotationLog.account_id == 3)
        )
    ).scalars().all()
    assert len(rows) == 2
    reasons = {r.reason for r in rows}
    assert reasons == {"PROXY_DEAD", "login_redirect"}


# --- local_cookie regression guard -----------------------------------------

@pytest.mark.asyncio
async def test_local_cookie_ricochet_behavior_unchanged(
    session: AsyncSession,
) -> None:
    """REGRESSION GUARD. The local_cookie branch must keep working
    exactly as it did pre-#1114: a doubao account with an
    EXPIRED_ACCOUNT_REASONS failure (``doubao_not_logged_in``)
    bumps expired_transition_count and transitions to
    ``status='expired'``. If this test fails after a #1114 edit, the
    new vm_session branch leaked into the local_cookie path."""
    acc = _local_account(4)
    session.add(acc)
    await session.commit()

    pool = AccountPool(session)
    # Use the legacy expired-account-reason that triggers the strike
    # path (one of EXPIRED_ACCOUNT_REASONS).
    await pool.report_failure(account_id=4, reason="doubao_not_logged_in")

    await session.refresh(acc)
    assert acc.status == AccountStatus.EXPIRED.value
    assert acc.expired_transition_count == 1


@pytest.mark.asyncio
async def test_local_cookie_proxy_dead_uses_legacy_branch(
    session: AsyncSession,
) -> None:
    """A PROXY_DEAD reason on a local_cookie account is NOT in
    EXPIRED_ACCOUNT_REASONS and NOT in DOUBAO_SESSION_COOLDOWN_REASONS,
    so the legacy code falls into the "else: consecutive_fails += 1"
    branch. The vm_session branch must NOT route local_cookie traffic
    into its 30-min cooldown shortcut."""
    acc = _local_account(5)
    session.add(acc)
    await session.commit()

    pool = AccountPool(session)
    await pool.report_failure(account_id=5, reason="PROXY_DEAD")

    await session.refresh(acc)
    # Legacy fall-through path: status stays active until the 3-strike
    # consecutive_fails gate fires. cooldown_until is unset.
    assert acc.status == AccountStatus.ACTIVE.value
    assert acc.consecutive_fails == 1
    assert acc.cooldown_until is None
    # And the vm-session counter MUST NOT have been touched.
    assert acc.expired_transition_count == 0
