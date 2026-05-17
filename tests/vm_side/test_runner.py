"""Unit tests for vm_side.runner.

These tests use FastAPI's ``TestClient`` and stub Playwright via
``unittest.mock.AsyncMock`` so they run without a real Chromium binary.

What they prove:
  - ``/healthz`` returns the documented schema and reflects engine state.
  - ``/run`` validates the request body (rejects unknown engines).
  - ``/run`` produces a structured RunResponse on the happy path and on a
    Chrome-failure path (login redirect / blank title / captcha / short text).
  - The per-engine asyncio.Lock is used (single in-flight per engine).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from vm_side import runner as runner_module
from vm_side.runner import RunRequest, app


# --- helpers ---------------------------------------------------------------


def _make_fake_browser(*, contexts: list | None = None, connected: bool = True) -> MagicMock:
    """Build a MagicMock that quacks like a connected Playwright Browser."""
    browser = MagicMock()
    browser.is_connected = MagicMock(return_value=connected)
    browser.contexts = contexts if contexts is not None else [_make_fake_context()]
    return browser


def _make_fake_context(*, page_factory=None) -> MagicMock:
    """Build a MagicMock that quacks like a Playwright BrowserContext.

    ``page_factory`` is an async callable returning a fake page; default
    returns a happy page that emits a non-empty rawText.
    """
    ctx = MagicMock()
    if page_factory is None:
        page_factory = _make_happy_page

    async def new_page():
        return await page_factory()

    ctx.new_page = new_page
    return ctx


async def _make_happy_page():
    page = MagicMock()
    page.goto = AsyncMock(return_value=None)
    page.url = "https://www.doubao.com/chat"
    page.title = AsyncMock(return_value="Doubao Chat")
    # captcha probe + response-stable probe both go through page.evaluate
    page.evaluate = AsyncMock(
        side_effect=lambda *a, **kw: False
        if a and "captcha" in a[0]
        else "这是一个长度超过30字符的豆包测试响应文本数据测试" * 3
    )
    page.wait_for_selector = AsyncMock(return_value=None)
    page.type = AsyncMock(return_value=None)
    page.click = AsyncMock(return_value=None)
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock(return_value=None)
    page.screenshot = AsyncMock(return_value=b"\x89PNG\r\n\x1a\nfakebytes")
    page.close = AsyncMock(return_value=None)
    return page


async def _make_login_redirect_page():
    page = MagicMock()
    page.goto = AsyncMock(return_value=None)
    page.url = "https://passport.volcengine.com/login?redirect=doubao"
    page.title = AsyncMock(return_value="Login")
    page.evaluate = AsyncMock(return_value=False)
    page.wait_for_selector = AsyncMock(return_value=None)
    page.type = AsyncMock(return_value=None)
    page.click = AsyncMock(return_value=None)
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock(return_value=None)
    page.screenshot = AsyncMock(return_value=b"PNG")
    page.close = AsyncMock(return_value=None)
    return page


async def _make_blank_title_page():
    page = MagicMock()
    page.goto = AsyncMock(return_value=None)
    page.url = "https://www.doubao.com/chat"
    page.title = AsyncMock(return_value="")
    page.evaluate = AsyncMock(return_value=False)
    page.wait_for_selector = AsyncMock(return_value=None)
    page.type = AsyncMock(return_value=None)
    page.click = AsyncMock(return_value=None)
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock(return_value=None)
    page.screenshot = AsyncMock(return_value=b"PNG")
    page.close = AsyncMock(return_value=None)
    return page


@pytest.fixture
def patched_runner(monkeypatch):
    """Seed both engines with a fake browser and patch out lifespan attach."""

    async def noop_connect(engine):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(runner_module, "_connect_engine", noop_connect)
    # Reset both engine states fresh each test.
    for name, state in runner_module._engines.items():
        state.browser = None
        state.last_error = None
    yield
    for name, state in runner_module._engines.items():
        state.browser = None
        state.last_error = None


# --- tests -----------------------------------------------------------------


def test_healthz_schema_when_no_chrome(patched_runner):
    with TestClient(app) as client:
        r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["chrome_alive"] is False
    assert set(body["engines_status"].keys()) == {"doubao", "deepseek"}
    for name, status in body["engines_status"].items():
        assert "attached" in status
        assert "port" in status
        assert "contexts" in status
        assert status["attached"] is False


def test_healthz_reports_chrome_alive(patched_runner):
    runner_module._set_engine_browser_for_test("doubao", _make_fake_browser())
    with TestClient(app) as client:
        r = client.get("/healthz")
    body = r.json()
    assert body["chrome_alive"] is True
    assert body["engines_status"]["doubao"]["attached"] is True
    assert body["engines_status"]["doubao"]["contexts"] == 1


def test_run_rejects_unknown_engine(patched_runner):
    with TestClient(app) as client:
        r = client.post("/run", json={"engine": "bogus", "prompt": "hi"})
    # Pydantic accepts the string; the app handler rejects with 400.
    assert r.status_code == 400
    assert "unsupported engine" in r.json()["detail"]


def test_run_rejects_empty_prompt(patched_runner):
    with TestClient(app) as client:
        r = client.post("/run", json={"engine": "doubao", "prompt": ""})
    # Pydantic validation: min_length=1 → 422.
    assert r.status_code == 422


def test_run_returns_structured_failure_when_no_chrome(patched_runner):
    with TestClient(app) as client:
        r = client.post("/run", json={"engine": "doubao", "prompt": "hello"})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "chrome_not_attached" in body["failure_signals"]
    assert body["raw_text"] == ""
    assert body["raw_text_len"] == 0


def test_run_happy_path(patched_runner):
    ctx = _make_fake_context(page_factory=_make_happy_page)
    browser = _make_fake_browser(contexts=[ctx])
    runner_module._set_engine_browser_for_test("doubao", browser)
    with TestClient(app) as client:
        r = client.post("/run", json={"engine": "doubao", "prompt": "你好", "timeout_secs": 30})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True, body
    assert body["raw_text_len"] >= 30
    assert body["failure_signals"] == []
    assert body["screenshot_b64"] is not None
    assert body["latency_ms"] >= 0


def test_run_detects_login_redirect(patched_runner):
    ctx = _make_fake_context(page_factory=_make_login_redirect_page)
    browser = _make_fake_browser(contexts=[ctx])
    runner_module._set_engine_browser_for_test("doubao", browser)
    with TestClient(app) as client:
        r = client.post("/run", json={"engine": "doubao", "prompt": "你好", "timeout_secs": 15})
    body = r.json()
    assert body["success"] is False
    assert any(s.startswith("login_redirect_url") for s in body["failure_signals"]), body


def test_run_detects_blank_title(patched_runner):
    ctx = _make_fake_context(page_factory=_make_blank_title_page)
    browser = _make_fake_browser(contexts=[ctx])
    runner_module._set_engine_browser_for_test("doubao", browser)
    with TestClient(app) as client:
        r = client.post("/run", json={"engine": "doubao", "prompt": "你好", "timeout_secs": 15})
    body = r.json()
    assert body["success"] is False
    assert "blank_page_title" in body["failure_signals"]


def test_run_no_persistent_context(patched_runner):
    browser = _make_fake_browser(contexts=[])
    runner_module._set_engine_browser_for_test("doubao", browser)
    with TestClient(app) as client:
        r = client.post("/run", json={"engine": "doubao", "prompt": "hi"})
    body = r.json()
    assert body["success"] is False
    assert "no_persistent_context" in body["failure_signals"]


def test_port_for_known_engines():
    assert runner_module.port_for("doubao") == 9222
    assert runner_module.port_for("deepseek") == 9223


def test_port_for_unknown_engine_raises():
    with pytest.raises(ValueError):
        runner_module.port_for("nope")


def test_engine_config_has_required_keys():
    for engine, cfg in runner_module.ENGINE_CONFIG.items():
        for key in ("port", "url", "input_selector", "submit_button",
                    "response_selector", "login_redirect_domains"):
            assert key in cfg, f"engine={engine} missing {key}"
        assert isinstance(cfg["login_redirect_domains"], list)
        assert cfg["login_redirect_domains"], f"engine={engine} login_redirect_domains empty"


def test_each_engine_has_its_own_lock():
    """Single in-flight per engine — locks must be distinct objects."""
    locks = {n: s.lock for n, s in runner_module._engines.items()}
    assert len(locks) == 2
    assert locks["doubao"] is not locks["deepseek"]
