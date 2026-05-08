"""LLM web-search collector stub.

The shared admin-side implementation lives in
``backend/app/admin/hot_topics/collectors.py`` and is invoked from the
backend FastAPI process via the admin manual-trigger endpoint. The Celery
worker image does not bundle the backend package, so this collector
returns an empty list when run from worker context. Beat-driven LLM
search collection should be wired through a backend HTTP call if/when
needed; until then, manual admin triggers cover the use case.
"""
from __future__ import annotations

from .base import HotspotCandidate, HotspotCollector


class LLMSearchCollector(HotspotCollector):
    SOURCE_NAME = "llm_search"
    REQUIRES_BROWSER = False

    def __init__(self, *, industry: str | None = None):
        self.industry = industry

    def collect(self, *, limit: int = 20) -> list[HotspotCandidate]:
        return []
