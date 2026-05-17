"""Unit tests for vm_side.login_watchdog.

We do not exercise the real Prometheus HTTP server or a real Playwright
browser; instead we substitute factories so the loop runs synchronously for
one iteration and we observe the orchestrator POST + the gauge value.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from vm_side import login_watchdog as wd


# --- helpers ---------------------------------------------------------------


def _make_pw_with_pages(pages: dict[int, MagicMock]):
    """Build a playwright_factory whose ``connect_over_cdp(endpoint)`` returns a
    browser whose contexts[0].new_page() returns the page registered under the
    endpoint's port."""

    class FakePlaywright:
        def __init__(self):
            self.chromium = self
            self.started = False

        async def start(self):
            self.started = True
            return self

        async def stop(self):
            self.started = False

        async def connect_over_cdp(self, endpoint: str):
            # endpoint looks like http://127.0.0.1:9222
            port = int(endpoint.rsplit(":", 1)[-1])
            page = pages.get(port)
            if page is None:
                raise RuntimeError(f"no page registered for port {port}")
            ctx = MagicMock()

            async def new_page():
                return page

            ctx.new_page = new_page
            browser = MagicMock()
            browser.contexts = [ctx]
            browser.close = AsyncMock(return_value=None)
            return browser

    def factory():
        return FakePlaywright()

    return factory


def _make_healthy_page(url: str = "https://www.doubao.com/chat", title: str = "Doubao"):
    page = MagicMock()
    page.goto = AsyncMock(return_value=None)
    page.url = url
    page.title = AsyncMock(return_value=title)
    page.evaluate = AsyncMock(return_value=False)  # no captcha
    page.close = AsyncMock(return_value=None)
    return page


def _make_login_redirect_page():
    page = MagicMock()
    page.goto = AsyncMock(return_value=None)
    page.url = "https://passport.volcengine.com/sso?from=doubao"
    page.title = AsyncMock(return_value="Sign in")
    page.evaluate = AsyncMock(return_value=False)
    page.close = AsyncMock(return_value=None)
    return page


def _make_captcha_page():
    page = MagicMock()
    page.goto = AsyncMock(return_value=None)
    page.url = "https://www.doubao.com/chat"
    page.title = AsyncMock(return_value="Doubao")
    page.evaluate = AsyncMock(return_value=True)  # captcha present
    page.close = AsyncMock(return_value=None)
    return page


def _make_empty_title_page():
    page = MagicMock()
    page.goto = AsyncMock(return_value=None)
    page.url = "https://www.doubao.com/chat"
    page.title = AsyncMock(return_value="")
    page.evaluate = AsyncMock(return_value=False)
    page.close = AsyncMock(return_value=None)
    return page


class _RecordingClient:
    """Stand-in for httpx.AsyncClient — records calls instead of sending."""

    def __init__(self):
        self.posts: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, json=None, timeout=None):  # noqa: A002
        self.posts.append((url, json))
        resp = MagicMock()
        resp.status_code = 200
        return resp


# --- tests -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_probe_engine_healthy():
    pw_factory = _make_pw_with_pages(
        {9222: _make_healthy_page()}
    )
    pw = await pw_factory().start()
    healthy, reason = await wd.probe_engine(pw, "doubao")
    assert healthy is True
    assert reason is None


@pytest.mark.asyncio
async def test_probe_engine_login_redirect():
    pw_factory = _make_pw_with_pages({9222: _make_login_redirect_page()})
    pw = await pw_factory().start()
    healthy, reason = await wd.probe_engine(pw, "doubao")
    assert healthy is False
    assert reason == "login_redirect"


@pytest.mark.asyncio
async def test_probe_engine_captcha():
    pw_factory = _make_pw_with_pages({9222: _make_captcha_page()})
    pw = await pw_factory().start()
    healthy, reason = await wd.probe_engine(pw, "doubao")
    assert healthy is False
    assert reason == "captcha"


@pytest.mark.asyncio
async def test_probe_engine_empty_title():
    pw_factory = _make_pw_with_pages({9222: _make_empty_title_page()})
    pw = await pw_factory().start()
    healthy, reason = await wd.probe_engine(pw, "doubao")
    assert healthy is False
    assert reason == "empty_title"


