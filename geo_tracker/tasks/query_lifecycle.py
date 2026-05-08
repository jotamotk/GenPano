from __future__ import annotations

from datetime import UTC, datetime


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def mark_query_started(query, *, now: datetime | None = None) -> datetime:
    started_at = now or _utcnow_naive()
    query.status = "running"
    query.executed_at = started_at
    query.started_at = started_at
    query.finished_at = None
    query.latency_ms = None
    return started_at


def mark_query_finished(
    query,
    *,
    status: str,
    started_at: datetime | None = None,
    reason: str | None = None,
    now: datetime | None = None,
) -> datetime:
    finished_at = now or _utcnow_naive()
    query.status = status
    query.finished_at = finished_at
    start = started_at or getattr(query, "started_at", None)
    if start is not None:
        query.latency_ms = max(0, int((finished_at - start).total_seconds() * 1000))
    query.retry_reason = reason
    return finished_at
