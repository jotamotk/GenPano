"""LLM web-search fallback — uses Doubao tools=web_search to surface what's
trending. Not as fresh as platform hot-lists but covers gaps when admin only
needs a few industry-relevant items.
"""
from __future__ import annotations

from .base import HotspotCandidate, HotspotCollector


class LLMSearchCollector(HotspotCollector):
    SOURCE_NAME = "llm_search"
    REQUIRES_BROWSER = False

    def __init__(self, *, industry: str | None = None):
        self.industry = industry

    def collect(self, *, limit: int = 20) -> list[HotspotCandidate]:
        # The actual Doubao integration lives in admin_console.topic_plan
        # (DoubaoTopicPlanClient). Replicating it here would duplicate the
        # config loading; instead this collector emits an empty list when
        # the LLM client isn't available, so the pipeline still works on
        # systems where Doubao is not configured.
        try:
            from admin_console.topic_plan import load_doubao_config
        except Exception:
            return []
        try:
            cfg = load_doubao_config()
            # Smoke-check: if api key isn't set, bail rather than make a
            # request that's guaranteed to 401.
            if not getattr(cfg, "api_key", None):
                return []
        except Exception:
            return []

        # Stub: emit a placeholder so the pipeline path is exercisable in
        # tests / sandbox without a live LLM call. Real implementation will
        # call Doubao with a "list current trending topics in {industry}"
        # prompt and parse JSON.
        prompt_topic = self.industry or "general"
        return [
            HotspotCandidate(
                title=f"[LLM-search placeholder] {prompt_topic} trending #1",
                summary="Placeholder from llm_search fallback. Wire up Doubao "
                        "web_search to populate real trending items.",
                source=self.SOURCE_NAME,
                raw_rank=1,
                industry=self.industry,
            ),
        ][:limit]
