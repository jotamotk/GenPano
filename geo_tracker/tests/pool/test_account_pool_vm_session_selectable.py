"""Refs Epic #1110 / Issue #1116 (Codex review on PR #1122 — vm_session
selectability regression).

Headline guarantee: an ``execution_mode='vm_session'`` account with
``cookies_json = NULL`` MUST be selectable by both ``AccountPool.acquire``
and ``acquire_query_account``. Without this, the entire Phase 2 VM-per-
account architecture is dead code because the dispatcher's
cookies-required filter (correct for legacy local_cookie rows) silently
rejects every vm_session row created by the Admin UI from PR #1122.

Regression guard: a ``local_cookie`` account with ``cookies_json = NULL``
must STILL be rejected — that's a broken legacy row and the filter is
correct to skip it. vm_session is the only exception, and a future edit
that weakens the local_cookie predicate would re-introduce the original
"dispatcher rotates a broken cookie account" symptom that the filter
was added to prevent.

The pool acquire path also exercises ``count_acquirable_accounts``
because PR #963 documented that the two predicate sets must stay in
lockstep; if they drift, the proactive pre-warm task miscomputes the
deficit and the pool's effective size diverges from its labeled size.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from geo_tracker.db.models import AccountStatus, Base, LLMAccount
from geo_tracker.pool.account_pool import AccountPool, count_acquirable_accounts
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


def _vm_session_account(
    account_id: int,
    *,
    llm_name: str = "doubao",
    vm_id: str = "vm-prod-007",
    status: str = AccountStatus.ACTIVE.value,
) -> LLMAccount:
    """A vm_session account exactly as the Admin UI (PR #1122) would
    create it: cookies NULL, vm_id populated, execution_mode='vm_session'.
    Mirrors the shape that ``chk_exec_mode_cookies`` (PR #1121) accepts."""
    return LLMAccount(
        id=account_id,
        llm_name=llm_name,
        email=f"vm{account_id}@local",
        phone_number=f"800000{account_id}",
        cookies_json=None,
        cookies_updated_at=None,
        daily_limit=20,
        query_count_today=0,
        consecutive_fails=0,
        status=status,
        cooldown_until=None,
        execution_mode="vm_session",
        vm_id=vm_id,
        expired_transition_count=0,
    )


def _legacy_local_account_no_cookies(
    account_id: int,
    *,
    llm_name: str = "doubao",
    status: str = AccountStatus.ACTIVE.value,
) -> LLMAccount:
    """A legacy local_cookie account that is broken (no cookies). The
    pre-existing cookies filter exists precisely to skip these; this test
    fixture exists so the regression-guard assertion can prove the
    vm_session exception did NOT widen into a general local_cookie
    loophole."""
    return LLMAccount(
        id=account_id,
        llm_name=llm_name,
        email=f"local{account_id}@local",
        phone_number=f"900000{account_id}",
        cookies_json=None,
        cookies_updated_at=None,
        daily_limit=20,
        query_count_today=0,
        consecutive_fails=0,
        status=status,
        cooldown_until=None,
        execution_mode="local_cookie",
        vm_id=None,
        expired_transition_count=0,
    )


# --- AccountPool.acquire() ---------------------------------------------------


@pytest.mark.asyncio
async def test_pool_acquire_selects_vm_session_account_with_null_cookies(
    session: AsyncSession,
) -> None:
    """The headline regression: vm_session row with cookies=NULL is the
    only account in the pool; ``acquire`` must return it. Pre-fix this
    returned None because the SQL ``cookies_json != None`` predicate
    filtered the row out."""
    session.add(_vm_session_account(1))
    await session.commit()

    pool = AccountPool(session)
    account = await pool.acquire("doubao")

    assert account is not None, (
        "vm_session account was rejected by the pool's cookies filter — "
        "the VM-per-account path is unreachable."
    )
    assert account.id == 1
    assert account.execution_mode == "vm_session"
    assert account.cookies_json is None
    assert account.vm_id == "vm-prod-007"


@pytest.mark.asyncio
async def test_pool_acquire_still_rejects_local_cookie_without_cookies(
    session: AsyncSession,
) -> None:
    """REGRESSION GUARD. The vm_session exception MUST be narrow — a
    legacy ``local_cookie`` account without cookies is a broken row and
    must continue to be rejected. If this fails, the cookies-required
    filter was over-relaxed and the dispatcher will start handing out
    accounts that cannot drive a browser session."""
    session.add(_legacy_local_account_no_cookies(2))
    await session.commit()

    pool = AccountPool(session)
    account = await pool.acquire("doubao")

    assert account is None, (
        "local_cookie account without cookies was selected — the "
        "cookies filter was weakened beyond the vm_session exception."
    )


@pytest.mark.asyncio
async def test_pool_acquire_prefers_vm_session_alongside_broken_local(
    session: AsyncSession,
) -> None:
    """Mixed pool: one vm_session (cookies=NULL, valid), one local_cookie
    (cookies=NULL, broken). ``acquire`` must pick the vm_session one and
    skip the broken local_cookie one — proving the filter discriminates
    on ``execution_mode``, not on the absence of cookies alone."""
    session.add_all(
        [
            _vm_session_account(10, vm_id="vm-mix-010"),
            _legacy_local_account_no_cookies(11),
        ]
    )
    await session.commit()

    pool = AccountPool(session)
    account = await pool.acquire("doubao")

    assert account is not None
    assert account.id == 10
    assert account.execution_mode == "vm_session"


# --- count_acquirable_accounts (predicate-sync invariant) --------------------


@pytest.mark.asyncio
async def test_count_acquirable_accounts_includes_vm_session(
    session: AsyncSession,
) -> None:
    """``count_acquirable_accounts`` documents that it must mirror
    ``AccountPool.acquire``'s predicate set exactly (PR #963 Codex P2
    review). If the count excludes vm_session rows that ``acquire``
    would return, the proactive pre-warm deficit calculation
    re-introduces the "snapshot=N active, acquire=None" bug."""
    session.add_all(
        [
            _vm_session_account(20),
            _legacy_local_account_no_cookies(21),
        ]
    )
    await session.commit()

    count = await count_acquirable_accounts(session, "doubao")
    assert count == 1, (
        "count_acquirable_accounts drifted from acquire's predicate set: "
        f"expected 1 (the vm_session row), got {count}."
    )


# --- acquire_query_account (end-to-end dispatch path) ------------------------


@pytest.mark.asyncio
async def test_acquire_query_account_honors_scheduler_preassigned_vm_session(
    session: AsyncSession,
) -> None:
    """End-to-end: the scheduler pre-assigned a vm_session account to a
    query (``queries.account_id`` is set). ``acquire_query_account``
    runs ``is_account_executable_for_query`` (which calls
    ``_has_cookies``). Pre-fix this returned False and the function
    fell back to the pool, which also rejected the account. Post-fix
    the pre-assigned account is honored directly."""
    session.add(_vm_session_account(30, vm_id="vm-pre-030"))
    await session.commit()

    query = SimpleNamespace(
        id=12345,
        account_id=30,
        target_llm="doubao",
        profile_id=None,
    )

    chosen = await acquire_query_account(session, query)

    assert chosen is not None
    assert chosen.id == 30
    assert chosen.execution_mode == "vm_session"


@pytest.mark.asyncio
async def test_acquire_query_account_falls_back_to_vm_session_pool_pick(
    session: AsyncSession,
) -> None:
    """End-to-end: query has no pre-assigned account. The pool path
    must still surface the vm_session account."""
    session.add(_vm_session_account(40, vm_id="vm-fb-040"))
    await session.commit()

    query = SimpleNamespace(
        id=12346,
        account_id=None,
        target_llm="doubao",
        profile_id=None,
    )

    chosen = await acquire_query_account(session, query)

    assert chosen is not None
    assert chosen.id == 40
    assert chosen.execution_mode == "vm_session"


@pytest.mark.asyncio
async def test_acquire_query_account_skips_broken_local_falls_through(
    session: AsyncSession,
) -> None:
    """Pre-assigned but broken local_cookie account: dispatcher falls
    back to the pool, which finds nothing. Returning None here proves
    the local_cookie cookies-required check is still enforced through
    both layers (eligibility helper and pool SQL)."""
    session.add(_legacy_local_account_no_cookies(50))
    await session.commit()

    query = SimpleNamespace(
        id=12347,
        account_id=50,
        target_llm="doubao",
        profile_id=None,
    )

    chosen = await acquire_query_account(session, query)
    assert chosen is None
