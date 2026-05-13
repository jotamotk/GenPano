from __future__ import annotations

import asyncio
import sys
import types

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from geo_tracker.db.models import Base


class _TaskSessionContext:
    def __init__(self, maker):
        self._maker = maker
        self._session = None

    async def __aenter__(self):
        self._session = self._maker()
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        await self._session.close()
        return False


class _FakeRedisClient:
    def __init__(self, *, cooldown_active: bool = False):
        self.cooldown_active = cooldown_active

    async def exists(self, _key):
        return self.cooldown_active

    async def aclose(self):
        return None


def _install_fake_playwright(monkeypatch):
    playwright = types.ModuleType("playwright")
    playwright_async = types.ModuleType("playwright.async_api")
    playwright_async.async_playwright = object
    playwright_async.BrowserContext = object
    playwright_async.ElementHandle = object
    playwright_async.Page = object
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.async_api", playwright_async)


def test_auto_login_cooldown_skip_releases_new_account_lock_without_failure(
    monkeypatch,
):
    _install_fake_playwright(monkeypatch)

    import redis.asyncio as aioredis

    from geo_tracker.agent import sms_login
    from geo_tracker.tasks import celery_tasks

    class DummyTaskEngine:
        async def dispose(self):
            return None

    release_calls: list[dict] = []

    async def fake_release_new_account_lock(platform, *, failed):
        release_calls.append({"platform": platform, "failed": failed})

    monkeypatch.setattr(celery_tasks, "create_task_engine", lambda: DummyTaskEngine())
    monkeypatch.setattr(
        aioredis,
        "from_url",
        lambda *args, **kwargs: _FakeRedisClient(cooldown_active=True),
    )
    monkeypatch.setattr(celery_tasks, "release_new_account_lock", fake_release_new_account_lock)
    monkeypatch.setattr(
        sms_login,
        "get_handler",
        lambda _platform: (_ for _ in ()).throw(AssertionError("handler should not run")),
    )

    result = celery_tasks.auto_login.run(platform="chatgpt", new_account=True)

    assert result == {"status": "skipped", "reason": "cooldown_active"}
    assert release_calls == [{"platform": "chatgpt", "failed": False}]


def test_auto_login_failed_new_account_registration_sets_failure_cooldown(
    monkeypatch,
    tmp_path,
):
    _install_fake_playwright(monkeypatch)

    import redis.asyncio as aioredis

    from geo_tracker.agent import sms_login
    from geo_tracker.tasks import celery_tasks

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'failed-new-account.db'}"

    async def seed_database():
        engine = create_async_engine(db_url, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(seed_database())

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    class FakeHandler:
        async def login_or_register(self):
            return {"status": "failed", "reason": "requires_manual_challenge"}

    release_calls: list[dict] = []

    async def fake_release_new_account_lock(platform, *, failed):
        release_calls.append({"platform": platform, "failed": failed})

    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(
        aioredis,
        "from_url",
        lambda *args, **kwargs: _FakeRedisClient(cooldown_active=False),
    )
    monkeypatch.setattr(celery_tasks, "release_new_account_lock", fake_release_new_account_lock)
    monkeypatch.setattr(sms_login, "get_handler", lambda _platform: FakeHandler())

    result = celery_tasks.auto_login.run(platform="chatgpt", new_account=True)

    assert result == {
        "status": "failed",
        "platform": "chatgpt",
        "reason": "requires_manual_challenge",
    }
    assert release_calls == [{"platform": "chatgpt", "failed": True}]


def test_auto_login_successful_new_account_registration_releases_without_failure(
    monkeypatch,
    tmp_path,
):
    _install_fake_playwright(monkeypatch)

    import redis.asyncio as aioredis

    from geo_tracker.agent import sms_login
    from geo_tracker.tasks import celery_tasks

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'successful-new-account.db'}"

    async def seed_database():
        engine = create_async_engine(db_url, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(seed_database())

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    class FakeHandler:
        async def login_or_register(self):
            return {
                "cookies": [{"name": "session", "value": "fresh"}],
                "phone": "18200000000",
            }

    release_calls: list[dict] = []

    async def fake_release_new_account_lock(platform, *, failed):
        release_calls.append({"platform": platform, "failed": failed})

    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(
        aioredis,
        "from_url",
        lambda *args, **kwargs: _FakeRedisClient(cooldown_active=False),
    )
    monkeypatch.setattr(celery_tasks, "release_new_account_lock", fake_release_new_account_lock)
    monkeypatch.setattr(sms_login, "get_handler", lambda _platform: FakeHandler())

    result = celery_tasks.auto_login.run(platform="chatgpt", new_account=True)

    assert result["status"] == "success"
    assert result["phone"] == "18200000000"
    assert release_calls == [{"platform": "chatgpt", "failed": False}]
