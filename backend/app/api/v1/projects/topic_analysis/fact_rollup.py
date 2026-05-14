"""Fact-row helpers: per-row counters, scope checks, sort keys, position buckets.

Phase 4 of splitting `_topic_analysis_service.py` (Epic #885, design #887).
These helpers are pure dict-row transforms used by the analyzer fact-row
pipeline (`_fact_rows`) and by chart sub-package consumers
(`charts/engine_metric.py`, `charts/topic_heatmap.py`, `charts/position.py`).
"""

from __future__ import annotations

from typing import Any

from app.api.v1.projects.topic_analysis.normalize import _timestamp_key


def _fact_brand_scope_matched(row: dict[str, Any]) -> bool:
    return bool(row.get("brand_scope_matched"))


def _fact_target_mention_count(row: dict[str, Any]) -> int:
    return int(row.get("target_mention_count") or 0)


def _fact_all_mention_count(
    row: dict[str, Any],
    target_mentions: int | None = None,
) -> int:
    total = int(row.get("all_mention_count") or 0)
    return total


def _logical_query_key(row: dict[str, Any]) -> str:
    query_text = " ".join(str(row.get("query_text") or "").strip().lower().split())
    prompt = str(row.get("prompt_id") or "")
    return "|".join([prompt, query_text])


def _row_attempt_time(row: dict[str, Any]) -> Any:
    return (
        row.get("query_executed_at")
        or row.get("query_finished_at")
        or row.get("response_created_at")
        or row.get("query_created_at")
    )


def _row_attempt_sort_key(row: dict[str, Any]) -> tuple[str, int, str, int]:
    return (
        _timestamp_key(_row_attempt_time(row)),
        int(row.get("query_id") or 0),
        _timestamp_key(row.get("response_created_at")),
        int(row.get("response_id") or 0),
    )


def _bucket_position(rank: int | None) -> str | None:
    if rank is None:
        return None
    if rank == 1:
        return "Top1"
    if rank <= 3:
        return "Top3"
    if rank <= 5:
        return "Top5"
    if rank <= 10:
        return "Top10"
    return "Other"
