"""Tests for Refs #963 audit pain points #1 and #2.

Pain point #1: proactive pool pre-warming via the ``prewarm_account_pool``
celery beat task. When the active pool sits below ``DOUBAO_TARGET_ACTIVE_POOL``
the task must enqueue ``auto_login(platform=engine, new_account=True)`` up to
the deficit, honoring the existing ``should_enqueue_new_account`` registration
lock + 30-min failure cooldown.

Pain point #2: 3-strike permanent ban when a Doubao account ricochets
``expired → re-login → active → expired`` via ``doubao_not_logged_in``
(or any EXPIRED_ACCOUNT_REASONS reason). Non-Doubao accounts must NOT be
banned this way because their dominant failure modes aren't in
EXPIRED_ACCOUNT_REASONS — the existing ``consecutive_fails`` gate already
handles them.

Backward compat: rows that pre-date the schema column should behave as if
``expired_transition_count=0`` (the server_default backfill in the Alembic
migration covers this in production; the test confirms the read path with an
explicit 0 starting value).
"""
from __future__ import annotations

import asyncio

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


def _account(
    account_id: int,
    *,
    llm_name: str = "doubao",
    status: str = AccountStatus.ACTIVE.value,
    cookies: str | None = '[{"name": "a", "value": "b"}]',
    consecutive_fails: int = 0,
    expired_transition_count: int = 0,
) -> LLMAccount:
    return LLMAccount(
        id=account_id,
        llm_name=llm_name,
        email=f"acc{account_id}@local",
        phone_number=f"100000{account_id:04d}",
        cookies_json=cookies,
        daily_limit=20,
        query_count_today=0,
        consecutive_fails=consecutive_fails,
        expired_transition_count=expired_transition_count,
        status=status,
    )


# ─── Fix B: 3-strike ban on doubao_not_logged_in ricochet ────────────────────


@pytest.mark.asyncio
async def test_doubao_banned_after_three_expired_transitions(
    session: AsyncSession,
) -> None:
    """Doubao account that hits ``doubao_not_logged_in`` 3 times in a row
    transitions to ``banned`` on the 3rd strike. Without this, the account
    would ricochet ``expired → re-login → active → expired`` forever because
    ``consecutive_fails`` is reset to 0 on every expired transition."""
    session.add(_account(1))
    await session.commit()
    pool = AccountPool(session)

    await pool.report_failure(1, reason="doubao_not_logged_in")
    await session.refresh((acc := await session.get(LLMAccount, 1)))
    assert acc.status == AccountStatus.EXPIRED.value
    assert acc.expired_transition_count == 1

    await pool.report_failure(1, reason="doubao_not_logged_in")
    await session.refresh(acc)
    assert acc.status == AccountStatus.EXPIRED.value
    assert acc.expired_transition_count == 2

    await pool.report_failure(1, reason="doubao_not_logged_in")
    await session.refresh(acc)
    assert acc.status == AccountStatus.BANNED.value, (
        "3rd consecutive doubao_not_logged_in must permanently ban "
        "the Doubao account to stop the ricochet"
    )
    assert acc.expired_transition_count == 3


@pytest.mark.asyncio
async def test_doubao_successful_relogin_resets_expired_counter(
    session: AsyncSession,
) -> None:
    """A successful re-login (``save_cookies``) between expired strikes resets
    the counter so the account does NOT get banned on the next two-strike run.
    """
    session.add(_account(1, expired_transition_count=2))
    await session.commit()
    pool = AccountPool(session)

    # Two strikes already; one more would ban without a reset.
    await pool.save_cookies(1, '[{"name": "fresh", "value": "cookie"}]')
    acc = await session.get(LLMAccount, 1)
    assert acc.expired_transition_count == 0
    assert acc.status == AccountStatus.ACTIVE.value

    # Now two more strikes still only count as 1 + 2 — must stay expired.
    await pool.report_failure(1, reason="doubao_not_logged_in")
    await pool.report_failure(1, reason="doubao_not_logged_in")
    await session.refresh(acc)
    assert acc.status == AccountStatus.EXPIRED.value
    assert acc.expired_transition_count == 2


