"""Refs Epic #1110 / Issue #1113.

Unit tests for the ``BrowserConnector`` extraction. These tests use
``unittest.mock.AsyncMock`` end-to-end — no real Camoufox/Chromium is
launched, so the suite runs in any Python environment that has
pytest-asyncio. They verify:

  - ``GuestQueryExecutor()`` defaults its ``connector`` attribute to a
    ``LocalLaunchConnector`` instance (production behavior unchanged).
  - ``GuestQueryExecutor(connector=...)`` accepts and stores an
    injected connector (the seam Issue #1114 will use).
  - When the executor runs a query with an injected mock connector,
    ``acquire_context`` is awaited with ``(llm, query)`` and
    ``release_context`` is awaited on the same context, even on
    failure.
  - ``LocalLaunchConnector.acquire_context`` does not silently swallow
    a malformed cookies_json payload for an LLM whose config requires
    cookies — the parse failure leaves ``add_cookies`` un-called,
    which is the documented "logged warning, no injection" production
    behavior we want to lock in.
"""
from __future__ import annotations

import json
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest


def _install_fake_playwright(monkeypatch):
    """Stub out ``playwright.async_api`` so importing ``guest_executor`` /
    ``executors.local`` succeeds in environments without playwright
    installed. Mirrors the helper in
    ``test_query_execution_debugging.py``."""
    playwright = types.ModuleType("playwright")
    playwright_async = types.ModuleType("playwright.async_api")
    playwright_async.async_playwright = MagicMock()
    playwright_async.BrowserContext = object
    playwright_async.ElementHandle = object
    playwright_async.Page = object
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.async_api", playwright_async)


def test_default_connector_is_local_launch_connector(monkeypatch):
    """``GuestQueryExecutor`` with no connector argument uses
    ``LocalLaunchConnector`` so existing call sites preserve behavior."""
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.executors import LocalLaunchConnector
    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    executor = GuestQueryExecutor()
    assert isinstance(executor.connector, LocalLaunchConnector)


def test_executor_accepts_injected_connector(monkeypatch):
    """The injection seam (#1114 will use this for ``RemoteCDPConnector``)."""
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.executors import BrowserConnector
    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    class _MockConnector(BrowserConnector):
        async def acquire_context(self, llm, account):
            raise NotImplementedError

        async def release_context(self, context):
            return None

    mock_connector = _MockConnector()
    executor = GuestQueryExecutor(connector=mock_connector)
    assert executor.connector is mock_connector


def test_executor_default_connector_is_unique_per_instance(monkeypatch):
    """Two ``GuestQueryExecutor`` instances should not share a single
    ``LocalLaunchConnector`` (resource handles would clash). Verifies
    the default is constructed per-instance, not aliased to a module-
    level singleton."""
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    e1 = GuestQueryExecutor()
    e2 = GuestQueryExecutor()
    assert e1.connector is not e2.connector


@pytest.mark.asyncio
async def test_execute_once_invokes_connector_acquire_and_release(monkeypatch):
    """Inside ``_execute_once``, the injected connector's
    ``acquire_context`` must be awaited with ``(llm, account)``, and
    ``release_context`` must run on the same context even when the
    downstream code fails. This pins the seam contract.

    Refs Codex review on PR #1121 (Bug 1): the second positional arg is
    the ``account`` (per ABC in ``executors/base.py``), NOT the ``query``.
    The earlier version of this test asserted ``is fake_query`` and
    locked in a broken contract — ``RemoteCDPConnector.acquire_context``
    reads ``account.vm_id`` from this slot, so passing the ``Query``
    raised ``NO_ACCOUNT_AVAILABLE`` on every vm_session query. The fix
    threads ``account`` through ``GuestQueryExecutor.__init__`` and
    ``select_executor``; this test now pins the corrected contract.
    """
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.executors import BrowserConnector
    from geo_tracker.agent.guest_executor import GUEST_LLM_CONFIG, GuestQueryExecutor

    # Fake context with a ``new_page`` that raises so the executor's
    # try-block falls into the failure return path. The connector's
    # release_context must still run via the finally.
    fake_context = MagicMock()
    fake_context.new_page = AsyncMock(side_effect=RuntimeError("synthetic"))

    acquire_calls: list[tuple] = []
    release_calls: list = []

    class _RecordingConnector(BrowserConnector):
        # Mirrors the public attributes the executor reads off the
        # connector after acquire (see ``executors/local.py`` for the
        # production source of these values).
        local_storage_data: dict = {}
        use_camoufox: bool = False
        active_qg_lease = None

        async def acquire_context(self, llm, account):
            acquire_calls.append((llm, account))
            return fake_context

        async def release_context(self, context):
            release_calls.append(context)

    connector = _RecordingConnector()
    # Use an account stand-in with a ``vm_id`` attribute so the assertion
    # below mirrors what ``RemoteCDPConnector.acquire_context`` will
    # actually read off the arg (``getattr(account, "vm_id", None)``).
    fake_account = MagicMock()
    fake_account.vm_id = "vm-test-001"
    fake_account.id = 99
    executor = GuestQueryExecutor(connector=connector, account=fake_account)

    fake_query = MagicMock()
    fake_query.target_llm = "perplexity"  # 8-engine key with no login

    result = await executor._execute_once(
        fake_query, GUEST_LLM_CONFIG["perplexity"], use_proxy=False
    )

    # _execute_once swallows the inner failure and returns None; what we
    # care about is the connector contract.
    assert result is None
    assert len(acquire_calls) == 1
    assert acquire_calls[0][0] == "perplexity"
    # The connector MUST receive the account (so it can read .vm_id),
    # NOT the query. Bug 1 in PR #1121 had this slot wired to ``query``.
    assert acquire_calls[0][1] is fake_account
    assert getattr(acquire_calls[0][1], "vm_id", None) == "vm-test-001"
    assert release_calls == [fake_context]


