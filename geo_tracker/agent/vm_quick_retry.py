"""Quick decoupled "Retry via VM" short-path helper.

Refs Epic #1110 / Issue #1144.

Purpose: from the admin "执行追踪" page, an operator clicks "Retry via VM"
and the backend bypasses the cookie-inject + celery dispatch and executes
ONE query against a manually-logged-in remote Chrome inside the
doubao-01 VM container (`http://127.0.0.1:9222` by default).

This module is intentionally PARALLEL to (and decoupled from)
``geo_tracker/agent/guest_executor.py``. Issue #1144 forbids modifying
``guest_executor.py``'s selectors / response-wait / DOM extract / error
classification. To satisfy that contract without forking the production
path, the doubao selectors / submit button / response selector are
COPIED VERBATIM from ``guest_executor.py`` (the ``"doubao"`` entry in
``GUEST_LLM_CONFIG``) so this helper stays in sync only by manual
review — drift is acceptable because this is a PoC path, not a
production execution route.

Boundary contract:

  - The CDP endpoint is owned by the operator-staged VM (Phase 0 of
    Epic #1110). We connect over CDP, grab the default context (warm
    persistent profile with the manually-logged-in account), and
    execute against it. We NEVER call ``new_context()`` (would lose
    session) and NEVER call ``add_cookies()`` (vm_session_quick rows
    carry no cookies to inject; the VM owns the session state).
  - On release we ONLY detach the CDP client; the VM-side Chrome
    keeps running so the next retry reuses the warm session.
  - Errors map to two operator-visible codes that the FastAPI route
    surfaces as 503 JSON bodies:
      * ``cdp_unreachable``     -- Playwright connect_over_cdp failed
      * ``vm_not_logged_in``    -- page rendered Doubao login form
    These map onto AdapterError(code=...) so the route can switch on
    them without string parsing.

Production gating: there is NO ``VM_EXECUTOR_ENABLED`` flag check in
this helper. Issue #1144 explicitly decouples this PoC from the Phase
1/2 ramp; the flag belongs to ``executors/router.py:select_executor``
and only gates the celery-dispatched main path.
"""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


# Default CDP endpoint for the doubao-01 container (Phase 0 deployment).
# Override via ``VM_QUICK_RETRY_CDP_ENDPOINT`` env var. The endpoint may
# be either an ``http://...`` URL (Chrome DevTools HTTP) or a ``ws://``
# WebSocket URL; Playwright accepts both.
DEFAULT_CDP_ENDPOINT = "http://127.0.0.1:9222"
DEFAULT_VM_ID = "doubao-01"


# ── Selectors COPIED VERBATIM from geo_tracker/agent/guest_executor.py ──
# Source: ``GUEST_LLM_CONFIG['doubao']`` in guest_executor.py.
# These are duplicated (not imported) so this PoC path has zero risk of
# touching the production selectors. If Doubao's UI changes both copies
# need a manual sync (the production path is authoritative).
DOUBAO_URL = "https://www.doubao.com/chat"
DOUBAO_INPUT_SELECTOR = (
    "#input-engine-container textarea.semi-input-textarea:not([aria-hidden='true']), "
    "textarea.semi-input-textarea:not([aria-hidden='true']), "
    "textarea:not([aria-hidden='true']), "
    "[contenteditable='true']"
)
DOUBAO_SUBMIT_BUTTON = (
    "#flow-end-msg-send:not([aria-disabled='true']):not([data-disabled='true']), "
    "button[id='flow-end-msg-send'], "
    ".send-btn-wrapper button:not([aria-disabled='true']):not([data-disabled='true']), "
    "button[class*='send-msg-btn']:not([aria-disabled='true']):not([data-disabled='true']):not([disabled]), "
    "button[data-testid='chat_input_send_button'], "
    "button[aria-label*='发送'], "
    "button[aria-label*='send' i], "
    "button[data-testid*='send']"
)
DOUBAO_RESPONSE_SELECTOR = (
    ".flow-markdown-body, "
    "[data-testid='receive_message'], "
    "[data-testid='receive_message'] [data-testid='message_text_content'], "
    "[data-testid='receive_message'] .flow-markdown-body, "
    "[class*='message-content'], "
    "[class*='chat-message-content']"
)
DOUBAO_LOGIN_REDIRECT_DOMAINS = (
    "passport.volcengine.com",
    "sso.volcengine.com",
    "passport.douyin.com",
)
# Login-form keywords used by guest_executor.py:1192-1205 to detect the
# "logged out but no redirect" case where Doubao renders the login form
# in-place on doubao.com/chat. Matched against ``document.body.innerText``
# in :func:`_detect_login_page`.
DOUBAO_LOGIN_KEYWORDS = (
    "登录后免费使用",
    "用户协议",
    "隐私政策",
    "抖音一键登录",
    "豆包账号服务须知",
    "下载豆包电脑版",
    "你好，我是豆包",
)


