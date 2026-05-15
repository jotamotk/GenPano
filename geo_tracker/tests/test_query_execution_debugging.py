from __future__ import annotations

import sys
import types
import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from geo_tracker.db.models import (
    AccountStatus,
    Base,
    LLMAccount,
    LLMResponse,
    Query,
    QueryStatus,
)
from geo_tracker.agent.response_validation import (
    chatgpt_auth_state_reason,
    doubao_auth_state_reason,
    invalid_response_reason,
)
from geo_tracker.tasks.account_assignment import (
    account_unavailable_reason_from_accounts,
    acquire_query_account,
)
from geo_tracker.tasks.query_failure import (
    classify_execution_failure,
    resolve_execution_failure_reason,
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


def test_chatgpt_home_shell_is_not_a_valid_response():
    text = (
        "Skip to content New chat Search chats Recents Chat history New chat "
        "Search chats Codex More James Free ChatGPT What's on your mind today?"
    )

    assert invalid_response_reason("chatgpt", text) == "chatgpt_home_shell"


def test_chatgpt_apple_signin_page_is_not_a_valid_response():
    text = (
        "Apple Account Sign in Use your Apple Account to sign in to ChatGPT. "
        "Email or Phone Number Continue"
    )

    assert invalid_response_reason("chatgpt", text) == "chatgpt_auth_redirect"


def test_chatgpt_session_log_summary_excludes_sensitive_body(monkeypatch):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.guest_executor import _chatgpt_session_log_summary

    body = (
        '{"accessToken":true,'
        '"refreshToken":true,'
        '"user":{"display":"Fixture User"},'
        '"expires":true}'
    )

    summary = _chatgpt_session_log_summary(body)

    assert "refreshToken" not in summary
    assert "Fixture User" not in summary
    assert "access_token_present=True" in summary
    assert "user_present=True" in summary
    assert "expires_present=True" in summary


def test_chatgpt_token_invalidated_runtime_event_is_detected():
    reason = chatgpt_auth_state_reason(
        "Your session has expired. Please log in again to continue using the app.",
        runtime_events=[
            {
                "kind": "console",
                "text": (
                    "401 token_invalidated Your authentication token has been "
                    "invalidated. Please try signing in again."
                ),
            }
        ],
    )

    assert reason == "token_invalidated"


def test_invalid_response_reason_detects_chatgpt_token_invalidated_message():
    text = "Your authentication token has been invalidated. Please try signing in again."

    assert invalid_response_reason("chatgpt", text) == "token_invalidated"


@pytest.mark.parametrize(
    ("url", "title", "text"),
    [
        (
            "https://appleid.apple.com/auth/authorize?client_id=com.openai.chat",
            "Sign in to Apple Account",
            "Use your Apple Account to sign in to ChatGPT Email or Phone Number",
        ),
        (
            "https://auth0.openai.com/u/login?state=abc",
            "Log in to ChatGPT",
            "Log in to ChatGPT Continue with Google Continue with Microsoft",
        ),
        (
            "https://login.openai.com/authorize?client_id=chatgpt",
            "Sign in",
            "Sign in to ChatGPT Continue with Apple",
        ),
    ],
)
def test_chatgpt_auth_redirect_is_operator_visible(url, title, text):
    reason = chatgpt_auth_state_reason(
        text,
        url=url,
        title=title,
    )

    assert reason == "chatgpt_auth_redirect"


def test_chatgpt_logged_out_shell_with_prompt_box_is_not_authenticated():
    text = (
        "ChatGPT Log in Sign up for free "
        "Log in to get answers based on saved chats and uploaded files. "
        "Accept all cookies #prompt-textarea Message ChatGPT"
    )
    runtime_events = [
        {"kind": "console", "text": "script-src allows https://auth0.openai.com"}
    ]

    assert chatgpt_auth_state_reason(text, url="https://chatgpt.com/") == "chatgpt_not_logged_in"
    assert (
        chatgpt_auth_state_reason(
            text,
            url="https://chatgpt.com/",
            runtime_events=runtime_events,
        )
        == "chatgpt_not_logged_in"
    )
    assert invalid_response_reason("chatgpt", text) == "chatgpt_not_logged_in"


def test_chatgpt_auth0_csp_allowlist_on_chatgpt_shell_is_not_redirect():
    text = (
        "ChatGPT New chat Search chats James Free Upgrade Get Plus "
        "#prompt-textarea Message ChatGPT What's on your mind today?"
    )
    runtime_events = [
        {
            "kind": "console",
            "text": (
                "Refused to load script because it violates script-src "
                "https://auth0.openai.com https://chatgpt.com"
            ),
        }
    ]

    reason = chatgpt_auth_state_reason(
        text,
        url="https://chatgpt.com/",
        title="ChatGPT",
        runtime_events=runtime_events,
    )

    assert reason is None


@pytest.mark.asyncio
async def test_chatgpt_auth0_csp_allowlist_does_not_override_submit_failed(monkeypatch):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    class FakePage:
        url = "https://chatgpt.com/"

        async def evaluate(self, script):
            assert "innerText" in script
            return (
                "ChatGPT New chat Search chats James Free Upgrade Get Plus "
                "#prompt-textarea Message ChatGPT What's on your mind today?"
            )

        async def title(self):
            return "ChatGPT"

    executor = GuestQueryExecutor()
    executor.last_error_reason = "submit_failed"

    reason = await executor._prefer_chatgpt_auth_failure_reason(
        "chatgpt",
        FakePage(),
        runtime_events=[
            {
                "kind": "console",
                "text": (
                    "script-src allows https://auth0.openai.com "
                    "https://chatgpt.com"
                ),
            }
        ],
    )

    assert reason is None
    assert executor.last_error_reason == "submit_failed"


@pytest.mark.asyncio
async def test_chatgpt_auth_redirect_overrides_generic_browser_timeout(monkeypatch):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    class FakePage:
        url = "https://appleid.apple.com/auth/authorize?client_id=com.openai.chat"

        async def evaluate(self, script):
            assert "innerText" in script
            return "Use your Apple Account to sign in to ChatGPT Email or Phone Number"

        async def title(self):
            return "Sign in to Apple Account"

    executor = GuestQueryExecutor()
    executor.last_error_reason = "browser_timeout"

    reason = await executor._prefer_chatgpt_auth_failure_reason("chatgpt", FakePage())

    assert reason == "chatgpt_auth_redirect"
    assert executor.last_error_reason == "chatgpt_auth_redirect"


@pytest.mark.asyncio
async def test_clash_proxy_group_401_sets_auth_diagnostic(monkeypatch):
    from geo_tracker.agent import clash_api

    captured_headers: dict[str, str] = {}

    class FakeResponse:
        status_code = 401
        text = "Unauthorized"

        def json(self):
            return {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url, headers=None):
            captured_headers.update(headers or {})
            return FakeResponse()

    monkeypatch.setenv("CLASH_API_SECRET", "test-secret")
    monkeypatch.setattr(clash_api.httpx, "AsyncClient", FakeClient)
    clash_api.clear_last_error_reason()

    group = await clash_api.get_proxy_group("http://clash.local:9098", "Ai")

    assert group is None
    assert captured_headers["Authorization"] == "Bearer test-secret"
    assert clash_api.get_last_error_reason() == "proxy_api_unauthorized"


@pytest.mark.asyncio
async def test_chatgpt_global_direct_route_switches_to_ai_platform_node(monkeypatch):
    from geo_tracker.agent import clash_api

    calls: list[tuple[str, str, dict | None]] = []

    class FakeResponse:
        def __init__(self, status_code, payload=None, text=""):
            self.status_code = status_code
            self._payload = payload or {}
            self.text = text

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url, headers=None):
            calls.append(("GET", url, None))
            if url.endswith("/proxies/GLOBAL"):
                return FakeResponse(
                    200,
                    {"now": "DIRECT", "all": ["DIRECT", "node-a", "node-b"]},
                )
            if url.endswith("/proxies/Ai"):
                return FakeResponse(200, {"now": "node-b", "all": ["node-a", "node-b"]})
            raise AssertionError(url)

        async def put(self, url, json=None, headers=None):
            calls.append(("PUT", url, json))
            return FakeResponse(204)

    monkeypatch.setattr(clash_api.httpx, "AsyncClient", FakeClient)

    diagnostic = await clash_api.ensure_global_proxy_route(
        "http://clash.local:9098",
        "Ai",
    )

    assert diagnostic.ok is True
    assert diagnostic.changed is True
    assert diagnostic.selected_node == "node-b"
    assert ("PUT", "http://clash.local:9098/proxies/GLOBAL", {"name": "node-b"}) in calls


@pytest.mark.asyncio
async def test_chatgpt_global_wrong_route_switches_to_ai_platform_group(monkeypatch):
    from geo_tracker.agent import clash_api

    calls: list[tuple[str, str, dict | None]] = []

    class FakeResponse:
        def __init__(self, status_code, payload=None, text=""):
            self.status_code = status_code
            self._payload = payload or {}
            self.text = text

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url, headers=None):
            calls.append(("GET", url, None))
            if url.endswith("/proxies/GLOBAL"):
                return FakeResponse(
                    200,
                    {"now": "Domestic", "all": ["DIRECT", "Domestic", "Ai"]},
                )
            if url.endswith("/proxies/Ai"):
                return FakeResponse(200, {"now": "node-b", "all": ["node-a", "node-b"]})
            raise AssertionError(url)

        async def put(self, url, json=None, headers=None):
            calls.append(("PUT", url, json))
            return FakeResponse(204)

    monkeypatch.setattr(clash_api.httpx, "AsyncClient", FakeClient)

    diagnostic = await clash_api.ensure_global_proxy_route(
        "http://clash.local:9098",
        "Ai",
    )

    assert diagnostic.ok is True
    assert diagnostic.changed is True
    assert diagnostic.global_now == "Ai"
    assert diagnostic.selected_node == "Ai"
    assert ("PUT", "http://clash.local:9098/proxies/GLOBAL", {"name": "Ai"}) in calls


def test_session_debug_text_redacts_tokens(monkeypatch):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.guest_executor import (
        _redact_runtime_data,
        _redact_sensitive_text,
    )

    text = (
        '{"accessToken":"secret-access","refreshToken":"secret-refresh"} Bearer abc.def'
    )

    redacted = _redact_sensitive_text(text)

    assert "secret-access" not in redacted
    assert "secret-refresh" not in redacted
    assert "abc.def" not in redacted
    assert "[redacted]" in redacted
    nested = _redact_runtime_data({"bodyText": text, "events": [{"text": text}]})
    assert "secret-access" not in str(nested)


def test_doubao_unavailable_page_text_is_detected(monkeypatch):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.guest_executor import _is_doubao_unavailable_page_text

    assert _is_doubao_unavailable_page_text("该页面暂时不可用\n请尝试刷新此页面")
    assert _is_doubao_unavailable_page_text("刷新页面")
    assert not _is_doubao_unavailable_page_text("你好，欢迎使用豆包")


# Refs #958: prior behavior reloaded once, waited 5s, then flipped the account
# into a 12-hour cooldown. The recovery helper now reloads up to N times with a
# growing backoff so transient platform errors don't burn account capacity.
@pytest.mark.asyncio
async def test_recover_from_doubao_unavailable_page_retries_until_input_returns(
    monkeypatch,
):
    _install_fake_playwright(monkeypatch)
    monkeypatch.setenv("DOUBAO_UNAVAILABLE_RELOAD_MAX", "3")
    # The helper floors the wait at 1000ms to keep production safe from
    # accidental zero waits; pick a value above the floor so backoff math is
    # observable in the test.
    monkeypatch.setenv("DOUBAO_UNAVAILABLE_RELOAD_WAIT_MS", "1500")

    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    class FakeInput:
        pass

    class FakePage:
        def __init__(self):
            self.reload_calls = 0
            self.body_texts = [
                "该页面暂时不可用 刷新页面",  # initial probe
                "该页面暂时不可用 刷新页面",  # after reload 1
                "该页面暂时不可用 刷新页面",  # after reload 2
                "豆包正常加载",                # after reload 3 → recovered
            ]
            self.waits: list[int] = []

        async def evaluate(self, _script):
            return self.body_texts.pop(0) if self.body_texts else "豆包正常加载"

        async def reload(self, wait_until=None, timeout=None):
            self.reload_calls += 1

        async def wait_for_timeout(self, ms):
            self.waits.append(ms)

        async def wait_for_selector(self, selector, timeout, state):
            return FakeInput()

    page = FakePage()
    executor = GuestQueryExecutor()

    class _Q:
        id = 184985

    snapshot_calls: list[tuple[int, str]] = []

    async def fake_snapshot(page_arg, query_id, suffix, **_kwargs):
        snapshot_calls.append((query_id, suffix))

    monkeypatch.setattr(
        "geo_tracker.agent.guest_executor._save_runtime_snapshot", fake_snapshot
    )
    monkeypatch.setattr(
        "geo_tracker.agent.guest_executor._save_screenshot", fake_snapshot
    )

    result = await executor._recover_from_doubao_unavailable_page(
        page,
        query=_Q(),
        config={},
        selectors=["textarea"],
        runtime_events=None,
        proxy_diagnostic=None,
    )

    assert isinstance(result, FakeInput)
    assert page.reload_calls == 3
    # Backoff is linear: base_ms * attempt → 1500, 3000, 4500
    assert page.waits == [1500, 3000, 4500]
    # last_error_reason MUST stay unset when recovery succeeded — otherwise the
    # caller would still cool the account down on a successful run.
    assert executor.last_error_reason is None
    # The pre-reload diagnostic snapshot is the only artifact saved on success.
    assert snapshot_calls == [(184985, "doubao_page_unavailable_before_reload")]


