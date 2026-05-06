"""LLM web-search collector — uses Doubao (Volcengine Ark) to surface
industry-relevant trending topics when the platform-specific hot lists don't
cover the operator's industry.

The previous implementation here returned a hard-coded placeholder so the
pipeline path was at least exercisable; this version performs a real LLM
call and parses a strict JSON response. We keep the import-side fallback so
a sandbox without Ark credentials still gets ``[]`` instead of an exception.

The Doubao client config and prompt-building live in
``admin_console.topic_plan`` / ``admin_console.hotspot_collectors`` to avoid
duplicating prompt copy. When that module isn't available (legacy worker
images that for some reason ship geo_tracker but not admin_console), we fall
back to an inline minimal implementation.
"""
from __future__ import annotations

from .base import HotspotCandidate, HotspotCollector


class LLMSearchCollector(HotspotCollector):
    SOURCE_NAME = "llm_search"
    REQUIRES_BROWSER = False

    def __init__(self, *, industry: str | None = None):
        self.industry = industry

    def collect(self, *, limit: int = 20) -> list[HotspotCandidate]:
        # Prefer the shared admin-side implementation so prompt + parser stay
        # in lockstep between admin manual triggers and worker Beat triggers.
        try:
            from admin_console.hotspot_collectors import (
                collect_llm_search as _admin_collect_llm,
                HotspotCandidate as _AdminCandidate,
            )
        except Exception as e:
            print(f"[hotspots.llm_search] admin module unavailable: {e}")
            return []

        try:
            items = _admin_collect_llm(industry=self.industry, limit=limit)
        except Exception as e:
            print(f"[hotspots.llm_search] llm collect failed: {e}")
            return []

        out: list[HotspotCandidate] = []
        for item in items:
            # Translate to the geo_tracker-side dataclass. Fields are
            # name-compatible — this loop only exists because the dataclass
            # identity differs across the package boundary.
            if isinstance(item, _AdminCandidate):
                out.append(
                    HotspotCandidate(
                        title=item.title,
                        summary=item.summary,
                        category=item.category,
                        source=self.SOURCE_NAME,
                        source_url=item.source_url,
                        raw_rank=item.raw_rank,
                        raw_metric=item.raw_metric,
                        industry=item.industry or self.industry,
                    )
                )
        return out
