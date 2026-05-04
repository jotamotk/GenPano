"""Xiaohongshu (RED) Explore Hot collector — browser-use, requires logged-in account.

Note: XHS has the strictest anti-bot detection of the platforms supported.
Run with conservative concurrency and longer cooldowns. The collector falls
back gracefully when blocked; the pipeline-level dedupe means missing one
cycle is not fatal.
"""
from __future__ import annotations

from .base import HotspotCandidate
from .browser import BrowserHotspotCollector


class XHSHotsCollector(BrowserHotspotCollector):
    SOURCE_NAME = "xhs"
    LLM_NAME = "xhs_hots"
    URL = "https://www.xiaohongshu.com/explore"

    async def _scrape(self, page, *, limit: int = 30) -> list[HotspotCandidate]:
        out: list[HotspotCandidate] = []
        try:
            # Try a couple of explore-feed selectors; XHS A/Bs them.
            await page.wait_for_selector(
                "section.note-item, .feeds-page section, .explore-list .note",
                timeout=20_000,
            )
        except Exception:
            return out
        items = await page.locator(
            "section.note-item, .feeds-page section, .explore-list .note"
        ).all()
        for i, it in enumerate(items[:limit]):
            try:
                title_el = it.locator("a.title, .title").first
                title = (await title_el.text_content() or "").strip()
                if not title:
                    # Fall back to first line of the item content.
                    title = (await it.text_content() or "").strip().splitlines()[0] if await it.count() else ""
                if not title:
                    continue
                href = await it.locator("a").first.get_attribute("href") if await it.locator("a").count() else None
                out.append(HotspotCandidate(
                    title=title[:200],
                    source=self.SOURCE_NAME,
                    source_url=("https://www.xiaohongshu.com" + href) if href and href.startswith("/") else href,
                    raw_rank=i + 1,
                ))
            except Exception:
                continue
        return out
