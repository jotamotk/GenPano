"""Bounded re-queue helper for Doubao when no account is available.

Extracted from ``celery_tasks.py`` so unit tests can exercise the helper
without importing the full Celery task module (which pulls in playwright
and the rest of the worker stack).

Issue refs: #908, #916.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Tuple

from geo_tracker.db.models import QueryStatus


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return default


NO_ACCOUNT_REQUEUE_REASONS = frozenset(
    {
        "account_pool_empty",
        "account_no_active",
        "account_no_cookies",
        "no_account_available",
    }
)
NO_ACCOUNT_REQUEUE_LLMS = frozenset({"doubao"})
NO_ACCOUNT_REQUEUE_REASON_TAG = "no_account_available_requeue"


def maybe_requeue_for_no_account(
    query,
    failure_reason: str,
    *,
    now: datetime | None = None,
) -> Tuple[bool, int, int]:
    """Bounded re-queue back to ``pending`` when no account was available.

    Returns ``(requeued, current_retry, retry_max)``. When ``requeued`` is
    ``True`` the query fields are updated in-place and the caller commits.
    The historical FAILED branch is preserved when this returns ``False``
    (e.g. budget exhausted, non-Doubao engine, non-pool failure reason),
    which keeps the existing "avoid infinite loop" guarantee.
    """
    current = now or datetime.utcnow()
    retry_max = _env_int("DOUBAO_NO_ACCOUNT_REQUEUE_MAX", 3)
    current_retry = int(getattr(query, "retry_count", 0) or 0)

    target_llm = getattr(query, "target_llm", "") or ""
    eligible = (
        target_llm in NO_ACCOUNT_REQUEUE_LLMS
        and failure_reason in NO_ACCOUNT_REQUEUE_REASONS
        and current_retry < retry_max
    )
    if not eligible:
        return (False, current_retry, retry_max)

    query.status = QueryStatus.PENDING.value
    query.retry_count = current_retry + 1
    query.retry_reason = NO_ACCOUNT_REQUEUE_REASON_TAG
    query.started_at = None
    query.finished_at = None
    query.executed_at = None
    query.queued_at = current
    return (True, query.retry_count, retry_max)
