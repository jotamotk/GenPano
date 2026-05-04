"""Weibo Hot Search collector — public mobile JSON, no account / browser needed.

Originally drafted as a browser-use collector (PR #212), but the mobile-web
trending endpoint (``m.weibo.cn/api/container/getIndex``) returns the same
~50 trending list anonymously and is far more reliable than parsing the
desktop HTML or driving Camoufox.

Falls back to the desktop ``s.weibo.com/top/summary`` HTML scrape only if
the mobile API stops working.
"""
from __future__ import annotations

import json as _json
import re
import urllib.request

from .base import HotspotCandidate, HotspotCollector

MOBILE_API = (
    "https://m.weibo.cn/api/container/getIndex"
    "?containerid=106003type%3D25%26t%3D3%26disable_hot%3D1%26filter_type%3Drealtimehot"
)
DESKTOP_FALLBACK = "https://s.weibo.com/top/summary"

UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)
UA_DESKTOP = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class WeiboHotsCollector(HotspotCollector):
    SOURCE_NAME = "weibo"
    REQUIRES_BROWSER = False
    LLM_NAME = ""  # No account needed — kept for parity with browser collectors.

    def collect(self, *, limit: int = 50) -> list[HotspotCandidate]:
        items = self._collect_mobile(limit=limit)
        if items:
            return items
        return self._collect_desktop(limit=limit)

    def _collect_mobile(self, *, limit: int) -> list[HotspotCandidate]:
        try:
            req = urllib.request.Request(MOBILE_API, headers={
                "User-Agent": UA_MOBILE,
                "Accept": "application/json",
                "Referer": "https://m.weibo.cn/p/106003type=25&t=3&disable_hot=1",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = _json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception as e:
            print(f"[weibo] mobile API failed: {e}")
            return []

        cards = (payload.get("data") or {}).get("cards") or []
        out: list[HotspotCandidate] = []
        rank = 0
        for card in cards:
            groups = card.get("card_group") or ([card] if card.get("desc") else [])
            for g in groups:
                title = (g.get("desc") or g.get("title_sub") or "").strip()
                if not title or "更多热搜" in title:
                    continue
                rank += 1
                if rank > limit:
                    break
                metric = (g.get("desc_extr") or "").strip() or None
                href = g.get("scheme") or g.get("url")
                out.append(HotspotCandidate(
                    title=title,
                    source=self.SOURCE_NAME,
                    source_url=href,
                    raw_rank=rank,
                    raw_metric=str(metric) if metric else None,
                ))
            if rank >= limit:
                break
        return out

    def _collect_desktop(self, *, limit: int) -> list[HotspotCandidate]:
        """Fallback: scrape the desktop hot summary table.

        Anonymous requests get the same list as logged-in users since 2023.
        Parsed via regex to avoid pulling in BeautifulSoup as a hard dep.
        """
        try:
            req = urllib.request.Request(DESKTOP_FALLBACK, headers={
                "User-Agent": UA_DESKTOP,
                "Accept": "text/html,application/xhtml+xml",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f"[weibo] desktop fallback failed: {e}")
            return []

        # Each row in the hot table looks like:
        #   <td class="td-02"><a href="...">title</a><span>metric</span></td>
        pattern = re.compile(
            r'<td[^>]*class="td-02"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
            r'(?:\s*<span[^>]*>(.*?)</span>)?',
            re.DOTALL,
        )
        out: list[HotspotCandidate] = []
        for i, m in enumerate(pattern.finditer(html)):
            if len(out) >= limit:
                break
            href = m.group(1).strip()
            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            metric = re.sub(r"<[^>]+>", "", m.group(3) or "").strip() or None
            if not title or title.startswith("置顶"):
                continue
            out.append(HotspotCandidate(
                title=title,
                source=self.SOURCE_NAME,
                source_url=("https://s.weibo.com" + href) if href.startswith("/") else href,
                raw_rank=i + 1,
                raw_metric=metric,
            ))
        return out