@pytest.mark.asyncio
async def test_non_doubao_engine_not_banned_by_expired_ricochet(
    session: AsyncSession,
) -> None:
    """DeepSeek / ChatGPT accounts must NOT trigger the 3-strike ban on
    expired transitions — the ricochet pattern is Doubao-specific. Their
    pre-existing ``consecutive_fails >= 3`` gate stays the only ban path for
    non-EXPIRED_ACCOUNT_REASONS failures."""
    session.add(_account(1, llm_name="deepseek"))
    await session.commit()
    pool = AccountPool(session)

    for _ in range(5):
        await pool.report_failure(1, reason="cookies_expired")

    acc = await session.get(LLMAccount, 1)
    assert acc.status == AccountStatus.EXPIRED.value, (
        "Non-Doubao engines must keep the legacy expired-then-wait-for-re-login "
        "semantics; ricochet ban is opt-in via EXPIRED_RICOCHET_BAN_ENGINES."
    )
    assert acc.expired_transition_count == 5


@pytest.mark.asyncio
async def test_existing_account_with_null_expired_count_behaves_normally(
    session: AsyncSession,
) -> None:
    """Backward compat: rows whose counter was backfilled to 0 by the Alembic
    migration must still trigger the legacy ``expired`` transition on the
    first failure and only escalate to ``banned`` on the 3rd. Confirms no
    regression for accounts created before the schema change."""
    # Counter explicitly 0 emulates the Alembic server_default backfill.
    session.add(_account(1, expired_transition_count=0))
    await session.commit()
    pool = AccountPool(session)

    await pool.report_failure(1, reason="doubao_not_logged_in")
    acc = await session.get(LLMAccount, 1)
    assert acc.status == AccountStatus.EXPIRED.value
    assert acc.expired_transition_count == 1


@pytest.mark.asyncio
async def test_doubao_non_expired_failure_does_not_bump_expired_counter(
    session: AsyncSession,
) -> None:
    """Non-expired Doubao failures (e.g. ``rate_limit``, transient errors)
    must NOT increment ``expired_transition_count`` — that counter is
    specifically for the EXPIRED_ACCOUNT_REASONS lifecycle, not the general
    ``consecutive_fails`` ban path."""
    session.add(_account(1))
    await session.commit()
    pool = AccountPool(session)

    await pool.report_failure(1, reason="rate_limit")
    acc = await session.get(LLMAccount, 1)
    assert acc.expired_transition_count == 0
    # rate_limit puts the account into COOLDOWN per existing semantics.
    assert acc.status == AccountStatus.COOLDOWN.value


# ─── Fix A: proactive pool pre-warming ────────────────────────────────────────


def _seed_pool_sync(db_url: str, *, doubao_active_count: int) -> None:
    """Synchronously seed an sqlite test DB with N active Doubao accounts."""

    async def _seed() -> None:
        engine = create_async_engine(db_url, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as db:
            for i in range(doubao_active_count):
                db.add(
                    LLMAccount(
                        id=100 + i,
                        llm_name="doubao",
                        email=f"acc{100+i}@local",
                        phone_number=f"10000000{i:03d}",
                        cookies_json='[{"name":"a","value":"b"}]',
                        daily_limit=20,
                        query_count_today=0,
                        consecutive_fails=0,
                        expired_transition_count=0,
                        status=AccountStatus.ACTIVE.value,
                    )
                )
            await db.commit()
        await engine.dispose()

    asyncio.run(_seed())


class _TaskSessionContext:
    """Minimal async-context-manager wrapper around an ``async_sessionmaker``,
    mirroring ``get_task_async_session`` used by celery tasks at runtime."""

    def __init__(self, maker):
        self._maker = maker
        self._db = None

    async def __aenter__(self):
        self._db = self._maker()
        return self._db

    async def __aexit__(self, exc_type, exc, tb):
        if self._db is not None:
            await self._db.close()


class _FakeAutoLogin:
    """Capture ``apply_async`` invocations like the existing pattern in
    test_query_execution_debugging.py."""

    calls: list[dict] = []

    @classmethod
    def apply_async(cls, *, kwargs, queue):
        cls.calls.append({"kwargs": kwargs, "queue": queue})


def test_prewarm_enqueues_when_active_below_target(monkeypatch, tmp_path):
    """When ``doubao`` active count is below the target, the prewarm task must
    enqueue ``auto_login(new_account=True)`` exactly ``target - active`` times.
    """
    from geo_tracker.tasks import celery_tasks

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'prewarm-deficit.db'}"
    _seed_pool_sync(db_url, doubao_active_count=0)  # active=0, target=3 -> 3 enqueues

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    async def fake_should_enqueue_new_account(platform):
        return True

    _FakeAutoLogin.calls = []
    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(
        celery_tasks,
        "should_enqueue_new_account",
        fake_should_enqueue_new_account,
    )
    monkeypatch.setattr(celery_tasks, "auto_login", _FakeAutoLogin)
    monkeypatch.setenv("DOUBAO_TARGET_ACTIVE_POOL", "3")

    result = celery_tasks.prewarm_account_pool.run()

    assert result["total_enqueued"] == 3
    assert result["per_engine"]["doubao"]["active"] == 0
    assert result["per_engine"]["doubao"]["target_active"] == 3
    assert result["per_engine"]["doubao"]["enqueued"] == 3
    # Each call should target Doubao via new_account=True; queue=account_login.
    for call in _FakeAutoLogin.calls:
        assert call["queue"] == "account_login"
        assert call["kwargs"] == {"platform": "doubao", "new_account": True}
    assert len(_FakeAutoLogin.calls) == 3


