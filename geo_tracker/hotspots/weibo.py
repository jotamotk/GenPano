"""Weibo Hot Search collector — browser-use, requires logged-in account."""
from __future__ import annotations

from .base import HotspotCandidate
from .browser import BrowserHotspotCollector


class WeiboHotsCollector(BrowserHotspotCollector):
    SOURCE_NAME = "weibo"
    LLM_NAME = "weibo_hots"
    URL = "https://s.weibo.com/top/summary"

    async def _scrape(self, page, *, limit: int = 50) -> list[HotspotCandidate]:
        out: list[HotspotCandidate] = []
        try:
            await page.wait_for_selector("table.list-table, .data, .HotTopic_inner_3WLkr", timeout=15_000)
        except Exception:
            return out
        rows = await page.locator("table.list-table tbody tr").all()
        for i, row in enumerate(rows[:limit]):
            try:
                title_el = row.locator("td.td-02 a")
                title = (await title_el.first.text_content() or "").strip()
                if not title or title.startswith("置顶"):
                    continue
                href = await title_el.first.get_attribute("href")
                metric_el = row.locator("td.td-02 span")
                metric = (await metric_el.first.text_content() or "").strip() if await metric_el.count() else None
                out.append(HotspotCandidate(
                    title=title,
                    source=self.SOURCE_NAME,
                    source_url=("https://s.weibo.com" + href) if href and href.startswith("/") else href,
                    raw_rank=i + 1,
                    raw_metric=metric or None,
                ))
            except Exception:
                continue
        return out