@pytest.mark.asyncio
async def test_recover_from_doubao_unavailable_page_marks_failure_after_max_reloads(
    monkeypatch,
):
    _install_fake_playwright(monkeypatch)
    monkeypatch.setenv("DOUBAO_UNAVAILABLE_RELOAD_MAX", "2")
    monkeypatch.setenv("DOUBAO_UNAVAILABLE_RELOAD_WAIT_MS", "5")

    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    class FakePage:
        def __init__(self):
            self.reload_calls = 0

        async def evaluate(self, _script):
            return "该页面暂时不可用 刷新页面"

        async def reload(self, wait_until=None, timeout=None):
            self.reload_calls += 1

        async def wait_for_timeout(self, ms):
            return None

        async def wait_for_selector(self, selector, timeout, state):
            raise RuntimeError("not attached")

    page = FakePage()
    executor = GuestQueryExecutor()

    class _Q:
        id = 184985

    snapshot_calls: list[tuple[int, str]] = []

    async def fake_snapshot(page_arg, query_id, suffix, **_kwargs):
        snapshot_calls.append((query_id, suffix))

    monkeypatch.setattr(
        "geo_tracker.agent.guest_executor._save_runtime_snapshot", fake_snapshot
    )
    monkeypatch.setattr(
        "geo_tracker.agent.guest_executor._save_screenshot", fake_snapshot
    )

    result = await executor._recover_from_doubao_unavailable_page(
        page,
        query=_Q(),
        config={},
        selectors=["textarea"],
        runtime_events=None,
        proxy_diagnostic=None,
    )

    assert result is None
    assert page.reload_calls == 2
    assert executor.last_error_reason == "page_unavailable"
    # On exhaustion the helper saves a `_final` artifact with a matching name so
    # operators see page_unavailable in the filename, not the misleading no_input.
    suffixes = {suffix for _, suffix in snapshot_calls}
    assert "doubao_page_unavailable_before_reload" in suffixes
    assert "doubao_page_unavailable_final" in suffixes


@pytest.mark.asyncio
async def test_recover_from_doubao_unavailable_page_no_op_when_markers_absent(
    monkeypatch,
):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    class FakePage:
        def __init__(self):
            self.reload_calls = 0

        async def evaluate(self, _script):
            return "你好，欢迎使用豆包"

        async def reload(self, **_kwargs):
            self.reload_calls += 1

    page = FakePage()
    executor = GuestQueryExecutor()

    class _Q:
        id = 1

    result = await executor._recover_from_doubao_unavailable_page(
        page,
        query=_Q(),
        config={},
        selectors=["textarea"],
        runtime_events=None,
        proxy_diagnostic=None,
    )

    assert result is None
    assert page.reload_calls == 0
    assert executor.last_error_reason is None


def test_doubao_page_unavailable_cooldown_uses_short_window_by_default(monkeypatch):
    from datetime import timedelta

    monkeypatch.delenv("DOUBAO_PAGE_UNAVAILABLE_COOLDOWN_MINUTES", raising=False)
    from geo_tracker.pool import account_pool

    delta = account_pool._doubao_page_unavailable_cooldown()
    # Default is 30 minutes — significantly shorter than COOLDOWN_HOURS=12.
    assert delta == timedelta(minutes=30)


def test_doubao_page_unavailable_cooldown_respects_env_override(monkeypatch):
    from datetime import timedelta

    monkeypatch.setenv("DOUBAO_PAGE_UNAVAILABLE_COOLDOWN_MINUTES", "5")
    from geo_tracker.pool import account_pool

    assert account_pool._doubao_page_unavailable_cooldown() == timedelta(minutes=5)


def test_doubao_page_unavailable_cooldown_falls_back_when_disabled(monkeypatch):
    from datetime import timedelta

    monkeypatch.setenv("DOUBAO_PAGE_UNAVAILABLE_COOLDOWN_MINUTES", "0")
    from geo_tracker.pool import account_pool

    # 0 / negative disables the short window and reverts to the global 12h cooldown
    # so operators can opt out without redeploying.
    assert account_pool._doubao_page_unavailable_cooldown() == timedelta(
        hours=account_pool.COOLDOWN_HOURS
    )


def test_doubao_page_unavailable_cooldown_ignores_garbage_env(monkeypatch):
    from datetime import timedelta

    monkeypatch.setenv("DOUBAO_PAGE_UNAVAILABLE_COOLDOWN_MINUTES", "not-a-number")
    from geo_tracker.pool import account_pool

    assert account_pool._doubao_page_unavailable_cooldown() == timedelta(minutes=30)


def test_doubao_page_unavailable_report_failure_uses_short_cooldown(monkeypatch):
    from datetime import datetime, timedelta

    monkeypatch.delenv("DOUBAO_PAGE_UNAVAILABLE_COOLDOWN_MINUTES", raising=False)
    from geo_tracker.pool.account_pool import (
        AccountPool,
        AccountStatus,
        COOLDOWN_HOURS,
    )

    class FakeAccount:
        def __init__(self):
            self.id = 7
            self.llm_name = "doubao"
            self.status = AccountStatus.ACTIVE.value
            self.cooldown_until = None
            self.consecutive_fails = 0

    class FakeDb:
        def __init__(self, account):
            self.account = account
            self.added: list = []

        async def get(self, _model, _id):
            return self.account

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            return None

    account = FakeAccount()
    pool = AccountPool(FakeDb(account))

    before = datetime.utcnow()
    asyncio.run(pool.report_failure(7, reason="doubao_page_unavailable"))
    after = datetime.utcnow()

    assert account.status == AccountStatus.COOLDOWN.value
    assert account.cooldown_until is not None
    # Short window: cooldown must end well within the global 12h ceiling.
    short_ceiling = after + timedelta(minutes=30) + timedelta(seconds=5)
    long_floor = before + timedelta(hours=COOLDOWN_HOURS - 1)
    assert account.cooldown_until <= short_ceiling
    assert account.cooldown_until < long_floor


def test_doubao_proxy_runtime_diagnostic_records_proxy_path(monkeypatch):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.guest_executor import _proxy_runtime_diagnostic

    monkeypatch.setenv("DOUBAO_USE_PROXY", "1")
    monkeypatch.setenv("CLASH_FORCE_GLOBAL_PROXY_ROUTE", "1")

    payload = _proxy_runtime_diagnostic(
        "doubao",
        "http://user:secret@proxy.internal:6789",
        True,
    )

    assert payload["llm"] == "doubao"
    assert payload["proxyConfigured"] is True
    assert payload["useProxy"] is True
    assert "secret" not in payload["proxyUrl"]
    assert payload["forceGlobalRoute"] is True
    assert payload["doubaoUseProxy"] is True


def test_doubao_answer_like_page_with_free_login_state_is_rejected():
    text = (
        "bestCoffer 在咖啡机品类中主要覆盖便携浓缩、车载场景和露营人群。\n"
        "登录\n"
        "7天免登录"
    )
    html = """
    <header>
      <button class="login-button">登录</button>
      <span class="trial-copy">7天免登录</span>
    </header>
    <main>
      <div class="flow-markdown-body">bestCoffer 的差异化在于便携和即热能力。</div>
    </main>
    """

    assert doubao_auth_state_reason(text, html) == "doubao_not_logged_in"


def test_doubao_answer_like_page_with_login_button_is_rejected():
    text = "bestCoffer 的核心优势包括便携、电池续航和户外咖啡场景。\n登录"
    html = """
    <header>
      <button data-testid="login-button" aria-label="登录">登录</button>
    </header>
    <main>
      <div class="flow-markdown-body">bestCoffer 的核心优势包括便携、电池续航和户外咖啡场景。</div>
    </main>
    """

    assert doubao_auth_state_reason(text, html) == "doubao_not_logged_in"


def test_doubao_top_right_login_overrides_generic_avatar_markup():
    text = "bestCoffer 的核心优势包括便携、电池续航和户外咖啡场景。"
    html = """
    <header>
      <div class="avatar-placeholder"></div>
      <div class="toolbar-action">登录</div>
    </header>
    <main>
      <div class="flow-markdown-body">bestCoffer 的核心优势包括便携、电池续航和户外咖啡场景。</div>
    </main>
    """

    assert doubao_auth_state_reason(text, html) == "doubao_not_logged_in"


def test_doubao_authenticated_page_ignores_hidden_template_login_chrome():
    text = "bestCoffer answer text with authenticated session chrome."
    html = """
    <header>
      <button class="user-avatar" aria-label="\u8d26\u53f7\u83dc\u5355">
        <img alt="\u7528\u6237\u5934\u50cf" src="https://lf-doubao.com/avatar/user.png" />
      </button>
    </header>
    <template id="login-dialog">
      <button data-testid="login-button">\u767b\u5f55</button>
    </template>
    <div style="display:none">
      <button class="login-button">\u767b\u5f55</button>
    </div>
    <main>
      <div class="flow-markdown-body">
        bestCoffer answer text with authenticated session chrome.
      </div>
    </main>
    """

    assert doubao_auth_state_reason(text, html) is None


def test_doubao_authenticated_completed_answer_is_allowed():
    text = "bestCoffer 的核心优势包括便携、电池续航和户外咖啡场景。"
    html = """
    <header>
      <button class="user-avatar" aria-label="账号菜单">
        <img alt="用户头像" src="https://lf-doubao.com/avatar/user.png" />
      </button>
    </header>
    <main>
      <div class="send-msg-bubble-bg">bestCoffer 在咖啡机领域有哪些优势？</div>
      <div class="flow-markdown-body">bestCoffer 的核心优势包括便携、电池续航和户外咖啡场景。</div>
    </main>
    """

    assert doubao_auth_state_reason(text, html) is None


def test_doubao_runtime_logged_out_state_rejects_false_success():
    text = "bestCoffer generated-looking answer"
    html = """
    <script>
    window.__doubao_state__ = {
      accountInfo: {data: {description: "会话过期，请重新登录", error_code: 13, user_id: 0}},
      userSetting: {data: {is_login: false}}
    };
    </script>
    <button id="login-btn-header">登录</button>
    <main><div class="flow-markdown-body">answer text</div></main>
    """

    assert doubao_auth_state_reason(text, html) == "doubao_not_logged_in"


def test_doubao_persistence_gate_allows_answer_html_with_generic_toolbar_login():
    from geo_tracker.agent.response_validation import doubao_persistence_auth_reason

    raw_text = "bestCoffer answers with concrete portable coffee strengths."
    response_html = """
    <header>
      <div class="avatar-placeholder"></div>
      <div class="toolbar-action">\u767b\u5f55</div>
    </header>
    <main>
      <div class="flow-markdown-body">
        bestCoffer has portable coffee strengths for driving and camping.
      </div>
    </main>
    """

    assert doubao_persistence_auth_reason("doubao", raw_text, response_html) is None


def test_doubao_persistence_gate_rejects_answer_html_with_strong_logout_state():
    from geo_tracker.agent.response_validation import doubao_persistence_auth_reason

    raw_text = "bestCoffer answer text"
    response_html = """
    <script>
    window.__doubao_state__ = {
      accountInfo: {data: {description: "\u4f1a\u8bdd\u8fc7\u671f\uff0c\u8bf7\u91cd\u65b0\u767b\u5f55", error_code: 13, user_id: 0}},
      userSetting: {data: {is_login: false}}
    };
    </script>
    <button id="login-btn-header">\u767b\u5f55</button>
    <main><div class="flow-markdown-body">bestCoffer answer text</div></main>
    """

    assert (
        doubao_persistence_auth_reason("doubao", raw_text, response_html)
        == "doubao_not_logged_in"
    )


def test_doubao_persistence_gate_rejects_answer_html_with_qr_login_dialog():
    from geo_tracker.agent.response_validation import doubao_persistence_auth_reason

    raw_text = "bestCoffer answer text"
    response_html = """
    <main><div class="flow-markdown-body">bestCoffer answer text</div></main>
    <div role="dialog">
      <h2>\u626b\u7801\u767b\u5f55</h2>
      <button class="login-button">\u767b\u5f55</button>
    </div>
    """

    assert (
        doubao_persistence_auth_reason("doubao", raw_text, response_html)
        == "doubao_not_logged_in"
    )


def test_doubao_persistence_gate_rejects_answer_html_with_login_dialog():
    from geo_tracker.agent.response_validation import doubao_persistence_auth_reason

    raw_text = "bestCoffer answer text"
    response_html = """
    <main><div class="flow-markdown-body">bestCoffer answer text</div></main>
    <div role="dialog">
      <input placeholder="\u624b\u673a\u53f7" />
      <button class="login-button">\u767b\u5f55</button>
    </div>
    """

    assert (
        doubao_persistence_auth_reason("doubao", raw_text, response_html)
        == "doubao_not_logged_in"
    )


def test_doubao_persistence_gate_strong_logout_overrides_auth_ok_marker():
    from geo_tracker.agent.response_validation import doubao_persistence_auth_reason

    raw_text = "bestCoffer answer-like content"
    response_html = (
        "<div class='flow-markdown-body'>bestCoffer answer-like content</div>"
        "\n<button id='login-btn-header'>\u767b\u5f55</button>"
        "\n<script>window.__state__={is_login:false,user_id:0}</script>"
        "\n<!-- doubao-auth-state:ok -->"
    )

    assert (
        doubao_persistence_auth_reason("doubao", raw_text, response_html)
        == "doubao_not_logged_in"
    )


def test_doubao_persistence_gate_allows_executor_auth_ok_marker():
    from geo_tracker.agent.response_validation import doubao_persistence_auth_reason

    raw_text = "bestCoffer answer-like content"
    response_html = (
        "<div class='flow-markdown-body'>bestCoffer answer-like content</div>"
        "\n<!-- doubao-auth-state:ok -->"
    )

    assert doubao_persistence_auth_reason("doubao", raw_text, response_html) is None


@pytest.mark.asyncio
async def test_doubao_no_response_login_dialog_sets_auth_failure_reason(monkeypatch):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    class FakePage:
        async def evaluate(self, script):
            assert "innerText" in script
            return "登录以解锁更多功能\n手机号\n扫码登录\n登录"

        async def content(self):
            return """
            <div role="dialog">
              <h2>登录以解锁更多功能</h2>
              <input placeholder="手机号" />
              <button class="login-button">登录</button>
            </div>
            <header><button class="login-button">登录</button></header>
            """

    executor = GuestQueryExecutor()
    executor.last_error_reason = "no_response"

    reason = await executor._prefer_doubao_auth_failure_reason("doubao", FakePage())

    assert reason == "doubao_not_logged_in"
    assert executor.last_error_reason == "doubao_not_logged_in"


