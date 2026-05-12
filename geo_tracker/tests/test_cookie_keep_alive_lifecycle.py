from __future__ import annotations

import asyncio
import json
import logging
import sys
import types
from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from geo_tracker.db.models import AccountStatus, Base, LLMAccount


def _install_fake_playwright(monkeypatch: pytest.MonkeyPatch) -> None:
    playwright_pkg = types.ModuleType("playwright")
    playwright_async = types.ModuleType("playwright.async_api")
    playwright_async.async_playwright = object
    playwright_async.BrowserContext = object
    playwright_async.ElementHandle = object
    playwright_async.Page = object
    playwright_async.TimeoutError = TimeoutError
    monkeypatch.setitem(sys.modules, "playwright", playwright_pkg)
    monkeypatch.setitem(sys.modules, "playwright.async_api", playwright_async)


class _TaskSessionContext:
    def __init__(self, maker):
        self.maker = maker
        self.session = None

    async def __aenter__(self):
        self.session = self.maker()
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        await self.session.close()
        return False


async def _seed_account(db_url: str, account: LLMAccount) -> None:
    engine = create_async_engine(db_url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        session.add(account)
        await session.commit()
    await engine.dispose()


async def _load_account(db_url: str, account_id: int) -> LLMAccount:
    engine = create_async_engine(db_url, future=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        account = await session.get(LLMAccount, account_id)
        await session.refresh(account)
    await engine.dispose()
    return account


def _patch_task_db(monkeypatch: pytest.MonkeyPatch, celery_tasks, db_url: str) -> None:
    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(celery_tasks.asyncio, "sleep", no_sleep)


def test_cookie_keep_alive_marks_chatgpt_auth_redirect_expired_and_relogin_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    caplog: pytest.LogCaptureFixture,
):
    _install_fake_playwright(monkeypatch)
    from geo_tracker.tasks import celery_tasks

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'keepalive-expired.db'}"
    account_id = 61801
    asyncio.run(
        _seed_account(
            db_url,
            LLMAccount(
                id=account_id,
                llm_name="chatgpt",
                status=AccountStatus.ACTIVE.value,
                cookies_json=json.dumps(
                    {
                        "cookies": [{"name": "session", "value": "<redacted>"}],
                        "localStorage": {"auth": "<redacted>"},
                    }
                ),
                cookies_updated_at=datetime.utcnow(),
                daily_limit=20,
            ),
        )
    )
    _patch_task_db(monkeypatch, celery_tasks, db_url)

    class FakeGuestQueryExecutor:
        def __init__(self, *args, **kwargs):
            self.last_error_reason = None
            self.keep_alive_evidence = None

    async def fake_visit_and_refresh(executor, _config, llm_name):
        assert llm_name == "chatgpt"
        executor.last_error_reason = "chatgpt_auth_redirect"
        executor.keep_alive_evidence = "url_host=auth.openai.com"
        return None

    relogin_calls: list[dict] = []

    async def fake_should_enqueue_relogin(enqueued_account_id):
        assert enqueued_account_id == account_id
        return True

    class FakeAutoLogin:
        @staticmethod
        def apply_async(*, kwargs, queue):
            relogin_calls.append({"kwargs": kwargs, "queue": queue})

    monkeypatch.setenv("COOKIE_KEEP_ALIVE_AUTO_RELOGIN", "true")
    monkeypatch.setattr(celery_tasks, "GuestQueryExecutor", FakeGuestQueryExecutor)
    monkeypatch.setattr(celery_tasks, "_visit_and_refresh", fake_visit_and_refresh)
    monkeypatch.setattr(celery_tasks, "should_enqueue_relogin", fake_should_enqueue_relogin)
    monkeypatch.setattr(celery_tasks, "auto_login", FakeAutoLogin)
    caplog.set_level(logging.INFO)

    result = celery_tasks.cookie_keep_alive.run()

    account = asyncio.run(_load_account(db_url, account_id))
    assert result["failed"] == 1
    assert account.status == AccountStatus.EXPIRED.value
    assert account.cooldown_until is None
    assert relogin_calls == [
        {"kwargs": {"account_id": account_id}, "queue": "account_login"}
    ]
    assert "reason=chatgpt_auth_redirect" in caplog.text
    assert "new_status=expired" in caplog.text
    assert "url_host=auth.openai.com" in caplog.text
    assert '"cookies"' not in caplog.text
    assert '"localStorage"' not in caplog.text


