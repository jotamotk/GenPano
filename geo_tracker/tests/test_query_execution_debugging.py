from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from geo_tracker.db.models import AccountStatus, LLMAccount, Query
from geo_tracker.agent.response_validation import invalid_response_reason
from geo_tracker.tasks.account_assignment import acquire_query_account
from geo_tracker.tasks.query_failure import (
    classify_execution_failure,
    _empty_response_failure_reason,
    _should_report_account_failure,
)
from geo_tracker.tasks.query_lifecycle import mark_query_finished, mark_query_started


def test_chatgpt_application_error_is_not_a_valid_response():
    text = """
    Application Error
    bu@https://chatgpt.com/cdn/assets/2340486e-jpw996a67rppk812.js:8:106803
    yu@https://chatgpt.com/cdn/assets/2340486e-jpw996a67rppk812.js:8:106178
    """

    assert invalid_response_reason("chatgpt", text) == "chatgpt_application_error"


def test_normal_chatgpt_answer_is_valid_response():
    text = "Use water first, then apply serum after the skin has absorbed the toner."

    assert invalid_response_reason("chatgpt", text) is None


def test_query_execution_debug_fields_are_populated():
    query = Query(query_text="hello", target_llm="doubao")
    started_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=2)

    mark_query_started(query, now=started_at)
    mark_query_finished(query, status="done", started_at=started_at, reason=None)

    assert query.status == "done"
    assert query.started_at == started_at
    assert query.finished_at is not None
    assert query.latency_ms is not None
    assert query.latency_ms >= 0
    assert query.retry_reason is None


def test_browser_launch_timeout_is_classified_as_infrastructure_failure():
    exc = RuntimeError("BrowserType.launch: Timeout 180000ms exceeded.")

    assert classify_execution_failure(exc) == "browser_launch_timeout"


def test_empty_response_preserves_executor_failure_reason():
    class Executor:
        last_error_reason = "browser_launch_timeout"

    assert (
        _empty_response_failure_reason(
            None,
            executor=Executor(),
            account_cookies='{"cookies":[]}',
        )
        == "browser_launch_timeout"
    )


def test_browser_failures_do_not_penalize_llm_accounts():
    assert _should_report_account_failure("cookies_expired") is True
    assert _should_report_account_failure("browser_launch_timeout") is False
    assert _should_report_account_failure("soft_time_limit") is False


class _FakeDb:
    def __init__(self, account: LLMAccount | None = None):
        self.account = account
        self.commits = 0

    async def get(self, model, row_id):
        assert model is LLMAccount
        if self.account and self.account.id == row_id:
            return self.account
        return None

    async def commit(self):
        self.commits += 1


class _RecordingPool:
    def __init__(self, account: LLMAccount | None = None):
        self.account = account
        self.calls: list[dict[str, str | None]] = []

    async def acquire(self, llm_name, country_code=None, profile_id=None):
        self.calls.append(
            {
                "llm_name": llm_name,
                "country_code": country_code,
                "profile_id": profile_id,
            }
        )
        return self.account


@pytest.mark.asyncio
async def test_execute_query_prefers_scheduler_assigned_account():
    assigned = LLMAccount(
        id=33,
        llm_name="chatgpt",
        status=AccountStatus.ACTIVE.value,
        cookies_json='[{"name":"session"}]',
        query_count_today=2,
        daily_limit=80,
    )
    query = Query(account_id=33, target_llm="chatgpt", profile_id=12)
    db = _FakeDb(assigned)
    pool = _RecordingPool()

    account = await acquire_query_account(db, query, pool=pool)

    assert account is assigned
    assert pool.calls == []
    assert assigned.query_count_today == 3
    assert assigned.last_used_at is not None
    assert db.commits == 1


@pytest.mark.asyncio
async def test_execute_query_falls_back_to_profile_scoped_pool_when_assignment_unusable():
    assigned = LLMAccount(
        id=33,
        llm_name="chatgpt",
        status=AccountStatus.ACTIVE.value,
        cookies_json="",
        query_count_today=2,
        daily_limit=80,
    )
    fallback = LLMAccount(
        id=34,
        llm_name="chatgpt",
        status=AccountStatus.ACTIVE.value,
        cookies_json='[{"name":"session"}]',
        query_count_today=0,
        daily_limit=80,
    )
    query = Query(account_id=33, target_llm="chatgpt", profile_id=12)
    db = _FakeDb(assigned)
    pool = _RecordingPool(fallback)

    account = await acquire_query_account(db, query, pool=pool)

    assert account is fallback
    assert pool.calls == [
        {"llm_name": "chatgpt", "country_code": None, "profile_id": "12"}
    ]
    assert assigned.query_count_today == 2
    assert db.commits == 0