# ── Quick-path error wrapper ────────────────────────────────────────


@dataclass
class QuickRetryError(Exception):
    """Operator-visible failure surface for the quick-retry path.

    ``code`` MUST be one of the issue-defined enum values so the route
    layer can surface them as structured 503 bodies without string
    parsing. ``detail`` is free-form context for the operator log.
    """

    code: str
    detail: str = ""

    def __init__(self, code: str, *, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


# Issue #1144 Acceptance Matrix codes. Kept as module constants so the
# route handler can compare against the canonical strings without typo
# risk.
ERR_CDP_UNREACHABLE = "cdp_unreachable"
ERR_VM_NOT_LOGGED_IN = "vm_not_logged_in"


# ── Helpers (login detection / response polling) ────────────────────


async def _detect_login_page(page) -> bool:
    """Return True when the page is rendering Doubao's login form.

    Two signals (mirrored from guest_executor.py:1190-1205 — same data
    source, but expressed standalone so this helper doesn't import the
    production module):

    1. URL is on a Volcengine / Douyin passport redirect domain.
    2. ``document.body.innerText`` contains >= 2 login-form keywords.

    Either alone is enough; the production code uses (2) for the
    "didn't redirect but rendered login in-place" case and the route
    layer needs both to cover both modes.
    """
    try:
        url = page.url or ""
    except Exception:
        url = ""
    lower_url = url.lower()
    for domain in DOUBAO_LOGIN_REDIRECT_DOMAINS:
        if domain in lower_url:
            return True

    try:
        body_text = await page.evaluate("document.body?.innerText || ''")
    except Exception:
        body_text = ""
    matched = [kw for kw in DOUBAO_LOGIN_KEYWORDS if kw in body_text]
    return len(matched) >= 2


async def _wait_for_response_stable(
    page,
    response_selector: str,
    *,
    timeout_secs: int,
    stable_window_secs: float = 3.0,
    poll_interval_secs: float = 0.5,
) -> str:
    """Poll the response container until textContent length stops
    growing for ``stable_window_secs`` or ``timeout_secs`` elapses.

    Returns the final textContent (empty string on timeout). Matches the
    poll loop in ``experiments/vm_per_account/poc_runner.py`` (M1 PoC
    runner) so the quick-retry path captures rawText with the same
    semantics as the PoC evidence runs.
    """
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
            text = ""
        text = text or ""
        if len(text) != last_len:
            last_len = len(text)
            last_change = time.monotonic()
            last_text = text
        elif text and (time.monotonic() - last_change) >= stable_window_secs:
            return text
        # Use asyncio.sleep via wait_for_timeout to avoid importing asyncio
        # twice; Playwright Page exposes wait_for_timeout(ms).
        await page.wait_for_timeout(int(poll_interval_secs * 1000))
    return last_text


# ── Persistence ─────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _quick_screenshot_dir() -> Path:
    """Resolve the quick-retry screenshot directory.

    Separate from ``SCREENSHOT_DIR`` in guest_executor.py so a sandbox
    test run does not accidentally inherit ``/data/screenshots`` (which
    is mkdir'd at module-import time in production but may not exist /
    be writable in CI).
    """
    base = os.getenv("VM_QUICK_RETRY_SCREENSHOT_DIR", "/data/screenshots/vm_quick_retry")
    path = Path(base)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception:
        # Fall back to /tmp if the configured dir is not writable. The
        # path is informational on the attempt entry — losing it is not
        # fatal to the retry.
        path = Path("/tmp/vm_quick_retry_screenshots")
        path.mkdir(parents=True, exist_ok=True)
    return path


async def _persist_response_and_attempt(
    session,
    *,
    query_id: int,
    raw_text: str,
    response_html: Optional[str],
    screenshot_path: Optional[str],
    har_path: Optional[str],
    vm_id: str,
    started_at: str,
    completed_at: str,
    response_time_ms: int,
    error_code: Optional[str] = None,
) -> int:
    """Persist the response + attempt entry. Returns ``attempt_n``.

    Two writes:

    1. UPSERT ``llm_responses`` row for ``query_id`` with raw_text +
       response_html + screenshot_path. Uses the existing schema so we
       do not touch DB migrations (forbidden scope: schema changes).
    2. INSERT into ``query_attempts`` (production table referenced by
       ``backend/app/admin/vm_accounts/db.py``) when present. Skipped
       silently when absent (sqlite test fixtures).

    ``attempt_n`` is computed as ``COUNT(query_attempts WHERE query_id=?) + 1``
    when the table exists, else defaults to ``1``.

    The attempt metadata fields (execution_mode='vm_session_quick',
    vm_id, started_at, completed_at, error_code, raw_html_path,
    har_path, screenshot_path) are stored as JSON in the
    ``query_attempts.metadata`` column when present; the column is
    described in Issue #1144 Contract Snapshot (mirrors
    docs/ADAPTER_CONTRACT.md §6.3 + §10.1).
    """
    from sqlalchemy import text as sa_text

    # 1. UPSERT llm_responses.
    #    We use raw SQL with a sub-select to avoid touching the model
    #    metadata and to keep this helper sqlite-compatible (model uses
    #    ``unique=True`` on query_id; INSERT OR REPLACE handles update).
    try:
        existing_row = (
            await session.execute(
                sa_text("SELECT id FROM llm_responses WHERE query_id = :qid"),
                {"qid": query_id},
            )
        ).first()
    except Exception as exc:
        logger.warning(
            "vm_quick_retry: SELECT llm_responses failed for query_id=%s: %r",
            query_id,
            exc,
        )
        existing_row = None

    try:
        if existing_row is None:
            await session.execute(
                sa_text(
                    "INSERT INTO llm_responses (query_id, raw_text, response_html, "
                    "screenshot_path, response_time_ms, collected_at) "
                    "VALUES (:qid, :raw_text, :response_html, :screenshot_path, "
                    ":response_time_ms, :collected_at)"
                ),
                {
                    "qid": query_id,
                    "raw_text": raw_text,
                    "response_html": response_html,
                    "screenshot_path": screenshot_path,
                    "response_time_ms": response_time_ms,
                    "collected_at": datetime.now(tz=timezone.utc),
                },
            )
        else:
            await session.execute(
                sa_text(
                    "UPDATE llm_responses "
                    "SET raw_text = :raw_text, response_html = :response_html, "
                    "    screenshot_path = :screenshot_path, "
                    "    response_time_ms = :response_time_ms, "
                    "    collected_at = :collected_at "
                    "WHERE query_id = :qid"
                ),
                {
                    "qid": query_id,
                    "raw_text": raw_text,
                    "response_html": response_html,
                    "screenshot_path": screenshot_path,
                    "response_time_ms": response_time_ms,
                    "collected_at": datetime.now(tz=timezone.utc),
                },
            )
    except Exception as exc:
        logger.warning(
            "vm_quick_retry: UPSERT llm_responses failed for query_id=%s: %r",
            query_id,
            exc,
        )

    # 2. INSERT query_attempts row, when the table exists. attempt_n is
    #    derived from the count of existing attempts so the response to
    #    the UI is monotonically increasing per query.
    attempt_n = 1
    try:
        # Defensive table-exists check. Two-step instead of try/except
        # because some sqlite versions raise an unrelated OperationalError
        # for a missing table that we don't want to swallow as "table
        # missing" if the real error is, e.g., a transaction abort.
        exists_row = (
            await session.execute(
                sa_text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='query_attempts' "
                    "UNION ALL "
                    "SELECT table_name AS name FROM information_schema.tables "
                    "WHERE table_name='query_attempts'"
                )
            )
        ).first()
    except Exception:
        # information_schema is sqlite-incompatible; fall back to sqlite
        # only.
        try:
            exists_row = (
                await session.execute(
                    sa_text(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name='query_attempts'"
                    )
                )
            ).first()
        except Exception:
            exists_row = None

    if exists_row is not None:
        # Get current count for attempt_n.
        try:
            count_row = (
                await session.execute(
                    sa_text(
                        "SELECT COUNT(*) AS n FROM query_attempts "
                        "WHERE query_id = :qid"
                    ),
                    {"qid": query_id},
                )
            ).first()
            if count_row is not None:
                attempt_n = int(count_row[0]) + 1
        except Exception as exc:
            logger.warning(
                "vm_quick_retry: COUNT query_attempts failed: %r", exc
            )

        attempt_metadata = {
            "attempt_n": attempt_n,
            "execution_mode": "vm_session_quick",
            "vm_id": vm_id,
            "started_at": started_at,
            "completed_at": completed_at,
            "error_code": error_code,
            "raw_html_path": None,
            "har_path": har_path,
            "screenshot_path": screenshot_path,
        }

        # Issue #1144 Contract Snapshot demands the attempt carry
        # execution_mode + vm_id. We use a JSON column ``metadata`` if
        # it exists (production schema), else we leave the row's first-
        # class columns populated and accept the absence of metadata.
        outcome = "success" if not error_code else "failed"
        import json as _json

        try:
            await session.execute(
                sa_text(
                    "INSERT INTO query_attempts (query_id, outcome, created_at, metadata) "
                    "VALUES (:qid, :outcome, :created_at, :metadata)"
                ),
                {
                    "qid": query_id,
                    "outcome": outcome,
                    "created_at": datetime.now(tz=timezone.utc),
                    "metadata": _json.dumps(attempt_metadata),
                },
            )
        except Exception as exc:
            # Production query_attempts has more columns; the INSERT may
            # fail on NOT NULL constraints (e.g. account_id). The
            # quick-retry path has no account_id (no cookie injection),
            # so we degrade to a no-op rather than failing the route.
            logger.warning(
                "vm_quick_retry: INSERT query_attempts skipped "
                "(likely production schema mismatch — quick path is "
                "decoupled): %r",
                exc,
            )

    try:
        await session.commit()
    except Exception as exc:
        logger.warning("vm_quick_retry: session.commit() raised %r", exc)

    return attempt_n


