"""VM-side login watchdog (Issue #1115).

Long-running async script that polls each per-engine Chrome (via CDP) once per
minute and decides whether the persistent profile is still logged in. Surface
state is reported in two channels:

1. **Prometheus gauges** on a local HTTP server (default port 8000):
       ``doubao_session_alive{vm="<vm_id>"}``     0 / 1
       ``deepseek_session_alive{vm="<vm_id>"}``   0 / 1
   The orchestrator scrapes these on the Tailnet.

2. **HTTP POST to the orchestrator** at ``${ORCHESTRATOR_URL}/admin/needs_relogin``
   with payload ``{vm_id, engine, reason}`` whenever the watchdog flips from
   healthy -> unhealthy. Reasons: ``login_redirect``, ``captcha``, ``empty_title``.

Healthy = (page URL is NOT on ``login_redirect_domains``) AND (page title is
non-empty) AND (no ``[class*="captcha"]`` element visible in DOM).

The watchdog mirrors the runner's failure signals but runs read-only — it
never types into the chat box. It is safe to run alongside the runner because
each cycle opens a NEW page (then closes it) on the persistent context.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import httpx

try:
    from prometheus_client import Gauge, start_http_server  # type: ignore
except Exception:  # pragma: no cover - test envs without prometheus_client
    Gauge = None  # type: ignore
    start_http_server = None  # type: ignore

try:
    from playwright.async_api import async_playwright  # type: ignore
except Exception:  # pragma: no cover
    async_playwright = None  # type: ignore

# Reuse engine selectors / ports so watchdog and runner agree on what "logged
# in" means. We deliberately import from the local module — no geo_tracker /
# experiments dependency.
from vm_side.runner import ENGINE_CONFIG, SUPPORTED_ENGINES, _url_hits_login_redirect

logger = logging.getLogger("vm_side.login_watchdog")
logging.basicConfig(
    level=os.getenv("VM_SIDE_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s [%(levelname)s] %(message)s",
)

DEFAULT_POLL_SECS = int(os.getenv("VM_SIDE_WATCHDOG_POLL_SECS", "60"))
DEFAULT_PROM_PORT = int(os.getenv("VM_SIDE_PROM_PORT", "8000"))
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "").rstrip("/")
VM_ID = os.getenv("VM_ID", "unknown-vm")


# --- gauge registry ---------------------------------------------------------


_GAUGES: dict[str, Any] = {}


def _ensure_gauges() -> dict[str, Any]:
    """Lazily create one Gauge per engine. Names match the spec:
    doubao_session_alive / deepseek_session_alive, labeled by vm.
    """
    if _GAUGES:
        return _GAUGES
    if Gauge is None:
        return _GAUGES
    for engine in SUPPORTED_ENGINES:
        gauge_name = f"{engine}_session_alive"
        _GAUGES[engine] = Gauge(
            gauge_name,
            f"1 if {engine} VM Chrome session is logged in, 0 otherwise",
            labelnames=("vm",),
        )
    return _GAUGES


# --- single-engine probe ----------------------------------------------------


async def probe_engine(playwright_handle: Any, engine: str) -> tuple[bool, str | None]:
    """Return (healthy, reason_if_unhealthy).

    Reason vocabulary matches the orchestrator contract:
      - ``login_redirect``  page URL is on login_redirect_domains
      - ``empty_title``     page title is blank
      - ``captcha``         DOM contains a captcha widget
      - ``cdp_unreachable`` we cannot attach to the per-engine Chrome
    """
    cfg = ENGINE_CONFIG[engine]
    port = cfg["port"]
    endpoint = f"http://127.0.0.1:{port}"
    try:
        browser = await playwright_handle.chromium.connect_over_cdp(endpoint)
    except Exception as exc:
        logger.warning("probe %s: CDP connect failed: %s", engine, exc)
        return False, "cdp_unreachable"

    contexts = browser.contexts
    if not contexts:
        try:
            await browser.close()
        except Exception:
            pass
        return False, "no_persistent_context"

    context = contexts[0]
    page = None
    try:
        page = await context.new_page()
        await page.goto(cfg["url"], wait_until="domcontentloaded", timeout=30_000)
        url = page.url
        if _url_hits_login_redirect(url, cfg["login_redirect_domains"]):
            return False, "login_redirect"
        try:
            title = await page.title()
        except Exception:
            title = ""
        if not title:
            return False, "empty_title"
        # captcha check — single DOM probe, no JS execution beyond querySelector.
        has_captcha = False
        try:
            has_captcha = bool(
                await page.evaluate(
                    """() => !!document.querySelector("[class*='captcha']")"""
                )
            )
        except Exception:
            has_captcha = False
        if has_captcha:
            return False, "captcha"
        return True, None
    except Exception as exc:
        logger.warning("probe %s: page error: %s", engine, exc)
        return False, f"page_error: {exc!r}"
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass
        try:
            await browser.close()
        except Exception:
            pass


# --- orchestrator alert -----------------------------------------------------


async def notify_orchestrator(client: httpx.AsyncClient, engine: str, reason: str) -> None:
    if not ORCHESTRATOR_URL:
        logger.info(
            "ORCHESTRATOR_URL not set; would have POSTed needs_relogin engine=%s reason=%s",
            engine,
            reason,
        )
        return
    url = f"{ORCHESTRATOR_URL}/admin/needs_relogin"
    payload = {"vm_id": VM_ID, "engine": engine, "reason": reason}
    try:
        resp = await client.post(url, json=payload, timeout=10.0)
        logger.info(
            "POST %s engine=%s reason=%s -> status=%s",
            url,
            engine,
            reason,
            resp.status_code,
        )
    except Exception as exc:
        logger.warning("orchestrator POST failed: %s", exc)


# --- main loop --------------------------------------------------------------


async def watchdog_loop(
    poll_secs: int = DEFAULT_POLL_SECS,
    iterations: int | None = None,
    playwright_factory: Any = None,
    http_client_factory: Any = None,
) -> None:
    """Async polling loop. Visible for testing — ``iterations`` lets a unit
    test cap the number of cycles, and the factory parameters let the test
    inject mocks instead of real playwright + httpx.
    """
    gauges = _ensure_gauges()

    if playwright_factory is None:
        if async_playwright is None:
            raise RuntimeError("playwright not installed and no factory provided")
        playwright_factory = async_playwright

    if http_client_factory is None:
        http_client_factory = httpx.AsyncClient

    pw = await playwright_factory().start()
    last_state: dict[str, bool] = {engine: True for engine in SUPPORTED_ENGINES}

    async with http_client_factory() as client:
        cycle = 0
        while iterations is None or cycle < iterations:
            cycle += 1
            for engine in SUPPORTED_ENGINES:
                healthy, reason = await probe_engine(pw, engine)
                if engine in gauges:
                    gauges[engine].labels(vm=VM_ID).set(1.0 if healthy else 0.0)
                logger.info(
                    "cycle=%d engine=%s healthy=%s reason=%s",
                    cycle,
                    engine,
                    healthy,
                    reason,
                )
                if not healthy and reason:
                    # Edge-trigger: only alert on healthy -> unhealthy transition,
                    # OR on every cycle for the cdp_unreachable case which is the
                    # most urgent (Chrome process died).
                    if last_state.get(engine, True) or reason == "cdp_unreachable":
                        await notify_orchestrator(client, engine, reason)
                last_state[engine] = healthy
            if iterations is None:
                await asyncio.sleep(poll_secs)

    try:
        await pw.stop()
    except Exception:
        pass


# --- entry point ------------------------------------------------------------


def main() -> None:
    if start_http_server is None:
        logger.warning("prometheus_client not available — Prometheus gauges disabled")
    else:
        _ensure_gauges()
        start_http_server(DEFAULT_PROM_PORT)
        logger.info("Prometheus HTTP server listening on :%d", DEFAULT_PROM_PORT)
    asyncio.run(watchdog_loop())


if __name__ == "__main__":
    main()


__all__ = [
    "watchdog_loop",
    "probe_engine",
    "notify_orchestrator",
    "main",
    "VM_ID",
    "ORCHESTRATOR_URL",
]