@pytest.mark.asyncio
async def test_local_connector_invalid_cookie_json_does_not_inject(monkeypatch):
    """``LocalLaunchConnector`` is asked to set up a context for an
    engine whose config requires login. Account-pool cookies are present
    but malformed (not valid JSON). The connector must not silently
    inject empty cookies — production behavior logs a warning then
    falls through to env-cookie lookup, which we verify here by
    asserting ``add_cookies`` was never awaited.

    This test exists so future edits cannot accidentally swallow a
    cookie-parse failure into a successful-looking acquire path.
    """
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.executors import LocalLaunchConnector
    from geo_tracker.agent.executors import local as local_mod

    # Force ``HAS_CAMOUFOX = False`` so the connector takes the plain
    # Chromium path (the path we can mock cleanly without a real
    # camoufox install).
    monkeypatch.setattr(local_mod, "HAS_CAMOUFOX", False)

    # Mock playwright launch so acquire_context produces our mock
    # context without actually opening a browser. We also patch
    # ``cleanup_browser_resources`` so release_context is a no-op on
    # the mocks.
    fake_context = MagicMock()
    fake_context.add_cookies = AsyncMock()
    fake_context.route = AsyncMock()
    fake_browser = MagicMock()
    fake_browser.new_context = AsyncMock(return_value=fake_context)
    fake_pw_driver = MagicMock()
    fake_pw_driver.chromium = MagicMock()
    fake_pw_driver.chromium.launch = AsyncMock(return_value=fake_browser)
    fake_pw = MagicMock()
    fake_pw.start = AsyncMock(return_value=fake_pw_driver)
    monkeypatch.setattr(
        local_mod, "async_playwright", MagicMock(return_value=fake_pw)
    )
    monkeypatch.setattr(
        local_mod, "cleanup_browser_resources", AsyncMock(return_value=None)
    )

    # ChatGPT requires login. We pass a malformed cookies_json blob.
    # The connector logs+warns and falls back to the env cookie
    # path. With no env cookie set, injected_cookies stays empty
    # → ``context.add_cookies`` is NEVER called.
    monkeypatch.delenv("CHATGPT_COOKIES_JSON", raising=False)

    from geo_tracker.agent.guest_executor import GUEST_LLM_CONFIG

    config = GUEST_LLM_CONFIG["chatgpt"]
    assert config["requires_login"] is True  # invariant the test depends on

    connector = LocalLaunchConnector(
        proxy_url=None,
        account_cookies="this is not json {{",
        use_proxy=False,
        target_url=config["url"],
        config=config,
        qg_proxy_client=None,
    )

    fake_account = object()
    context = await connector.acquire_context("chatgpt", fake_account)

    # Same context object the launch produced.
    assert context is fake_context
    # No cookies were added — the malformed payload was rejected (as a
    # warning, not silently transformed into an empty cookie list that
    # would still call add_cookies([])).
    fake_context.add_cookies.assert_not_awaited()


@pytest.mark.asyncio
async def test_local_connector_legacy_cookie_list_format_is_injected(monkeypatch):
    """Cookie payload as a plain JSON array (legacy format) is parsed
    and injected. Confirms the legacy path still works after the
    move."""
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.executors import local as local_mod

    cookies = [{"name": "session", "value": "abc", "domain": ".x.test"}]
    raw = json.dumps(cookies)

    monkeypatch.setattr(local_mod, "HAS_CAMOUFOX", False)

    fake_context = MagicMock()
    fake_context.add_cookies = AsyncMock()
    fake_context.route = AsyncMock()
    fake_browser = MagicMock()
    fake_browser.new_context = AsyncMock(return_value=fake_context)
    fake_pw_driver = MagicMock()
    fake_pw_driver.chromium = MagicMock()
    fake_pw_driver.chromium.launch = AsyncMock(return_value=fake_browser)
    fake_pw = MagicMock()
    fake_pw.start = AsyncMock(return_value=fake_pw_driver)
    monkeypatch.setattr(
        local_mod, "async_playwright", MagicMock(return_value=fake_pw)
    )
    monkeypatch.setattr(
        local_mod, "cleanup_browser_resources", AsyncMock(return_value=None)
    )

    connector = local_mod.LocalLaunchConnector(
        proxy_url=None,
        account_cookies=raw,
        use_proxy=False,
        target_url="https://www.perplexity.ai",
        config={"url": "https://www.perplexity.ai", "requires_login": False},
        qg_proxy_client=None,
    )
    context = await connector.acquire_context("perplexity", object())

    assert context is fake_context
    fake_context.add_cookies.assert_awaited_once_with(cookies)
