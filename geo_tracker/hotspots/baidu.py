"""Baidu Hot Search collector — public JSON, no browser needed."""
from __future__ import annotations

from .base import HotspotCandidate, HotspotCollector

API_URL = "https://top.baidu.com/api/board?platform=wise&tab=realtime"


class BaiduHotsCollector(HotspotCollector):
    SOURCE_NAME = "baidu"
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
            print(f"[baidu] collect failed: {e}")
            return []

        cards = (payload.get("data") or {}).get("cards") or []
        if not cards:
            return []
        items = cards[0].get("content") or []

        out: list[HotspotCandidate] = []
        for i, item in enumerate(items[:limit]):
            title = (item.get("word") or item.get("query") or "").strip()
            if not title:
                continue
            out.append(HotspotCandidate(
                title=title,
                summary=(item.get("desc") or "").strip() or None,
                source=self.SOURCE_NAME,
                source_url=item.get("url") or item.get("rawUrl"),
                raw_rank=i + 1,
                raw_metric=f"热度 {item.get('hotScore', '')}".strip() or None,
            ))
        return out