@pytest.mark.asyncio
async def test_probe_engine_cdp_unreachable():
    class BrokenPlaywright:
        def __init__(self):
            self.chromium = self

        async def connect_over_cdp(self, endpoint):
            raise RuntimeError("connection refused")

        async def start(self):
            return self

    healthy, reason = await wd.probe_engine(BrokenPlaywright(), "doubao")
    assert healthy is False
    assert reason == "cdp_unreachable"


@pytest.mark.asyncio
async def test_watchdog_loop_posts_orchestrator_on_unhealthy(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_URL", "http://orch.local")
    monkeypatch.setattr(wd, "ORCHESTRATOR_URL", "http://orch.local")
    monkeypatch.setattr(wd, "VM_ID", "vm-test-7")

    pw_factory = _make_pw_with_pages(
        {
            9222: _make_login_redirect_page(),  # doubao unhealthy
            9223: _make_captcha_page(),  # deepseek unhealthy
        }
    )
    rec = _RecordingClient()

    def http_factory():
        return rec

    await wd.watchdog_loop(
        poll_secs=0,
        iterations=1,
        playwright_factory=pw_factory,
        http_client_factory=http_factory,
    )

    # Two POSTs expected, one per engine, on the first cycle since last_state
    # defaults to True.
    assert len(rec.posts) == 2
    urls = [p[0] for p in rec.posts]
    payloads = [p[1] for p in rec.posts]
    assert all(u == "http://orch.local/admin/needs_relogin" for u in urls)
    engines = {p["engine"]: p for p in payloads}
    assert engines["doubao"]["reason"] == "login_redirect"
    assert engines["doubao"]["vm_id"] == "vm-test-7"
    assert engines["deepseek"]["reason"] == "captcha"


@pytest.mark.asyncio
async def test_watchdog_loop_skips_post_when_orchestrator_unset(monkeypatch):
    monkeypatch.setattr(wd, "ORCHESTRATOR_URL", "")
    pw_factory = _make_pw_with_pages(
        {9222: _make_login_redirect_page(), 9223: _make_login_redirect_page()}
    )
    rec = _RecordingClient()

    await wd.watchdog_loop(
        poll_secs=0,
        iterations=1,
        playwright_factory=pw_factory,
        http_client_factory=lambda: rec,
    )

    # Without ORCHESTRATOR_URL the watchdog logs but does not POST.
    assert rec.posts == []


@pytest.mark.asyncio
async def test_watchdog_loop_updates_prometheus_gauges(monkeypatch):
    pytest.importorskip("prometheus_client")
    from prometheus_client import REGISTRY

    # Reset gauge registry so this test owns the gauges. Both the local cache
    # in vm_side AND the prometheus_client global REGISTRY need clearing,
    # because Gauge.__init__ auto-registers into the default registry.
    for g in list(wd._GAUGES.values()):
        try:
            REGISTRY.unregister(g)
        except Exception:
            pass
    wd._GAUGES.clear()
    monkeypatch.setattr(wd, "VM_ID", "vm-prom-1")

    # Doubao page healthy; DeepSeek page has empty title -> unhealthy. Using
    # empty_title rather than login_redirect avoids cross-engine domain coupling
    # (each engine's login_redirect_domains list is engine-specific).
    pw_factory = _make_pw_with_pages(
        {
            9222: _make_healthy_page(),
            9223: _make_empty_title_page(),
        }
    )
    rec = _RecordingClient()
    await wd.watchdog_loop(
        poll_secs=0,
        iterations=1,
        playwright_factory=pw_factory,
        http_client_factory=lambda: rec,
    )

    doubao_samples = [s for m in wd._GAUGES["doubao"].collect() for s in m.samples]
    deepseek_samples = [s for m in wd._GAUGES["deepseek"].collect() for s in m.samples]
    doubao_val = next(s.value for s in doubao_samples if s.labels.get("vm") == "vm-prom-1")
    deepseek_val = next(s.value for s in deepseek_samples if s.labels.get("vm") == "vm-prom-1")
    assert doubao_val == 1.0
    assert deepseek_val == 0.0


@pytest.mark.asyncio
async def test_notify_orchestrator_handles_post_exception(monkeypatch):
    monkeypatch.setattr(wd, "ORCHESTRATOR_URL", "http://orch.local")

    class FailingClient:
        async def post(self, url, json=None, timeout=None):  # noqa: A002
            raise httpx.ConnectError("nope")

    # Should not raise — failures are swallowed and logged.
    await wd.notify_orchestrator(FailingClient(), "doubao", "captcha")