def test_cookie_keep_alive_success_preserves_local_storage_and_storage_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    _install_fake_playwright(monkeypatch)
    from geo_tracker.tasks import celery_tasks

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'keepalive-storage.db'}"
    account_id = 61802
    storage_state = {
        "origins": [
            {
                "origin": "https://chat.deepseek.com",
                "localStorage": [{"name": "auth", "value": "<redacted>"}],
            }
        ]
    }
    asyncio.run(
        _seed_account(
            db_url,
            LLMAccount(
                id=account_id,
                llm_name="deepseek",
                status=AccountStatus.ACTIVE.value,
                cookies_json=json.dumps(
                    {
                        "cookies": [{"name": "old", "value": "<redacted>"}],
                        "localStorage": {"auth": "<redacted>"},
                        "storageState": storage_state,
                    }
                ),
                cookies_updated_at=datetime.utcnow(),
                daily_limit=20,
            ),
        )
    )
    _patch_task_db(monkeypatch, celery_tasks, db_url)

    class FakeGuestQueryExecutor:
        def __init__(self, *args, **kwargs):
            pass

    async def fake_visit_and_refresh(_executor, _config, llm_name):
        assert llm_name == "deepseek"
        return [{"name": "fresh", "value": "<redacted>", "domain": ".deepseek.com", "path": "/"}]

    monkeypatch.setattr(celery_tasks, "GuestQueryExecutor", FakeGuestQueryExecutor)
    monkeypatch.setattr(celery_tasks, "_visit_and_refresh", fake_visit_and_refresh)

    result = celery_tasks.cookie_keep_alive.run()

    account = asyncio.run(_load_account(db_url, account_id))
    payload = json.loads(account.cookies_json)
    assert result["refreshed"] == 1
    assert payload["cookies"][0]["name"] == "fresh"
    assert payload["localStorage"] == {"auth": "<redacted>"}
    assert payload["storageState"] == storage_state


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("llm_name", "config", "page", "expected_reason"),
    [
        (
            "chatgpt",
            {"login_redirect_domains": ["auth.openai.com"]},
            {
                "url": "https://chatgpt.com/",
                "title": "ChatGPT",
                "text": "Log in to get answers based on saved chats Sign up for free Stay logged out",
            },
            "chatgpt_not_logged_in",
        ),
        (
            "doubao",
            {"login_redirect_domains": ["passport.douyin.com"]},
            {
                "url": "https://www.doubao.com/chat",
                "title": "Doubao",
                "text": "\u514d\u767b\u5f55 \u767b\u5f55",
                "html": "<button>\u767b\u5f55</button>",
            },
            "doubao_not_logged_in",
        ),
        (
            "deepseek",
            {"login_redirect_domains": ["login.deepseek.com", "deepseek.com/sign_in"]},
            {
                "url": "https://login.deepseek.com/sign_in",
                "title": "Sign in",
                "text": "Sign in to continue",
            },
            "login_redirect",
        ),
    ],
)
async def test_keep_alive_probe_classifies_supported_login_loss_signals(
    monkeypatch: pytest.MonkeyPatch,
    llm_name: str,
    config: dict,
    page: dict,
    expected_reason: str,
):
    _install_fake_playwright(monkeypatch)
    from geo_tracker.tasks import celery_tasks

    class FakePage:
        url = page["url"]

        async def title(self):
            return page.get("title", "")

        async def evaluate(self, script):
            if "outerHTML" in script:
                return page.get("html", "")
            return page.get("text", "")

    reason, evidence = await celery_tasks._keep_alive_probe_failure_reason(
        llm_name,
        config,
        FakePage(),
    )

    assert reason == expected_reason
    assert "url_host=" in evidence or "body_marker=" in evidence
    assert page.get("text", "") not in evidence


@pytest.mark.asyncio
async def test_chatgpt_keep_alive_session_200_without_token_is_auth_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    _install_fake_playwright(monkeypatch)
    from geo_tracker.tasks import celery_tasks

    class FakeResponse:
        ok = True
        status = 200

    class FakePage:
        async def goto(self, url, **_kwargs):
            assert url == "https://chatgpt.com/api/auth/session"
            return FakeResponse()

        async def inner_text(self, selector):
            assert selector == "body"
            return '{"user":{}}'

    reason, evidence = await celery_tasks._chatgpt_keep_alive_session_failure_reason(
        FakePage()
    )

    assert reason == "chatgpt_not_logged_in"
    assert "session_access_token=false" in evidence
    assert '{"user":{}}' not in evidence