@pytest.mark.asyncio
async def test_doubao_no_response_login_dialog_missing_state_overrides_generic_reason(
    monkeypatch,
):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    class FakePage:
        async def evaluate(self, script):
            assert "innerText" in script
            return "登录以解锁更多功能\n手机号\n扫码登录"

        async def content(self):
            return """
            <div role="dialog">
              <h2>登录以解锁更多功能</h2>
              <input placeholder="手机号" />
            </div>
            """

    executor = GuestQueryExecutor()
    executor.last_error_reason = "no_response"

    reason = await executor._prefer_doubao_auth_failure_reason("doubao", FakePage())

    assert reason == "doubao_not_logged_in"
    assert executor.last_error_reason == "doubao_not_logged_in"


@pytest.mark.asyncio
async def test_doubao_submit_failed_promotes_auth_failure_reason(monkeypatch):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    class FakePage:
        async def evaluate(self, script):
            assert "innerText" in script
            return "登录以解锁更多功能\n手机号\n扫码登录\n登录"

        async def content(self):
            return """
            <div role="dialog">
              <h2>登录以解锁更多功能</h2>
              <input placeholder="手机号" />
              <button class="login-button">登录</button>
            </div>
            """

    executor = GuestQueryExecutor()
    executor.last_error_reason = "submit_failed"

    reason = await executor._prefer_doubao_auth_failure_reason("doubao", FakePage())

    assert reason == "doubao_not_logged_in"
    assert executor.last_error_reason == "doubao_not_logged_in"


@pytest.mark.asyncio
async def test_doubao_auth_state_overrides_generic_browser_timeout(monkeypatch):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    class FakePage:
        async def evaluate(self, script):
            assert "innerText" in script
            return (
                "bestCoffer 的核心优势包括协同、权限和审计。\n"
                "登录"
            )

        async def content(self):
            return """
            <main>
              <section>bestCoffer 的核心优势包括协同、权限和审计。</section>
              <header><button class="login-button">登录</button></header>
            </main>
            """

    executor = GuestQueryExecutor()
    executor.last_error_reason = "browser_timeout"

    reason = await executor._prefer_doubao_auth_failure_reason("doubao", FakePage())

    assert reason == "doubao_not_logged_in"
    assert executor.last_error_reason == "doubao_not_logged_in"


@pytest.mark.asyncio
async def test_doubao_page_load_failure_promotes_login_reason(monkeypatch):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    class FakePage:
        async def evaluate(self, script):
            assert "innerText" in script
            return "\u767b\u5f55\u4ee5\u89e3\u9501\u66f4\u591a\u529f\u80fd\n\u624b\u673a\u53f7\n\u626b\u7801\u767b\u5f55\n\u767b\u5f55"

        async def content(self):
            return """
            <div role="dialog">
              <h2>\u767b\u5f55\u4ee5\u89e3\u9501\u66f4\u591a\u529f\u80fd</h2>
              <input placeholder="\u624b\u673a\u53f7" />
              <button class="login-button">\u767b\u5f55</button>
            </div>
            """

    executor = GuestQueryExecutor()
    executor.last_error_reason = "page_load_failed"

    reason = await executor._prefer_doubao_load_failure_reason("doubao", FakePage())

    assert reason == "doubao_not_logged_in"
    assert executor.last_error_reason == "doubao_not_logged_in"


@pytest.mark.asyncio
async def test_doubao_page_load_failure_promotes_visual_challenge_reason(monkeypatch):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    class FakePage:
        async def evaluate(self, script):
            assert "innerText" in script
            return (
                "bestCoffer portable coffee maker advantages\n"
                "\u9700\u8981\u7535\u529b\u9a71\u52a8\u7684\u4e1c\u897f\n"
                "\u8bf7\u9009\u62e9\u6240\u6709\u7b26\u5408\u4e0a\u6587\u63cf\u8ff0\u7684\u56fe\u7247\uff0c"
                "\u5e76\u62d6\u62fd\u5230\u4e0b\u65b9\n"
                "\u56fe\u7247\u52a0\u8f7d\u5931\u8d25\uff0c\u8bf7\u5237\u65b0\u91cd\u8bd5[5202]\n"
                "\u5237\u65b0\n\u53cd\u9988\n\u63d0\u4ea4"
            )

        async def content(self):
            return """
            <main>
              <textarea>bestCoffer portable coffee maker advantages</textarea>
            </main>
            <div role="dialog" class="verify-modal">
              <h2>\u9700\u8981\u7535\u529b\u9a71\u52a8\u7684\u4e1c\u897f</h2>
              <p>\u8bf7\u9009\u62e9\u6240\u6709\u7b26\u5408\u4e0a\u6587\u63cf\u8ff0\u7684\u56fe\u7247\uff0c\u5e76\u62d6\u62fd\u5230\u4e0b\u65b9</p>
              <p>\u56fe\u7247\u52a0\u8f7d\u5931\u8d25\uff0c\u8bf7\u5237\u65b0\u91cd\u8bd5[5202]</p>
              <button>\u5237\u65b0</button><button>\u53cd\u9988</button><button>\u63d0\u4ea4</button>
            </div>
            """

    executor = GuestQueryExecutor()
    executor.last_error_reason = "page_load_failed"

    reason = await executor._prefer_doubao_load_failure_reason("doubao", FakePage())

    assert reason == "doubao_image_challenge_load_failed"
    assert executor.last_error_reason == "doubao_image_challenge_load_failed"


def test_doubao_visual_challenge_text_is_classified_as_image_load_failure(monkeypatch):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.guest_executor import _doubao_visual_challenge_state_from_text

    body_text = (
        "bestCoffer \u5728\u4fbf\u643a\u5496\u5561\u673a\u54c1\u7c7b\u6709\u54ea\u4e9b\u4f18\u52bf\uff1f\n"
        "\u9700\u8981\u7535\u529b\u9a71\u52a8\u7684\u4e1c\u897f\n"
        "\u8bf7\u9009\u62e9\u6240\u6709\u7b26\u5408\u4e0a\u6587\u63cf\u8ff0\u7684\u56fe\u7247\uff0c"
        "\u5e76\u62d6\u62fd\u5230\u4e0b\u65b9\n"
        "\u56fe\u7247\u52a0\u8f7d\u5931\u8d25\uff0c\u8bf7\u5237\u65b0\u91cd\u8bd5[5202]\n"
        "\u5237\u65b0\n\u53cd\u9988\n\u63d0\u4ea4"
    )

    state = _doubao_visual_challenge_state_from_text(body_text)

    assert state["reason"] == "doubao_image_challenge_load_failed"
    assert state["imageLoadFailed"] is True
    assert "\u9700\u8981\u7535\u529b\u9a71\u52a8\u7684\u4e1c\u897f" in state["modalText"]
    assert "5202" in state["modalText"]


@pytest.mark.asyncio
async def test_doubao_runtime_snapshot_preserves_visual_challenge_evidence(
    monkeypatch,
    tmp_path,
):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent import guest_executor

    challenge_text = (
        "\u9700\u8981\u7535\u529b\u9a71\u52a8\u7684\u4e1c\u897f\n"
        "\u8bf7\u9009\u62e9\u6240\u6709\u7b26\u5408\u4e0a\u6587\u63cf\u8ff0\u7684\u56fe\u7247\uff0c"
        "\u5e76\u62d6\u62fd\u5230\u4e0b\u65b9\n"
        "\u56fe\u7247\u52a0\u8f7d\u5931\u8d25\uff0c\u8bf7\u5237\u65b0\u91cd\u8bd5[5202]\n"
        "\u5237\u65b0\n\u53cd\u9988\n\u63d0\u4ea4"
    )

    class FakePage:
        async def evaluate(self, script, selector_payload):
            assert "challengeLikeNodes" in script
            return {
                "url": "https://www.doubao.com/chat/",
                "title": "Doubao",
                "readyState": "complete",
                "activeElement": None,
                "bodyText": challenge_text,
                "inputSelectors": [],
                "responseSelectors": [],
                "loginLikeNodes": [],
                "challengeLikeNodes": [
                    {
                        "selector": "[role='dialog']",
                        "count": 1,
                        "visibleCount": 1,
                        "firstText": challenge_text,
                        "firstHtml": "<div role='dialog'>challenge</div>",
                    }
                ],
            }

    monkeypatch.setattr(guest_executor, "SCREENSHOT_DIR", tmp_path)

    path = await guest_executor._save_runtime_snapshot(
        FakePage(),
        184406,
        "doubao_image_challenge_load_failed",
        config={"url": "https://www.doubao.com/chat/", "input_selector": "", "response_selector": ""},
    )

    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["doubaoVisualChallenge"]["reason"] == "doubao_image_challenge_load_failed"
    assert payload["doubaoVisualChallenge"]["imageLoadFailed"] is True
    assert "5202" in payload["doubaoVisualChallenge"]["modalText"]


@pytest.mark.asyncio
async def test_doubao_visual_challenge_overrides_homepage_content_reason(monkeypatch):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    class FakePage:
        async def evaluate(self, script):
            assert "innerText" in script
            return (
                "bestCoffer \u5728\u4fbf\u643a\u5496\u5561\u673a\u54c1\u7c7b\u6709\u54ea\u4e9b\u4f18\u52bf\uff1f\n"
                "\u9700\u8981\u7535\u529b\u9a71\u52a8\u7684\u4e1c\u897f\n"
                "\u8bf7\u9009\u62e9\u6240\u6709\u7b26\u5408\u4e0a\u6587\u63cf\u8ff0\u7684\u56fe\u7247\uff0c"
                "\u5e76\u62d6\u62fd\u5230\u4e0b\u65b9\n"
                "\u56fe\u7247\u52a0\u8f7d\u5931\u8d25\uff0c\u8bf7\u5237\u65b0\u91cd\u8bd5[5202]\n"
                "\u5237\u65b0\n\u53cd\u9988\n\u63d0\u4ea4"
            )

        async def content(self):
            return """
            <main>
              <textarea>bestCoffer</textarea>
              <div class="send-msg-bubble-bg">bestCoffer query</div>
            </main>
            <div role="dialog" class="verify-modal">
              <h2>\u9700\u8981\u7535\u529b\u9a71\u52a8\u7684\u4e1c\u897f</h2>
              <p>\u8bf7\u9009\u62e9\u6240\u6709\u7b26\u5408\u4e0a\u6587\u63cf\u8ff0\u7684\u56fe\u7247\uff0c\u5e76\u62d6\u62fd\u5230\u4e0b\u65b9</p>
              <p>\u56fe\u7247\u52a0\u8f7d\u5931\u8d25\uff0c\u8bf7\u5237\u65b0\u91cd\u8bd5[5202]</p>
              <button>\u5237\u65b0</button><button>\u53cd\u9988</button><button>\u63d0\u4ea4</button>
            </div>
            """

    executor = GuestQueryExecutor()
    executor.last_error_reason = "doubao_homepage_content"

    reason = await executor._prefer_doubao_visual_challenge_reason("doubao", FakePage())

    assert reason == "doubao_image_challenge_load_failed"
    assert executor.last_error_reason == "doubao_image_challenge_load_failed"


@pytest.mark.asyncio
async def test_doubao_auth_state_overrides_visual_challenge_reason(monkeypatch):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    class FakePage:
        async def evaluate(self, script):
            assert "innerText" in script
            return (
                "bestCoffer \u5728\u4fbf\u643a\u5496\u5561\u673a\u54c1\u7c7b\u6709\u54ea\u4e9b\u4f18\u52bf\uff1f\n"
                "\u9700\u8981\u7535\u529b\u9a71\u52a8\u7684\u4e1c\u897f\n"
                "\u8bf7\u9009\u62e9\u6240\u6709\u7b26\u5408\u4e0a\u6587\u63cf\u8ff0\u7684\u56fe\u7247\uff0c"
                "\u5e76\u62d6\u62fd\u5230\u4e0b\u65b9\n"
                "\u56fe\u7247\u52a0\u8f7d\u5931\u8d25\uff0c\u8bf7\u5237\u65b0\u91cd\u8bd5[5202]\n"
                "\u5237\u65b0\n\u53cd\u9988\n\u63d0\u4ea4\n"
                "\u767b\u5f55"
            )

        async def content(self):
            return """
            <main>
              <textarea>bestCoffer</textarea>
              <div class="send-msg-bubble-bg">bestCoffer query</div>
            </main>
            <div role="dialog" class="verify-modal">
              <h2>\u9700\u8981\u7535\u529b\u9a71\u52a8\u7684\u4e1c\u897f</h2>
              <p>\u8bf7\u9009\u62e9\u6240\u6709\u7b26\u5408\u4e0a\u6587\u63cf\u8ff0\u7684\u56fe\u7247\uff0c\u5e76\u62d6\u62fd\u5230\u4e0b\u65b9</p>
              <p>\u56fe\u7247\u52a0\u8f7d\u5931\u8d25\uff0c\u8bf7\u5237\u65b0\u91cd\u8bd5[5202]</p>
              <button>\u5237\u65b0</button><button>\u53cd\u9988</button><button>\u63d0\u4ea4</button>
            </div>
            <header><button class="login-button">\u767b\u5f55</button></header>
            """

    executor = GuestQueryExecutor()

    challenge_reason = await executor._prefer_doubao_visual_challenge_reason(
        "doubao", FakePage()
    )
    auth_reason = await executor._prefer_doubao_auth_failure_reason("doubao", FakePage())

    assert challenge_reason == "doubao_image_challenge_load_failed"
    assert auth_reason == "doubao_not_logged_in"
    assert executor.last_error_reason == "doubao_not_logged_in"


