"""Celery tasks for hotspot collection (Module D Beat).

Thin wrappers around ``geo_tracker.hotspots.pipeline`` so Celery Beat can
fire them on a cron schedule. Each source gets its own task entry so
- failures isolate per source
- stagger of cron minutes spreads the network load across the hour
- one source being slow doesn't block another
"""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="hotspots.collect_source", queue="beat", routing_key="beat")
def collect_source(source: str, *, industry: str | None = None) -> dict:
    """Run a single collector and persist new candidates as draft hot_topics.

    ``source`` must be one of the keys in
    ``geo_tracker.hotspots.pipeline.COLLECTOR_REGISTRY`` —
    typically baidu / zhihu / weibo / douyin / xhs / llm_search.
    """
    from geo_tracker.hotspots.pipeline import run_collection_cycle
    result = run_collection_cycle(sources=[source], industry_filter=industry)
    logger.info("hotspots.collect_source(%s) -> %s", source, result)
    return result


@shared_task(name="hotspots.archive_expired", queue="beat", routing_key="beat")
def archive_expired() -> int:
    """Daily task — flip status='active' rows whose effective_until has
    passed to status='expired'. Idempotent.
    """
    from geo_tracker.hotspots.pipeline import archive_expired_hotspots
    n = archive_expired_hotspots()
    logger.info("hotspots.archive_expired -> %d rows", n)
    return n
