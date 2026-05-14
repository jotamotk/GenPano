"""Tests for bounded no-account re-queue helper (issue #916 / #908)."""
from __future__ import annotations

from datetime import datetime

import pytest

from geo_tracker.db.models import Query, QueryStatus
from geo_tracker.tasks.no_account_requeue import (
    NO_ACCOUNT_REQUEUE_LLMS,
    NO_ACCOUNT_REQUEUE_REASONS,
    _env_int,
    maybe_requeue_for_no_account,
)


def _query(
    *,
    target_llm: str = "doubao",
    retry_count: int = 0,
    status: str = QueryStatus.RUNNING.value,
) -> Query:
    return Query(
        id=184974,
        brand_id=24,
        target_llm=target_llm,
        query_text="bestCoffer Doubao stuck-pipeline replay",
        status=status,
        retry_count=retry_count,
    )


def test_constants_are_immutable() -> None:
    assert isinstance(NO_ACCOUNT_REQUEUE_REASONS, frozenset)
    assert isinstance(NO_ACCOUNT_REQUEUE_LLMS, frozenset)
    assert "doubao" in NO_ACCOUNT_REQUEUE_LLMS
    assert "account_pool_empty" in NO_ACCOUNT_REQUEUE_REASONS


def test_doubao_requeue_path_resets_run_fields() -> None:
    q = _query()
    q.started_at = datetime(2026, 5, 14, 12, 0, 0)
    q.executed_at = datetime(2026, 5, 14, 12, 0, 0)
    q.finished_at = None

    now = datetime(2026, 5, 14, 12, 5, 0)
    requeued, retry_count, retry_max = maybe_requeue_for_no_account(
        q, "account_pool_empty", now=now
    )

    assert requeued is True
    assert retry_count == 1
    assert retry_max == 3
    assert q.status == QueryStatus.PENDING.value
    assert q.retry_count == 1
    assert q.retry_reason == "no_account_available_requeue"
    assert q.started_at is None
    assert q.executed_at is None
    assert q.finished_at is None
    assert q.queued_at == now


def test_chatgpt_not_in_requeue_set() -> None:
    q = _query(target_llm="chatgpt")
    requeued, _, _ = maybe_requeue_for_no_account(q, "account_pool_empty")
    assert requeued is False
    assert q.status == QueryStatus.RUNNING.value


def test_non_pool_reason_does_not_requeue() -> None:
    q = _query()
    requeued, _, _ = maybe_requeue_for_no_account(q, "doubao_page_unavailable")
    assert requeued is False
    assert q.status == QueryStatus.RUNNING.value


def test_budget_exhausted_falls_through_to_failed_branch(monkeypatch) -> None:
    monkeypatch.setenv("DOUBAO_NO_ACCOUNT_REQUEUE_MAX", "2")
    q = _query(retry_count=2)
    requeued, current, retry_max = maybe_requeue_for_no_account(
        q, "account_pool_empty"
    )
    assert requeued is False
    assert current == 2
    assert retry_max == 2
    assert q.status == QueryStatus.RUNNING.value


def test_env_int_handles_garbage(monkeypatch) -> None:
    monkeypatch.setenv("DOUBAO_NO_ACCOUNT_REQUEUE_MAX", "not-an-int")
    assert _env_int("DOUBAO_NO_ACCOUNT_REQUEUE_MAX", 7) == 7

    monkeypatch.delenv("DOUBAO_NO_ACCOUNT_REQUEUE_MAX", raising=False)
    assert _env_int("DOUBAO_NO_ACCOUNT_REQUEUE_MAX", 5) == 5

    monkeypatch.setenv("DOUBAO_NO_ACCOUNT_REQUEUE_MAX", "  9 ")
    assert _env_int("DOUBAO_NO_ACCOUNT_REQUEUE_MAX", 0) == 9


def test_retry_count_increments_across_calls(monkeypatch) -> None:
    monkeypatch.setenv("DOUBAO_NO_ACCOUNT_REQUEUE_MAX", "3")
    q = _query()
    for expected in (1, 2, 3):
        q.status = QueryStatus.RUNNING.value
        requeued, retry_count, _ = maybe_requeue_for_no_account(
            q, "account_no_active"
        )
        assert requeued is (expected <= 3)
        assert retry_count == expected
    q.status = QueryStatus.RUNNING.value
    requeued, retry_count, _ = maybe_requeue_for_no_account(
        q, "account_no_active"
    )
    assert requeued is False
    assert retry_count == 3
