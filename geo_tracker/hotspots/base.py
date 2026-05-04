"""Hotspot collector interface + candidate dataclass."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class HotspotCandidate:
    """A single trending item from one source.

    `summary` and `category` may be None when the source only provides a title
    (e.g. weibo top-list); the pipeline's LLM enrichment step fills them in
    before persistence.
    """
    title: str
    summary: str | None = None
    category: str | None = None
    source: str = "unknown"
    source_url: str | None = None
    raw_rank: int | None = None
    raw_metric: str | None = None
    industry: str | None = None
    extras: dict = field(default_factory=dict)


class HotspotCollector(ABC):
    """Common interface for one source. Sync or async (the pipeline awaits)."""

    SOURCE_NAME: str = "unknown"
    REQUIRES_BROWSER: bool = False

    @abstractmethod
    def collect(self, *, limit: int = 50) -> list[HotspotCandidate]:
        """Return up to ``limit`` candidates from this source.

        Implementations should swallow recoverable errors (timeout, rate limit)
        and return what they got, rather than raising — the pipeline runs many
        collectors and a single source failing should not abort the cycle.
        """
        raise NotImplementedError