@pytest.mark.asyncio
async def test_doubao_no_response_extraction_path_prefers_auth_over_visual_challenge(
    monkeypatch,
):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent import guest_executor
    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    async def _noop_artifact(*args, **kwargs):
        return None

    monkeypatch.setattr(guest_executor, "_save_html", _noop_artifact)
    monkeypatch.setattr(guest_executor, "_save_screenshot", _noop_artifact)
    monkeypatch.setattr(guest_executor, "_save_runtime_snapshot", _noop_artifact)

    query_text = "bestCoffer portable coffee maker advantages"
    body_text = (
        f"{query_text}\n"
        "\u9700\u8981\u7535\u529b\u9a71\u52a8\u7684\u4e1c\u897f\n"
        "\u8bf7\u9009\u62e9\u6240\u6709\u7b26\u5408\u4e0a\u6587\u63cf\u8ff0\u7684\u56fe\u7247\uff0c"
        "\u5e76\u62d6\u62fd\u5230\u4e0b\u65b9\n"
        "\u56fe\u7247\u52a0\u8f7d\u5931\u8d25\uff0c\u8bf7\u5237\u65b0\u91cd\u8bd5[5202]\n"
        "\u5237\u65b0\n\u53cd\u9988\n\u63d0\u4ea4\n"
        "\u767b\u5f55"
    )

    class FakeInput:
        async def bounding_box(self):
            return None

        async def click(self, *args, **kwargs):
            return None

        async def fill(self, *args, **kwargs):
            return None

        async def evaluate(self, *args, **kwargs):
            return query_text

    class FakeKeyboard:
        async def press(self, *args, **kwargs):
            return None

        async def type(self, *args, **kwargs):
            return None

    class FakeMouse:
        async def move(self, *args, **kwargs):
            return None

    class FakeSubmitHandle:
        def as_element(self):
            return None

    class FakePage:
        url = "https://www.doubao.com/chat/"

        def __init__(self):
            self.keyboard = FakeKeyboard()
            self.mouse = FakeMouse()

        async def wait_for_timeout(self, *args, **kwargs):
            return None

        async def evaluate_handle(self, *args, **kwargs):
            return FakeSubmitHandle()

        async def query_selector(self, *args, **kwargs):
            return None

        async def query_selector_all(self, *args, **kwargs):
            return []

        async def evaluate(self, script, *args):
            script_text = str(script)
            if "document.body?.innerText" in script_text:
                return body_text
            if "queryText" in script_text:
                return True
            return ""

        async def content(self):
            return f"""
            <main>
              <textarea>{query_text}</textarea>
              <div class="send-msg-bubble-bg">{query_text}</div>
            </main>
            <div role="dialog" class="verify-modal">
              <h2>\u9700\u8981\u7535\u529b\u9a71\u52a8\u7684\u4e1c\u897f</h2>
              <p>\u8bf7\u9009\u62e9\u6240\u6709\u7b26\u5408\u4e0a\u6587\u63cf\u8ff0\u7684\u56fe\u7247\uff0c\u5e76\u62d6\u62fd\u5230\u4e0b\u65b9</p>
              <p>\u56fe\u7247\u52a0\u8f7d\u5931\u8d25\uff0c\u8bf7\u5237\u65b0\u91cd\u8bd5[5202]</p>
              <button>\u5237\u65b0</button><button>\u53cd\u9988</button><button>\u63d0\u4ea4</button>
            </div>
            <header><button class="login-button">\u767b\u5f55</button></header>
            """

    executor = GuestQueryExecutor()
    response = await executor._browser_query(
        FakePage(),
        {
            "input_selector": "textarea",
            "response_selector": "[data-testid='receive_message']",
            "submit_button": "",
            "wait_after_submit": 0,
            "login_redirect_domains": [],
            "url": "https://www.doubao.com/chat/",
        },
        query_text,
        "doubao",
        input_el=FakeInput(),
        query_id=184406,
        runtime_events=[],
    )

    assert response == ("", "", [])
    assert executor.last_error_reason == "doubao_not_logged_in"


@pytest.mark.asyncio
async def test_doubao_browser_query_keeps_extracted_answer_with_toolbar_login(
    monkeypatch,
):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent import guest_executor
    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    async def _noop_artifact(*args, **kwargs):
        return None

    monkeypatch.setattr(guest_executor, "_save_html", _noop_artifact)
    monkeypatch.setattr(guest_executor, "_save_screenshot", _noop_artifact)
    monkeypatch.setattr(guest_executor, "_save_runtime_snapshot", _noop_artifact)

    query_text = "bestCoffer portable coffee maker advantages"
    answer_text = (
        "bestCoffer has portable coffee strengths for driving, camping, "
        "and compact outdoor brewing."
    )

    class FakeInput:
        async def bounding_box(self):
            return None

        async def click(self, *args, **kwargs):
            return None

        async def fill(self, *args, **kwargs):
            return None

        async def evaluate(self, *args, **kwargs):
            return query_text

    class FakeKeyboard:
        async def press(self, *args, **kwargs):
            return None

        async def type(self, *args, **kwargs):
            return None

    class FakeMouse:
        async def move(self, *args, **kwargs):
            return None

    class FakeSubmitHandle:
        def as_element(self):
            return None

    class FakeResponseElement:
        async def inner_text(self):
            return answer_text

        async def inner_html(self):
            return "bestCoffer has portable coffee strengths for outdoor brewing."

    class FakePage:
        url = "https://www.doubao.com/chat/"

        def __init__(self):
            self.keyboard = FakeKeyboard()
            self.mouse = FakeMouse()

        async def wait_for_timeout(self, *args, **kwargs):
            return None

        async def wait_for_selector(self, *args, **kwargs):
            raise RuntimeError("not found")

        async def evaluate_handle(self, *args, **kwargs):
            return FakeSubmitHandle()

        async def query_selector(self, selector, *args, **kwargs):
            return None

        async def query_selector_all(self, selector, *args, **kwargs):
            if selector == ".flow-markdown-body":
                return [FakeResponseElement()]
            return []

        async def evaluate(self, script, *args):
            script_text = str(script)
            if "document.body?.innerText" in script_text:
                return f"{query_text}\n{answer_text}\n\u767b\u5f55"
            if "queryText" in script_text:
                return True
            if "return citations" in script_text:
                return []
            return ""

        async def content(self):
            return f"""
            <header>
              <div class="avatar-placeholder"></div>
              <div class="toolbar-action">\u767b\u5f55</div>
            </header>
            <main>
              <div class="send-msg-bubble-bg">{query_text}</div>
              <div class="flow-markdown-body">{answer_text}</div>
            </main>
            """

    executor = GuestQueryExecutor()
    response = await executor._browser_query(
        FakePage(),
        {
            "input_selector": "textarea",
            "response_selector": ".flow-markdown-body",
            "submit_button": "",
            "wait_after_submit": 0,
            "login_redirect_domains": [],
            "url": "https://www.doubao.com/chat/",
        },
        query_text,
        "doubao",
        input_el=FakeInput(),
        query_id=184968,
        runtime_events=[],
    )

    assert response[0] == answer_text
    assert executor.last_error_reason is None


@pytest.mark.asyncio
async def test_doubao_page_load_artifact_failure_preserves_promoted_reason(
    monkeypatch,
):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent import guest_executor
    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    async def _noop_artifact(*args, **kwargs):
        return None

    async def _save_html(page, query_id, suffix=""):
        if suffix == "doubao_image_challenge_load_failed":
            raise RuntimeError("page torn down during artifact save")
        return None

    async def _cleanup_browser_resources(*args, **kwargs):
        return None

    class FakePage:
        url = "https://www.doubao.com/chat/"

        def on(self, *args, **kwargs):
            return None

        async def add_init_script(self, *args, **kwargs):
            return None

        async def goto(self, *args, **kwargs):
            raise RuntimeError("page load failed")

        async def wait_for_selector(self, *args, **kwargs):
            raise RuntimeError("not attached")

        async def wait_for_timeout(self, *args, **kwargs):
            return None

        async def title(self):
            return "Doubao"

        async def evaluate(self, script, *args):
            if "document.body?.innerText" in str(script):
                return (
                    "bestCoffer portable coffee maker advantages\n"
                    "\u9700\u8981\u7535\u529b\u9a71\u52a8\u7684\u4e1c\u897f\n"
                    "\u8bf7\u9009\u62e9\u6240\u6709\u7b26\u5408\u4e0a\u6587\u63cf\u8ff0\u7684\u56fe\u7247\uff0c"
                    "\u5e76\u62d6\u62fd\u5230\u4e0b\u65b9\n"
                    "\u56fe\u7247\u52a0\u8f7d\u5931\u8d25\uff0c\u8bf7\u5237\u65b0\u91cd\u8bd5[5202]\n"
                    "\u5237\u65b0\n\u53cd\u9988\n\u63d0\u4ea4"
                )
            return ""

        async def content(self):
            return """
            <main>
              <textarea>bestCoffer portable coffee maker advantages</textarea>
            </main>
            <div role="dialog" class="verify-modal">
              <h2>\u9700\u8981\u7535\u529b\u9a71\u52a8\u7684\u4e1c\u897f</h2>
              <p>\u8bf7\u9009\u62e9\u6240\u6709\u7b26\u5408\u4e0a\u6587\u63cf\u8ff0\u7684\u56fe\u7247\uff0c\u5e76\u62d6\u62fd\u5230\u4e0b\u65b9</p>
              <p>\u56fe\u7247\u52a0\u8f7d\u5931\u8d25\uff0c\u8bf7\u5237\u65b0\u91cd\u8bd5[5202]</p>
              <button>\u5237\u65b0</button><button>\u53cd\u9988</button><button>\u63d0\u4ea4</button>
            </div>
            """

    class FakeContext:
        async def route(self, *args, **kwargs):
            return None

        async def new_page(self):
            return FakePage()

    class FakeBrowser:
        async def new_context(self, *args, **kwargs):
            return FakeContext()

    class FakeChromium:
        async def launch(self, *args, **kwargs):
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakePlaywrightFactory:
        async def start(self):
            return FakePlaywright()

    monkeypatch.setattr(guest_executor, "async_playwright", FakePlaywrightFactory)
    monkeypatch.setattr(guest_executor, "_save_html", _save_html)
    monkeypatch.setattr(guest_executor, "_save_screenshot", _noop_artifact)
    monkeypatch.setattr(guest_executor, "_save_runtime_snapshot", _noop_artifact)
    monkeypatch.setattr(
        guest_executor, "cleanup_browser_resources", _cleanup_browser_resources
    )

    executor = GuestQueryExecutor()
    response = await executor._execute_once(
        Query(
            id=184863,
            query_text="bestCoffer portable coffee maker advantages",
            target_llm="doubao",
        ),
        {
            "url": "https://www.doubao.com/chat/",
            "input_selector": "textarea",
            "response_selector": "[data-testid='receive_message']",
            "submit_button": "",
            "wait_after_submit": 0,
            "load_wait": 1,
            "login_redirect_domains": [],
            "requires_login": False,
        },
        use_proxy=False,
    )

    assert response is None
    assert executor.last_error_reason == "doubao_image_challenge_load_failed"


def test_doubao_visual_challenge_does_not_penalize_llm_account():
    assert _should_report_account_failure("doubao_visual_challenge") is False
    assert _should_report_account_failure("doubao_image_challenge_load_failed") is False


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
    assert _should_report_account_failure("token_invalidated") is True
    assert _should_report_account_failure("chatgpt_not_logged_in") is True
    assert _should_report_account_failure("chatgpt_auth_redirect") is True
    assert _should_report_account_failure("browser_launch_timeout") is False
    assert _should_report_account_failure("doubao_browser_timeout:response_wait") is False
    assert _should_report_account_failure("doubao_browser_timeout:existing_response") is False
    assert _should_report_account_failure("page_unavailable") is False
    assert _should_report_account_failure("proxy_api_unauthorized") is False
    assert _should_report_account_failure("proxy_global_no_candidate") is False
    assert _should_report_account_failure("soft_time_limit") is False


@pytest.mark.asyncio
async def test_deepseek_account_session_lock_serializes_same_account(monkeypatch):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.tasks import celery_tasks

    class FakeRedisClient:
        store: dict[str, str] = {}

        async def set(self, key, value, *, nx=False, ex=None):
            if nx and key in self.store:
                return False
            self.store[key] = value
            return True

        async def get(self, key):
            return self.store.get(key)

        async def delete(self, key):
            self.store.pop(key, None)
            return 1

        async def aclose(self):
            return None

    monkeypatch.setattr(
        celery_tasks.aioredis,
        "from_url",
        lambda *args, **kwargs: FakeRedisClient(),
    )

    first_started = asyncio.Event()
    release_first = asyncio.Event()
    events: list[str] = []

    async def first_browser_section():
        events.append("first:start")
        first_started.set()
        await release_first.wait()
        events.append("first:end")
        return "first"

    async def second_browser_section():
        events.append("second:start")
        events.append("second:end")
        return "second"

    first = asyncio.create_task(
        celery_tasks._run_with_account_session_lock(
            "deepseek",
            42,
            184414,
            first_browser_section,
            poll_interval_s=0.01,
            wait_timeout_s=1.0,
            lock_ttl_s=30,
        )
    )
    await first_started.wait()
    second = asyncio.create_task(
        celery_tasks._run_with_account_session_lock(
            "deepseek",
            42,
            184417,
            second_browser_section,
            poll_interval_s=0.01,
            wait_timeout_s=1.0,
            lock_ttl_s=30,
        )
    )

    await asyncio.sleep(0.05)
    assert events == ["first:start"]

    release_first.set()

    assert await first == "first"
    assert await second == "second"
    assert events == ["first:start", "first:end", "second:start", "second:end"]


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


def test_account_unavailability_classifies_all_expired_accounts():
    accounts = [
        LLMAccount(
            id=61,
            llm_name="chatgpt",
            status=AccountStatus.EXPIRED.value,
            cookies_json='[{"name":"session"}]',
            query_count_today=0,
            daily_limit=20,
        ),
        LLMAccount(
            id=62,
            llm_name="chatgpt",
            status=AccountStatus.EXPIRED.value,
            cookies_json='[{"name":"session"}]',
            query_count_today=0,
            daily_limit=20,
        ),
    ]

    assert account_unavailable_reason_from_accounts(accounts) == "account_all_expired"


@pytest.mark.asyncio
async def test_proxied_attempt_exhaustion_without_proxy_error_is_no_response(
    monkeypatch,
):
    playwright = types.ModuleType("playwright")
    playwright_async = types.ModuleType("playwright.async_api")
    playwright_async.async_playwright = object
    playwright_async.BrowserContext = object
    playwright_async.ElementHandle = object
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
    monkeypatch.setattr(
        guest_executor_module, "get_current_node", fake_get_current_node
    )
    monkeypatch.setattr(
        guest_executor_module,
        "switch_to_next_node",
        fake_switch_to_next_node,
    )
    monkeypatch.setenv("CLASH_FORCE_GLOBAL_PROXY_ROUTE", "0")

    executor = GuestQueryExecutor(proxy_url="http://proxy.internal:6789")

    result = await executor.execute(Query(query_text="hello", target_llm="chatgpt"))

    assert result is None
    assert attempts == 3
    assert executor.last_error_reason == "no_response"


