"""Douyin Hot Topics collector — browser-use, requires logged-in account."""
from __future__ import annotations

from .base import HotspotCandidate
from .browser import BrowserHotspotCollector


class DouyinHotsCollector(BrowserHotspotCollector):
    SOURCE_NAME = "douyin"
    LLM_NAME = "douyin_hots"
    URL = "https://www.douyin.com/hot"

    async def _scrape(self, page, *, limit: int = 30) -> list[HotspotCandidate]:
        out: list[HotspotCandidate] = []
        try:
            # Douyin's hot list lives under multiple selectors depending on AB.
            await page.wait_for_selector(
                "[data-e2e='douyin-hot-rank-item'], .hot-rank-item, .ranking-item",
                timeout=15_000,
            )
        except Exception:
            return out
        items = await page.locator(
            "[data-e2e='douyin-hot-rank-item'], .hot-rank-item, .ranking-item"
        ).all()
        for i, it in enumerate(items[:limit]):
            try:
                title = (await it.text_content() or "").strip().splitlines()[0]
                if not title:
                    continue
                href = await it.locator("a").first.get_attribute("href") if await it.locator("a").count() else None
                out.append(HotspotCandidate(
                    title=title[:200],
                    source=self.SOURCE_NAME,
                    source_url=href,
                    raw_rank=i + 1,
                ))
            except Exception:
                continue
        return out
