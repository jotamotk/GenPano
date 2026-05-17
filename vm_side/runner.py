"""VM-side FastAPI runner (Issue #1115).

Long-running HTTP service on each VM. Listens on 127.0.0.1:7000 (loopback only —
external access is via Tailscale-tunneled SSH, never raw TCP from the public
internet) and exposes two endpoints:

    GET  /healthz   -> liveness + per-engine CDP attach status
    POST /run       -> run one query against the per-engine persistent Chrome

Architecture invariants enforced here (see CLAUDE.md / approved plan):

- Connects via Playwright ``connect_over_cdp`` to the per-engine Chrome that
  is already running under a persistent ``--user-data-dir`` profile. Per-port
  Chrome:  doubao -> 9222, deepseek -> 9223.
- Reuses ``browser.contexts[0]`` — the persistent profile owns the cookies.
  We MUST NOT call ``context.add_cookies()`` nor ``browser.new_context()``.
- Selectors are copied verbatim from
  ``experiments/vm_per_account/poc_runner.py`` ``ENGINE_CONFIG`` so this
  module has zero runtime dependency on the experiments package or on
  ``geo_tracker/``.
- One in-flight ``/run`` per engine port — an ``asyncio.Lock`` per port
  prevents concurrent automation on the same Chrome (which would race input
  selectors / response containers).
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import random
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

try:  # Playwright is required at runtime but tests stub it via patching.
    from playwright.async_api import (  # type: ignore
        Browser,
        BrowserContext,
        Page,
        async_playwright,
    )
except Exception:  # pragma: no cover - import guard for test envs without playwright
    Browser = Any  # type: ignore
    BrowserContext = Any  # type: ignore
    Page = Any  # type: ignore
    async_playwright = None  # type: ignore


# --- Engine config (copied from experiments/vm_per_account/poc_runner.py) ----
# DO NOT import from experiments/ or geo_tracker/. Selectors live LOCALLY so
# this runner is independently deployable to a VM that has only vm_side/.

ENGINE_CONFIG: dict[str, dict[str, Any]] = {
    "doubao": {
        "port": 9222,
        "url": "https://www.doubao.com/chat",
        "input_selector": (
            "#input-engine-container textarea.semi-input-textarea:not([aria-hidden='true']), "
            "textarea.semi-input-textarea:not([aria-hidden='true']), "
            "textarea:not([aria-hidden='true']), "
            "[contenteditable='true']"
        ),
        "submit_button": (
            "#flow-end-msg-send:not([aria-disabled='true']):not([data-disabled='true']), "
            "button[id='flow-end-msg-send']"
        ),
        "response_selector": (
            ".flow-markdown-body, "
            "[data-testid='receive_message'] .flow-markdown-body"
        ),
        "login_redirect_domains": [
            "passport.volcengine.com",
            "sso.volcengine.com",
            "passport.douyin.com",
        ],
    },
    "deepseek": {
        "port": 9223,
        "url": "https://chat.deepseek.com",
        "input_selector": "textarea, [contenteditable=true], input[type=text]",
        "submit_button": "div[role='button']:has-text('发送')",
        "response_selector": ".ds-markdown, [class*='message-content'] .markdown",
        "login_redirect_domains": [
            "login.deepseek.com",
            "deepseek.com/sign_in",
        ],
    },
}

SUPPORTED_ENGINES: tuple[str, ...] = tuple(ENGINE_CONFIG.keys())

logger = logging.getLogger("vm_side.runner")
logging.basicConfig(
    level=os.getenv("VM_SIDE_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s [%(levelname)s] %(message)s",
)


# --- module-level connection state ------------------------------------------


class _EngineState:
    """Holds the per-engine playwright Browser handle plus a Lock so that only
    one ``/run`` can execute on each Chrome at a time.
    """

    __slots__ = ("browser", "lock", "last_error")

    def __init__(self) -> None:
        self.browser: Browser | None = None
        self.lock: asyncio.Lock = asyncio.Lock()
        self.last_error: str | None = None


_engines: dict[str, _EngineState] = {name: _EngineState() for name in SUPPORTED_ENGINES}
_playwright_handle: Any = None  # set by lifespan


def port_for(engine: str) -> int:
    cfg = ENGINE_CONFIG.get(engine)
    if not cfg:
        raise ValueError(f"unknown engine: {engine}")
    return int(cfg["port"])


async def _connect_engine(engine: str) -> None:
    """Attach to the per-engine Chrome over CDP. Idempotent — if a browser is
    already attached and ``is_connected()``, this is a no-op."""
    if async_playwright is None:
        raise RuntimeError("playwright is not installed in this environment")
    state = _engines[engine]
    if state.browser is not None:
        try:
            if state.browser.is_connected():
                return
        except Exception:  # pragma: no cover - defensive
            pass
    port = port_for(engine)
    endpoint = f"http://127.0.0.1:{port}"
    global _playwright_handle
    if _playwright_handle is None:
        _playwright_handle = await async_playwright().start()
    try:
        browser = await _playwright_handle.chromium.connect_over_cdp(endpoint)
    except Exception as exc:
        state.last_error = f"connect_over_cdp({endpoint}) failed: {exc!r}"
        logger.warning("%s", state.last_error)
        state.browser = None
        return
    state.browser = browser
    state.last_error = None
    logger.info("attached engine=%s endpoint=%s contexts=%d", engine, endpoint, len(browser.contexts))


async def _disconnect_all() -> None:
    global _playwright_handle
    for engine, state in _engines.items():
        if state.browser is not None:
            try:
                await state.browser.close()
            except Exception:
                pass
            state.browser = None
    if _playwright_handle is not None:
        try:
            await _playwright_handle.stop()
        except Exception:
            pass
        _playwright_handle = None


# --- failure-signal helpers (copied from poc_runner.py) ----------------------


def _url_hits_login_redirect(url: str, login_domains: list[str]) -> bool:
    if not url:
        return False
    lower = url.lower()
    return any(d.lower() in lower for d in login_domains)


async def _dom_has_captcha(page: Page) -> bool:
    try:
        return await page.evaluate(
            """() => {
                const sel = [
                    "[class*='captcha']",
                    "[class*='verify']",
                    "iframe[src*='captcha']",
                ];
                for (const s of sel) {
                    const el = document.querySelector(s);
                    if (el) {
                        const r = el.getBoundingClientRect ? el.getBoundingClientRect() : null;
                        if (!r || (r.width > 0 && r.height > 0)) {
                            return true;
                        }
                    }
                }
                return false;
            }"""
        )
    except Exception:
        return False


async def _wait_for_response_stable(
    page: Page,
    response_selector: str,
    timeout_secs: int,
    *,
    stable_window_secs: float = 3.0,
    poll_interval_secs: float = 0.5,
) -> str:
    deadline = time.monotonic() + timeout_secs
    last_len = -1
    last_change = time.monotonic()
    last_text = ""
    while time.monotonic() < deadline:
        try:
            text = await page.evaluate(
                """(sel) => {
                    const nodes = document.querySelectorAll(sel);
                    if (!nodes || nodes.length === 0) return "";
                    return nodes[nodes.length - 1].textContent || "";
                }""",
                response_selector,
            )
        except Exception:
            text = last_text
        if text and len(text) != last_len:
            last_len = len(text)
            last_text = text
            last_change = time.monotonic()
        elif text and (time.monotonic() - last_change) >= stable_window_secs:
            return text
        await asyncio.sleep(poll_interval_secs)
    return last_text


# --- request/response models -------------------------------------------------


class RunRequest(BaseModel):
    engine: str = Field(..., description="doubao | deepseek")
    prompt: str = Field(..., min_length=1)
    timeout_secs: int = Field(default=180, ge=10, le=600)


class RunResponse(BaseModel):
    success: bool
    raw_text: str
    raw_text_len: int
    latency_ms: int
    failure_signals: list[str]
    screenshot_b64: str | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    ok: bool
    chrome_alive: bool
    engines_status: dict[str, dict[str, Any]]


# --- FastAPI app -------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Attach lazily — if Chrome isn't up yet at runner start, /healthz will
    # surface chrome_alive=False and the watchdog will alert. We still try once
    # so /healthz is informative immediately.
    for engine in SUPPORTED_ENGINES:
        try:
            await _connect_engine(engine)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("startup attach engine=%s failed: %s", engine, exc)
    yield
    await _disconnect_all()


app = FastAPI(title="vm_side runner", version="0.1.0", lifespan=lifespan)


@app.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    engines_status: dict[str, dict[str, Any]] = {}
    any_alive = False
    for engine, state in _engines.items():
        # Re-attempt attach if not connected — cheap and self-healing.
        if state.browser is None or not _safe_is_connected(state.browser):
            try:
                await _connect_engine(engine)
            except Exception:
                pass
        attached = state.browser is not None and _safe_is_connected(state.browser)
        engines_status[engine] = {
            "attached": attached,
            "port": port_for(engine),
            "contexts": len(state.browser.contexts) if attached else 0,
            "last_error": state.last_error,
        }
        any_alive = any_alive or attached
    return HealthResponse(
        ok=True,
        chrome_alive=any_alive,
        engines_status=engines_status,
    )


def _safe_is_connected(browser: Browser | None) -> bool:
    if browser is None:
        return False
    try:
        return bool(browser.is_connected())
    except Exception:
        return False


@app.post("/run", response_model=RunResponse)
async def run(req: RunRequest) -> RunResponse:
    if req.engine not in ENGINE_CONFIG:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported engine: {req.engine} (supported: {list(SUPPORTED_ENGINES)})",
        )
    state = _engines[req.engine]
    cfg = ENGINE_CONFIG[req.engine]

    # Single in-flight per engine — guards the underlying Chrome from racing
    # input/submit/response on the same persistent tab.
    async with state.lock:
        if state.browser is None or not _safe_is_connected(state.browser):
            await _connect_engine(req.engine)
        if state.browser is None or not _safe_is_connected(state.browser):
            return RunResponse(
                success=False,
                raw_text="",
                raw_text_len=0,
                latency_ms=0,
                failure_signals=["chrome_not_attached"],
                screenshot_b64=None,
                error=state.last_error or "chrome not attached",
            )
        # Reuse persistent context — DO NOT add_cookies / new_context.
        contexts = state.browser.contexts
        if not contexts:
            return RunResponse(
                success=False,
                raw_text="",
                raw_text_len=0,
                latency_ms=0,
                failure_signals=["no_persistent_context"],
                screenshot_b64=None,
                error="browser.contexts[0] missing — Chrome started without persistent profile?",
            )
        context: BrowserContext = contexts[0]
        return await _run_one(context, req, cfg)


async def _run_one(
    context: BrowserContext,
    req: RunRequest,
    cfg: dict[str, Any],
) -> RunResponse:
    """Execute one query against the already-attached persistent context.

    Mirrors the 5 failure signals from
    ``experiments/vm_per_account/poc_runner.py``:
      1. login_redirect_url
      2. blank_page_title
      3. captcha_widget_detected
      4. raw_text_too_short
      5. page_lifecycle_error  (catch-all for closed page/context/browser)
    """
    failure_signals: list[str] = []
    raw_text = ""
    screenshot_bytes: bytes | None = None
    error_str: str | None = None
    t0 = time.monotonic()
    page: Page | None = None
    try:
        page = await context.new_page()
        await page.goto(
            cfg["url"],
            wait_until="domcontentloaded",
            timeout=req.timeout_secs * 1000,
        )

        # Pre-submit failure signals
        current_url = page.url
        if _url_hits_login_redirect(current_url, cfg["login_redirect_domains"]):
            failure_signals.append(f"login_redirect_url: {current_url}")

        try:
            title = await page.title()
        except Exception:
            title = ""
        if not title:
            failure_signals.append("blank_page_title")

        if await _dom_has_captcha(page):
            failure_signals.append("captcha_widget_detected")

        # If pre-submit signals say login/captcha, do not type — that would
        # leak the prompt to the wrong surface. Still capture a screenshot.
        if not failure_signals:
            try:
                await page.wait_for_selector(
                    cfg["input_selector"],
                    state="visible",
                    timeout=min(30_000, req.timeout_secs * 1000),
                )
                await page.type(
                    cfg["input_selector"],
                    req.prompt,
                    delay=random.randint(20, 80),
                )
                await asyncio.sleep(random.uniform(2.0, 5.0))
                try:
                    await page.click(cfg["submit_button"], timeout=15_000)
                except Exception:
                    # Fallback for engines where the send button is reactive.
                    await page.keyboard.press("Enter")

                remaining = max(10, req.timeout_secs - int(time.monotonic() - t0))
                raw_text = await _wait_for_response_stable(
                    page,
                    cfg["response_selector"],
                    timeout_secs=remaining,
                )
            except Exception as exc:
                failure_signals.append(f"page_lifecycle_error: {exc!r}")

        # Always try to capture a screenshot for forensic evidence.
        try:
            screenshot_bytes = await page.screenshot(full_page=True)
        except Exception as exc:
            failure_signals.append(f"screenshot_failed: {exc!r}")

    except Exception as exc:
        failure_signals.append(f"page_lifecycle_error: {exc!r}")
        error_str = repr(exc)
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass

    raw_len = len(raw_text or "")
    if raw_len < 30 and not failure_signals:
        failure_signals.append(f"raw_text_too_short: {raw_len} chars")

    success = not failure_signals
    latency_ms = int((time.monotonic() - t0) * 1000)
    return RunResponse(
        success=success,
        raw_text=raw_text or "",
        raw_text_len=raw_len,
        latency_ms=latency_ms,
        failure_signals=failure_signals,
        screenshot_b64=base64.b64encode(screenshot_bytes).decode("ascii") if screenshot_bytes else None,
        error=error_str,
    )


# --- entry point (also reachable via __main__) ------------------------------


def main() -> None:
    import uvicorn

    host = os.getenv("VM_SIDE_HOST", "127.0.0.1")
    port = int(os.getenv("VM_SIDE_PORT", "7000"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()


# Convenience hook for tests that want to seed the engine state without a real
# Chrome attached (see tests/vm_side/test_runner.py).
def _set_engine_browser_for_test(engine: str, browser: Any) -> None:
    _engines[engine].browser = browser
    _engines[engine].last_error = None


# httpx is imported for parity with the watchdog and to make it easy for
# operators to embed a small client probe; the runner itself does not call out.
__all__ = [
    "app",
    "ENGINE_CONFIG",
    "SUPPORTED_ENGINES",
    "port_for",
    "RunRequest",
    "RunResponse",
    "HealthResponse",
    "main",
    "httpx",
]