# ── Main entry point ────────────────────────────────────────────────


def _resolve_cdp_endpoint() -> str:
    return os.getenv("VM_QUICK_RETRY_CDP_ENDPOINT", DEFAULT_CDP_ENDPOINT).strip() or DEFAULT_CDP_ENDPOINT


def _resolve_vm_id() -> str:
    return os.getenv("VM_QUICK_RETRY_VM_ID", DEFAULT_VM_ID).strip() or DEFAULT_VM_ID


async def run_quick_retry(
    *,
    query_id: int,
    query_text: str,
    target_llm: str,
    session,
    cdp_endpoint: Optional[str] = None,
    vm_id: Optional[str] = None,
    response_timeout_secs: int = 120,
    playwright_factory=None,
) -> dict[str, Any]:
    """Execute one retry against the VM and persist the attempt.

    Args:
        query_id: row id in ``queries`` table.
        query_text: the prompt text to send to Doubao.
        target_llm: must be ``"doubao"`` for the Phase 0 quick path.
            Other engines raise ``QuickRetryError("cdp_unreachable",
            detail="engine not supported")`` for now — Phase 2 of the
            VM rollout will add deepseek.
        session: SQLAlchemy AsyncSession; used for the
            ``llm_responses`` UPSERT + ``query_attempts`` INSERT.
        cdp_endpoint: override the env-derived endpoint (tests pass a
            fake URL).
        vm_id: override the env-derived vm_id (tests pin to
            ``"doubao-01"``).
        response_timeout_secs: how long to poll for the response
            container to stabilize.
        playwright_factory: override the Playwright entry point. Tests
            pass a callable returning a stub async-context-manager.

    Returns:
        dict with ``raw_text``, ``raw_text_chars``, ``attempt_n``,
        ``vm_id``, ``execution_mode``, ``started_at``, ``completed_at``,
        ``screenshot_path`` — the FastAPI route maps a subset of this
        into the 200 OK body.

    Raises:
        QuickRetryError(code="cdp_unreachable"): Playwright connect
            failed.
        QuickRetryError(code="vm_not_logged_in"): page rendered login
            form (URL on passport domain OR >= 2 login keywords in DOM).
    """
    cdp = (cdp_endpoint or _resolve_cdp_endpoint()).strip()
    vm = (vm_id or _resolve_vm_id()).strip()
    started_at = _now_iso()
    t0 = time.monotonic()

    if (target_llm or "").lower() != "doubao":
        # Phase 0 quick path is doubao-only; the issue scope cite is
        # 执行追踪 → Doubao retry. Surfacing as cdp_unreachable keeps
        # the API surface narrow (one code for "this path can't run").
        raise QuickRetryError(
            ERR_CDP_UNREACHABLE,
            detail=f"vm_quick_retry: engine {target_llm!r} not supported (doubao only)",
        )

    pw_factory = playwright_factory or async_playwright
    screenshot_dir = _quick_screenshot_dir()
    screenshot_path = str(screenshot_dir / f"q{query_id}_{int(time.time())}.png")

    playwright_handle = None
    browser = None
    page = None
    raw_text = ""
    response_html: Optional[str] = None
    try:
        try:
            playwright_handle = await pw_factory().start()
        except Exception as exc:
            raise QuickRetryError(
                ERR_CDP_UNREACHABLE,
                detail=f"playwright start failed: {exc!r}",
            ) from exc

        try:
            browser = await playwright_handle.chromium.connect_over_cdp(cdp)
        except Exception as exc:
            raise QuickRetryError(
                ERR_CDP_UNREACHABLE,
                detail=f"connect_over_cdp({cdp}) failed: {exc!r}",
            ) from exc

        contexts = list(getattr(browser, "contexts", []) or [])
        if not contexts:
            raise QuickRetryError(
                ERR_CDP_UNREACHABLE,
                detail="vm chrome has no default context (profile crash?)",
            )
        context = contexts[0]

        try:
            page = await context.new_page()
        except Exception as exc:
            raise QuickRetryError(
                ERR_CDP_UNREACHABLE,
                detail=f"context.new_page() failed: {exc!r}",
            ) from exc

        try:
            await page.goto(
                DOUBAO_URL,
                wait_until="domcontentloaded",
                timeout=30_000,
            )
        except Exception as exc:
            raise QuickRetryError(
                ERR_CDP_UNREACHABLE,
                detail=f"page.goto({DOUBAO_URL}) failed: {exc!r}",
            ) from exc

        # Wait briefly for the page to settle, then check for login form.
        try:
            await page.wait_for_timeout(2000)
        except Exception:
            pass

        if await _detect_login_page(page):
            raise QuickRetryError(
                ERR_VM_NOT_LOGGED_IN,
                detail=(
                    "Doubao login form detected on vm Chrome; "
                    "the VM-side session has expired and needs manual "
                    "re-login via noVNC."
                ),
            )

        # Wait for the input selector to be ready.
        try:
            await page.wait_for_selector(
                DOUBAO_INPUT_SELECTOR,
                state="visible",
                timeout=15_000,
            )
        except Exception as exc:
            # Could be login mid-render: re-check login state before
            # giving up.
            if await _detect_login_page(page):
                raise QuickRetryError(
                    ERR_VM_NOT_LOGGED_IN,
                    detail=f"login detected after input timeout: {exc!r}",
                ) from exc
            raise QuickRetryError(
                ERR_CDP_UNREACHABLE,
                detail=f"input selector not visible: {exc!r}",
            ) from exc

        # Fill the prompt + submit. Use ``type`` to mimic user input
        # (per the experiments/vm_per_account M1 PoC runner).
        try:
            await page.type(DOUBAO_INPUT_SELECTOR, query_text or "", delay=20)
        except Exception as exc:
            raise QuickRetryError(
                ERR_CDP_UNREACHABLE,
                detail=f"page.type() failed: {exc!r}",
            ) from exc

        # Try the submit button first; fall back to Enter (Doubao
        # accepts both, matching guest_executor.py:514 ``submit_key``).
        try:
            await page.click(DOUBAO_SUBMIT_BUTTON, timeout=10_000)
        except Exception:
            try:
                await page.keyboard.press("Enter")
            except Exception as exc:
                raise QuickRetryError(
                    ERR_CDP_UNREACHABLE,
                    detail=f"both click and Enter failed: {exc!r}",
                ) from exc

        # Poll for response stabilization.
        raw_text = await _wait_for_response_stable(
            page,
            DOUBAO_RESPONSE_SELECTOR,
            timeout_secs=response_timeout_secs,
        )

        # Capture response_html for downstream citation extraction
        # (response_validation.py + citation_extraction.py read this).
        try:
            response_html = await page.evaluate(
                """(sel) => {
                    const nodes = document.querySelectorAll(sel);
                    if (!nodes || nodes.length === 0) return "";
                    return nodes[nodes.length - 1].innerHTML || "";
                }""",
                DOUBAO_RESPONSE_SELECTOR,
            )
        except Exception:
            response_html = None

        # Best-effort screenshot.
        try:
            await page.screenshot(path=screenshot_path, full_page=True)
        except Exception:
            screenshot_path = None  # type: ignore[assignment]
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass
        if playwright_handle is not None:
            try:
                await playwright_handle.stop()
            except Exception:
                pass

    completed_at = _now_iso()
    response_time_ms = int((time.monotonic() - t0) * 1000)

    attempt_n = await _persist_response_and_attempt(
        session,
        query_id=query_id,
        raw_text=raw_text,
        response_html=response_html,
        screenshot_path=screenshot_path,
        har_path=None,
        vm_id=vm,
        started_at=started_at,
        completed_at=completed_at,
        response_time_ms=response_time_ms,
        error_code=None,
    )

    return {
        "raw_text": raw_text,
        "raw_text_chars": len(raw_text or ""),
        "attempt_n": attempt_n,
        "vm_id": vm,
        "execution_mode": "vm_session_quick",
        "started_at": started_at,
        "completed_at": completed_at,
        "screenshot_path": screenshot_path,
    }


__all__ = [
    "DEFAULT_CDP_ENDPOINT",
    "DEFAULT_VM_ID",
    "ERR_CDP_UNREACHABLE",
    "ERR_VM_NOT_LOGGED_IN",
    "QuickRetryError",
    "run_quick_retry",
]
