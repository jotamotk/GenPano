from __future__ import annotations

import sys
import types
from datetime import UTC, datetime, timedelta

import pytest

from geo_tracker.db.models import AccountStatus, LLMAccount, Query
from geo_tracker.agent.response_validation import invalid_response_reason
from geo_tracker.tasks.account_assignment import (
    account_unavailable_reason_from_accounts,
    acquire_query_account,
)
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


def test_session_debug_text_redacts_tokens(monkeypatch):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.guest_executor import (
        _redact_runtime_data,
        _redact_sensitive_text,
    )

    text = '{"accessToken":"secret-access","refreshToken":"secret-refresh"} Bearer abc.def'

    redacted = _redact_sensitive_text(text)

    assert "secret-access" not in redacted
    assert "secret-refresh" not in redacted
    assert "abc.def" not in redacted
    assert "[redacted]" in redacted
    nested = _redact_runtime_data({"bodyText": text, "events": [{"text": text}]})
    assert "secret-access" not in str(nested)


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


def test_account_unavailability_classifies_daily_limit_exhaustion():
    accounts = [
        LLMAccount(
            id=16,
            llm_name="chatgpt",
            status=AccountStatus.ACTIVE.value,
            cookies_json='[{"name":"session"}]',
            query_count_today=20,
            daily_limit=20,
        ),
        LLMAccount(
            id=17,
            llm_name="chatgpt",
            status=AccountStatus.ACTIVE.value,
            cookies_json='[{"name":"session"}]',
            query_count_today=60,
            daily_limit=60,
        ),
    ]

    assert (
        account_unavailable_reason_from_accounts(accounts)
        == "account_daily_limit_exhausted"
    )


@pytest.mark.asyncio
async def test_proxied_attempt_exhaustion_without_proxy_error_is_no_response(monkeypatch):
    playwright = types.ModuleType("playwright")
    playwright_async = types.ModuleType("playwright.async_api")
    playwright_async.async_playwright = object
    playwright_async.BrowserContext = object
    playwright_async.Page = object
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.async_api", playwright_async)

    import geo_tracker.agent.guest_executor as guest_executor_module
    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    attempts = 0

    async def fake_execute_once(self, query, config, *, use_proxy):
        nonlocal attempts
        attempts += 1
        assert use_proxy is True
        return None

    async def fake_get_current_node(api_url, group_name):
        return f"node-{attempts}"

    async def fake_switch_to_next_node(api_url, group_name, exclude=None):
        return f"node-next-{len(exclude or set())}"

    monkeypatch.setattr(GuestQueryExecutor, "_execute_once", fake_execute_once)
    monkeypatch.setattr(guest_executor_module, "get_current_node", fake_get_current_node)
    monkeypatch.setattr(
        guest_executor_module,
        "switch_to_next_node",
        fake_switch_to_next_node,
    )

    executor = GuestQueryExecutor(proxy_url="http://proxy.internal:6789")

    result = await executor.execute(Query(query_text="hello", target_llm="chatgpt"))

    assert result is None
    assert attempts == 3
    assert executor.last_error_reason == "no_response"


def _install_fake_playwright(monkeypatch):
    playwright = types.ModuleType("playwright")
    playwright_async = types.ModuleType("playwright.async_api")
    playwright_async.async_playwright = object
    playwright_async.BrowserContext = object
    playwright_async.Page = object
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.async_api", playwright_async)


@pytest.mark.asyncio
async def test_find_attached_selector_recovers_partially_loaded_input(monkeypatch):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.guest_executor import _find_attached_selector

    class FakeElement:
        async def is_visible(self):
            return True

    class FakePage:
        def __init__(self):
            self.calls: list[tuple[str, int, str]] = []

        async def wait_for_selector(self, selector, timeout, state):
            self.calls.append((selector, timeout, state))
            if selector == "#ready":
                return FakeElement()
            raise RuntimeError("not attached")

    page = FakePage()

    selector, visible = await _find_attached_selector(
        page,
        "textarea, #ready, [contenteditable='true']",
        timeout=123,
    )

    assert selector == "#ready"
    assert visible is True
    assert page.calls == [
        ("textarea", 123, "attached"),
        ("#ready", 123, "attached"),
    ]


@pytest.mark.asyncio
async def test_doubao_controlled_textarea_prefers_js_injection(monkeypatch):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    class FakeKeyboard:
        def __init__(self):
            self.typed: list[str] = []

        async def type(self, text, delay=0):
            self.typed.append(text)

    class FakePage:
        def __init__(self):
            self.keyboard = FakeKeyboard()

        async def wait_for_timeout(self, ms):
            return None

    class FakeInput:
        def __init__(self):
            self.value = ""
            self.scripts: list[str] = []

        async def fill(self, text):
            self.value = text

        async def evaluate(self, script, arg=None):
            self.scripts.append(script)
            if arg is not None and "beforeinput" in script and "InputEvent" in script:
                self.value = arg
                return self.value
            return self.value

    page = FakePage()
    input_el = FakeInput()
    executor = GuestQueryExecutor()

    filled = await executor._fill_plain_text_input(page, input_el, "hello doubao", "doubao")

    assert filled is True
    assert input_el.value == "hello doubao"
    assert page.keyboard.typed == []
    assert any("compositionend" in script for script in input_el.scripts)


def test_doubao_response_selector_accepts_receive_message_container(monkeypatch):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.guest_executor import GUEST_LLM_CONFIG

    selectors = [
        selector.strip()
        for selector in GUEST_LLM_CONFIG["doubao"]["response_selector"].split(",")
    ]

    assert "[data-testid='receive_message']" in selectors


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