def test_prewarm_skips_when_active_at_target(monkeypatch, tmp_path):
    """When the pool already has TARGET_ACTIVE active accounts, the task must
    not enqueue anything — pre-existing reactive path stays the only writer."""
    from geo_tracker.tasks import celery_tasks

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'prewarm-full.db'}"
    _seed_pool_sync(db_url, doubao_active_count=3)  # active=3, target=3

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    async def fake_should_enqueue_new_account(platform):
        return True

    _FakeAutoLogin.calls = []
    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(
        celery_tasks,
        "should_enqueue_new_account",
        fake_should_enqueue_new_account,
    )
    monkeypatch.setattr(celery_tasks, "auto_login", _FakeAutoLogin)
    monkeypatch.setenv("DOUBAO_TARGET_ACTIVE_POOL", "3")

    result = celery_tasks.prewarm_account_pool.run()

    assert result["total_enqueued"] == 0
    assert result["per_engine"]["doubao"]["enqueued"] == 0
    assert _FakeAutoLogin.calls == []


def test_prewarm_respects_should_enqueue_new_account_gate(monkeypatch, tmp_path):
    """When ``should_enqueue_new_account`` returns False (in-flight lock held
    or 30-min failure cooldown active), the task must stop enqueuing — burning
    extra apply_async calls past a closed gate just wastes broker work and
    creates noise in the lock/cooldown logs."""
    from geo_tracker.tasks import celery_tasks

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'prewarm-locked.db'}"
    _seed_pool_sync(db_url, doubao_active_count=0)

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    async def fake_should_enqueue_new_account(platform):
        return False  # gate closed

    _FakeAutoLogin.calls = []
    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(
        celery_tasks,
        "should_enqueue_new_account",
        fake_should_enqueue_new_account,
    )
    monkeypatch.setattr(celery_tasks, "auto_login", _FakeAutoLogin)
    monkeypatch.setenv("DOUBAO_TARGET_ACTIVE_POOL", "3")

    result = celery_tasks.prewarm_account_pool.run()

    assert result["total_enqueued"] == 0
    assert result["per_engine"]["doubao"]["enqueued"] == 0
    assert result["per_engine"]["doubao"]["lock_skipped"] == 1
    assert _FakeAutoLogin.calls == []


def test_prewarm_zero_target_does_not_enqueue(monkeypatch, tmp_path):
    """``DOUBAO_TARGET_ACTIVE_POOL=0`` opts the engine OUT of pre-warming so
    operators can disable it without removing the beat entry. The snapshot is
    still logged for visibility."""
    from geo_tracker.tasks import celery_tasks

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'prewarm-disabled.db'}"
    _seed_pool_sync(db_url, doubao_active_count=0)

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    async def fake_should_enqueue_new_account(platform):
        return True

    _FakeAutoLogin.calls = []
    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(
        celery_tasks,
        "should_enqueue_new_account",
        fake_should_enqueue_new_account,
    )
    monkeypatch.setattr(celery_tasks, "auto_login", _FakeAutoLogin)
    monkeypatch.setenv("DOUBAO_TARGET_ACTIVE_POOL", "0")

    result = celery_tasks.prewarm_account_pool.run()

    assert result["total_enqueued"] == 0
    assert result["per_engine"]["doubao"]["target_active"] == 0
    assert result["per_engine"]["doubao"]["enqueued"] == 0
    assert _FakeAutoLogin.calls == []