@pytest.mark.asyncio
async def test_doubao_account_mode_uses_proxy_and_global_route(monkeypatch):
    _install_fake_playwright(monkeypatch)

    import geo_tracker.agent.guest_executor as guest_executor_module
    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    route_calls: list[tuple[str, str]] = []
    execute_calls: list[bool] = []

    async def fake_ensure_global_proxy_route(api_url, group_name):
        route_calls.append((api_url, group_name))
        return types.SimpleNamespace(
            ok=True,
            reason=None,
            global_group="GLOBAL",
            global_now="Ai",
            source_group=group_name,
            source_now="node-a",
            selected_node="Ai",
            changed=False,
        )

    async def fake_execute_once(self, query, config, *, use_proxy):
        execute_calls.append(use_proxy)
        return LLMResponse(query_id=query.id, raw_text="authenticated Doubao answer text")

    monkeypatch.setattr(
        guest_executor_module,
        "ensure_global_proxy_route",
        fake_ensure_global_proxy_route,
    )
    monkeypatch.setattr(GuestQueryExecutor, "_execute_once", fake_execute_once)

    executor = GuestQueryExecutor(
        proxy_url="http://proxy.internal:6789",
        account_cookies='[{"name":"session"}]',
    )

    response = await executor.execute(
        Query(id=184610, query_text="bestCoffer", target_llm="doubao")
    )

    assert response is not None
    assert route_calls == [(guest_executor_module.CLASH_API_URL, guest_executor_module.CLASH_PROXY_GROUP)]
    assert execute_calls == [True]
    assert executor.last_error_reason is None


@pytest.mark.asyncio
async def test_doubao_proxy_route_failure_blocks_before_page_open(monkeypatch):
    _install_fake_playwright(monkeypatch)

    import geo_tracker.agent.guest_executor as guest_executor_module
    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    async def fake_ensure_global_proxy_route(api_url, group_name):
        return types.SimpleNamespace(
            ok=False,
            reason="proxy_global_no_candidate",
            global_group="GLOBAL",
            global_now="DIRECT",
            source_group=group_name,
            source_now=None,
            selected_node=None,
            changed=False,
        )

    async def fake_execute_once(self, query, config, *, use_proxy):
        raise AssertionError("Doubao page should not open when proxy route preflight fails")

    monkeypatch.setattr(
        guest_executor_module,
        "ensure_global_proxy_route",
        fake_ensure_global_proxy_route,
    )
    monkeypatch.setattr(GuestQueryExecutor, "_execute_once", fake_execute_once)

    executor = GuestQueryExecutor(
        proxy_url="http://proxy.internal:6789",
        account_cookies='[{"name":"session"}]',
    )

    response = await executor.execute(
        Query(id=184611, query_text="bestCoffer", target_llm="doubao")
    )

    assert response is None
    assert executor.last_error_reason == "proxy_global_no_candidate"


def _install_fake_playwright(monkeypatch):
    playwright = types.ModuleType("playwright")
    playwright_async = types.ModuleType("playwright.async_api")
    playwright_async.async_playwright = object
    playwright_async.BrowserContext = object
    playwright_async.ElementHandle = object
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

    filled = await executor._fill_plain_text_input(
        page, input_el, "hello doubao", "doubao"
    )

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


class _TaskSessionContext:
    def __init__(self, maker):
        self.maker = maker
        self.session = None

    async def __aenter__(self):
        self.session = self.maker()
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        await self.session.close()
        return False


