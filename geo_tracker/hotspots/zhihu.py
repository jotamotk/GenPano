"""Zhihu Hot List collector — public JSON, no browser needed."""
from __future__ import annotations

from .base import HotspotCandidate, HotspotCollector

API_URL = (
    "https://api.zhihu.com/topstory/hot-list?"
    "limit=50&reverse_order=0&desktop=true"
)


class ZhihuHotsCollector(HotspotCollector):
    SOURCE_NAME = "zhihu"
    REQUIRES_BROWSER = False

    def collect(self, *, limit: int = 50) -> list[HotspotCandidate]:
        try:
            import urllib.request
            import json as _json
            req = urllib.request.Request(API_URL, headers={
                "User-Agent": "Mozilla/5.0 (compatible; GenPano-HotspotCollector/1.0)",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = _json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception as e:
            print(f"[zhihu] collect failed: {e}")
            return []

        items = payload.get("data") or []
        out: list[HotspotCandidate] = []
        for i, item in enumerate(items[:limit]):
            target = item.get("target") or {}
            title = (target.get("title") or item.get("query") or "").strip()
            if not title:
                continue
            excerpt = (target.get("excerpt") or "").strip()
            metric = (item.get("detail_text") or "").strip() or None
            out.append(HotspotCandidate(
                title=title,
                summary=excerpt or None,
                source=self.SOURCE_NAME,
                source_url=target.get("url") or item.get("link"),
                raw_rank=i + 1,
                raw_metric=metric,
            ))
        return out
