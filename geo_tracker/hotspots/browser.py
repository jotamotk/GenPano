"""Shared browser-collector scaffolding.

Module D-B collectors (weibo / douyin / xiaohongshu) need a real browser
(Camoufox) and a logged-in account (some platforms 403 anonymous traffic).
The browser-use stack used by ``geo_tracker.agent.executor`` is reused here
so we don't reinvent the cookie / profile / proxy / cleanup machinery —
each collector subclass only writes its scrape coroutine.

Account convention:
    Each platform claims an ``llm_name`` slot in the existing AccountPool,
    just as ChatGPT / Doubao do today:
        - ``weibo_hots``
        - ``douyin_hots``
        - ``xhs_hots``
    Operators provision one or more accounts under each name; the collector
    acquires one per cycle and reports failure on selector misses (= cooldown).

Live execution:
    Browser collectors are deliberately gated behind an explicit opt-in
    (``HOTSPOT_BROWSER_COLLECTORS=1``) so a default ``run_collection_cycle``
    in a test or sandbox doesn't spin up Camoufox.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Awaitable, Callable

from .base import HotspotCandidate, HotspotCollector


def browser_collectors_enabled() -> bool:
    return os.getenv("HOTSPOT_BROWSER_COLLECTORS") == "1"


class BrowserHotspotCollector(HotspotCollector):
    """Common base for hotspot collectors that need a real browser session.

    Subclasses implement ``async def _scrape(page, *, limit) -> list[HotspotCandidate]``.
    Everything else (account acquire / Camoufox launch / cookie save /
    cleanup / failure reporting) lives here.
    """

    SOURCE_NAME: str = "unknown"
    REQUIRES_BROWSER: bool = True
    LLM_NAME: str = ""  # AccountPool slot name (e.g. "weibo_hots")
    URL: str = ""

    async def _scrape(self, page: Any, *, limit: int) -> list[HotspotCandidate]:
        raise NotImplementedError

    def collect(self, *, limit: int = 50) -> list[HotspotCandidate]:
        """Sync wrapper that runs the async pipeline once.

        Returns ``[]`` rather than raising when:
          - browser collectors are disabled via env (production opt-in),
          - no account is bound to the platform's slot yet,
          - selector timed out (treated as cooldown),
          - any other recoverable error in the agent stack.

        The pipeline runs many collectors and one source failing should
        never block the cycle.
        """
        if not browser_collectors_enabled():
            return []
        try:
            return asyncio.run(self._collect_async(limit=limit))
        except Exception as e:  # pragma: no cover - environment dependent
            print(f"[{self.SOURCE_NAME}] collect failed: {e}")
            return []

    async def _collect_async(self, *, limit: int) -> list[HotspotCandidate]:
        # Imports are inside the function so that smoke tests / sandbox
        # boots that don't have camoufox installed still succeed at import.
        from camoufox.async_api import AsyncCamoufox  # type: ignore

        from geo_tracker.agent.browser_lifecycle import (
            cleanup_browser_resources, install_resource_blocker,
        )
        from geo_tracker.pool.account_pool import AccountPool

        pool = AccountPool()
        try:
            account = await pool.acquire(llm_name=self.LLM_NAME)
        except Exception as e:
            print(f"[{self.SOURCE_NAME}] no account for slot={self.LLM_NAME}: {e}")
            return []
        if not account:
            return []

        browser = context = page = camoufox_ctx = None
        try:
            camoufox_ctx = AsyncCamoufox(headless=True)
            browser = await camoufox_ctx.__aenter__()
            context = await browser.new_context()
            await install_resource_blocker(context)
            # Restore cookies if the account already has any.
            cookies_json = getattr(account, "cookies_json", None)
            if cookies_json:
                try:
                    import json as _json
                    await context.add_cookies(_json.loads(cookies_json))
                except Exception as e:
                    print(f"[{self.SOURCE_NAME}] cookie restore failed: {e}")
            page = await context.new_page()
            await page.goto(self.URL, wait_until="domcontentloaded", timeout=30_000)
            results = await self._scrape(page, limit=limit)
            # Persist refreshed cookies so subsequent runs reuse the session.
            try:
                import json as _json
                cookies = await context.cookies()
                await pool.save_cookies(account.id, _json.dumps(cookies))
            except Exception as e:
                print(f"[{self.SOURCE_NAME}] cookie save failed: {e}")
            await pool.report_success(account.id)
            return results
        except Exception as e:
            err = str(e).lower()
            is_ban = any(k in err for k in ["banned", "blocked", "suspended", "403", "captcha"])
            reason = "ban" if is_ban else "exception"
            await pool.report_failure(account.id, reason=reason, is_ban=is_ban)
            print(f"[{self.SOURCE_NAME}] scrape failed ({reason}): {e}")
            return []
        finally:
            await cleanup_browser_resources(page=page, context=context,
                                            browser=browser, camoufox_ctx=camoufox_ctx)


def _safe_text(node: Any) -> Callable[[], Awaitable[str]]:
    async def _runner() -> str:
        try:
            return (await node.text_content()) or ""
        except Exception:
            return ""
    return _runner