def test_execute_query_enqueues_chatgpt_new_account_when_pool_has_no_active(
    monkeypatch,
    tmp_path,
):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.tasks import celery_tasks

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'chatgpt-no-active.db'}"
    query_id = 184617

    async def seed_database():
        engine = create_async_engine(db_url, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            session.add(
                Query(
                    id=query_id,
                    target_llm="chatgpt",
                    query_text="coffee brand advantages",
                    status=QueryStatus.PENDING.value,
                )
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(seed_database())

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    async def fake_acquire_query_account(db, query, pool=None):
        return None

    async def fake_diagnose_account_unavailable(db, llm_name):
        assert llm_name == "chatgpt"
        return "account_no_active"

    enqueue_calls: list[dict] = []

    async def fake_should_enqueue_new_account(platform):
        assert platform == "chatgpt"
        return True

    class FakeAutoLogin:
        @staticmethod
        def apply_async(*, kwargs, queue):
            enqueue_calls.append({"kwargs": kwargs, "queue": queue})

    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(
        celery_tasks,
        "acquire_query_account",
        fake_acquire_query_account,
    )
    monkeypatch.setattr(
        celery_tasks,
        "diagnose_account_unavailable",
        fake_diagnose_account_unavailable,
    )
    monkeypatch.setattr(
        celery_tasks,
        "should_enqueue_new_account",
        fake_should_enqueue_new_account,
    )
    monkeypatch.setattr(celery_tasks, "auto_login", FakeAutoLogin)

    result = celery_tasks.execute_query.run(query_id)

    assert result == {
        "query_id": query_id,
        "status": "failed",
        "reason": "account_no_active",
    }
    assert enqueue_calls == [
        {
            "kwargs": {"platform": "chatgpt", "new_account": True},
            "queue": "account_login",
        }
    ]


def test_execute_query_enqueues_doubao_new_account_with_query_handoff(
    monkeypatch,
    tmp_path,
):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.tasks import celery_tasks

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'doubao-no-active.db'}"
    query_id = 184968

    async def seed_database():
        engine = create_async_engine(db_url, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            session.add(
                Query(
                    id=query_id,
                    target_llm="doubao",
                    query_text="bestCoffer advantages",
                    status=QueryStatus.PENDING.value,
                    retry_count=10,
                    retry_reason="manual retry from admin",
                )
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(seed_database())

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    async def fake_acquire_query_account(db, query, pool=None):
        return None

    async def fake_diagnose_account_unavailable(db, llm_name):
        assert llm_name == "doubao"
        return "account_no_active"

    enqueue_calls: list[dict] = []

    async def fake_should_enqueue_new_account(platform):
        assert platform == "doubao"
        return True

    class FakeAutoLogin:
        @staticmethod
        def apply_async(*, kwargs, queue):
            enqueue_calls.append({"kwargs": kwargs, "queue": queue})

    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(
        celery_tasks,
        "acquire_query_account",
        fake_acquire_query_account,
    )
    monkeypatch.setattr(
        celery_tasks,
        "diagnose_account_unavailable",
        fake_diagnose_account_unavailable,
    )
    monkeypatch.setattr(
        celery_tasks,
        "should_enqueue_new_account",
        fake_should_enqueue_new_account,
    )
    monkeypatch.setattr(celery_tasks, "auto_login", FakeAutoLogin)

    result = celery_tasks.execute_query.run(query_id)

    assert result == {
        "query_id": query_id,
        "status": "failed",
        "reason": "account_no_active",
    }
    assert enqueue_calls == [
        {
            "kwargs": {
                "platform": "doubao",
                "new_account": True,
                "query_id": query_id,
            },
            "queue": "account_login",
        }
    ]


def test_auto_login_chatgpt_manual_challenge_does_not_create_account(
    monkeypatch,
    tmp_path,
):
    _install_fake_playwright(monkeypatch)

    import redis.asyncio as aioredis

    from geo_tracker.agent import sms_login
    from geo_tracker.tasks import celery_tasks

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'chatgpt-auto-login.db'}"

    async def seed_database():
        engine = create_async_engine(db_url, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(seed_database())

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    class FakeRedisClient:
        async def exists(self, _key):
            return False

        async def delete(self, _key):
            return 1

        async def set(self, *_args, **_kwargs):
            return True

        async def aclose(self):
            return None

    class FakeChatGPTHandler:
        async def login_or_register(self, **_kwargs):
            return {"status": "failed", "reason": "requires_manual_challenge"}

    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(aioredis, "from_url", lambda *args, **kwargs: FakeRedisClient())
    monkeypatch.setattr(
        sms_login,
        "get_handler",
        lambda platform: FakeChatGPTHandler() if platform == "chatgpt" else None,
    )

    result = celery_tasks.auto_login.run(platform="chatgpt", new_account=True)

    async def count_accounts():
        engine = create_async_engine(db_url, future=True)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            rows = await session.execute(select(LLMAccount))
            count = len(rows.scalars().all())
        await engine.dispose()
        return count

    assert result == {
        "status": "failed",
        "platform": "chatgpt",
        "reason": "requires_manual_challenge",
    }
    assert asyncio.run(count_accounts()) == 0


def test_doubao_auto_login_new_account_requeues_no_active_query(
    monkeypatch,
    tmp_path,
):
    _install_fake_playwright(monkeypatch)

    import redis.asyncio as aioredis

    from geo_tracker.agent import sms_login
    from geo_tracker.tasks import celery_tasks

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'doubao-new-account-handoff.db'}"
    query_id = 184968
    old_account_id = 42

    async def seed_database():
        engine = create_async_engine(db_url, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            session.add_all(
                [
                    LLMAccount(
                        id=old_account_id,
                        llm_name="doubao",
                        status=AccountStatus.EXPIRED.value,
                        cookies_json='[{"name":"stale"}]',
                        query_count_today=5,
                        daily_limit=100,
                        phone_number="17000007065",
                    ),
                    Query(
                        id=query_id,
                        account_id=old_account_id,
                        target_llm="doubao",
                        query_text="bestCoffer advantages",
                        status=QueryStatus.FAILED.value,
                        retry_count=11,
                        retry_reason="account_no_active",
                    ),
                ]
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(seed_database())

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    class FakeRedisClient:
        async def exists(self, _key):
            return False

        async def delete(self, _key):
            return 1

        async def set(self, *_args, **_kwargs):
            return True

        async def aclose(self):
            return None

    class FakeDoubaoHandler:
        async def login_or_register(self, **_kwargs):
            return {
                "cookies": [{"name": "session", "value": "fresh"}],
                "phone": "17000008888",
                "localStorage": {"session": "fresh"},
            }

    requeued: list[dict] = []

    class FakeExecuteQuery:
        @staticmethod
        def apply_async(*, args, queue):
            requeued.append({"args": args, "queue": queue})

    async def fake_release_new_account_lock(_platform, *, failed=False):
        return None

    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(aioredis, "from_url", lambda *args, **kwargs: FakeRedisClient())
    monkeypatch.setattr(
        sms_login,
        "get_handler",
        lambda platform: FakeDoubaoHandler() if platform == "doubao" else None,
    )
    monkeypatch.setattr(celery_tasks, "execute_query", FakeExecuteQuery)
    monkeypatch.setattr(
        celery_tasks,
        "release_new_account_lock",
        fake_release_new_account_lock,
    )

    result = celery_tasks.auto_login.run(
        platform="doubao",
        new_account=True,
        query_id=query_id,
    )

    async def load_state():
        engine = create_async_engine(db_url, future=True)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            query = await session.get(Query, query_id)
            accounts = (await session.execute(select(LLMAccount))).scalars().all()
            new_accounts = [
                account for account in accounts if account.id != old_account_id
            ]
            assert len(new_accounts) == 1
            new_account = new_accounts[0]
            state = {
                "query_status": query.status,
                "query_account_id": query.account_id,
                "retry_count": query.retry_count,
                "retry_reason": query.retry_reason,
                "started_at": query.started_at,
                "finished_at": query.finished_at,
                "latency_ms": query.latency_ms,
                "new_account_id": new_account.id,
                "new_account_status": new_account.status,
                "new_account_has_cookies": bool(new_account.cookies_json),
            }
        await engine.dispose()
        return state

    state = asyncio.run(load_state())
    new_account_id = state["new_account_id"]

    assert result == {
        "status": "success",
        "account_id": new_account_id,
        "phone": "17000008888",
        "requeued_query_id": query_id,
    }
    assert state == {
        "query_status": QueryStatus.PENDING.value,
        "query_account_id": new_account_id,
        "retry_count": 12,
        "retry_reason": f"doubao_new_account_retry:{new_account_id}",
        "started_at": None,
        "finished_at": None,
        "latency_ms": None,
        "new_account_id": new_account_id,
        "new_account_status": AccountStatus.ACTIVE.value,
        "new_account_has_cookies": True,
    }
    assert requeued == [{"args": [query_id], "queue": "llm_doubao"}]


def test_execute_query_persists_doubao_answer_with_generic_toolbar_login(
    monkeypatch, tmp_path
):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.tasks import celery_tasks

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'doubao-auth-gate.db'}"
    query_id = 184595
    account_id = 595

    async def seed_database():
        engine = create_async_engine(db_url, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            session.add_all(
                [
                    LLMAccount(
                        id=account_id,
                        llm_name="doubao",
                        status=AccountStatus.ACTIVE.value,
                        cookies_json='[{"name":"session"}]',
                        query_count_today=1,
                        daily_limit=20,
                    ),
                    Query(
                        id=query_id,
                        target_llm="doubao",
                        query_text="bestCoffer advantages",
                        status=QueryStatus.PENDING.value,
                    ),
                ]
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(seed_database())

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    async def fake_acquire_query_account(db, query, pool=None):
        return LLMAccount(
            id=account_id,
            llm_name="doubao",
            status=AccountStatus.ACTIVE.value,
            cookies_json='[{"name":"session"}]',
        )

    relogin_calls: list[dict] = []

    async def fake_should_enqueue_relogin(enqueued_account_id):
        assert enqueued_account_id == account_id
        return True

    class FakeAutoLogin:
        @staticmethod
        def apply_async(*, kwargs, queue):
            relogin_calls.append({"kwargs": kwargs, "queue": queue})

    class FakeGuestQueryExecutor:
        def __init__(self, *args, **kwargs):
            self.last_error_reason = None

        async def execute(self, query):
            return LLMResponse(
                query_id=query.id,
                raw_text="bestCoffer has portable coffee advantages in outdoor travel.",
                response_html=(
                    "<header><div class='toolbar-action'>\u767b\u5f55</div></header>"
                    "<main><div class='flow-markdown-body'>bestCoffer answer text</div></main>"
                ),
            )

    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(
        celery_tasks, "acquire_query_account", fake_acquire_query_account
    )
    monkeypatch.setattr(celery_tasks, "GuestQueryExecutor", FakeGuestQueryExecutor)
    monkeypatch.setattr(celery_tasks, "should_enqueue_relogin", fake_should_enqueue_relogin)
    monkeypatch.setattr(celery_tasks, "auto_login", FakeAutoLogin)

    result = celery_tasks.execute_query.run(query_id)

    async def load_query_state():
        engine = create_async_engine(db_url, future=True)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            query = await session.get(Query, query_id)
            response_result = await session.execute(
                select(LLMResponse).where(LLMResponse.query_id == query_id)
            )
            response = response_result.scalar_one_or_none()
            account = await session.get(LLMAccount, account_id)
            state = {
                "status": query.status,
                "retry_reason": query.retry_reason,
                "response": response,
                "account_status": account.status,
                "account_cooldown_until": account.cooldown_until,
            }
        await engine.dispose()
        return state

    state = asyncio.run(load_query_state())

    assert result == {
        "query_id": query_id,
        "status": "done",
        "mode": "guest",
        "analysis_enqueued": False,
    }
    assert state["status"] == QueryStatus.DONE.value
    assert state["retry_reason"] is None
    assert state["response"] is not None
    assert (
        state["response"].raw_text
        == "bestCoffer has portable coffee advantages in outdoor travel."
    )
    assert state["account_status"] == AccountStatus.ACTIVE.value
    assert state["account_cooldown_until"] is None
    assert relogin_calls == []


def test_execute_query_converts_doubao_browser_hang_to_stage_timeout_reason(
    monkeypatch,
    tmp_path,
):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.tasks import celery_tasks

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'doubao-browser-timeout.db'}"
    query_id = 184963
    account_id = 963

    async def seed_database():
        engine = create_async_engine(db_url, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            session.add_all(
                [
                    LLMAccount(
                        id=account_id,
                        llm_name="doubao",
                        status=AccountStatus.ACTIVE.value,
                        cookies_json='[{"name":"session"}]',
                        query_count_today=1,
                        daily_limit=20,
                    ),
                    Query(
                        id=query_id,
                        target_llm="doubao",
                        query_text="bestCoffer advantages",
                        status=QueryStatus.PENDING.value,
                    ),
                ]
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(seed_database())

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    async def fake_acquire_query_account(db, query, pool=None):
        return LLMAccount(
            id=account_id,
            llm_name="doubao",
            status=AccountStatus.ACTIVE.value,
            cookies_json='[{"name":"session"}]',
        )

    class FakeGuestQueryExecutor:
        def __init__(self, *args, **kwargs):
            self.last_error_reason = None
            self.execution_stage = "response_wait"

        async def execute(self, query):
            await asyncio.sleep(1)
            return None

    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(celery_tasks, "acquire_query_account", fake_acquire_query_account)
    monkeypatch.setattr(celery_tasks, "GuestQueryExecutor", FakeGuestQueryExecutor)
    monkeypatch.setattr(celery_tasks, "_browser_execution_timeout_seconds", lambda llm: 0.01)

    result = celery_tasks.execute_query.run(query_id)

    async def load_state():
        engine = create_async_engine(db_url, future=True)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            query = await session.get(Query, query_id)
            account = await session.get(LLMAccount, account_id)
            state = {
                "status": query.status,
                "retry_reason": query.retry_reason,
                "query_count_today": account.query_count_today,
            }
        await engine.dispose()
        return state

    state = asyncio.run(load_state())

    assert result == {
        "query_id": query_id,
        "status": "failed",
        "reason": "doubao_browser_timeout:response_wait:0",
    }
    assert state == {
        "status": QueryStatus.FAILED.value,
        "retry_reason": "doubao_browser_timeout:response_wait",
        "query_count_today": 0,
    }


@pytest.mark.asyncio
async def test_preserve_cancellation_evidence_captures_page_state_and_snapshot(
    monkeypatch,
    tmp_path,
):
    """Refs #963: on outer wait_for cancellation, the executor must capture
    URL/title/body and persist a runtime snapshot before the finally-block
    cleanup tears the page down. Without this, operators only see a bare
    `doubao_browser_timeout:<stage>` reason and cannot tell which page state
    the browser was in when it hung."""
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent import guest_executor as guest_executor_mod
    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    class FakePage:
        url = "https://www.doubao.com/chat/?conversation=stuck"

        async def title(self):
            return "Doubao - bestCoffer advantages (stuck)"

        async def evaluate(self, script):
            assert "innerText" in script
            return "bestCoffer advantages content snippet that hung in response_wait stage"

    snapshot_calls: list[dict] = []

    async def fake_snapshot(page, query_id, suffix, **kwargs):
        snapshot_calls.append({"query_id": query_id, "suffix": suffix, **kwargs})
        return tmp_path / f"snapshot_{query_id}.json"

    screenshot_calls: list[dict] = []

    async def fake_screenshot(page, query_id, suffix=""):
        screenshot_calls.append({"query_id": query_id, "suffix": suffix})

    monkeypatch.setattr(guest_executor_mod, "_save_runtime_snapshot", fake_snapshot)
    monkeypatch.setattr(guest_executor_mod, "_save_screenshot", fake_screenshot)

    executor = GuestQueryExecutor()
    executor.execution_stage = "response_wait"

    await executor._preserve_cancellation_evidence(
        FakePage(),
        184968,
        "doubao",
        config={"url": "https://www.doubao.com/chat/", "input_selector": ""},
        runtime_events=[{"kind": "console", "text": "stuck"}],
        proxy_diagnostic={"in_use": True},
        stage="response_wait",
    )

    assert executor.last_page_url == "https://www.doubao.com/chat/?conversation=stuck"
    assert executor.last_page_title == "Doubao - bestCoffer advantages (stuck)"
    assert executor.last_page_body_snippet is not None
    assert "response_wait" in executor.last_page_body_snippet
    assert executor.last_snapshot_path == str(tmp_path / "snapshot_184968.json")
    assert len(snapshot_calls) == 1
    assert snapshot_calls[0]["query_id"] == 184968
    assert snapshot_calls[0]["suffix"] == "doubao_browser_timeout_response_wait"
    assert snapshot_calls[0]["runtime_events"] == [{"kind": "console", "text": "stuck"}]
    assert screenshot_calls == [
        {"query_id": 184968, "suffix": "doubao_browser_timeout_response_wait"}
    ]


def test_execute_query_browser_timeout_logs_page_url_and_title(monkeypatch, tmp_path, caplog):
    """Refs #963 handoff: when the outer wait_for fires, the celery task
    must surface the executor's preserved page URL/title/body snippet on
    the operator log so timeout failures stop reading as a bare reason
    code."""
    _install_fake_playwright(monkeypatch)

    from geo_tracker.tasks import celery_tasks

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'doubao-timeout-evidence.db'}"
    query_id = 184968
    account_id = 968

    async def seed_database():
        engine = create_async_engine(db_url, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            session.add_all(
                [
                    LLMAccount(
                        id=account_id,
                        llm_name="doubao",
                        status=AccountStatus.ACTIVE.value,
                        cookies_json='[{"name":"session"}]',
                        query_count_today=1,
                        daily_limit=20,
                    ),
                    Query(
                        id=query_id,
                        target_llm="doubao",
                        query_text="bestCoffer advantages",
                        status=QueryStatus.PENDING.value,
                    ),
                ]
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(seed_database())

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    async def fake_acquire_query_account(db, query, pool=None):
        return LLMAccount(
            id=account_id,
            llm_name="doubao",
            status=AccountStatus.ACTIVE.value,
            cookies_json='[{"name":"session"}]',
        )

    class FakeGuestQueryExecutor:
        def __init__(self, *args, **kwargs):
            self.last_error_reason = None
            self.execution_stage = "response_wait"
            self.last_page_url = "https://www.doubao.com/chat/?cid=stuck-184968"
            self.last_page_title = "Doubao chat session — stuck"
            self.last_page_body_snippet = "bestCoffer advantages, response panel blank"
            self.last_snapshot_path = "/data/screenshots/query_184968_doubao_browser_timeout_response_wait_1.json"

        async def execute(self, query):
            await asyncio.sleep(1)
            return None

    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(celery_tasks, "acquire_query_account", fake_acquire_query_account)
    monkeypatch.setattr(celery_tasks, "GuestQueryExecutor", FakeGuestQueryExecutor)
    monkeypatch.setattr(celery_tasks, "_browser_execution_timeout_seconds", lambda llm: 0.01)

    with caplog.at_level("WARNING", logger="geo_tracker.tasks.celery_tasks"):
        result = celery_tasks.execute_query.run(query_id)

    assert result == {
        "query_id": query_id,
        "status": "failed",
        "reason": "doubao_browser_timeout:response_wait:0",
    }

    timeout_logs = [
        rec.getMessage()
        for rec in caplog.records
        if "browser execution timed out" in rec.getMessage()
    ]
    assert timeout_logs, "timeout warning should be emitted"
    timeout_msg = timeout_logs[0]
    assert "https://www.doubao.com/chat/?cid=stuck-184968" in timeout_msg
    assert "Doubao chat session" in timeout_msg
    assert "response_wait" in timeout_msg
    assert "query_184968_doubao_browser_timeout_response_wait" in timeout_msg
    assert "bestCoffer advantages, response panel blank" in timeout_msg


def test_doubao_auto_login_new_account_claims_oldest_when_query_id_missing(
    monkeypatch,
    tmp_path,
):
    """Refs #963 handoff: any Doubao new-account success must claim the
    oldest waiting no-account query, not only the one explicitly passed in
    via query_id. Without this, a query that exhausted its bounded
    no-account requeue budget while a sibling auto_login was in flight
    would stay stuck even after a fresh Doubao account became available."""
    _install_fake_playwright(monkeypatch)

    import redis.asyncio as aioredis

    from geo_tracker.agent import sms_login
    from geo_tracker.tasks import celery_tasks

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'doubao-claim-oldest.db'}"
    older_query_id = 184968
    newer_query_id = 184971

    async def seed_database():
        engine = create_async_engine(db_url, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            base_time = datetime(2026, 5, 15, 1, 0, 0)
            session.add_all(
                [
                    Query(
                        id=older_query_id,
                        target_llm="doubao",
                        query_text="bestCoffer advantages older",
                        status=QueryStatus.FAILED.value,
                        retry_count=3,
                        retry_reason="account_no_active",
                        created_at=base_time,
                    ),
                    Query(
                        id=newer_query_id,
                        target_llm="doubao",
                        query_text="bestCoffer advantages newer",
                        status=QueryStatus.FAILED.value,
                        retry_count=3,
                        retry_reason="account_no_active",
                        created_at=base_time + timedelta(minutes=5),
                    ),
                ]
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(seed_database())

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    class FakeRedisClient:
        async def exists(self, _key):
            return False

        async def delete(self, _key):
            return 1

        async def set(self, *_args, **_kwargs):
            return True

        async def aclose(self):
            return None

    class FakeDoubaoHandler:
        async def login_or_register(self, **_kwargs):
            return {
                "cookies": [{"name": "session", "value": "fresh"}],
                "phone": "17000099999",
                "localStorage": {"session": "fresh"},
            }

    requeued: list[dict] = []

    class FakeExecuteQuery:
        @staticmethod
        def apply_async(*, args, queue):
            requeued.append({"args": args, "queue": queue})

    async def fake_release_new_account_lock(_platform, *, failed=False):
        return None

    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(aioredis, "from_url", lambda *args, **kwargs: FakeRedisClient())
    monkeypatch.setattr(
        sms_login,
        "get_handler",
        lambda platform: FakeDoubaoHandler() if platform == "doubao" else None,
    )
    monkeypatch.setattr(celery_tasks, "execute_query", FakeExecuteQuery)
    monkeypatch.setattr(
        celery_tasks,
        "release_new_account_lock",
        fake_release_new_account_lock,
    )

    result = celery_tasks.auto_login.run(
        platform="doubao",
        new_account=True,
        # query_id intentionally omitted to simulate auto_login triggered
        # by a sibling failure (or already in flight when this row failed).
    )

    async def load_state():
        engine = create_async_engine(db_url, future=True)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            older = await session.get(Query, older_query_id)
            newer = await session.get(Query, newer_query_id)
            accounts = (await session.execute(select(LLMAccount))).scalars().all()
            new_accounts = [account for account in accounts]
            state = {
                "older_status": older.status,
                "older_retry_count": older.retry_count,
                "older_retry_reason": older.retry_reason,
                "older_account_id": older.account_id,
                "newer_status": newer.status,
                "newer_retry_count": newer.retry_count,
                "newer_retry_reason": newer.retry_reason,
                "newer_account_id": newer.account_id,
                "new_account_count": len(new_accounts),
                "new_account_status": (
                    new_accounts[0].status if new_accounts else None
                ),
            }
            if new_accounts:
                state["new_account_id"] = new_accounts[0].id
        await engine.dispose()
        return state

    state = asyncio.run(load_state())
    new_account_id = state["new_account_id"]

    assert result == {
        "status": "success",
        "account_id": new_account_id,
        "phone": "17000099999",
        "requeued_query_id": older_query_id,
    }
    # Only the older stuck row was claimed; the newer one stays parked for
    # the next auto_login cycle.
    assert state["older_status"] == QueryStatus.PENDING.value
    assert state["older_retry_count"] == 4
    assert state["older_retry_reason"] == f"doubao_new_account_retry:{new_account_id}"
    assert state["older_account_id"] == new_account_id
    assert state["newer_status"] == QueryStatus.FAILED.value
    assert state["newer_retry_count"] == 3
    assert state["newer_retry_reason"] == "account_no_active"
    assert state["newer_account_id"] is None
    assert state["new_account_status"] == AccountStatus.ACTIVE.value
    assert requeued == [{"args": [older_query_id], "queue": "llm_doubao"}]


def test_doubao_auto_login_new_account_falls_back_when_explicit_query_resolved(
    monkeypatch,
    tmp_path,
):
    """Refs #963 handoff: if the explicit query_id is already resolved (or
    no longer qualifies) by the time auto_login finishes, the fresh
    Doubao account must still claim another stuck no-account query rather
    than wasting the cookie."""
    _install_fake_playwright(monkeypatch)

    import redis.asyncio as aioredis

    from geo_tracker.agent import sms_login
    from geo_tracker.tasks import celery_tasks

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'doubao-fallback-other.db'}"
    explicit_query_id = 184968
    stuck_query_id = 184971

    async def seed_database():
        engine = create_async_engine(db_url, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            base_time = datetime(2026, 5, 15, 2, 0, 0)
            # Explicit query already moved to DONE by a sibling worker
            # (e.g. raced to a different fresh account). It must NOT be
            # mutated again.
            session.add_all(
                [
                    Query(
                        id=explicit_query_id,
                        target_llm="doubao",
                        query_text="bestCoffer advantages explicit",
                        status=QueryStatus.DONE.value,
                        retry_count=2,
                        retry_reason=None,
                        created_at=base_time,
                    ),
                    Query(
                        id=stuck_query_id,
                        target_llm="doubao",
                        query_text="bestCoffer advantages stuck",
                        status=QueryStatus.FAILED.value,
                        retry_count=3,
                        retry_reason="account_no_active",
                        created_at=base_time + timedelta(minutes=10),
                    ),
                ]
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(seed_database())

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    class FakeRedisClient:
        async def exists(self, _key):
            return False

        async def delete(self, _key):
            return 1

        async def set(self, *_args, **_kwargs):
            return True

        async def aclose(self):
            return None

    class FakeDoubaoHandler:
        async def login_or_register(self, **_kwargs):
            return {
                "cookies": [{"name": "session", "value": "fresh"}],
                "phone": "17000077777",
            }

    requeued: list[dict] = []

    class FakeExecuteQuery:
        @staticmethod
        def apply_async(*, args, queue):
            requeued.append({"args": args, "queue": queue})

    async def fake_release_new_account_lock(_platform, *, failed=False):
        return None

    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(aioredis, "from_url", lambda *args, **kwargs: FakeRedisClient())
    monkeypatch.setattr(
        sms_login,
        "get_handler",
        lambda platform: FakeDoubaoHandler() if platform == "doubao" else None,
    )
    monkeypatch.setattr(celery_tasks, "execute_query", FakeExecuteQuery)
    monkeypatch.setattr(
        celery_tasks,
        "release_new_account_lock",
        fake_release_new_account_lock,
    )

    result = celery_tasks.auto_login.run(
        platform="doubao",
        new_account=True,
        query_id=explicit_query_id,
    )

    async def load_state():
        engine = create_async_engine(db_url, future=True)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            explicit = await session.get(Query, explicit_query_id)
            stuck = await session.get(Query, stuck_query_id)
            accounts = (await session.execute(select(LLMAccount))).scalars().all()
            state = {
                "explicit_status": explicit.status,
                "explicit_retry_count": explicit.retry_count,
                "explicit_retry_reason": explicit.retry_reason,
                "explicit_account_id": explicit.account_id,
                "stuck_status": stuck.status,
                "stuck_retry_count": stuck.retry_count,
                "stuck_retry_reason": stuck.retry_reason,
                "stuck_account_id": stuck.account_id,
                "new_account_id": accounts[0].id if accounts else None,
            }
        await engine.dispose()
        return state

    state = asyncio.run(load_state())
    new_account_id = state["new_account_id"]

    assert result == {
        "status": "success",
        "account_id": new_account_id,
        "phone": "17000077777",
        "requeued_query_id": stuck_query_id,
    }
    # The already-DONE explicit row was not touched.
    assert state["explicit_status"] == QueryStatus.DONE.value
    assert state["explicit_retry_count"] == 2
    assert state["explicit_retry_reason"] is None
    assert state["explicit_account_id"] is None
    # The other stuck no-account row was claimed instead.
    assert state["stuck_status"] == QueryStatus.PENDING.value
    assert state["stuck_retry_count"] == 4
    assert state["stuck_retry_reason"] == f"doubao_new_account_retry:{new_account_id}"
    assert state["stuck_account_id"] == new_account_id
    assert requeued == [{"args": [stuck_query_id], "queue": "llm_doubao"}]


def test_doubao_auto_login_success_requeues_failed_query_once(monkeypatch, tmp_path):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.tasks import celery_tasks
    import geo_tracker.agent.sms_login as sms_login

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'doubao-reauth-retry.db'}"
    query_id = 184610
    account_id = 610

    async def seed_database():
        engine = create_async_engine(db_url, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            session.add_all(
                [
                    LLMAccount(
                        id=account_id,
                        llm_name="doubao",
                        status=AccountStatus.EXPIRED.value,
                        cookies_json='[{"name":"stale"}]',
                        query_count_today=1,
                        daily_limit=20,
                        phone_number="18200000000",
                    ),
                    Query(
                        id=query_id,
                        account_id=account_id,
                        target_llm="doubao",
                        query_text="bestCoffer advantages",
                        status=QueryStatus.FAILED.value,
                        retry_count=0,
                        retry_reason="doubao_not_logged_in",
                    ),
                ]
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(seed_database())

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    class FakeHandler:
        async def login_or_register(self, *, existing_cookies=None, phone=None):
            return {
                "cookies": [{"name": "session", "value": "fresh"}],
                "phone": phone,
            }

    requeued: list[dict] = []

    class FakeExecuteQuery:
        @staticmethod
        def apply_async(*, args, queue):
            requeued.append({"args": args, "queue": queue})

    async def fake_release_relogin_lock(_account_id):
        return None

    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(sms_login, "get_handler", lambda _platform: FakeHandler())
    monkeypatch.setattr(celery_tasks, "execute_query", FakeExecuteQuery)
    monkeypatch.setattr(celery_tasks, "release_relogin_lock", fake_release_relogin_lock)
    monkeypatch.setenv("DOUBAO_REAUTH_QUERY_RETRY_MAX", "1")

    result = celery_tasks.auto_login.run(account_id=account_id, query_id=query_id)

    async def load_state():
        engine = create_async_engine(db_url, future=True)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            account = await session.get(LLMAccount, account_id)
            query = await session.get(Query, query_id)
            state = {
                "account_status": account.status,
                "cookies_json": account.cookies_json,
                "query_status": query.status,
                "retry_count": query.retry_count,
                "retry_reason": query.retry_reason,
                "finished_at": query.finished_at,
                "latency_ms": query.latency_ms,
            }
        await engine.dispose()
        return state

    state = asyncio.run(load_state())

    assert result == {
        "status": "success",
        "account_id": account_id,
        "requeued_query_id": query_id,
    }
    assert state["account_status"] == AccountStatus.ACTIVE.value
    assert "fresh" in state["cookies_json"]
    assert state["query_status"] == QueryStatus.PENDING.value
    assert state["retry_count"] == 1
    assert state["retry_reason"] == "doubao_reauth_retry:610"
    assert state["finished_at"] is None
    assert state["latency_ms"] is None
    assert requeued == [{"args": [query_id], "queue": "llm_doubao"}]


def test_doubao_auto_login_default_budget_allows_post_reauth_retry_for_historical_row(
    monkeypatch,
    tmp_path,
):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.tasks import celery_tasks
    import geo_tracker.agent.sms_login as sms_login

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'doubao-reauth-historical-row.db'}"
    query_id = 184968
    account_id = 42

    async def seed_database():
        engine = create_async_engine(db_url, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            session.add_all(
                [
                    LLMAccount(
                        id=account_id,
                        llm_name="doubao",
                        status=AccountStatus.EXPIRED.value,
                        cookies_json='[{"name":"stale"}]',
                        query_count_today=3,
                        daily_limit=100,
                        phone_number="17000007065",
                    ),
                    Query(
                        id=query_id,
                        account_id=account_id,
                        target_llm="doubao",
                        query_text="bestCoffer advantages",
                        status=QueryStatus.FAILED.value,
                        retry_count=9,
                        retry_reason="doubao_not_logged_in",
                    ),
                ]
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(seed_database())

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    class FakeHandler:
        async def login_or_register(self, *, existing_cookies=None, phone=None):
            return {
                "cookies": [{"name": "session", "value": "fresh"}],
                "phone": phone,
            }

    requeued: list[dict] = []

    class FakeExecuteQuery:
        @staticmethod
        def apply_async(*, args, queue):
            requeued.append({"args": args, "queue": queue})

    async def fake_release_relogin_lock(_account_id):
        return None

    monkeypatch.delenv("DOUBAO_REAUTH_QUERY_RETRY_MAX", raising=False)
    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(sms_login, "get_handler", lambda _platform: FakeHandler())
    monkeypatch.setattr(celery_tasks, "execute_query", FakeExecuteQuery)
    monkeypatch.setattr(celery_tasks, "release_relogin_lock", fake_release_relogin_lock)

    result = celery_tasks.auto_login.run(account_id=account_id, query_id=query_id)

    async def load_query():
        engine = create_async_engine(db_url, future=True)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            query = await session.get(Query, query_id)
            state = {
                "status": query.status,
                "retry_count": query.retry_count,
                "retry_reason": query.retry_reason,
            }
        await engine.dispose()
        return state

    state = asyncio.run(load_query())

    assert result == {
        "status": "success",
        "account_id": account_id,
        "requeued_query_id": query_id,
    }
    assert state == {
        "status": QueryStatus.PENDING.value,
        "retry_count": 10,
        "retry_reason": "doubao_reauth_retry:42",
    }
    assert requeued == [{"args": [query_id], "queue": "llm_doubao"}]


def test_doubao_auto_login_default_budget_allows_current_row_after_manual_retry(
    monkeypatch,
    tmp_path,
):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.tasks import celery_tasks
    import geo_tracker.agent.sms_login as sms_login

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'doubao-reauth-current-row.db'}"
    query_id = 184968
    account_id = 42

    async def seed_database():
        engine = create_async_engine(db_url, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            session.add_all(
                [
                    LLMAccount(
                        id=account_id,
                        llm_name="doubao",
                        status=AccountStatus.EXPIRED.value,
                        cookies_json='[{"name":"stale"}]',
                        query_count_today=4,
                        daily_limit=100,
                        phone_number="17000007065",
                    ),
                    Query(
                        id=query_id,
                        account_id=account_id,
                        target_llm="doubao",
                        query_text="bestCoffer advantages",
                        status=QueryStatus.FAILED.value,
                        retry_count=10,
                        retry_reason="doubao_not_logged_in",
                    ),
                ]
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(seed_database())

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    class FakeHandler:
        async def login_or_register(self, *, existing_cookies=None, phone=None):
            return {
                "cookies": [{"name": "session", "value": "fresh"}],
                "phone": phone,
            }

    requeued: list[dict] = []

    class FakeExecuteQuery:
        @staticmethod
        def apply_async(*, args, queue):
            requeued.append({"args": args, "queue": queue})

    async def fake_release_relogin_lock(_account_id):
        return None

    monkeypatch.delenv("DOUBAO_REAUTH_QUERY_RETRY_MAX", raising=False)
    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(sms_login, "get_handler", lambda _platform: FakeHandler())
    monkeypatch.setattr(celery_tasks, "execute_query", FakeExecuteQuery)
    monkeypatch.setattr(celery_tasks, "release_relogin_lock", fake_release_relogin_lock)

    result = celery_tasks.auto_login.run(account_id=account_id, query_id=query_id)

    async def load_query():
        engine = create_async_engine(db_url, future=True)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            query = await session.get(Query, query_id)
            state = {
                "status": query.status,
                "retry_count": query.retry_count,
                "retry_reason": query.retry_reason,
            }
        await engine.dispose()
        return state

    state = asyncio.run(load_query())

    assert result == {
        "status": "success",
        "account_id": account_id,
        "requeued_query_id": query_id,
    }
    assert state == {
        "status": QueryStatus.PENDING.value,
        "retry_count": 11,
        "retry_reason": "doubao_reauth_retry:42",
    }
    assert requeued == [{"args": [query_id], "queue": "llm_doubao"}]


def test_doubao_auto_login_reauth_requeue_ignores_manual_retry_count(
    monkeypatch,
    tmp_path,
):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.tasks import celery_tasks
    import geo_tracker.agent.sms_login as sms_login

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'doubao-reauth-manual-count.db'}"
    query_id = 184968
    account_id = 42

    async def seed_database():
        engine = create_async_engine(db_url, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            session.add_all(
                [
                    LLMAccount(
                        id=account_id,
                        llm_name="doubao",
                        status=AccountStatus.EXPIRED.value,
                        cookies_json='[{"name":"stale"}]',
                        query_count_today=5,
                        daily_limit=100,
                        phone_number="17000007065",
                    ),
                    Query(
                        id=query_id,
                        account_id=account_id,
                        target_llm="doubao",
                        query_text="bestCoffer advantages",
                        status=QueryStatus.FAILED.value,
                        retry_count=11,
                        retry_reason="doubao_not_logged_in",
                    ),
                ]
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(seed_database())

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    class FakeHandler:
        async def login_or_register(self, *, existing_cookies=None, phone=None):
            return {
                "cookies": [{"name": "session", "value": "fresh"}],
                "phone": phone,
            }

    requeued: list[dict] = []

    class FakeExecuteQuery:
        @staticmethod
        def apply_async(*, args, queue):
            requeued.append({"args": args, "queue": queue})

    async def fake_release_relogin_lock(_account_id):
        return None

    monkeypatch.delenv("DOUBAO_REAUTH_QUERY_RETRY_MAX", raising=False)
    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(sms_login, "get_handler", lambda _platform: FakeHandler())
    monkeypatch.setattr(celery_tasks, "execute_query", FakeExecuteQuery)
    monkeypatch.setattr(celery_tasks, "release_relogin_lock", fake_release_relogin_lock)

    result = celery_tasks.auto_login.run(account_id=account_id, query_id=query_id)

    async def load_query():
        engine = create_async_engine(db_url, future=True)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            query = await session.get(Query, query_id)
            state = {
                "status": query.status,
                "retry_count": query.retry_count,
                "retry_reason": query.retry_reason,
            }
        await engine.dispose()
        return state

    state = asyncio.run(load_query())

    assert result == {
        "status": "success",
        "account_id": account_id,
        "requeued_query_id": query_id,
    }
    assert state == {
        "status": QueryStatus.PENDING.value,
        "retry_count": 12,
        "retry_reason": "doubao_reauth_retry:42",
    }
    assert requeued == [{"args": [query_id], "queue": "llm_doubao"}]


def test_doubao_auto_login_does_not_requeue_when_reauth_retry_disabled(
    monkeypatch,
    tmp_path,
):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.tasks import celery_tasks
    import geo_tracker.agent.sms_login as sms_login

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'doubao-reauth-retry-budget.db'}"
    query_id = 184611
    account_id = 611

    async def seed_database():
        engine = create_async_engine(db_url, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            session.add_all(
                [
                    LLMAccount(
                        id=account_id,
                        llm_name="doubao",
                        status=AccountStatus.EXPIRED.value,
                        cookies_json='[{"name":"stale"}]',
                        daily_limit=20,
                        phone_number="18200000000",
                    ),
                    Query(
                        id=query_id,
                        account_id=account_id,
                        target_llm="doubao",
                        query_text="bestCoffer advantages",
                        status=QueryStatus.FAILED.value,
                        retry_count=1,
                        retry_reason="doubao_not_logged_in",
                    ),
                ]
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(seed_database())

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    class FakeHandler:
        async def login_or_register(self, *, existing_cookies=None, phone=None):
            return {"cookies": [{"name": "session", "value": "fresh"}]}

    requeued: list[dict] = []

    class FakeExecuteQuery:
        @staticmethod
        def apply_async(*, args, queue):
            requeued.append({"args": args, "queue": queue})

    async def fake_release_relogin_lock(_account_id):
        return None

    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(sms_login, "get_handler", lambda _platform: FakeHandler())
    monkeypatch.setattr(celery_tasks, "execute_query", FakeExecuteQuery)
    monkeypatch.setattr(celery_tasks, "release_relogin_lock", fake_release_relogin_lock)
    monkeypatch.setenv("DOUBAO_REAUTH_QUERY_RETRY_MAX", "0")

    result = celery_tasks.auto_login.run(account_id=account_id, query_id=query_id)

    async def load_query():
        engine = create_async_engine(db_url, future=True)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            query = await session.get(Query, query_id)
            state = {
                "status": query.status,
                "retry_count": query.retry_count,
                "retry_reason": query.retry_reason,
            }
        await engine.dispose()
        return state

    state = asyncio.run(load_query())

    assert result == {"status": "success", "account_id": account_id}
    assert state == {
        "status": QueryStatus.FAILED.value,
        "retry_count": 1,
        "retry_reason": "doubao_not_logged_in",
    }
    assert requeued == []


def test_execute_query_rejects_chatgpt_login_page_and_expires_account(
    monkeypatch,
    tmp_path,
):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.tasks import celery_tasks

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'chatgpt-login-page.db'}"
    query_id = 184615
    account_id = 615

    async def seed_database():
        engine = create_async_engine(db_url, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            session.add_all(
                [
                    LLMAccount(
                        id=account_id,
                        llm_name="chatgpt",
                        status=AccountStatus.ACTIVE.value,
                        cookies_json='[{"name":"session"}]',
                        query_count_today=1,
                        daily_limit=20,
                    ),
                    Query(
                        id=query_id,
                        target_llm="chatgpt",
                        query_text="coffee brand advantages",
                        status=QueryStatus.PENDING.value,
                    ),
                ]
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(seed_database())

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    async def fake_acquire_query_account(db, query, pool=None):
        return LLMAccount(
            id=account_id,
            llm_name="chatgpt",
            status=AccountStatus.ACTIVE.value,
            cookies_json='[{"name":"session"}]',
        )

    class FakeGuestQueryExecutor:
        def __init__(self, *args, **kwargs):
            self.last_error_reason = None

        async def execute(self, query):
            return LLMResponse(
                query_id=query.id,
                raw_text=(
                    "Sign in to ChatGPT. Continue with Google. "
                    "Continue with Microsoft. Continue with Apple."
                ),
            )

    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(celery_tasks, "acquire_query_account", fake_acquire_query_account)
    monkeypatch.setattr(celery_tasks, "GuestQueryExecutor", FakeGuestQueryExecutor)

    result = celery_tasks.execute_query.run(query_id)

    async def load_query_state():
        engine = create_async_engine(db_url, future=True)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            query = await session.get(Query, query_id)
            response_result = await session.execute(
                select(LLMResponse).where(LLMResponse.query_id == query_id)
            )
            response = response_result.scalar_one_or_none()
            account = await session.get(LLMAccount, account_id)
            state = {
                "status": query.status,
                "retry_reason": query.retry_reason,
                "response": response,
                "account_status": account.status,
                "account_cooldown_until": account.cooldown_until,
            }
        await engine.dispose()
        return state

    state = asyncio.run(load_query_state())

    assert result == {
        "query_id": query_id,
        "status": "failed",
        "reason": "chatgpt_auth_redirect",
    }
    assert state["status"] == QueryStatus.FAILED.value
    assert state["retry_reason"] == "chatgpt_auth_redirect"
    assert state["response"] is None
    assert state["account_status"] == AccountStatus.EXPIRED.value
    assert state["account_cooldown_until"] is None


def test_execute_query_cools_doubao_account_on_page_unavailable(monkeypatch, tmp_path):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.tasks import celery_tasks

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'doubao-page-unavailable.db'}"
    query_id = 184610
    account_id = 610

    async def seed_database():
        engine = create_async_engine(db_url, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            session.add_all(
                [
                    LLMAccount(
                        id=account_id,
                        llm_name="doubao",
                        status=AccountStatus.ACTIVE.value,
                        cookies_json='[{"name":"session"}]',
                        query_count_today=1,
                        daily_limit=20,
                    ),
                    Query(
                        id=query_id,
                        target_llm="doubao",
                        query_text="bestCoffer advantages",
                        status=QueryStatus.PENDING.value,
                    ),
                ]
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(seed_database())

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    async def fake_acquire_query_account(db, query, pool=None):
        return LLMAccount(
            id=account_id,
            llm_name="doubao",
            status=AccountStatus.ACTIVE.value,
            cookies_json='[{"name":"session"}]',
        )

    class FakeGuestQueryExecutor:
        def __init__(self, *args, **kwargs):
            self.last_error_reason = "page_unavailable"

        async def execute(self, query):
            return None

    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(celery_tasks, "acquire_query_account", fake_acquire_query_account)
    monkeypatch.setattr(celery_tasks, "GuestQueryExecutor", FakeGuestQueryExecutor)

    result = celery_tasks.execute_query.run(query_id)

    async def load_query_state():
        engine = create_async_engine(db_url, future=True)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            query = await session.get(Query, query_id)
            response_result = await session.execute(
                select(LLMResponse).where(LLMResponse.query_id == query_id)
            )
            response = response_result.scalar_one_or_none()
            account = await session.get(LLMAccount, account_id)
            state = {
                "status": query.status,
                "retry_reason": query.retry_reason,
                "response": response,
                "account_status": account.status,
                "account_cooldown_until": account.cooldown_until,
            }
        await engine.dispose()
        return state

    state = asyncio.run(load_query_state())

    assert result == {
        "query_id": query_id,
        "status": "failed",
        "reason": "page_unavailable:0",
    }
    assert state["status"] == QueryStatus.FAILED.value
    assert state["retry_reason"] == "page_unavailable"
    assert state["response"] is None
    assert state["account_status"] == AccountStatus.COOLDOWN.value
    assert state["account_cooldown_until"] is not None


def test_execute_query_does_not_loop_auto_login_after_post_reauth_failure(
    monkeypatch,
    tmp_path,
):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.tasks import celery_tasks

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'doubao-post-reauth-failed.db'}"
    query_id = 184968
    account_id = 42

    async def seed_database():
        engine = create_async_engine(db_url, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            session.add_all(
                [
                    LLMAccount(
                        id=account_id,
                        llm_name="doubao",
                        status=AccountStatus.ACTIVE.value,
                        cookies_json='[{"name":"session"}]',
                        query_count_today=1,
                        daily_limit=20,
                    ),
                    Query(
                        id=query_id,
                        account_id=account_id,
                        target_llm="doubao",
                        query_text="bestCoffer advantages",
                        status=QueryStatus.PENDING.value,
                        retry_count=12,
                        retry_reason="doubao_reauth_retry:42",
                    ),
                ]
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(seed_database())

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    async def fake_acquire_query_account(db, query, pool=None):
        return LLMAccount(
            id=account_id,
            llm_name="doubao",
            status=AccountStatus.ACTIVE.value,
            cookies_json='[{"name":"session"}]',
        )

    class FakeGuestQueryExecutor:
        def __init__(self, *args, **kwargs):
            self.last_error_reason = "doubao_not_logged_in"

        async def execute(self, query):
            return None

    relogin_requests: list[dict] = []

    class FakeAutoLogin:
        @staticmethod
        def apply_async(*, kwargs, queue):
            relogin_requests.append({"kwargs": kwargs, "queue": queue})

    async def fake_should_enqueue_relogin(_account_id):
        return True

    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(celery_tasks, "acquire_query_account", fake_acquire_query_account)
    monkeypatch.setattr(celery_tasks, "GuestQueryExecutor", FakeGuestQueryExecutor)
    monkeypatch.setattr(celery_tasks, "auto_login", FakeAutoLogin)
    monkeypatch.setattr(celery_tasks, "should_enqueue_relogin", fake_should_enqueue_relogin)

    result = celery_tasks.execute_query.run(query_id)

    async def load_state():
        engine = create_async_engine(db_url, future=True)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            query = await session.get(Query, query_id)
            account = await session.get(LLMAccount, account_id)
            state = {
                "query_status": query.status,
                "retry_reason": query.retry_reason,
                "account_status": account.status,
            }
        await engine.dispose()
        return state

    state = asyncio.run(load_state())

    assert result == {
        "query_id": query_id,
        "status": "failed",
        "reason": "doubao_post_reauth_doubao_not_logged_in:0",
    }
    assert state == {
        "query_status": QueryStatus.FAILED.value,
        "retry_reason": "doubao_post_reauth_doubao_not_logged_in",
        "account_status": AccountStatus.EXPIRED.value,
    }
    assert relogin_requests == []


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


# Refs #928 / #930: regression coverage for Doubao no_input being overwritten
# as browser_timeout when an artifact-save call inside the no_input branch
# raises a Playwright TimeoutError and bubbles to the outer except.
def test_resolve_execution_failure_reason_preserves_no_input_over_timeout_exception():
    exc = TimeoutError("Page.evaluate: Timeout 30000ms exceeded.")
    assert resolve_execution_failure_reason(exc, prior="no_input") == "no_input"


def test_resolve_execution_failure_reason_preserves_other_specific_reasons():
    exc = TimeoutError("Page.evaluate: Timeout 30000ms exceeded.")
    assert (
        resolve_execution_failure_reason(exc, prior="page_unavailable")
        == "page_unavailable"
    )
    assert (
        resolve_execution_failure_reason(exc, prior="cookies_expired")
        == "cookies_expired"
    )
    assert (
        resolve_execution_failure_reason(exc, prior="doubao_not_logged_in")
        == "doubao_not_logged_in"
    )


def test_resolve_execution_failure_reason_falls_back_to_classifier_when_no_prior():
    timeout_exc = TimeoutError("Page.evaluate: Timeout 30000ms exceeded.")
    assert resolve_execution_failure_reason(timeout_exc, prior=None) == "browser_timeout"
    assert resolve_execution_failure_reason(timeout_exc, prior="") == "browser_timeout"

    other_exc = RuntimeError("Connection reset")
    assert (
        resolve_execution_failure_reason(other_exc, prior=None) == "browser_exception"
    )


def test_classify_execution_failure_unchanged_for_existing_callers():
    assert (
        classify_execution_failure(TimeoutError("Timeout 90000ms exceeded."))
        == "browser_timeout"
    )
    assert (
        classify_execution_failure(RuntimeError("write EPIPE")) == "browser_epipe"
    )
    assert (
        classify_execution_failure(RuntimeError("plain failure"))
        == "browser_exception"
    )


# Refs #928: the AccountSessionLockTimeout caught at celery_tasks.py used to
# hardcode failure_reason="browser_timeout", masking Redis session-lock
# contention as if it were a Playwright timeout. The new value
# "scraper_session_lock_timeout" is reserved as infrastructure-class so it
# still bypasses account-level failure reporting (no false account flags).
def test_scraper_session_lock_timeout_is_infrastructure_reason():
    from geo_tracker.tasks.query_failure import (
        INFRASTRUCTURE_FAILURE_REASONS,
        _should_report_account_failure,
    )

    assert "scraper_session_lock_timeout" in INFRASTRUCTURE_FAILURE_REASONS
    # Infrastructure reasons MUST NOT trigger account-level failure escalation;
    # otherwise a worker pool / lock contention storm would erroneously cool
    # down or expire accounts.
    assert _should_report_account_failure("scraper_session_lock_timeout") is False
    # And the old name is still infrastructure (unchanged for unrelated callers).
    assert _should_report_account_failure("browser_timeout") is False


def test_account_session_lock_timeout_celery_handler_uses_distinct_reason():
    # We do not import celery_tasks end-to-end here (it requires Celery + Redis
    # + Playwright import chain that the unit-test layer does not have); but we
    # can pin the source contract that the AccountSessionLockTimeout handler
    # writes a value distinguishable from generic browser_timeout, so admin
    # Tracker and the #930 diagnostic recipe can separate the two failure modes.
    source_path = (
        Path(__file__).resolve().parent.parent / "tasks" / "celery_tasks.py"
    )
    source = source_path.read_text(encoding="utf-8")
    # The exact assignment line — drift here means the rename was reverted.
    assert 'failure_reason = "scraper_session_lock_timeout"' in source
    # And the misleading hardcoded "browser_timeout" assignment is gone.
    assert 'failure_reason = "browser_timeout"' not in source


# Refs PR #933 Codex review (P2): execute() retries _execute_once across
# proxy-rotation attempts without resetting self.last_error_reason between
# attempts. resolve_execution_failure_reason preserves any prior value, so
# attempt N raising a fresh Playwright exception with no in-attempt reason
# set would otherwise inherit attempt N-1's stale reason and mask the real
# current-attempt failure. _execute_once must reset the field at entry.
def test_execute_once_resets_last_error_reason_at_entry():
    source_path = (
        Path(__file__).resolve().parent.parent / "agent" / "guest_executor.py"
    )
    source = source_path.read_text(encoding="utf-8")
    sig_idx = source.index("async def _execute_once(")
    body_until_first_try = source[sig_idx : source.index("try:", sig_idx)]
    # The reset must appear before any other self.last_error_reason write or
    # before any operation that may set the field via inner branches.
    assert "self.last_error_reason = None" in body_until_first_try, (
        "_execute_once must reset self.last_error_reason at entry to prevent "
        "stale reasons from a prior retry attempt leaking through "
        "resolve_execution_failure_reason."
    )
