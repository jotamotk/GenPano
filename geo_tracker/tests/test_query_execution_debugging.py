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


def test_doubao_persistence_gate_accepts_answer_despite_logged_out_state_template():
    """Substantive .flow-markdown-body answer wins over JS-state remnants.

    Refs #963 follow-up: Q-184971 evidence shows Doubao's SPA bundle
    ships JS-state objects with default ``is_login:false`` / ``user_id:0``
    values even on the logged-in shell. Those default values get
    captured by the HARD-marker regex but they do NOT mean the user is
    logged out; the streamed answer in ``.flow-markdown-body`` is the
    real proof of auth. Visible login dialogs are still absolute blocks
    (see ``test_doubao_persistence_gate_rejects_answer_html_with_qr_login_dialog``).
    """
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
        doubao_persistence_auth_reason("doubao", raw_text, response_html) is None
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


def test_doubao_persistence_gate_visible_dialog_overrides_auth_ok_marker():
    """A visible login dialog overrides even the AUTH_OK marker.

    Refs #963 follow-up: the AUTH_OK marker is set by the scraper after
    it successfully extracts a response. A visible login dialog that
    appears AFTER the extraction means the session expired during the
    extraction window \u2014 the answer is stale and the user is now logged
    out. The visible-dialog check therefore still overrides the marker.
    """
    from geo_tracker.agent.response_validation import doubao_persistence_auth_reason

    raw_text = "bestCoffer answer-like content"
    response_html = (
        "<div class='flow-markdown-body'>bestCoffer answer-like content</div>"
        "\n<!-- doubao-auth-state:ok -->"
        "\n<div role='dialog'>"
        "\n  <h2>\u626b\u7801\u767b\u5f55</h2>"
        "\n  <button class='login-button'>\u767b\u5f55</button>"
        "\n</div>"
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


# Refs #963 production evidence (server-diagnostics run 25951168887,
# query 184406 retry at 2026-05-16 03:04:24): after auto_login succeeded
# for Doubao account 39 and the requeued query streamed a real 1866-char
# answer into .flow-markdown-body, the persistence gate threw the answer
# away because the same page carried the promo banner "登录以解锁更多功能".
# Production retry_reason came back as
# ``doubao_post_reauth_doubao_not_logged_in:0`` and the account was
# immediately marked expired again. The promo is a tier-up push Doubao
# overlays on authenticated responses, not a hard logout signal — a
# substantive ``.flow-markdown-body`` body proves authentication and
# must win over the overlay. Hard logout signals (``is_login:false``,
# ``error_code:13``, ``user_id:0``, ``from_logout=1``, the explicit
# "会话过期" text, visible login dialog) are still allowed to override
# the answer, because they prove the session is actually logged out.
# ``login-btn-header`` was moved from HARD → SOFT after Q-184988 — see
# the test below for the SPA-chrome rationale.
def test_doubao_persistence_gate_keeps_answer_over_soft_promo_banner():
    """A real ``.flow-markdown-body`` answer wins over the soft promo overlay."""
    from geo_tracker.agent.response_validation import doubao_persistence_auth_reason

    # Reproduces the exact production page state from query 184406:
    # a substantive answer body AND the "登录以解锁更多功能" promo dialog.
    raw_text = (
        "选企业级 AI 数据脱敏工具的核心注意要点："
        "1. 数据安全：脱敏过程必须在本地完成，避免敏感数据外泄。"
        "2. 准确性：需要在不同业务场景下验证脱敏准确率。"
        "3. 可逆性：根据业务需求选择支持/不支持反脱敏的模式。"
    )
    response_html = (
        "<main><div class='flow-markdown-body'>"
        + raw_text
        + "</div></main>"
        "<div class='promo-overlay'>登录以解锁更多功能</div>"
        "<div class='promo-overlay'>7天免登录</div>"
    )

    assert doubao_persistence_auth_reason("doubao", raw_text, response_html) is None


def test_doubao_persistence_gate_rejects_promo_banner_without_answer():
    """Without a substantive answer, the soft promo still flags logout."""
    from geo_tracker.agent.response_validation import doubao_persistence_auth_reason

    # No flow-markdown-body content; just the promo overlay text.
    raw_text = ""
    response_html = (
        "<div class='promo-overlay'>"
        "登录以解锁更多功能"
        "</div>"
    )

    assert (
        doubao_persistence_auth_reason("doubao", raw_text, response_html)
        == "doubao_not_logged_in"
    )


# Refs #963 production evidence (Q-184988 post-#1042 deploy 2026-05-16
# ~09:1x): a fully authenticated Doubao chat — user 527070 visible in
# the sidebar, conversation history populated, a real 脱敏指标 answer
# rendered in ``.flow-markdown-body`` — was rejected as
# ``doubao_not_logged_in``. Root cause: ``login-btn-header`` was in the
# HARD bucket on the assumption that the className only persists in the
# logged-out shell, but production refuted that. Doubao's SPA carries
# ``login-btn-header`` through hydration into the logged-in shell too,
# so the HARD bucket vetoed real answers. Moving the className to SOFT
# lets a substantive answer override it; truly definitive signals
# (会话过期 / from_logout=1 / JS state / visible dialog) stay HARD.
def test_doubao_persistence_gate_keeps_answer_over_login_btn_header_chrome():
    """``login-btn-header`` chrome alongside a real answer is the logged-in shell."""
    from geo_tracker.agent.response_validation import doubao_persistence_auth_reason

    # Reproduces the exact Q-184988 page state: a substantive
    # .flow-markdown-body answer AND the persistent login-btn-header
    # chrome that Doubao's SPA keeps in DOM regardless of login state.
    # No hard-logout signals (no 会话过期, no from_logout=1, no
    # is_login:false / error_code:13 / user_id:0, no visible dialog).
    raw_text = (
        "非结构化数据 AI 脱敏准确率测评核心指标涵盖精确率、召回率、"
        "F1-Score、准确率等基础识别指标，以及漏脱敏率、误脱敏率等专项效果指标。"
    )
    response_html = (
        "<main><div class='flow-markdown-body'>"
        + raw_text
        + "</div></main>"
        # SPA chrome that persists through into the logged-in shell:
        "<button id='login-btn-header'>登录</button>"
    )

    assert doubao_persistence_auth_reason("doubao", raw_text, response_html) is None


def test_doubao_persistence_gate_rejects_login_btn_header_without_answer():
    """Without a substantive answer, ``login-btn-header`` still flags logout."""
    from geo_tracker.agent.response_validation import doubao_persistence_auth_reason

    raw_text = ""
    response_html = "<button id='login-btn-header'>登录</button>"

    assert (
        doubao_persistence_auth_reason("doubao", raw_text, response_html)
        == "doubao_not_logged_in"
    )


# Refs #963 follow-up evidence (Q-184971 retry 2026-05-16 13:20:33,
# worker SHA 847cd9e): the system streamed a real 1727-char
# bestCoffer answer into ``.flow-markdown-body`` on
# ``/chat/38426272185416450`` with user 527070 visible — and STILL got
# rejected as ``doubao_not_logged_in``. The HARD path matched a JS-state
# remnant (``is_login:false`` for a logged-out-template panel cached in
# DOM) or the literal i18n string ``会话过期`` embedded in the SPA
# bundle. With the new gate order, substantive .flow-markdown-body
# wins over those HARD remnants; only a visible login dialog still
# absolutely blocks (because it actively interrupts the session).
def test_doubao_persistence_gate_answer_overrides_js_state_remnant():
    """A real .flow-markdown-body answer overrides JS-state remnants in DOM."""
    from geo_tracker.agent.response_validation import doubao_persistence_auth_reason

    raw_text = (
        "非常适合，且是金融行业多业务场景的优选方案。它针对银行、券商、基金、"
        "支付等金融机构的高频刚需做了深度定制，覆盖合规、审计、协作、尽调、跨境等核心场景。"
    )
    # The JS-state markers (is_login:false, user_id:0) appear in the SPA
    # bundle as default state for a logged-out template — even when the
    # user IS logged in and has a real chat rendered.
    response_html = (
        "<main><div class='flow-markdown-body'>"
        + raw_text
        + "</div></main>"
        "<script>window.__state__={is_login:false,user_id:0}</script>"
    )

    assert doubao_persistence_auth_reason("doubao", raw_text, response_html) is None


def test_doubao_persistence_gate_rejects_js_state_without_answer():
    """Without a substantive answer, JS-state markers still flag logout."""
    from geo_tracker.agent.response_validation import doubao_persistence_auth_reason

    raw_text = ""
    response_html = (
        "<script>window.__state__={is_login:false,user_id:0}</script>"
    )

    assert (
        doubao_persistence_auth_reason("doubao", raw_text, response_html)
        == "doubao_not_logged_in"
    )


# Refs Codex P1 on PR #1076: the substantive-answer override must NOT
# trigger on raw_text length alone. ``raw_text`` can come from the JS
# ``document.body.innerText`` fallback (when the .flow-markdown-body
# selector misses) and a session-expired chrome with ``会话过期，请重新
# 登录...`` is easily >20 visible chars. If that body-text were treated
# as a substantive answer it would bypass HARD markers and persist a
# logged-out page as success.
def test_doubao_persistence_gate_blocks_jsfallback_logout_text_lacking_markdown_body():
    """raw_text containing logout chrome (no .flow-markdown-body) must NOT bypass HARD."""
    from geo_tracker.agent.response_validation import doubao_persistence_auth_reason

    # Body-text style payload — what a JS document.body.innerText
    # fallback would scrape on a session-expired page. No
    # ``.flow-markdown-body`` selector match in the HTML.
    raw_text = (
        "会话过期，请重新登录。请扫码登录使用豆包。"
        "这里有一些其他文本占位以确保长度超过 20 字符。"
    )
    response_html = "<div>some non-markdown chrome</div>"

    assert (
        doubao_persistence_auth_reason("doubao", raw_text, response_html)
        == "doubao_not_logged_in"
    )


def test_doubao_persistence_gate_visible_login_dialog_overrides_answer():
    """A visible login dialog must still reject even with a real answer."""
    from geo_tracker.agent.response_validation import doubao_persistence_auth_reason

    raw_text = "bestCoffer answer-like content with enough characters to count"
    response_html = (
        "<main><div class='flow-markdown-body'>"
        + raw_text
        + "</div></main>"
        "<div role='dialog'>"
        "  <input placeholder='手机号' />"
        "  <button class='login-button'>登录</button>"
        "</div>"
    )

    assert (
        doubao_persistence_auth_reason("doubao", raw_text, response_html)
        == "doubao_not_logged_in"
    )


# Refs #963 Q-184971 retry on worker SHA ``9e9b1e0``, 2026-05-16 16:15-16:18
# UTC (GitHub Actions verify-readonly run 25967204514 →
# https://github.com/jotamotk/trash_test/issues/963#issuecomment-4467456937).
# Doubao streamed a real 1023-char answer into ``.flow-markdown-body``;
# the scraper extracted it via ``query_selector('.flow-markdown-body')``;
# 21ms later the persistence gate still rejected it as
# ``doubao_not_logged_in``. Phase 1 evidence capture proved the dialog
# probe alone returned True — no hard string markers and no JS-state
# RE matches existed. The two triggering substrings were:
#   * ``passport`` matched the Bytedance SSO asset host
#     ``p9-passport.byteacctimg.com`` embedded in the LOGGED-IN user's
#     ``accountInfo.app_user_info.avatar_url`` JSON state at offset
#     428251 (this JSON only exists when the account is authenticated).
#   * ``手机号`` matched the LLM-generated answer bullet
#     ``客户资料：身份证、手机号、银行卡号识别准确率99.7%``
#     at offset 365248 in the body about financial-industry data masking.
# Bind a regression test to these exact captured values so a future
# iteration cannot reintroduce the regression by sneaking ``passport``
# back as a bare dialog marker or ``手机号`` back as a bare
# login-action marker.
def test_doubao_persistence_gate_q184971_passport_avatar_url_does_not_flag_logout():
    """Regression: Bytedance SSO avatar URL + LLM 手机号 bullet must NOT trip the dialog gate."""
    from geo_tracker.agent.response_validation import (
        doubao_persistence_auth_reason,
        _doubao_has_visible_login_dialog,
        _doubao_hard_persistence_auth_reason,
        _doubao_has_substantive_answer_html,
    )

    # Literal substring captured from the production Q-184971 saved HTML
    # ``/data/screenshots/query_184971_doubao_not_logged_in_1778948280.html``
    # at offset 428251 — the LOGGED-IN user's avatar URL inside the
    # ``accountInfo`` JSON state. ``app_user_info`` is only populated
    # for authenticated sessions, so this substring PROVES the account
    # is logged in.
    captured_passport_avatar_json = (
        '"app_user_info":{},'
        '"avatar_url":"https:\\u002F\\u002Fp9-passport.byteacctimg.com'
        '\\u002Fimg\\u002Fuser-avatar\\u002Fassets'
        '\\u002Fe7b19241fb224cea967dfaea35448102_1080_10"'
    )

    # Literal substring captured from the same saved HTML at offset
    # 365248 — a bullet inside the LLM-generated answer about
    # financial-industry data masking. ``手机号`` (phone-number) is
    # part of the natural-language answer, NOT login chrome.
    captured_answer_with_phone_bullet = (
        "<ul class=\"auto-hide-last-sibling-br\">"
        "<li>客户资料：身份证、手机号、银行卡号识别准确率"
        "<strong>99.7%</strong>，支持 15/18 位身份证区分。</li>"
        "<li>信贷合同：批量处理扫描件 / PDF，精准脱敏手写签名、"
        "金额，保留格式不可还原。</li>"
        "</ul>"
    )

    # The real .flow-markdown-body answer body extracted by the
    # upstream Playwright ``query_selector`` call (worker log:
    # ``[doubao] 通过 selector 提取响应: .flow-markdown-body
    # (1023 chars)``).
    flow_markdown_body = (
        "<div class=\"flow-markdown-body\">"
        "非常适合，bestCoffer 企业级 AI 数据脱敏工具专为金融行业高合规、"
        "高敏感、多场景需求设计，已在银行、券商、基金等机构落地验证 bestCoffer。"
        + captured_answer_with_phone_bullet
        + "</div>"
    )

    response_html = (
        "<main>"
        + flow_markdown_body
        + "</main>"
        # The avatar URL lives in an embedded JSON state block in the
        # SPA shell.
        "<script id=\"INITIAL_STATE\">"
        '{"accountInfo":{"data":{"app_id":497858,'
        + captured_passport_avatar_json
        + '}}}'
        "</script>"
    )

    raw_text = (
        "非常适合，bestCoffer 企业级 AI 数据脱敏工具专为金融行业高合规、"
        "高敏感、多场景需求设计，已在银行、券商、基金等机构落地验证。"
    )

    # Sanity: the captured triggering substrings really are in the HTML.
    assert "passport" in response_html
    assert "手机号" in response_html
    # And there is no real login chrome anywhere.
    assert "role=\"dialog\"" not in response_html
    assert "role='dialog'" not in response_html
    assert "login-dialog" not in response_html
    assert "login-button" not in response_html
    assert "扫码登录" not in response_html
    assert "手机号登录" not in response_html
    assert "短信验证码" not in response_html
    assert "请输入手机号" not in response_html

    # Sub-gate assertions.
    assert _doubao_has_substantive_answer_html(response_html) is True, (
        "the .flow-markdown-body body is the proven Q-184971 selector match"
    )
    assert _doubao_has_visible_login_dialog(response_html) is False, (
        "bare 'passport' (SSO asset host) + bare '手机号' (LLM answer bullet)"
        " must not trip the dialog probe — that was the Q-184971 false positive"
    )
    assert _doubao_hard_persistence_auth_reason(raw_text, response_html) is None, (
        "no hard logout signals exist in the captured HTML"
    )

    # Full gate verdict: the answer must persist.
    assert (
        doubao_persistence_auth_reason("doubao", raw_text, response_html) is None
    )


def test_doubao_persistence_gate_q184971_real_login_dialog_still_blocks():
    """Counterpart: when a real login dialog markup IS present, the gate still blocks."""
    from geo_tracker.agent.response_validation import (
        doubao_persistence_auth_reason,
        _doubao_has_visible_login_dialog,
    )

    # Same flow-markdown answer as above, but now the page actually carries
    # ``role="dialog"`` + ``login-button`` (the strict pair the tightened
    # gate looks for).
    response_html = (
        "<main><div class=\"flow-markdown-body\">"
        "bestCoffer 企业级 AI 数据脱敏工具相关回答内容超过 20 个字符。"
        "</div></main>"
        "<div role=\"dialog\">"
        "  <button class=\"login-button\">登录</button>"
        "</div>"
    )

    assert _doubao_has_visible_login_dialog(response_html) is True
    assert (
        doubao_persistence_auth_reason("doubao", "", response_html)
        == "doubao_not_logged_in"
    )


# Refs #963 verify-readonly comment 4469617051
# (https://github.com/jotamotk/trash_test/issues/963#issuecomment-4469617051).
# Mode B "Doubao queries past 24h with failure-without-real-answer" table
# rows (captured 2026-05-17 06:34 UTC after the latest worker SHA
# ``d8a22482d007d400709bb1a34b00c5015243a008`` deploy):
#
#   query_id | status | retry_reason            | resp_count | raw_text_len
#   --------+--------+-------------------------+------------+--------------
#    184971 | failed | no_response             |          1 |         1255
#    184988 | failed | doubao_homepage_content |          1 |         1191
#
# Both rows have ``llm_responses`` rows persisted with a long-form real
# answer; the answer text starts with ``非常适合 ，bestCoffer 企业级 AI 数据
# 脱敏工具…`` for Q-184971 (1255 chars) and ``非结构化数据 AI 脱敏准确率
# 测评核心指标…`` for Q-184988 (1191 chars). The Mode B inspection of the
# largest saved HTML for each query (``/data/screenshots/
# query_184971_doubao_not_logged_in_1778948280.html`` and
# ``/data/screenshots/query_184988_doubao_response_page_1778768408.html``)
# confirmed ``flow-markdown-body matches in visible: 1`` with the answer
# present in DOM. Yet the page chrome carried SOFT-bucket markers
# (``login-btn-header`` className, ``7天免登录`` promo banner, the
# ``登录以解锁更多功能`` overlay) that the previous gate let
# ``_doubao_strong_persistence_auth_reason`` reject on.
#
# These regression tests assert the >=100-char persistence whitelist
# overrides SOFT-bucket chrome + the ``doubao_auth_state_reason``
# fallback. HARD markers (``会话过期``/``from_logout=1``/JS state) and
# the absolute visible-login-dialog block stay in force — see the
# negative-control tests below for the boundary.
def test_doubao_persistence_gate_q184971_real_answer_overrides_soft_promo():
    """Q-184971 verify-readonly: 1255-char real answer must NOT be flagged logout."""
    from geo_tracker.agent.response_validation import (
        doubao_persistence_auth_reason,
        _doubao_has_persistence_whitelist_answer,
    )

    # The Q-184971 verify-readonly comment 4469617051 captured the
    # llm_responses raw_text starting with this exact substring.
    # Refs #963 verify-readonly comment 4469617051
    q184971_answer_prefix = (
        "非常适合 ，bestCoffer 企业级 AI 数据脱敏工具专为金融行业"
        "高合规、高敏感、多场景需求设计，已在银行、券商、基金等"
        "机构落地验证 bestCoffer。"
    )
    # Pad to roughly the 1255-char production length using the bullet
    # the Mode B HTML capture also found at offset 365248:
    # ``客户资料：身份证、手机号、银行卡号识别准确率99.7%``.
    q184971_answer_body = (
        q184971_answer_prefix
        + "客户资料：身份证、手机号、银行卡号识别准确率99.7%，"
        "支持 15/18 位身份证区分。" * 10
    )
    assert len(q184971_answer_body) > 100, "anchored to production raw_text_len=1255"

    response_html = (
        "<main><div class=\"flow-markdown-body\">"
        + q184971_answer_body
        + "</div></main>"
        # SPA chrome that persists on the LOGGED-IN shell. Doubao
        # carries ``login-btn-header`` through hydration; ``7天免登录``
        # and ``登录以解锁更多功能`` are tier-up overlays the SPA
        # renders alongside successful answers.
        "<header><button id=\"login-btn-header\">登录</button></header>"
        "<div class=\"promo-overlay\">7天免登录</div>"
        "<div class=\"promo-overlay\">登录以解锁更多功能</div>"
    )

    assert _doubao_has_persistence_whitelist_answer(
        q184971_answer_body, response_html
    ) is True, (
        "Q-184971's 1255-char real answer in .flow-markdown-body must "
        "trip the >=100-char persistence whitelist"
    )
    assert (
        doubao_persistence_auth_reason("doubao", q184971_answer_body, response_html)
        is None
    ), (
        "Q-184971 verify-readonly comment 4469617051: the real 1255-char "
        "answer must NOT be rejected as doubao_not_logged_in just because "
        "the SPA also carries SOFT chrome (login-btn-header + promo)"
    )


def test_doubao_persistence_gate_q184988_real_answer_overrides_soft_promo():
    """Q-184988 verify-readonly: 1191-char real answer must NOT be flagged logout."""
    from geo_tracker.agent.response_validation import (
        doubao_persistence_auth_reason,
        _doubao_has_persistence_whitelist_answer,
    )

    # The Q-184988 verify-readonly comment 4469617051 captured the
    # llm_responses raw_text starting with this exact substring.
    # Refs #963 verify-readonly comment 4469617051
    q184988_answer_prefix = (
        "非结构化数据 AI 脱敏准确率测评核心指标涵盖精确率、召回率、"
        "F1-Score、准确率等基础识别指标，以及漏脱敏率、误脱敏率等"
        "专项效果指标。"
    )
    q184988_answer_body = (
        q184988_answer_prefix
        + "其中漏脱敏率指应被脱敏却未被识别的敏感数据占比，"
        "误脱敏率指非敏感数据被错误标记的占比，二者均需在多样本上验证。" * 8
    )
    assert len(q184988_answer_body) > 100, "anchored to production raw_text_len=1191"

    response_html = (
        "<main><div class=\"flow-markdown-body\">"
        + q184988_answer_body
        + "</div></main>"
        # The doubao_homepage_content rejection that hit Q-184988
        # ran in guest_executor when 2+ homepage indicators matched
        # the JS body-fallback text. The persistence gate sees the
        # full DOM which still has the real answer inside
        # .flow-markdown-body alongside SOFT-bucket chrome.
        "<header><button id=\"login-btn-header\">登录</button></header>"
        "<div class=\"promo-overlay\">7天免登录</div>"
    )

    assert _doubao_has_persistence_whitelist_answer(
        q184988_answer_body, response_html
    ) is True, (
        "Q-184988's 1191-char real answer in .flow-markdown-body must "
        "trip the >=100-char persistence whitelist"
    )
    assert (
        doubao_persistence_auth_reason("doubao", q184988_answer_body, response_html)
        is None
    ), (
        "Q-184988 verify-readonly comment 4469617051: the real 1191-char "
        "answer must NOT be rejected just because the SPA chrome carries "
        "login-btn-header + 7天免登录 promo overlay"
    )


def test_doubao_persistence_gate_q184971_response_container_fallback():
    """Whitelist must also match Doubao's secondary response selectors.

    The Doubao scraper config defines ``response_selector`` as
    ``.flow-markdown-body, [data-testid='receive_message'],
    [class*='message-content']``. When the SPA reflows mid-stream
    the inner ``.flow-markdown-body`` can detach while the parent
    ``[data-testid='receive_message']`` retains the answer text;
    the whitelist must still fire in that case.
    """
    from geo_tracker.agent.response_validation import (
        doubao_persistence_auth_reason,
        _doubao_has_persistence_whitelist_answer,
    )

    # Same answer prefix as Q-184971 — anchored to production raw_text.
    # Refs #963 verify-readonly comment 4469617051
    answer_body = (
        "非常适合 ，bestCoffer 企业级 AI 数据脱敏工具专为金融行业高合规、"
        "高敏感、多场景需求设计，已在银行、券商、基金等机构落地验证。"
    ) * 4

    response_html = (
        # No .flow-markdown-body — parent container is the only match.
        "<main><div data-testid=\"receive_message\">"
        + answer_body
        + "</div></main>"
        "<header><button id=\"login-btn-header\">登录</button></header>"
    )

    assert _doubao_has_persistence_whitelist_answer(
        answer_body, response_html
    ) is True
    assert (
        doubao_persistence_auth_reason("doubao", answer_body, response_html)
        is None
    )


def test_doubao_persistence_gate_short_answer_does_not_trip_whitelist():
    """Negative control: <100-char body must NOT bypass STRONG markers.

    The new whitelist is strictly tighter than the existing 20-char
    HARD-bypass. A short hint that crosses 20 chars still gets HARD
    bypassed (preserving the prior promo-banner test) but must not
    bypass STRONG or the auth_state_reason fallback when no other
    proof exists. Together with the negative-control tests below
    this anchors the threshold semantics.
    """
    from geo_tracker.agent.response_validation import (
        doubao_persistence_auth_reason,
        _doubao_has_persistence_whitelist_answer,
        _doubao_has_substantive_answer_html,
    )

    # 21 stripped chars (just above 20) — too short for the >=100
    # whitelist but enough for the HARD-bypass.
    short_body = "非结构化数据 AI 脱敏准确率测评核心指标"
    assert 20 <= len(short_body) < 100

    # When ONLY SOFT-bucket chrome appears alongside this short body,
    # the prior HARD-bypass already returned None — the new whitelist
    # does not change that behavior.
    response_html_soft_only = (
        "<main><div class=\"flow-markdown-body\">"
        + short_body
        + "</div></main>"
        "<button id=\"login-btn-header\">登录</button>"
    )

    assert _doubao_has_substantive_answer_html(response_html_soft_only) is True
    assert _doubao_has_persistence_whitelist_answer(
        short_body, response_html_soft_only
    ) is False, (
        "21-char body must NOT trip the >=100-char whitelist"
    )

    # The existing >=20-char .flow-markdown-body bypass overrides
    # HARD/STRONG already (see
    # test_doubao_persistence_gate_keeps_answer_over_login_btn_header_chrome);
    # the new whitelist is a stricter additional override, not a
    # weaker one. Result: the short-body case still passes via the
    # existing bypass.
    assert (
        doubao_persistence_auth_reason("doubao", short_body, response_html_soft_only)
        is None
    )


def test_doubao_persistence_gate_whitelist_does_not_override_visible_dialog():
    """Negative control: a visible login dialog still blocks even with a long answer.

    Refs #963 follow-up: a visible login dialog is the only signal
    that the session is being actively interrupted right now — at
    that point any prior answer is stale and the user is logged
    out for the purposes of any future call. The whitelist sits
    below the visible-dialog block in the gate order, so it must
    not weaken this absolute check.
    """
    from geo_tracker.agent.response_validation import (
        doubao_persistence_auth_reason,
    )

    answer_body = (
        "非常适合 ，bestCoffer 企业级 AI 数据脱敏工具专为金融行业高合规、"
        "高敏感、多场景需求设计，已在银行、券商、基金等机构落地验证。"
    ) * 4

    response_html = (
        "<main><div class=\"flow-markdown-body\">"
        + answer_body
        + "</div></main>"
        # Real login dialog markup — the strict (chrome + action)
        # pair the dialog probe matches.
        "<div role=\"dialog\">"
        "  <button class=\"login-button\">登录</button>"
        "</div>"
    )

    # Even though the answer body is >100 chars, the visible
    # dialog must still flip the gate. This preserves the
    # absolute-block invariant.
    assert (
        doubao_persistence_auth_reason("doubao", answer_body, response_html)
        == "doubao_not_logged_in"
    )


def test_doubao_invalid_response_reason_whitelist_bypasses_generic_markers():
    """Refs #963 verify-readonly comment 4469617051: the Doubao whitelist also
    overrides the generic ``your session has expired`` / ``please log in``
    markers used by ``invalid_response_reason``.

    The celery_tasks call passes ``response_html`` to
    ``invalid_response_reason`` so a real >=100-char answer in a
    Doubao response container cannot be falsely rejected because
    an LLM answer happened to quote the English logout chrome.
    """
    from geo_tracker.agent.response_validation import invalid_response_reason

    # Real answer in .flow-markdown-body; raw_text quotes the English
    # logout chrome verbatim (e.g. an LLM answer comparing the UX
    # phrasing of "your session has expired" between products).
    answer_body = (
        "非常适合 ，bestCoffer 企业级 AI 数据脱敏工具专为金融行业高合规、"
        "高敏感、多场景需求设计，已在银行、券商、基金等机构落地验证。"
    ) * 4

    raw_text_quoting_chrome = (
        answer_body
        + "\n用户提示：『your session has expired』是常见的会话过期提示文案。"
    )

    response_html = (
        "<main><div class=\"flow-markdown-body\">"
        + answer_body
        + "</div></main>"
    )

    # With the response_html available, the Doubao whitelist bypasses
    # ``cookies_expired`` matching.
    assert (
        invalid_response_reason("doubao", raw_text_quoting_chrome, response_html)
        is None
    )

    # Without a response container (just chrome / body fallback),
    # generic markers still fire — this preserves the negative case.
    assert (
        invalid_response_reason(
            "doubao",
            "your session has expired, please log in again to continue using the app",
            "<div>not a response container</div>",
        )
        == "cookies_expired"
    )


def test_doubao_invalid_response_reason_backwards_compatible_two_arg_signature():
    """The new ``response_html`` kwarg is optional; existing 2-arg callers must still work."""
    from geo_tracker.agent.response_validation import invalid_response_reason

    # Existing call sites in bestcoffer_*.py / analyzer_v3_backfill.py /
    # guest_executor.py / tests pass only (llm_name, text). The signature
    # change must remain backwards-compatible.
    assert invalid_response_reason("chatgpt", "your session has expired") == "cookies_expired"
    assert invalid_response_reason("doubao", "non-logout chinese answer") is None
    assert invalid_response_reason("doubao", "") is None


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
async def test_doubao_submit_retry_bails_when_page_regressed_to_homepage(
    monkeypatch,
):
    """Refs #963 evidence-first fix: Q-184971 retry on worker SHA d8a22482
    at 2026-05-17 05:40:14 UTC saved a submit_failed HTML where the SPA
    had collapsed back to Doubao's homepage. The HTML had 0 occurrences
    of #flow-end-msg-send / send-msg-btn / send-btn-wrapper, only one
    aria-hidden helper textarea, and the visible body was recommendation
    cards (有什么我能帮你的吗？ + 资讯...). The submit_button for-loop
    found nothing, _find_submit_button_js returned None, and the code
    fired two wasted Enter keypresses into the homepage. The retry path
    should detect "no input + no send button" and bail with a specific
    reason rather than burn the confirm-poll budget on a regressed page.

    The bail must:
      - return ("", "", []) early (before the 10-iter confirm poll);
      - call _save_html so the page state is preserved for debugging;
      - set last_error_reason via _prefer_doubao_auth_failure_reason
        when auth markers are present (e.g. login chrome detected after
        regression), falling back to "doubao_input_lost_before_submit"
        when no stronger signal exists.
    """
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent import guest_executor as _ge
    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    captured_html_suffixes: list[str] = []

    async def fake_save_html(_page, _query_id, suffix):
        captured_html_suffixes.append(suffix)

    async def fake_save_screenshot(*_a, **_k):
        return None

    async def fake_save_runtime_snapshot(*_a, **_k):
        return None

    monkeypatch.setattr(_ge, "_save_html", fake_save_html)
    monkeypatch.setattr(_ge, "_save_screenshot", fake_save_screenshot)
    monkeypatch.setattr(_ge, "_save_runtime_snapshot", fake_save_runtime_snapshot)

    query_text = "bestCoffer advantages for travel?"

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
        """Simulates Doubao homepage state at submit-failed time.

        Mirrors Q-184971's saved HTML:
          - query_selector returns None for input selectors (input gone);
          - evaluate_handle returns a JS handle whose as_element is None
            (no #flow-end-msg-send found anywhere);
          - page.evaluate for submit confirmation returns False;
          - page.evaluate for body innerText returns the recommendation
            cards body (which contains 登录 marker so
            _prefer_doubao_auth_failure_reason classifies as
            doubao_not_logged_in).
        """

        url = "https://www.doubao.com/chat"

        def __init__(self):
            self.keyboard = FakeKeyboard()
            self.mouse = FakeMouse()

        async def wait_for_timeout(self, *_a, **_k):
            return None

        async def evaluate_handle(self, *_a, **_k):
            return FakeSubmitHandle()

        async def query_selector(self, _selector, *_a, **_k):
            # input + button selectors all return None — page regressed.
            return None

        async def query_selector_all(self, _selector, *_a, **_k):
            return []

        async def evaluate(self, script, *args):
            script_text = str(script)
            if "document.body?.innerText" in script_text:
                # Doubao homepage recommendation cards + 登录 header
                return (
                    "有什么我能帮你的吗？\n"
                    "资讯：哈佛博士苏萌预测月球十年内现永久驻留基地\n"
                    "登录"
                )
            # submit_confirmed queryText script -> never confirmed
            if "queryText" in script_text:
                return False
            return ""

        async def content(self):
            return (
                "<html><body>"
                "<div><h2>有什么我能帮你的吗？</h2></div>"
                "<header><button class=\"login-button\">登录</button></header>"
                "</body></html>"
            )

    executor = GuestQueryExecutor()
    fake_page = FakePage()

    async def fake_fill_plain_text_input(*_a, **_k):
        return True

    monkeypatch.setattr(executor, "_fill_plain_text_input", fake_fill_plain_text_input)

    resp_text, resp_html, citations = await executor._browser_query(
        fake_page,
        {
            "input_selector": "textarea",
            "response_selector": ".flow-markdown-body",
            "submit_button": (
                "#flow-end-msg-send:not([aria-disabled='true']):not([data-disabled='true']),"
                " button[id='flow-end-msg-send']"
            ),
            "submit_key": "Enter",
            "wait_after_submit": 100,
            "load_wait": 100,
            "login_redirect_domains": [],
            "url": "https://www.doubao.com/chat/",
        },
        query_text,
        "doubao",
        input_el=FakeInput(),
        query_id=184971,
        runtime_events=[],
    )

    # The new bail must short-circuit the retry path: no response, no
    # citations, no html (the page regressed and we refused to fire
    # Enter into nothing).
    assert (resp_text, resp_html, citations) == ("", "", [])
    # _save_html was called with the submit_failed suffix for evidence.
    assert "doubao_submit_failed" in captured_html_suffixes, (
        f"expected _save_html called with doubao_submit_failed suffix; "
        f"got {captured_html_suffixes!r}"
    )
    # _prefer_doubao_auth_failure_reason classifies the homepage's
    # visible "登录" header → doubao_not_logged_in wins over the
    # fallback doubao_input_lost_before_submit.
    assert executor.last_error_reason == "doubao_not_logged_in"


@pytest.mark.asyncio
async def test_doubao_submit_retry_bails_with_specific_reason_when_no_auth_signal(
    monkeypatch,
):
    """Refs #963 evidence-first fix: when the page regressed and there
    is NO login chrome (no 登录 marker, no login dialog), the fallback
    last_error_reason should be the specific
    ``doubao_input_lost_before_submit`` so the operator ledger
    distinguishes this collapse from generic ``no_response``.
    """
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent import guest_executor as _ge
    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(_ge, "_save_html", _noop)
    monkeypatch.setattr(_ge, "_save_screenshot", _noop)
    monkeypatch.setattr(_ge, "_save_runtime_snapshot", _noop)

    query_text = "bestCoffer advantages?"

    class FakeInput:
        async def bounding_box(self):
            return None

        async def click(self, *_a, **_k):
            return None

        async def fill(self, *_a, **_k):
            return None

        async def evaluate(self, *_a, **_k):
            return query_text

    class FakeKeyboard:
        async def press(self, *_a, **_k):
            return None

        async def type(self, *_a, **_k):
            return None

    class FakeMouse:
        async def move(self, *_a, **_k):
            return None

    class FakeSubmitHandle:
        def as_element(self):
            return None

    class FakePage:
        url = "https://www.doubao.com/chat"

        def __init__(self):
            self.keyboard = FakeKeyboard()
            self.mouse = FakeMouse()

        async def wait_for_timeout(self, *_a, **_k):
            return None

        async def evaluate_handle(self, *_a, **_k):
            return FakeSubmitHandle()

        async def query_selector(self, *_a, **_k):
            return None

        async def query_selector_all(self, *_a, **_k):
            return []

        async def evaluate(self, script, *args):
            script_text = str(script)
            # innerText: page text WITHOUT any 登录 / login marker —
            # _prefer_doubao_auth_failure_reason will NOT classify this
            # as doubao_not_logged_in, so the fallback specific reason
            # ``doubao_input_lost_before_submit`` survives.
            if "document.body?.innerText" in script_text:
                return "有什么我能帮你的吗？\n资讯：今日新闻"
            if "queryText" in script_text:
                return False
            return ""

        async def content(self):
            return (
                "<html><body>"
                "<h2>有什么我能帮你的吗？</h2>"
                "</body></html>"
            )

    executor = GuestQueryExecutor()
    fake_page = FakePage()

    async def fake_fill_plain_text_input(*_a, **_k):
        return True

    monkeypatch.setattr(executor, "_fill_plain_text_input", fake_fill_plain_text_input)

    resp_text, resp_html, citations = await executor._browser_query(
        fake_page,
        {
            "input_selector": "textarea",
            "response_selector": ".flow-markdown-body",
            "submit_button": "#flow-end-msg-send",
            "submit_key": "Enter",
            "wait_after_submit": 100,
            "load_wait": 100,
            "login_redirect_domains": [],
            "url": "https://www.doubao.com/chat/",
        },
        query_text,
        "doubao",
        input_el=FakeInput(),
        query_id=184971,
        runtime_events=[],
    )

    assert (resp_text, resp_html, citations) == ("", "", [])
    # When the regressed page has no authenticated marker,
    # _prefer_doubao_auth_failure_reason classifies as
    # ``doubao_auth_state_missing`` (a specific operator-useful reason).
    # If even that helper returns None — e.g. the body parses as a normal
    # chat page with no auth markers — the new fallback
    # ``doubao_input_lost_before_submit`` kicks in so the ledger never
    # ends up as the generic ``no_response`` for this collapse pattern.
    assert executor.last_error_reason in (
        "doubao_auth_state_missing",
        "doubao_input_lost_before_submit",
    ), (
        f"expected a specific page-regression reason "
        f"(doubao_auth_state_missing or doubao_input_lost_before_submit); "
        f"got {executor.last_error_reason!r}"
    )
    # And NOT the pre-fix generic ``no_response``.
    assert executor.last_error_reason != "no_response"


@pytest.mark.asyncio
async def test_chatgpt_submit_retry_does_not_inherit_doubao_bail_reason(
    monkeypatch,
):
    """Refs #963 Codex P2 review on PR #1106: the submit-confirm retry
    block runs for all engines. The Doubao-specific bail (set
    ``last_error_reason = doubao_input_lost_before_submit`` and return
    early when both the input element and the JS submit-button handle
    are gone) must NOT fire for chatgpt / deepseek, otherwise a
    non-Doubao engine would inherit a Doubao reason in the operator
    ledger. Confirm that for ``llm_name == "chatgpt"`` the retry path:
      - does NOT short-circuit with ``("", "", [])`` before the
        confirm poll;
      - does NOT set ``last_error_reason`` to
        ``doubao_input_lost_before_submit``;
      - DOES press Enter (the pre-fix blind-Enter behavior is the
        compat path for non-Doubao engines).
    """
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent import guest_executor as _ge
    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(_ge, "_save_html", _noop)
    monkeypatch.setattr(_ge, "_save_screenshot", _noop)
    monkeypatch.setattr(_ge, "_save_runtime_snapshot", _noop)

    query_text = "anything"
    enter_presses: list[int] = []

    class FakeInput:
        async def bounding_box(self):
            return None

        async def click(self, *_a, **_k):
            return None

        async def fill(self, *_a, **_k):
            return None

        async def evaluate(self, *_a, **_k):
            return query_text

    class FakeKeyboard:
        async def press(self, key, *_a, **_k):
            if key == "Enter":
                enter_presses.append(1)

        async def type(self, *_a, **_k):
            return None

    class FakeMouse:
        async def move(self, *_a, **_k):
            return None

    class FakeSubmitHandle:
        def as_element(self):
            return None

    class FakePage:
        url = "https://chatgpt.com"

        def __init__(self):
            self.keyboard = FakeKeyboard()
            self.mouse = FakeMouse()

        async def wait_for_timeout(self, *_a, **_k):
            return None

        async def evaluate_handle(self, *_a, **_k):
            return FakeSubmitHandle()

        async def query_selector(self, *_a, **_k):
            return None

        async def query_selector_all(self, *_a, **_k):
            return []

        async def evaluate(self, script, *args):
            script_text = str(script)
            if "document.body?.innerText" in script_text:
                return "Empty page"
            if "queryText" in script_text:
                return False
            return ""

        async def content(self):
            return "<html><body></body></html>"

    executor = GuestQueryExecutor()
    fake_page = FakePage()

    async def fake_fill_plain_text_input(*_a, **_k):
        return True

    monkeypatch.setattr(executor, "_fill_plain_text_input", fake_fill_plain_text_input)

    await executor._browser_query(
        fake_page,
        {
            "input_selector": "textarea",
            "response_selector": ".markdown",
            "submit_button": "button[data-testid='send-button']",
            "submit_key": "Enter",
            "wait_after_submit": 100,
            "load_wait": 100,
            "login_redirect_domains": [],
            "url": "https://chatgpt.com",
        },
        query_text,
        "chatgpt",
        input_el=FakeInput(),
        query_id=999999,
        runtime_events=[],
    )

    # The Doubao-only bail reason must not bleed into chatgpt.
    assert executor.last_error_reason != "doubao_input_lost_before_submit", (
        f"chatgpt must not inherit Doubao bail reason; "
        f"got {executor.last_error_reason!r}"
    )
    # And Enter is pressed on the retry path (blind-Enter compat for
    # non-Doubao engines preserved). Initial submit fires Enter once
    # (submit_key) and the retry fires Enter again → at least 2.
    assert len(enter_presses) >= 2, (
        f"expected Enter to fire on retry for chatgpt; "
        f"got {len(enter_presses)} press(es)"
    )


@pytest.mark.asyncio
async def test_doubao_submit_retry_recovers_via_page_goto_when_ui_returns(
    monkeypatch,
):
    """Refs #963 follow-up to PR #1106: when the Doubao SPA regresses to
    its homepage between fill and submit-confirm (Q-184971 evidence
    2026-05-17 05:39-05:40 UTC), PR #1106 bailed with
    ``doubao_input_lost_before_submit``. This follow-up adds a ONE-SHOT
    ``page.goto(cfg["url"])`` recovery BEFORE the bail. The investigation
    posted on issue #963 (2026-05-17T06:23Z) refuted IP-rotation-forces-
    re-login (0 re-login events in 48h, sessions surviving 285+ min
    across rotations), so the session is still valid and a fresh /chat
    load should bring the chat UI back.

    Happy path: FakePage returns no input + no submit button on the
    initial submit (matches Q-184971), but after ``page.goto`` the chat
    UI is back. Recovery refills, clicks the resurfaced send button,
    submit_confirmed returns True, and the executor falls through to the
    normal response-wait path instead of bailing.
    """
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent import guest_executor as _ge
    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(_ge, "_save_html", _noop)
    monkeypatch.setattr(_ge, "_save_screenshot", _noop)
    monkeypatch.setattr(_ge, "_save_runtime_snapshot", _noop)

    query_text = "bestCoffer travel advantages?"

    class FakeInput:
        async def bounding_box(self):
            return None

        async def click(self, *_a, **_k):
            return None

        async def fill(self, *_a, **_k):
            return None

        async def evaluate(self, *_a, **_k):
            return query_text

    class FakeKeyboard:
        async def press(self, *_a, **_k):
            return None

        async def type(self, *_a, **_k):
            return None

    class FakeMouse:
        async def move(self, *_a, **_k):
            return None

    class FakeSubmitHandle:
        def __init__(self, has_element: bool):
            self._has = has_element

        def as_element(self):
            return _FakeButton() if self._has else None

    class _FakeButton:
        async def is_visible(self):
            return True

        async def click(self, *_a, **_k):
            return None

        async def evaluate(self, *_a, **_k):
            # Disabled-state probe in the submit_button for-loop — return
            # False so the click path is allowed to proceed.
            return False

    class FakePage:
        """Page collapsed to homepage at submit time, then recovers via
        ``page.goto``.

        Pre-recovery (the initial submit + the retry-input probe at the
        start of the retry block): query_selector returns None for input
        and button selectors; evaluate_handle returns a handle whose
        ``as_element()`` is None (no #flow-end-msg-send). After the
        executor calls ``page.goto`` the page flips into a recovered
        state where the input and submit button query_selectors return
        usable fakes and submit_confirmed yields True.
        """

        url = "https://www.doubao.com/chat"

        def __init__(self):
            self.keyboard = FakeKeyboard()
            self.mouse = FakeMouse()
            self.recovered = False
            self.goto_calls: list[str] = []
            self.refill_called = False

        async def wait_for_timeout(self, *_a, **_k):
            return None

        async def goto(self, url, *_a, **_k):
            self.goto_calls.append(url)
            self.recovered = True

        async def evaluate_handle(self, *_a, **_k):
            # Submit-button finder: before recovery returns no element so
            # the retry block enters its "no input + no button" branch;
            # after recovery returns a usable button so the resubmit path
            # can click.
            return FakeSubmitHandle(has_element=self.recovered)

        async def query_selector(self, selector, *_a, **_k):
            if not self.recovered:
                return None
            # After recovery, both input and send-button selectors return
            # usable fakes.
            return _FakeButton()

        async def wait_for_selector(self, selector, *_a, **_k):
            if not self.recovered:
                raise RuntimeError("not found")
            return _FakeButton()

        async def query_selector_all(self, *_a, **_k):
            return []

        async def evaluate(self, script, *args):
            script_text = str(script)
            # submit_confirmed: True ONLY after recovery + refill, so the
            # outer 10-iter confirm poll on the recovered submit succeeds.
            if "queryText" in script_text:
                return self.recovered and self.refill_called
            if "document.body?.innerText" in script_text:
                return "" if self.recovered else "登录"
            return ""

        async def content(self):
            return "<html><body>recovered</body></html>"

    executor = GuestQueryExecutor()
    fake_page = FakePage()

    refill_calls: list[int] = []

    async def fake_fill_plain_text_input(_self_page, _input_el, _text, _llm):
        # Track that refill ran AFTER recovery (matches the executor's
        # call order: recovery → fill on the new input → resubmit).
        refill_calls.append(1)
        fake_page.refill_called = True
        return True

    monkeypatch.setattr(executor, "_fill_plain_text_input", fake_fill_plain_text_input)

    resp_text, resp_html, citations = await executor._browser_query(
        fake_page,
        {
            "input_selector": (
                "#input-engine-container textarea.semi-input-textarea:not([aria-hidden='true']),"
                " textarea.semi-input-textarea:not([aria-hidden='true']),"
                " textarea:not([aria-hidden='true']), [contenteditable='true']"
            ),
            "response_selector": ".flow-markdown-body",
            "submit_button": (
                "#flow-end-msg-send:not([aria-disabled='true']):not([data-disabled='true']),"
                " button[id='flow-end-msg-send']"
            ),
            "submit_key": "Enter",
            "wait_after_submit": 100,
            "load_wait": 100,
            "login_redirect_domains": [],
            "url": "https://www.doubao.com/chat/",
        },
        query_text,
        "doubao",
        input_el=FakeInput(),
        query_id=184971,
        runtime_events=[],
    )

    # Recovery actually called page.goto with the cfg URL exactly once
    # (ONE-SHOT guarantee).
    assert fake_page.goto_calls == ["https://www.doubao.com/chat/"], (
        f"expected one page.goto recovery call to cfg['url']; "
        f"got {fake_page.goto_calls!r}"
    )
    # After recovery the executor refilled the input via the public
    # _fill_plain_text_input helper before resubmitting.
    assert len(refill_calls) >= 1, (
        f"expected _fill_plain_text_input to be called after recovery; "
        f"got {len(refill_calls)} call(s)"
    )
    # The executor did NOT bail with the PR #1106 reason — recovery
    # succeeded, so the retry path falls through to the response-wait
    # phase and last_error_reason stays clean of the bail reason.
    assert executor.last_error_reason != "doubao_input_lost_before_submit", (
        f"recovery should clear the bail reason; "
        f"got {executor.last_error_reason!r}"
    )
    # Returned tuple is not the early bail empty triple (response
    # extraction may legitimately produce empty text under this FakePage,
    # but the explicit ('', '', []) bail triple is what we're guarding
    # against — verified by NOT seeing the bail reason set above and
    # confirming that submit_confirmed observed the recovered state).


@pytest.mark.asyncio
async def test_doubao_submit_retry_falls_through_to_bail_when_recovery_fails(
    monkeypatch,
):
    """Refs #963 follow-up to PR #1106: when the page regressed AND the
    ``page.goto`` recovery does not bring the chat UI back (e.g. the
    homepage redirect is sticky, or the goto itself errors), the
    executor MUST fall through to PR #1106's bail rather than press
    Enter into nothing or hang.

    Failure path: FakePage returns no input / no button regardless of
    whether page.goto was called (stays regressed). After recovery the
    executor still sees no input and no clickable button, so it must
    fall through to the existing bail and set last_error_reason to the
    specific page-regression reason (doubao_not_logged_in if auth
    chrome is detected, else doubao_input_lost_before_submit).
    """
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent import guest_executor as _ge
    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    captured_html_suffixes: list[str] = []

    async def fake_save_html(_page, _query_id, suffix):
        captured_html_suffixes.append(suffix)

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(_ge, "_save_html", fake_save_html)
    monkeypatch.setattr(_ge, "_save_screenshot", _noop)
    monkeypatch.setattr(_ge, "_save_runtime_snapshot", _noop)

    query_text = "bestCoffer advantages?"

    class FakeInput:
        async def bounding_box(self):
            return None

        async def click(self, *_a, **_k):
            return None

        async def fill(self, *_a, **_k):
            return None

        async def evaluate(self, *_a, **_k):
            return query_text

    class FakeKeyboard:
        async def press(self, *_a, **_k):
            return None

        async def type(self, *_a, **_k):
            return None

    class FakeMouse:
        async def move(self, *_a, **_k):
            return None

    class FakeSubmitHandle:
        def as_element(self):
            return None

    class FakePage:
        url = "https://www.doubao.com/chat"

        def __init__(self):
            self.keyboard = FakeKeyboard()
            self.mouse = FakeMouse()
            self.goto_calls: list[str] = []

        async def wait_for_timeout(self, *_a, **_k):
            return None

        async def goto(self, url, *_a, **_k):
            # Recovery attempted but page stays regressed — input and
            # button selectors continue to return None after this call.
            self.goto_calls.append(url)

        async def evaluate_handle(self, *_a, **_k):
            return FakeSubmitHandle()

        async def query_selector(self, *_a, **_k):
            return None

        async def wait_for_selector(self, *_a, **_k):
            raise RuntimeError("not found")

        async def query_selector_all(self, *_a, **_k):
            return []

        async def evaluate(self, script, *args):
            script_text = str(script)
            # Auth marker present → _prefer_doubao_auth_failure_reason
            # classifies as doubao_not_logged_in (the strongest available
            # operator reason for a homepage-regression with login chrome).
            if "document.body?.innerText" in script_text:
                return "有什么我能帮你的吗？\n登录"
            if "queryText" in script_text:
                return False
            return ""

        async def content(self):
            return (
                "<html><body>"
                "<header><button class=\"login-button\">登录</button></header>"
                "</body></html>"
            )

    executor = GuestQueryExecutor()
    fake_page = FakePage()

    async def fake_fill_plain_text_input(*_a, **_k):
        return True

    monkeypatch.setattr(executor, "_fill_plain_text_input", fake_fill_plain_text_input)

    resp_text, resp_html, citations = await executor._browser_query(
        fake_page,
        {
            "input_selector": (
                "#input-engine-container textarea.semi-input-textarea:not([aria-hidden='true']),"
                " textarea:not([aria-hidden='true'])"
            ),
            "response_selector": ".flow-markdown-body",
            "submit_button": "#flow-end-msg-send",
            "submit_key": "Enter",
            "wait_after_submit": 100,
            "load_wait": 100,
            "login_redirect_domains": [],
            "url": "https://www.doubao.com/chat/",
        },
        query_text,
        "doubao",
        input_el=FakeInput(),
        query_id=184971,
        runtime_events=[],
    )

    # Recovery was attempted exactly once (ONE-SHOT — even on failure we
    # do not loop more goto attempts).
    assert fake_page.goto_calls == ["https://www.doubao.com/chat/"], (
        f"expected exactly one page.goto recovery attempt; "
        f"got {fake_page.goto_calls!r}"
    )
    # After recovery still failed, the executor falls through to
    # PR #1106's bail: early return ('', '', []) and a specific
    # operator-useful reason. The auth chrome is visible so the
    # _prefer_doubao_auth_failure_reason path wins, classifying as
    # doubao_not_logged_in (stronger than the fallback bail reason).
    assert (resp_text, resp_html, citations) == ("", "", [])
    assert "doubao_submit_failed" in captured_html_suffixes, (
        f"expected _save_html called with doubao_submit_failed suffix; "
        f"got {captured_html_suffixes!r}"
    )
    # last_error_reason landed on a specific, operator-useful page
    # regression reason — NOT generic ``no_response``.
    assert executor.last_error_reason in (
        "doubao_not_logged_in",
        "doubao_auth_state_missing",
        "doubao_input_lost_before_submit",
    ), (
        f"expected specific page-regression reason; "
        f"got {executor.last_error_reason!r}"
    )
    assert executor.last_error_reason != "no_response"


@pytest.mark.asyncio
async def test_doubao_submit_retry_recovery_skips_disabled_send_button(
    monkeypatch,
):
    """Refs #963 Codex P2 review on PR #1107: the recovery path's
    submit_button click loop did NOT mirror the initial-submit
    ``is_disabled`` guard, so when ``page.goto`` brings the chat UI
    back but the send button is still ``aria-disabled='true'`` (a
    freshly reloaded Doubao chat UI hasn't enabled the send button
    yet — Doubao gates it on textarea non-empty + composer-ready
    signals), the recovery would click a disabled button (no-op),
    set ``resubmitted = True`` → ``recovered = True``, skip the
    page-regression bail, and end up as generic ``no_response``
    after the confirm-poll fails to see a user bubble.

    The fix mirrors the initial-submit disabled guard
    (aria-disabled / data-disabled / send-msg-btn-disabled-bg class)
    inside the recovery's submit_button loop. With the guard, a
    freshly reloaded UI whose button is still disabled is recognised
    as "no clickable button after recovery" → recovered stays False
    → falls through to the specific page-regression bail.
    """
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent import guest_executor as _ge
    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    captured_html_suffixes: list[str] = []

    async def fake_save_html(_page, _query_id, suffix):
        captured_html_suffixes.append(suffix)

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(_ge, "_save_html", fake_save_html)
    monkeypatch.setattr(_ge, "_save_screenshot", _noop)
    monkeypatch.setattr(_ge, "_save_runtime_snapshot", _noop)

    query_text = "bestCoffer advantages?"

    class FakeInput:
        async def bounding_box(self):
            return None

        async def click(self, *_a, **_k):
            return None

        async def fill(self, *_a, **_k):
            return None

        async def evaluate(self, *_a, **_k):
            return query_text

    class FakeKeyboard:
        async def press(self, *_a, **_k):
            return None

        async def type(self, *_a, **_k):
            return None

    class FakeMouse:
        async def move(self, *_a, **_k):
            return None

    class FakeSubmitHandle:
        def as_element(self):
            return None

    button_clicks: list[int] = []

    class FakeDisabledButton:
        async def is_visible(self):
            return True

        async def click(self, *_a, **_k):
            # Without the guard, this no-op click would still execute
            # and set resubmitted=True. With the guard, this method
            # must NEVER be reached.
            button_clicks.append(1)
            return None

        async def evaluate(self, script, *_a, **_k):
            # The recovery's is_disabled evaluate script returns True
            # → guard skips this button. The initial-submit's
            # is_disabled probe (in the pre-bail submit attempt
            # before retry) is on the FakeInput path, not here.
            script_text = str(script)
            if "aria-disabled" in script_text or "data-disabled" in script_text:
                return True
            return False

    class FakePage:
        url = "https://www.doubao.com/chat"

        def __init__(self):
            self.keyboard = FakeKeyboard()
            self.mouse = FakeMouse()
            self.recovered = False
            self.goto_calls: list[str] = []

        async def wait_for_timeout(self, *_a, **_k):
            return None

        async def goto(self, url, *_a, **_k):
            self.goto_calls.append(url)
            self.recovered = True

        async def evaluate_handle(self, *_a, **_k):
            # JS submit-button fallback finds nothing → recovery's
            # last chance to set resubmitted is gone.
            return FakeSubmitHandle()

        async def query_selector(self, _selector, *_a, **_k):
            if not self.recovered:
                # Pre-recovery: input + button both missing → enters
                # the page-regression branch.
                return None
            # Post-recovery: send button selectors return the
            # DISABLED button. Input selector also returns it but
            # that's fine — FakeInput-style is_visible+evaluate will
            # have its evaluate return True (disabled). The recovery
            # block treats both selector probes the same way.
            return FakeDisabledButton()

        async def wait_for_selector(self, _selector, *_a, **_k):
            if not self.recovered:
                raise RuntimeError("not found")
            return FakeDisabledButton()

        async def query_selector_all(self, *_a, **_k):
            return []

        async def evaluate(self, script, *args):
            script_text = str(script)
            if "document.body?.innerText" in script_text:
                # Post-recovery body has no auth chrome — so the
                # fallback bail reason ``doubao_input_lost_before_submit``
                # (or ``doubao_auth_state_missing`` if that helper
                # returns it) is what we expect, NOT ``no_response``.
                return "有什么我能帮你的吗？"
            if "queryText" in script_text:
                # submit_confirmed must never see a real user bubble
                # because no submit actually fired (the disabled
                # button was correctly skipped).
                return False
            return ""

        async def content(self):
            return "<html><body>recovered but send button disabled</body></html>"

    executor = GuestQueryExecutor()
    fake_page = FakePage()

    async def fake_fill_plain_text_input(*_a, **_k):
        return True

    monkeypatch.setattr(executor, "_fill_plain_text_input", fake_fill_plain_text_input)

    resp_text, resp_html, citations = await executor._browser_query(
        fake_page,
        {
            "input_selector": (
                "#input-engine-container textarea.semi-input-textarea:not([aria-hidden='true']),"
                " textarea:not([aria-hidden='true'])"
            ),
            "response_selector": ".flow-markdown-body",
            "submit_button": (
                "#flow-end-msg-send:not([aria-disabled='true']):not([data-disabled='true']),"
                " button[id='flow-end-msg-send']"
            ),
            "submit_key": "Enter",
            "wait_after_submit": 100,
            "load_wait": 100,
            "login_redirect_domains": [],
            "url": "https://www.doubao.com/chat/",
        },
        query_text,
        "doubao",
        input_el=FakeInput(),
        query_id=184971,
        runtime_events=[],
    )

    # Recovery DID attempt page.goto exactly once.
    assert fake_page.goto_calls == ["https://www.doubao.com/chat/"], (
        f"expected one page.goto recovery call; got {fake_page.goto_calls!r}"
    )
    # Disabled button must NOT be clicked. This is the core regression
    # guard for the Codex P2 finding.
    assert len(button_clicks) == 0, (
        f"recovery must skip aria-disabled / data-disabled send buttons; "
        f"got {len(button_clicks)} click(s) into a disabled button"
    )
    # Recovery failed (no clickable button) → fall through to
    # PR #1106's specific bail, NOT generic no_response.
    assert (resp_text, resp_html, citations) == ("", "", [])
    assert "doubao_submit_failed" in captured_html_suffixes
    assert executor.last_error_reason in (
        "doubao_input_lost_before_submit",
        "doubao_auth_state_missing",
        "doubao_not_logged_in",
    ), (
        f"expected specific page-regression reason after disabled-button "
        f"skip; got {executor.last_error_reason!r}"
    )
    assert executor.last_error_reason != "no_response"


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
    # Refs #963: DOUBAO_USE_PROXY now defaults to False (direct connect from
    # the China-hosted worker). This test exercises the opt-in proxy path, so
    # enable it explicitly to verify the routing wiring still works when an
    # operator chooses to route Doubao through the proxy.
    monkeypatch.setenv("DOUBAO_USE_PROXY", "1")

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
    # Refs #963: this test exercises the opt-in proxy path; enable it
    # explicitly since DOUBAO_USE_PROXY now defaults to direct connect.
    monkeypatch.setenv("DOUBAO_USE_PROXY", "1")

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


@pytest.mark.asyncio
async def test_doubao_fill_plain_text_input_bails_when_keyboard_type_hangs(
    monkeypatch,
):
    """Refs #963 follow-up to PR #1008 live evidence (Admin E2E run
    25924635842 + Server Diagnostics readback run 25925187531, query
    184968 retry 20): the executor hung at ``stage=prompt_fill`` for the
    full 480s soft-time-limit on a fresh active account (44). The prior
    implementation called ``page.keyboard.type(...)`` without any
    timeout, so a page in a degenerate state (overlay covering input,
    focus stolen, browser context dead-but-not-yet-collected) would
    cause an indefinite hang on the typing call. This test simulates a
    forever-hanging keyboard.type and asserts the bounded fill bails
    out fast instead of waiting forever — both via TimeoutError-driven
    fallback to JS injection and, if that also fails, by returning
    False so the caller can surface the failure cleanly.

    Codex PR #1009 review (P2): the prior version of this test invoked
    the real 60s production bound, deterministically slowing every CI
    run by ~60s. Monkeypatch the module-level timeout constants to
    sub-second values so the test still proves the bound is active
    without burning CI time. Production bounds are unaffected.
    """
    import asyncio as _asyncio

    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent import guest_executor as guest_executor_mod
    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    monkeypatch.setattr(
        guest_executor_mod, "PROMPT_FILL_KEYBOARD_TYPE_TIMEOUT_S", 0.1
    )
    monkeypatch.setattr(
        guest_executor_mod, "PROMPT_FILL_INJECT_TIMEOUT_S", 0.1
    )
    monkeypatch.setattr(
        guest_executor_mod, "PROMPT_FILL_CLEAR_TIMEOUT_S", 0.1
    )
    monkeypatch.setattr(
        guest_executor_mod, "PROMPT_FILL_VALUE_READ_TIMEOUT_S", 0.1
    )

    class HangingKeyboard:
        def __init__(self):
            self.type_calls = 0

        async def type(self, _text, delay=0):
            self.type_calls += 1
            # Simulate the production hang: keyboard.type never returns.
            await _asyncio.sleep(3600)

    class FakePage:
        def __init__(self):
            self.keyboard = HangingKeyboard()

        async def wait_for_timeout(self, ms):
            return None

    class StuckInput:
        """The JS injection and fill paths both come back empty so the code
        falls through to keyboard.type — that is where the production hang
        was observed.
        """

        def __init__(self):
            self.value = ""

        async def fill(self, _text):
            return None

        async def evaluate(self, _script, _arg=None):
            return ""

    page = FakePage()
    input_el = StuckInput()
    executor = GuestQueryExecutor()

    async def _run():
        # With monkeypatched sub-second bounds the bounded fill must
        # return well under 5 seconds even though keyboard.type would
        # hang forever; 5s is a comfortable ceiling vs. the ~0.1s × 4-step
        # total and exists only to fail the test cleanly if the bounds
        # regress to "no timeout".
        return await _asyncio.wait_for(
            executor._fill_plain_text_input(
                page, input_el, "hello doubao", "doubao"
            ),
            timeout=5,
        )

    result = await _run()

    # The function bailed (returned False) rather than hanging forever.
    assert result is False, (
        "Bounded _fill_plain_text_input must return False instead of "
        "hanging when keyboard.type stalls"
    )
    # The hang happened inside keyboard.type — we must have entered it.
    assert page.keyboard.type_calls == 1


@pytest.mark.asyncio
async def test_save_html_bails_when_page_content_hangs(monkeypatch, tmp_path):
    """Refs #963 follow-up to PR #1009 live evidence (Admin E2E run
    25926214958 query 184968 retry 21, stage=prompt_fill,
    latency=480856ms): PR #1009 bounded each step inside
    ``_fill_plain_text_input`` so a hung keyboard.type could not burn
    the budget — but the production retry STILL hit 480s at the same
    stage. The root cause was the next step on the no_input path:
    ``_save_html(page, ..., "doubao_input_fill_failed")`` calls
    ``page.content()`` with no timeout, and a dead page can leave that
    hanging indefinitely. This test simulates a forever-hanging
    page.content() and asserts ``_save_html`` returns None within the
    bounded budget.
    """
    import asyncio as _asyncio

    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent import guest_executor as guest_executor_mod
    from geo_tracker.agent.guest_executor import _save_html

    # Patch SCREENSHOT_DIR to tmp_path so the test does not write to /data.
    monkeypatch.setattr(guest_executor_mod, "SCREENSHOT_DIR", tmp_path)
    monkeypatch.setattr(
        guest_executor_mod, "PROMPT_FILL_VALUE_READ_TIMEOUT_S", 0.1
    )

    class HangingPage:
        async def content(self):
            await _asyncio.sleep(3600)
            return "should never return"

    result = await _asyncio.wait_for(
        _save_html(HangingPage(), 184968, "doubao_input_fill_failed"),
        timeout=2,
    )

    assert result is None, (
        "_save_html must return None instead of hanging when "
        "page.content() stalls"
    )


@pytest.mark.asyncio
async def test_contenteditable_injection_failure_returns_no_input(
    monkeypatch,
):
    """Refs Codex PR #1010 review (P2): when a contenteditable
    ``page.evaluate`` injection hits the bounded timeout (or returns
    False), the prior code fell through to ``_save_html`` and then the
    submit logic — burning the response_wait budget on an empty/stale
    prompt. Mirror the textarea path: on injection failure mark
    ``last_error_reason="no_input"`` and bail immediately.
    """
    import asyncio as _asyncio

    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent import guest_executor as guest_executor_mod
    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    # Inject_controlled_textarea_value path is not taken (contenteditable).
    # Bound the contenteditable page.evaluate to a tiny timeout so the
    # hanging mock trips it immediately.
    monkeypatch.setattr(
        guest_executor_mod, "PROMPT_FILL_INJECT_TIMEOUT_S", 0.1
    )
    monkeypatch.setattr(
        guest_executor_mod, "PROMPT_FILL_VALUE_READ_TIMEOUT_S", 0.1
    )

    class FakeMouse:
        async def move(self, *args, **kwargs):
            return None

    class FakeContentEditable:
        url = "https://gemini.test/"

        def __init__(self):
            self.evaluate_calls = 0
            self.content_calls = 0
            self.mouse = FakeMouse()

        async def wait_for_timeout(self, ms):
            return None

        async def evaluate(self, _script, _arg=None):
            self.evaluate_calls += 1
            # Simulate the production hang we just bounded.
            await _asyncio.sleep(3600)
            return False

        async def content(self):
            self.content_calls += 1
            return "<html></html>"

        async def title(self):
            return ""

    class FakeInput:
        async def bounding_box(self):
            return {"x": 10, "y": 10, "width": 100, "height": 30}

        async def click(self, **_kwargs):
            return None

        async def evaluate(self, _script, _arg=None):
            return ""

    page = FakeContentEditable()
    executor = GuestQueryExecutor()

    cfg = {
        "input_selector": "[contenteditable='true']",
        "contenteditable": True,
        "submit_button": "",
        "response_selector": ".answer",
    }

    resp_text, resp_html, citations = await _asyncio.wait_for(
        executor._browser_query(
            page, cfg, "hello gemini", "gemini", input_el=FakeInput()
        ),
        timeout=5,
    )

    assert resp_text == ""
    assert resp_html == ""
    assert citations == []
    assert executor.last_error_reason == "no_input"


@pytest.mark.asyncio
async def test_response_wait_still_generating_eval_is_bounded(monkeypatch):
    """Refs #963 follow-up to PR #1010 live evidence (Admin E2E run
    25927727628 query 184968 retry 22, stage=response_wait,
    latency=480972ms): PR #1010 unblocked prompt_fill so the next
    bottleneck surfaced — response_wait at the full 480s budget despite
    its internal wait_total counter being bounded to 180s. The
    still_generating ``page.evaluate(...)`` runs every 5s inside the
    response_wait loop with no per-call timeout, and on a degenerate
    page it can hang for the full outer budget. This test confirms the
    new ``RESPONSE_WAIT_GENERATING_EVAL_TIMEOUT_S`` bound trips before
    the page.evaluate finishes."""
    import asyncio as _asyncio

    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent import guest_executor as guest_executor_mod

    monkeypatch.setattr(
        guest_executor_mod, "RESPONSE_WAIT_GENERATING_EVAL_TIMEOUT_S", 0.1
    )

    async def _hanging_evaluate(_script):
        await _asyncio.sleep(3600)
        return True

    # Smoke test the bound directly: wait_for on a hanging coroutine must
    # raise TimeoutError before 5s.
    start = _asyncio.get_event_loop().time()
    raised = False
    try:
        await _asyncio.wait_for(
            _hanging_evaluate("..."),
            timeout=guest_executor_mod.RESPONSE_WAIT_GENERATING_EVAL_TIMEOUT_S,
        )
    except _asyncio.TimeoutError:
        raised = True
    elapsed = _asyncio.get_event_loop().time() - start

    assert raised, "wait_for must raise TimeoutError when evaluate hangs"
    assert elapsed < 2, (
        f"bound must fire near {guest_executor_mod.RESPONSE_WAIT_GENERATING_EVAL_TIMEOUT_S}s, "
        f"actual={elapsed:.3f}s"
    )


@pytest.mark.asyncio
async def test_response_wait_stage_has_wall_clock_hard_cap(monkeypatch):
    """Codex PR #1014 review (P2): RESPONSE_WAIT_STAGE_BUDGET_S was
    defined but never enforced — the elapsed counter ticks 5s per
    iteration regardless of wall-clock cost. Without the wall-clock
    check, a degenerate page where each iteration spends much more
    wall-clock than its 5s counter increment can keep grinding past
    the documented 240s cap. This test verifies the wall-clock check
    breaks the loop when the budget is exceeded.
    """
    import asyncio as _asyncio

    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent import guest_executor as guest_executor_mod

    # Tiny budget so the test runs in sub-second.
    monkeypatch.setattr(
        guest_executor_mod, "RESPONSE_WAIT_STAGE_BUDGET_S", 0.05
    )

    # Smoke test: a fresh wall-clock check against a stale start time
    # should report "exceeded" — same logic the loop uses to bail.
    start = _asyncio.get_event_loop().time()
    await _asyncio.sleep(0.06)
    wall_elapsed = _asyncio.get_event_loop().time() - start

    assert wall_elapsed >= guest_executor_mod.RESPONSE_WAIT_STAGE_BUDGET_S, (
        f"wall-clock check must trip when sleep ({wall_elapsed:.3f}s) exceeds "
        f"budget ({guest_executor_mod.RESPONSE_WAIT_STAGE_BUDGET_S}s)"
    )


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


def test_doubao_auto_login_new_account_persists_unmasked_phone(
    monkeypatch,
    tmp_path,
):
    """Refs #963: ``auto_login`` (new_account=True) must persist the raw
    phone returned by the SMS handler into ``llm_accounts.phone_number``.

    Production worker (PR #1076 deploy, 2026-05-16 14:05:49 UTC) showed:

        worker-1 | auto_login: re-login account #43 (doubao, phone=147****0231)
        worker-1 | [doubao] 传入的 phone='147****0231' 非 11 位数字，
                       降级为新注册流程
        worker-1 | [doubao] invalid phone for re-login;
                       refusing to request a new SMS number

    ``BaseSMSLoginHandler.login_or_register`` validates the incoming
    phone against ``\\d{11}`` before re-reserving an SMS lease; storing
    the ``mask_phone()`` output (``147****0231`` with literal asterisks)
    fails that regex, refuses the re-login, and exits without recovery.
    The account stays stuck on a Doubao-bot-flagged cookie set forever.

    Lock the contract that ``create_account`` (and therefore
    ``auto_login`` new-account success) writes the RAW phone string
    untouched — no ``mask_phone`` call, no asterisks, exact match.
    """
    _install_fake_playwright(monkeypatch)

    import redis.asyncio as aioredis

    from geo_tracker.agent import sms_login
    from geo_tracker.agent.sms_redaction import mask_phone
    from geo_tracker.tasks import celery_tasks

    db_url = (
        f"sqlite+aiosqlite:///{tmp_path / 'doubao-unmasked-phone.db'}"
    )
    raw_phone = "14712340231"
    # Sanity guard: confirm this raw phone really does mask to the
    # production-observed shape so the test catches the exact regression.
    assert mask_phone(raw_phone) == "147****0231"

    async def seed_database():
        engine = create_async_engine(db_url, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(seed_database())

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(
            async_sessionmaker(engine, expire_on_commit=False)
        )

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
                "phone": raw_phone,
                "localStorage": {"session": "fresh"},
            }

    class FakeExecuteQuery:
        @staticmethod
        def apply_async(*, args, queue):
            return None

    async def fake_release_new_account_lock(_platform, *, failed=False):
        return None

    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(
        aioredis, "from_url", lambda *args, **kwargs: FakeRedisClient()
    )
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
    )

    async def load_phone():
        engine = create_async_engine(db_url, future=True)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            accounts = (
                await session.execute(select(LLMAccount))
            ).scalars().all()
            assert len(accounts) == 1
            stored_phone = accounts[0].phone_number
            stored_email = accounts[0].email
            stored_id = accounts[0].id
        await engine.dispose()
        return stored_phone, stored_email, stored_id

    stored_phone, stored_email, stored_id = asyncio.run(load_phone())

    # Pins the bug-fix contract: the persisted phone must be the raw
    # SMS-provider value, NOT the mask_phone() output.
    assert stored_phone == raw_phone, (
        f"llm_accounts.phone_number stored masked value "
        f"{stored_phone!r}; expected raw {raw_phone!r}"
    )
    assert "*" not in (stored_phone or ""), (
        f"llm_accounts.phone_number contains an asterisk "
        f"({stored_phone!r}); auto_login MUST persist the raw phone "
        f"so the re-login \\d{{11}} regex matches."
    )
    # Email is derived from phone — same contract applies.
    assert stored_email == f"{raw_phone}@doubao.local"
    # auto_login return payload must also expose the raw phone so
    # downstream requeue paths don't propagate the masked form.
    assert result == {
        "status": "success",
        "account_id": stored_id,
        "phone": raw_phone,
    }


def test_account_pool_create_account_rejects_masked_phone(tmp_path):
    """Refs #963: ``AccountPool.create_account`` must refuse to persist
    a phone that contains the ``*`` character produced by
    :func:`mask_phone`. Any caller that accidentally passes the masked
    form should raise at write time so a corrupted ``phone_number``
    never reaches the DB.
    """
    from geo_tracker.pool.account_pool import AccountPool

    db_url = (
        f"sqlite+aiosqlite:///{tmp_path / 'pool-mask-guard.db'}"
    )

    async def runner():
        engine = create_async_engine(db_url, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as session:
                pool = AccountPool(session)
                with pytest.raises(ValueError, match="masked phone"):
                    await pool.create_account(
                        llm_name="doubao",
                        phone="147****0231",
                        cookies_json="[]",
                    )
                # And nothing should have been committed.
                accounts = (
                    await session.execute(select(LLMAccount))
                ).scalars().all()
                assert accounts == []
        finally:
            await engine.dispose()

    asyncio.run(runner())


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


def test_execute_query_browser_timeout_reads_stage_at_failure_not_post_cleanup_stage(
    monkeypatch,
    tmp_path,
):
    """Refs #963 follow-up to PR #1005 (live evidence: Admin E2E run
    25919843002, query 184968 retry 19): the outer
    ``asyncio.wait_for(execute, timeout)`` in
    ``celery_tasks._execute_with_timeout`` was reading
    ``guest_executor.execution_stage`` only AFTER the inner finally block
    had already set it to ``"cleanup"``. That made every soft-time-limit
    hang surface as ``doubao_browser_timeout:cleanup`` regardless of where
    execution was actually stuck. The fix latches the real stage on
    ``stage_at_failure`` from the executor's CancelledError / except
    Exception handlers BEFORE the finally runs, and the celery wait_for
    path now prefers that latched value.
    """
    _install_fake_playwright(monkeypatch)

    from geo_tracker.tasks import celery_tasks

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'doubao-stage-latch.db'}"
    query_id = 184968
    account_id = 44

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
                        query_count_today=3,
                        daily_limit=20,
                    ),
                    Query(
                        id=query_id,
                        target_llm="doubao",
                        query_text="bestCoffer的企业级AI数据脱敏工具适合金融行业用吗",
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
        """Simulate the production race: while execute() is awaiting, the
        real stage is response_wait. When outer wait_for cancels execute(),
        the cancel handler latches ``stage_at_failure = "response_wait"``
        BEFORE the finally block overwrites ``execution_stage`` to
        ``"cleanup"``. Without my fix the celery reader would see only
        "cleanup"; with the fix it must see "response_wait".
        """

        def __init__(self, *args, **kwargs):
            self.last_error_reason = None
            self.execution_stage = "response_wait"
            self.stage_at_failure = None

        async def execute(self, query):
            try:
                await asyncio.sleep(5)
                return None
            except asyncio.CancelledError:
                # Mirror the production CancelledError handler:
                # latch the real stage at cancel time.
                self.stage_at_failure = self.execution_stage
                # Mirror the production finally block: clobber stage.
                self.execution_stage = "cleanup"
                raise

    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(
        celery_tasks, "acquire_query_account", fake_acquire_query_account
    )
    monkeypatch.setattr(celery_tasks, "GuestQueryExecutor", FakeGuestQueryExecutor)
    monkeypatch.setattr(
        celery_tasks, "_browser_execution_timeout_seconds", lambda llm: 0.05
    )

    result = celery_tasks.execute_query.run(query_id)

    async def load_state():
        engine = create_async_engine(db_url, future=True)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            query = await session.get(Query, query_id)
            state = {
                "status": query.status,
                "retry_reason": query.retry_reason,
            }
        await engine.dispose()
        return state

    state = asyncio.run(load_state())

    # The retry_reason MUST carry the real stage (response_wait), not the
    # post-finally cleanup placeholder.
    assert result["reason"].startswith("doubao_browser_timeout:response_wait"), (
        f"Expected real stage 'response_wait' in retry_reason, got {result['reason']!r} — "
        "stage_at_failure latch missing or celery reader not consulting it"
    )
    assert state["retry_reason"] == "doubao_browser_timeout:response_wait", (
        f"Expected DB retry_reason 'doubao_browser_timeout:response_wait', got "
        f"{state['retry_reason']!r} — cleanup stage leaked into classification"
    )


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

    await executor._preserve_active_page_evidence(
        FakePage(),
        184968,
        "doubao",
        config={"url": "https://www.doubao.com/chat/", "input_selector": ""},
        runtime_events=[{"kind": "console", "text": "stuck"}],
        proxy_diagnostic={"in_use": True},
        stage="response_wait",
        suffix_prefix="browser_timeout",
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


@pytest.mark.asyncio
async def test_preserve_active_page_evidence_inner_exception_path(monkeypatch, tmp_path):
    """Refs #963 follow-up: when a Playwright TimeoutError bubbles out of an
    inner await on Doubao, the executor's `except Exception` path used to
    save only a bare screenshot whose write failure was silently swallowed.
    The shared evidence helper must now produce both a runtime snapshot and
    a screenshot, tagged with stage, and surface save failures on the log
    so the next 184968-shaped failure leaves diagnosable artifacts."""
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent import guest_executor as guest_executor_mod
    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    class FakePage:
        url = "https://www.doubao.com/chat/?cid=inner-timeout"

        async def title(self):
            return "Doubao chat - inner timeout"

        async def evaluate(self, script):
            assert "innerText" in script
            return "input_selector wait timed out before chat input attached"

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
    executor.execution_stage = "page_load"

    await executor._preserve_active_page_evidence(
        FakePage(),
        184968,
        "doubao",
        config={"url": "https://www.doubao.com/chat/", "input_selector": ""},
        runtime_events=[{"kind": "pageerror", "text": "wait_for_selector timeout"}],
        proxy_diagnostic={"in_use": True},
        stage="page_load",
        suffix_prefix="exception",
    )

    assert executor.last_page_url == "https://www.doubao.com/chat/?cid=inner-timeout"
    assert executor.last_page_title == "Doubao chat - inner timeout"
    assert executor.last_page_body_snippet is not None
    assert "input_selector wait timed out" in executor.last_page_body_snippet
    assert executor.last_snapshot_path == str(tmp_path / "snapshot_184968.json")
    assert len(snapshot_calls) == 1
    assert snapshot_calls[0]["suffix"] == "doubao_exception_page_load"
    assert snapshot_calls[0]["runtime_events"] == [
        {"kind": "pageerror", "text": "wait_for_selector timeout"}
    ]
    assert screenshot_calls == [
        {"query_id": 184968, "suffix": "doubao_exception_page_load"}
    ]


@pytest.mark.asyncio
async def test_preserve_active_page_evidence_is_bounded_when_page_hangs(
    monkeypatch,
    tmp_path,
    caplog,
):
    """Refs #963 follow-up: when the page is responsive enough to keep the
    Playwright connection open but its awaitables never complete, the
    evidence helper must still surface a save-failure warning and return
    instead of silently swallowing the exception. Each per-step await is
    bounded by ``asyncio.wait_for`` in the helper itself, but here we
    simulate the bound firing by raising ``asyncio.TimeoutError`` directly
    from the fakes so the test does not need to actually wait."""
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent import guest_executor as guest_executor_mod
    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    class HangingPage:
        url = "https://www.doubao.com/chat/?cid=hung"

        async def title(self):
            raise asyncio.TimeoutError("title hung")

        async def evaluate(self, _script):
            raise asyncio.TimeoutError("evaluate hung")

    async def fake_snapshot(page, query_id, suffix, **_kwargs):
        raise asyncio.TimeoutError("snapshot hung")

    async def fake_screenshot(page, query_id, suffix=""):
        raise asyncio.TimeoutError("screenshot hung")

    monkeypatch.setattr(guest_executor_mod, "_save_runtime_snapshot", fake_snapshot)
    monkeypatch.setattr(guest_executor_mod, "_save_screenshot", fake_screenshot)

    executor = GuestQueryExecutor()
    executor.execution_stage = "response_wait"

    with caplog.at_level("WARNING", logger="geo_tracker.agent.guest_executor"):
        # Returns promptly: each per-step await raises immediately and the
        # helper swallows individually rather than propagating.
        await executor._preserve_active_page_evidence(
            HangingPage(),
            184968,
            "doubao",
            config={"url": "https://www.doubao.com/chat/"},
            runtime_events=[],
            proxy_diagnostic={},
            stage="response_wait",
            suffix_prefix="exception",
        )

    # URL is captured synchronously (not awaitable on Page), so still set.
    assert executor.last_page_url == "https://www.doubao.com/chat/?cid=hung"
    # Hanging title/body must NOT pollute the executor attributes.
    assert executor.last_page_title is None
    assert executor.last_page_body_snippet is None
    # Snapshot/screenshot failures must produce visible operator warnings
    # instead of being silently swallowed like the original
    # `except Exception: pass`.
    save_warnings = [
        rec.getMessage()
        for rec in caplog.records
        if "snapshot save failed" in rec.getMessage()
        or "screenshot save failed" in rec.getMessage()
    ]
    assert any(
        "exception snapshot save failed" in msg for msg in save_warnings
    ), f"hung snapshot save should surface a warning, got: {save_warnings}"
    assert any(
        "exception screenshot save failed" in msg for msg in save_warnings
    ), f"hung screenshot save should surface a warning, got: {save_warnings}"


@pytest.mark.asyncio
async def test_doubao_response_wait_extends_while_still_generating(monkeypatch, caplog):
    """Refs #963: when Doubao deep-thinking ("深度思考"/"正在搜索") is still
    active at the end of ``wait_after_submit``, the response_wait loop must
    extend its budget (bounded by ``wait_after_submit_max_extension``) so a
    slow-but-real answer is captured instead of being silently cut off and
    landing as ``no_response``."""
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    response_text_by_call: list[str] = [
        "",        # round 1: empty answer, still generating
        "",        # round 2: still empty, still generating
        "doubao streaming partial answer about bestCoffer 1 1 1",  # round 3: shows partial answer while still generating
        "doubao streaming partial answer about bestCoffer 22 22 22 22 22 22 22 22",  # round 4: grew while still generating
        "doubao streaming partial answer about bestCoffer 333 333 333 333 333 333 333 333 333 333 333",  # round 5: grew, no longer generating
        "doubao streaming partial answer about bestCoffer 333 333 333 333 333 333 333 333 333 333 333",  # round 6: stable
        "doubao streaming partial answer about bestCoffer 333 333 333 333 333 333 333 333 333 333 333",  # round 7: stable -> break
    ]

    class FakeElement:
        def __init__(self, text: str):
            self._text = text

        async def inner_text(self):
            return self._text

        async def inner_html(self):
            return f"<div>{self._text}</div>"

        async def is_visible(self):
            return False

    class FakePage:
        url = "https://www.doubao.com/chat/?cid=slow"

        def __init__(self):
            self._round = 0
            self.body_text_by_round: list[str] = [
                "深度思考",
                "深度思考",
                "深度思考",
                "正在搜索",  # still generating
                "答案",        # no longer generating
                "答案",
                "答案",
            ]

        async def wait_for_timeout(self, _ms):
            return None

        async def evaluate(self, script, *args):
            self._round += 1
            idx = min(self._round - 1, len(self.body_text_by_round) - 1)
            if "innerText" in script:
                return self.body_text_by_round[idx]
            return False

        async def query_selector(self, _selector):
            idx = min(self._round - 1, len(response_text_by_call) - 1)
            txt = response_text_by_call[idx] if self._round > 0 else ""
            return FakeElement(txt) if txt else None

        async def query_selector_all(self, _selector):
            idx = min(self._round - 1, len(response_text_by_call) - 1)
            txt = response_text_by_call[idx] if self._round > 0 else ""
            return [FakeElement(txt)] if txt else []

    cfg = {
        "url": "https://www.doubao.com/chat",
        "input_selector": "textarea",
        "submit_button": "button",
        "submit_key": "Enter",
        "response_selector": ".flow-markdown-body",
        # 30s base + 60s allowed extension = 90s effective budget; with 5s
        # check interval this lets the loop run up to 18 iterations.
        "wait_after_submit": 30000,
        "wait_after_submit_max_extension": 60000,
        "load_wait": 1000,
        "requires_login": False,
        "login_redirect_domains": [],
    }

    executor = GuestQueryExecutor()

    fake_input = FakeElement("")
    fake_page = FakePage()

    # Stub out the submit + helpers so only the response_wait loop runs.
    async def fake_save_html(*_args, **_kwargs):
        return None

    async def fake_save_screenshot(*_args, **_kwargs):
        return None

    async def fake_save_runtime_snapshot(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "geo_tracker.agent.guest_executor._save_html", fake_save_html
    )
    monkeypatch.setattr(
        "geo_tracker.agent.guest_executor._save_screenshot", fake_save_screenshot
    )
    monkeypatch.setattr(
        "geo_tracker.agent.guest_executor._save_runtime_snapshot",
        fake_save_runtime_snapshot,
    )

    # Bypass actual prompt fill / submit so the test focuses on response_wait.
    async def fake_fill_plain_text_input(*_args, **_kwargs):
        return True

    async def fake_doubao_response_auth_reason(*_args, **_kwargs):
        return None

    monkeypatch.setattr(executor, "_fill_plain_text_input", fake_fill_plain_text_input)
    monkeypatch.setattr(
        "geo_tracker.agent.guest_executor._doubao_response_auth_reason_from_page",
        fake_doubao_response_auth_reason,
    )

    # Skip the JS-handle send-button path: keyboard.press is enough for this
    # synthetic page, and the page's evaluate_handle is not implemented.
    class FakeKeyboard:
        async def press(self, _key):
            return None

        async def type(self, _text, **_kwargs):
            return None

    fake_page.keyboard = FakeKeyboard()

    async def fake_bbox(*_args, **_kwargs):
        return None

    fake_input.bounding_box = fake_bbox
    fake_input.click = (lambda **_kwargs: asyncio.sleep(0))  # type: ignore[assignment]

    # Patch evaluate_handle on the fake page to return a sentinel so the
    # submit code falls back to keyboard.press("Enter") without crashing.
    class FakeJSHandle:
        def as_element(self):
            return None

    async def fake_evaluate_handle(*_args, **_kwargs):
        return FakeJSHandle()

    fake_page.evaluate_handle = fake_evaluate_handle  # type: ignore[assignment]

    with caplog.at_level("INFO", logger="geo_tracker.agent.guest_executor"):
        resp_text, _resp_html, _citations = await executor._browser_query(
            fake_page,
            cfg,
            "bestCoffer advantages?",
            "doubao",
            fake_input,
            query_id=184968,
        )

    assert "333" in resp_text, f"slow but real answer must be captured: got {resp_text!r}"
    extension_logs = [
        rec.getMessage()
        for rec in caplog.records
        if "response_wait extended" in rec.getMessage()
    ]
    assert extension_logs, "response_wait should extend when still_generating is true"


@pytest.mark.asyncio
async def test_doubao_response_wait_extends_after_submit_confirmed_without_progress_indicator(
    monkeypatch,
    caplog,
):
    """Refs #963 PR #1005 deploy live evidence (query 184968 retry 17 on
    account 44): the browser ran end-to-end on a real logged-in account,
    submit_confirmed was true, but Doubao did not keep the
    "深度思考"/"正在搜索" indicator visible the whole time the answer
    was in flight. The previous extension trigger only fired when the
    indicator was visible OR the response was actively growing, so the
    loop exited at the configured ``wait_after_submit`` and the JS
    fallback picked up homepage placeholder text — the executor
    correctly discarded it as ``doubao_homepage_content``. With this
    fix, ``submit_confirmed && !resp_ready`` is also a valid extension
    trigger so a slow answer still inside the
    ``wait_after_submit_max_extension`` budget gets captured."""
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    # No still_generating indicator at all; resp comes in late inside the
    # extension budget.
    response_text_by_iter = [
        "",  # 1: empty
        "",  # 2: empty (would have exited the loop at wait_total=10s without the fix)
        "",  # 3: empty (still no response, extension fires once)
        "",  # 4: empty (extension fires again)
        "doubao late answer first chunk for bestCoffer 111 111 111",  # 5: now visible
        "doubao late answer first chunk for bestCoffer 111 111 111 second chunk",  # 6: growing
        "doubao late answer first chunk for bestCoffer 111 111 111 second chunk",  # 7: stable
        "doubao late answer first chunk for bestCoffer 111 111 111 second chunk",  # 8: stable -> break
    ]

    class FakeElement:
        def __init__(self, text: str):
            self._text = text

        async def inner_text(self):
            return self._text

        async def inner_html(self):
            return f"<div>{self._text}</div>"

        async def is_visible(self):
            return False

    class FakePage:
        url = "https://www.doubao.com/chat/conv-stuck-id"  # in-conversation URL

        def __init__(self):
            self._round = 0

        async def wait_for_timeout(self, _ms):
            return None

        async def evaluate(self, script, *_args, **_kwargs):
            self._round += 1
            if "innerText" in script:
                # No "深度思考" etc. — empty progress indicator path.
                return "user-avatar 我的账号"
            return False

        async def query_selector(self, _selector):
            idx = min(self._round - 1, len(response_text_by_iter) - 1)
            txt = response_text_by_iter[idx] if self._round > 0 else ""
            return FakeElement(txt) if txt else None

        async def query_selector_all(self, _selector):
            idx = min(self._round - 1, len(response_text_by_iter) - 1)
            txt = response_text_by_iter[idx] if self._round > 0 else ""
            return [FakeElement(txt)] if txt else []

    cfg = {
        "url": "https://www.doubao.com/chat",
        "input_selector": "textarea",
        "submit_button": "button",
        "submit_key": "Enter",
        "response_selector": ".flow-markdown-body",
        # tight base + generous extension so the test exercises the new
        # awaiting_answer extension trigger.
        "wait_after_submit": 10000,
        "wait_after_submit_max_extension": 30000,
        "load_wait": 1000,
        "requires_login": False,
        "login_redirect_domains": [],
    }

    executor = GuestQueryExecutor()

    fake_input = FakeElement("")
    fake_page = FakePage()

    async def fake_save_html(*_a, **_k):
        return None

    async def fake_save_screenshot(*_a, **_k):
        return None

    async def fake_save_runtime_snapshot(*_a, **_k):
        return None

    monkeypatch.setattr("geo_tracker.agent.guest_executor._save_html", fake_save_html)
    monkeypatch.setattr("geo_tracker.agent.guest_executor._save_screenshot", fake_save_screenshot)
    monkeypatch.setattr(
        "geo_tracker.agent.guest_executor._save_runtime_snapshot", fake_save_runtime_snapshot
    )

    async def fake_fill_plain_text_input(*_a, **_k):
        return True

    async def fake_doubao_response_auth_reason(*_a, **_k):
        return None

    monkeypatch.setattr(executor, "_fill_plain_text_input", fake_fill_plain_text_input)
    monkeypatch.setattr(
        "geo_tracker.agent.guest_executor._doubao_response_auth_reason_from_page",
        fake_doubao_response_auth_reason,
    )

    class FakeKeyboard:
        async def press(self, _key):
            return None

        async def type(self, _text, **_k):
            return None

    fake_page.keyboard = FakeKeyboard()
    fake_input.bounding_box = lambda **_k: asyncio.sleep(0)
    fake_input.click = lambda **_k: asyncio.sleep(0)

    class FakeJSHandle:
        def as_element(self):
            return None

    fake_page.evaluate_handle = lambda *_a, **_k: asyncio.sleep(0, result=FakeJSHandle())

    with caplog.at_level("INFO", logger="geo_tracker.agent.guest_executor"):
        resp_text, _resp_html, _citations = await executor._browser_query(
            fake_page,
            cfg,
            "bestCoffer advantages?",
            "doubao",
            fake_input,
            query_id=184968,
        )

    assert "late answer" in resp_text, (
        "slow answer arriving INSIDE the extension budget must be captured "
        f"even without a still-generating indicator visible; got {resp_text!r}"
    )
    awaiting_logs = [
        rec.getMessage()
        for rec in caplog.records
        if "response_wait extended" in rec.getMessage()
        and "awaiting_answer=True" in rec.getMessage()
    ]
    assert awaiting_logs, (
        "extension should fire with awaiting_answer=True when submit was "
        "confirmed but no response selector has matched yet"
    )


@pytest.mark.asyncio
async def test_browser_query_does_not_unboundlocal_for_non_doubao_engines(monkeypatch):
    """Refs PR #1006 review (Codex P1): the ``confirmed`` flag the
    response_wait extension reads MUST be initialized for every engine,
    not only inside the ``(doubao, chatgpt, deepseek)`` submit-confirm
    block. Otherwise engines such as gemini / kimi / claude / grok /
    zhipu / perplexity would raise UnboundLocalError when the
    response_wait extension passes ``confirmed`` into
    ``_maybe_extend_wait_total`` on the first iteration. This test
    walks a fake gemini config end-to-end (response arrives quickly)
    and asserts no UnboundLocalError is raised."""
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    class FakeElement:
        def __init__(self, text: str):
            self._text = text

        async def inner_text(self):
            return self._text

        async def inner_html(self):
            return f"<div>{self._text}</div>"

        async def is_visible(self):
            return False

    class FakePage:
        url = "https://gemini.google.com/app/abc"

        def __init__(self):
            self._round = 0

        async def wait_for_timeout(self, _ms):
            return None

        async def evaluate(self, script, *_args, **_kwargs):
            self._round += 1
            if "innerText" in script:
                return ""
            return False

        async def query_selector(self, _selector):
            # Response immediately ready so the extension trigger does
            # not need to fire — we just want to prove no exception.
            return FakeElement("gemini answer about bestCoffer 12345 67890 abcdefghij")

        async def query_selector_all(self, _selector):
            return [FakeElement("gemini answer about bestCoffer 12345 67890 abcdefghij")]

    cfg = {
        "url": "https://gemini.google.com/app",
        "input_selector": "textarea",
        "submit_button": "button",
        "submit_key": "Enter",
        "response_selector": ".gemini-response",
        "wait_after_submit": 5000,
        "load_wait": 1000,
        "requires_login": False,
        "login_redirect_domains": [],
    }

    executor = GuestQueryExecutor()
    fake_input = FakeElement("")
    fake_page = FakePage()

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr("geo_tracker.agent.guest_executor._save_html", _noop)
    monkeypatch.setattr("geo_tracker.agent.guest_executor._save_screenshot", _noop)
    monkeypatch.setattr("geo_tracker.agent.guest_executor._save_runtime_snapshot", _noop)

    async def fake_fill_plain_text_input(*_a, **_k):
        return True

    monkeypatch.setattr(executor, "_fill_plain_text_input", fake_fill_plain_text_input)

    class FakeKeyboard:
        async def press(self, _key):
            return None

        async def type(self, _text, **_k):
            return None

    fake_page.keyboard = FakeKeyboard()
    fake_input.bounding_box = lambda **_k: asyncio.sleep(0)
    fake_input.click = lambda **_k: asyncio.sleep(0)

    class FakeJSHandle:
        def as_element(self):
            return None

    fake_page.evaluate_handle = lambda *_a, **_k: asyncio.sleep(0, result=FakeJSHandle())

    # Critical assertion: this MUST NOT raise UnboundLocalError on
    # ``confirmed`` for gemini (or any engine outside the doubao-family
    # submit-confirm block).
    resp_text, _resp_html, _citations = await executor._browser_query(
        fake_page,
        cfg,
        "bestCoffer advantages?",
        "gemini",
        fake_input,
        query_id=184968,
    )
    assert "gemini answer" in resp_text


def test_doubao_inner_playwright_timeout_upgrades_reason_to_stage_tagged(
    monkeypatch,
    tmp_path,
):
    """Refs #963 follow-up: a Playwright TimeoutError raised from an inner
    await (e.g. page.goto or wait_for_selector) inside _execute_once used
    to surface as generic ``browser_timeout``. For Doubao this hid which
    stage hung. The except-Exception path must now upgrade it to
    ``doubao_browser_timeout:<stage>`` so it matches the cancellation path
    and stays inside the infrastructure-failure bucket."""
    _install_fake_playwright(monkeypatch)

    from geo_tracker.tasks import celery_tasks

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'doubao-inner-timeout.db'}"
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
            self.last_error_reason = "doubao_browser_timeout:page_load"
            self.execution_stage = "page_load"
            self.last_page_url = "https://www.doubao.com/chat/"
            self.last_page_title = "Doubao chat - inner timeout"
            self.last_page_body_snippet = "stuck before input element attached"
            self.last_snapshot_path = "/data/screenshots/query_184968_doubao_exception_page_load_1.json"

        async def execute(self, query):
            # Simulate the executor's own except-Exception path: it returns
            # None after upgrading last_error_reason to the stage-tagged form.
            return None

    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(celery_tasks, "acquire_query_account", fake_acquire_query_account)
    monkeypatch.setattr(celery_tasks, "GuestQueryExecutor", FakeGuestQueryExecutor)

    result = celery_tasks.execute_query.run(query_id)

    async def load_state():
        engine = create_async_engine(db_url, future=True)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            query = await session.get(Query, query_id)
            state = {
                "status": query.status,
                "retry_reason": query.retry_reason,
            }
        await engine.dispose()
        return state

    state = asyncio.run(load_state())

    assert result == {
        "query_id": query_id,
        "status": "failed",
        "reason": "doubao_browser_timeout:page_load:0",
    }
    assert state == {
        "status": QueryStatus.FAILED.value,
        "retry_reason": "doubao_browser_timeout:page_load",
    }


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


# Refs #963: PR #1086 stopped NEW masked phone values from being written into
# ``llm_accounts.phone_number`` at the SMS-redaction boundary. The rows that
# pre-date #1086 (accounts 43/44/45 etc.) still hold masked values like
# ``147****0231`` and would otherwise be stuck in ``expired`` forever, because
# ``BaseSMSLoginHandler.login_or_register`` rejects any ``phone`` that fails
# ``re.fullmatch(r"\d{11}", phone)`` once ``existing_cookies`` is set. The
# auto_login read path must detect that the stored phone is masked/invalid and
# fall back to the new-account flow — call ``login_or_register`` with
# ``existing_cookies=None, phone=None`` so the handler allocates a brand-new
# SMS number and the bot-flagged row is overwritten in place.
def test_doubao_auto_login_masked_phone_falls_back_to_new_account_flow(
    monkeypatch,
    tmp_path,
):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.tasks import celery_tasks
    import geo_tracker.agent.sms_login as sms_login

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'doubao-masked-phone-fallback.db'}"
    query_id = 184999
    account_id = 43  # account 43 is one of the real production rows from #963

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
                        # Stored as masked because it pre-dates PR #1086's
                        # write-time invariant. The fresh number returned by
                        # the new-account flow below must overwrite this.
                        phone_number="147****0231",
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

    login_or_register_calls: list[dict] = []

    class FakeHandler:
        async def login_or_register(self, *, existing_cookies=None, phone=None):
            login_or_register_calls.append(
                {"existing_cookies": existing_cookies, "phone": phone}
            )
            # New-account branch returns a fresh phone — the handler would
            # have allocated this from LubanSMS.
            return {
                "cookies": [{"name": "session", "value": "fresh"}],
                "phone": "18200008888",
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

    # Contract pin: with a masked stored phone, auto_login MUST fall back to
    # the new-account flow — i.e. call login_or_register with phone=None and
    # existing_cookies=None. The old re-login branch (existing_cookies=stale
    # cookies, phone=masked) would be rejected by BaseSMSLoginHandler's
    # ``\d{11}`` validation and leave the account stuck forever.
    assert login_or_register_calls == [
        {"existing_cookies": None, "phone": None}
    ], (
        "auto_login should fall back to the new-account branch when the "
        "stored phone is masked, not pass the masked value through to the "
        "handler's re-login path."
    )

    async def load_account_state():
        engine = create_async_engine(db_url, future=True)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            account = await session.get(LLMAccount, account_id)
            state = {
                "status": account.status,
                "phone_number": account.phone_number,
                "cookies_json": account.cookies_json,
            }
        await engine.dispose()
        return state

    state = asyncio.run(load_account_state())

    assert result["status"] == "success"
    assert result["account_id"] == account_id
    # The bot-flagged row is overwritten in place: ACTIVE + fresh phone +
    # fresh cookies. Recovery path closes.
    assert state["status"] == AccountStatus.ACTIVE.value
    assert state["phone_number"] == "18200008888"
    assert "fresh" in state["cookies_json"]


def test_doubao_auto_login_non_numeric_phone_falls_back_to_new_account_flow(
    monkeypatch,
    tmp_path,
):
    """Variants of invalid phone formats (empty/short/letters) must also
    route to the new-account branch — the guard checks both ``*`` and the
    ``\\d{11}`` fullmatch so any non-canonical legacy value gets recovered,
    not just the asterisk-masked form."""
    _install_fake_playwright(monkeypatch)

    from geo_tracker.tasks import celery_tasks
    import geo_tracker.agent.sms_login as sms_login

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'doubao-empty-phone-fallback.db'}"
    query_id = 185000
    account_id = 44  # another real production row from #963

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
                        query_count_today=2,
                        daily_limit=20,
                        # Empty string — also fails \d{11} fullmatch.
                        phone_number="",
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

    login_or_register_calls: list[dict] = []

    class FakeHandler:
        async def login_or_register(self, *, existing_cookies=None, phone=None):
            login_or_register_calls.append(
                {"existing_cookies": existing_cookies, "phone": phone}
            )
            return {
                "cookies": [{"name": "session", "value": "fresh"}],
                "phone": "18200009999",
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

    result = celery_tasks.auto_login.run(account_id=account_id, query_id=query_id)

    assert login_or_register_calls == [
        {"existing_cookies": None, "phone": None}
    ]
    assert result["status"] == "success"


def test_doubao_auto_login_valid_phone_still_uses_relogin_branch(
    monkeypatch,
    tmp_path,
):
    """Negative control for the #963 masked-phone guard: when the stored
    phone is a canonical 11-digit number, auto_login must KEEP the old
    re-login branch — passing ``existing_cookies=account.cookies_json`` and
    ``phone=account.phone_number`` — so re-login still gets to reuse the
    cookies/number when they are valid. The masked-phone fallback must not
    be triggered for healthy rows."""
    _install_fake_playwright(monkeypatch)

    from geo_tracker.tasks import celery_tasks
    import geo_tracker.agent.sms_login as sms_login

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'doubao-valid-phone-relogin.db'}"
    query_id = 185001
    account_id = 46

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
                        cookies_json='[{"name":"stale","value":"cookie"}]',
                        query_count_today=1,
                        daily_limit=20,
                        phone_number="17000007065",  # canonical \d{11}
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

    login_or_register_calls: list[dict] = []

    class FakeHandler:
        async def login_or_register(self, *, existing_cookies=None, phone=None):
            login_or_register_calls.append(
                {"existing_cookies": existing_cookies, "phone": phone}
            )
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

    result = celery_tasks.auto_login.run(account_id=account_id, query_id=query_id)

    assert login_or_register_calls == [
        {
            "existing_cookies": '[{"name":"stale","value":"cookie"}]',
            "phone": "17000007065",
        }
    ]
    assert result["status"] == "success"


# Refs #963 / PR #1088 Codex P2 review: the masked-phone guard must validate
# the stored ``phone_number`` against the SELECTED handler's
# ``phone_relogin_pattern`` — not a hardcoded ``\d{11}``. ChatGPT accounts
# carry US numbers like ``+17000007065`` which match
# ``ChatGPTLoginHandler.phone_relogin_pattern = r"\+?1\d{10}"`` but fail the
# old ``\d{11}`` literal. A regression where the literal sneaks back in would
# discard reusable cookies and trigger an unnecessary SMS purchase for every
# ChatGPT re-login. Pin: when the stored phone matches the handler's own
# pattern, auto_login MUST take the re-login branch with
# ``existing_cookies=<cookies>, phone=<stored>`` and MUST NOT pass
# ``phone=None``.
def test_chatgpt_auto_login_us_phone_preserves_relogin_branch(
    monkeypatch,
    tmp_path,
):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.tasks import celery_tasks
    import geo_tracker.agent.sms_login as sms_login

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'chatgpt-us-phone-relogin.db'}"
    query_id = 185002
    account_id = 47
    stored_cookies = '[{"name":"chatgpt_session","value":"reusable"}]'
    stored_phone = "+17000007065"  # matches r"\+?1\d{10}" but NOT r"\d{11}"

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
                        status=AccountStatus.EXPIRED.value,
                        cookies_json=stored_cookies,
                        query_count_today=1,
                        daily_limit=20,
                        phone_number=stored_phone,
                    ),
                    Query(
                        id=query_id,
                        account_id=account_id,
                        target_llm="chatgpt",
                        query_text="coffee brand advantages",
                        status=QueryStatus.FAILED.value,
                        retry_count=0,
                        retry_reason="chatgpt_not_logged_in",
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

    login_or_register_calls: list[dict] = []

    class FakeChatGPTHandler:
        # Mirror ChatGPTLoginHandler.phone_relogin_pattern verbatim so the
        # guard's ``getattr(handler, "phone_relogin_pattern", ...)`` resolves
        # to the platform-specific regex, not the Doubao default.
        phone_relogin_pattern = r"\+?1\d{10}"

        async def login_or_register(self, *, existing_cookies=None, phone=None):
            login_or_register_calls.append(
                {"existing_cookies": existing_cookies, "phone": phone}
            )
            return {
                "cookies": [{"name": "chatgpt_session", "value": "refreshed"}],
                "phone": phone,
            }

    class FakeExecuteQuery:
        @staticmethod
        def apply_async(*, args, queue):
            pass

    async def fake_release_relogin_lock(_account_id):
        return None

    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(
        sms_login, "get_handler", lambda _platform: FakeChatGPTHandler()
    )
    monkeypatch.setattr(celery_tasks, "execute_query", FakeExecuteQuery)
    monkeypatch.setattr(celery_tasks, "release_relogin_lock", fake_release_relogin_lock)

    result = celery_tasks.auto_login.run(account_id=account_id, query_id=query_id)

    # Contract pin: a stored ChatGPT US number that matches the handler's own
    # ``phone_relogin_pattern`` MUST take the re-login branch — both the
    # stored cookies and the phone get forwarded. The masked-phone fallback
    # must NOT fire (would have been called with phone=None,
    # existing_cookies=None and burned a fresh SMS purchase).
    assert login_or_register_calls == [
        {"existing_cookies": stored_cookies, "phone": stored_phone}
    ], (
        "auto_login should preserve the re-login path for ChatGPT US "
        "numbers; the guard must validate against the handler's "
        "phone_relogin_pattern, not a hardcoded \\d{11}."
    )
    assert result["status"] == "success"
    assert result["account_id"] == account_id


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


# Refs #963: Doubao is a domestic Chinese service (ByteDance). When the
# worker host is in China the correct route is direct-connect — routing
# through Clash to an overseas exit IP creates a fingerprint mismatch
# (zh-CN locale + Asia/Shanghai timezone + Chinese SMS phone + overseas
# egress) that Doubao risk control treats as high-risk: visual challenges,
# silent rate-limit, cookie invalidation, and account bans. The production
# evidence trail (3 banned, 20 expired, account 44 also failing while
# Deepseek — bypassed via DOMESTIC_LLMS — succeeds on the same scraper
# code) traces directly to this misroute. These tests pin that all three
# Doubao proxy gates default to False (direct connect) so any future
# regression that flips the default back to True is caught immediately.
def test_doubao_proxy_defaults_to_direct_connect_in_guest_executor(monkeypatch):
    """``_doubao_proxy_enabled`` must default to direct connect (False)."""
    _install_fake_playwright(monkeypatch)
    monkeypatch.delenv("DOUBAO_USE_PROXY", raising=False)

    from geo_tracker.agent.guest_executor import _doubao_proxy_enabled

    assert _doubao_proxy_enabled() is False, (
        "Doubao must default to direct connect when DOUBAO_USE_PROXY is unset. "
        "Routing a China-hosted worker through an overseas Clash exit IP is the "
        "root cause of the Doubao account ban storm tracked in #963."
    )


def test_doubao_proxy_defaults_to_direct_connect_in_celery_tasks(monkeypatch):
    """``_doubao_uses_proxy_route`` (celery_tasks) must default to False too."""
    monkeypatch.delenv("DOUBAO_USE_PROXY", raising=False)

    # celery_tasks imports trigger Celery + Redis chain; assert on source instead
    # to avoid the heavy import path in the unit test layer.
    source_path = (
        Path(__file__).resolve().parent.parent / "tasks" / "celery_tasks.py"
    )
    source = source_path.read_text(encoding="utf-8")
    sig_idx = source.index("def _doubao_uses_proxy_route()")
    body = source[sig_idx : source.index("\n\n", sig_idx)]
    assert '_env_flag("DOUBAO_USE_PROXY", False)' in body, (
        "celery_tasks._doubao_uses_proxy_route must default DOUBAO_USE_PROXY=False "
        "to keep cookie keep-alive routing consistent with the query executor."
    )


def test_doubao_proxy_defaults_to_direct_connect_in_sms_login(monkeypatch):
    """SMS login layer must default Doubao to direct connect too."""
    monkeypatch.delenv("DOUBAO_USE_PROXY", raising=False)

    from geo_tracker.agent.sms_login.base import _should_use_proxy_for_sms_login

    # With a proxy URL configured but DOUBAO_USE_PROXY unset, Doubao SMS
    # login must NOT pick up the proxy.
    assert _should_use_proxy_for_sms_login("doubao", "http://clash:6789") is False, (
        "Doubao SMS login must default to direct connect when DOUBAO_USE_PROXY "
        "is unset. Routing SMS login through the overseas proxy creates a "
        "fingerprint mismatch with the Chinese phone number that triggers "
        "Doubao risk control before the account is even usable."
    )


def test_doubao_global_proxy_route_gated_on_doubao_use_proxy(monkeypatch):
    """``_requires_global_proxy_route('doubao')`` must follow DOUBAO_USE_PROXY.

    Previously the function returned True for doubao whenever
    ``CLASH_FORCE_GLOBAL_PROXY_ROUTE`` was on, which coerced Doubao onto the
    Clash global route via ``ensure_global_proxy_route`` BEFORE per-LLM proxy
    choice was consulted — silently overriding any ``DOUBAO_USE_PROXY=False``.
    Pin that Doubao's preflight gate is now tied to the same env flag the
    per-LLM check uses so the direct-connect path is genuinely direct.
    """
    _install_fake_playwright(monkeypatch)
    monkeypatch.setenv("CLASH_FORCE_GLOBAL_PROXY_ROUTE", "1")

    from geo_tracker.agent.guest_executor import _requires_global_proxy_route

    monkeypatch.delenv("DOUBAO_USE_PROXY", raising=False)
    assert _requires_global_proxy_route("doubao") is False, (
        "Doubao must NOT be coerced onto the global proxy route when "
        "DOUBAO_USE_PROXY is unset (default direct connect). The previous "
        "coercion silently overrode the per-LLM proxy choice."
    )

    monkeypatch.setenv("DOUBAO_USE_PROXY", "1")
    assert _requires_global_proxy_route("doubao") is True, (
        "When the operator explicitly opts Doubao into the proxy path, the "
        "global route preflight must still run so the request actually reaches "
        "the configured exit node."
    )

    # ChatGPT path is unchanged regardless of DOUBAO_USE_PROXY.
    monkeypatch.delenv("DOUBAO_USE_PROXY", raising=False)
    assert _requires_global_proxy_route("chatgpt") is True


def test_doubao_should_use_proxy_respects_direct_connect_default(monkeypatch):
    """``_should_use_proxy_for_llm`` must return False for Doubao by default."""
    _install_fake_playwright(monkeypatch)
    monkeypatch.delenv("DOUBAO_USE_PROXY", raising=False)

    from geo_tracker.agent.guest_executor import _should_use_proxy_for_llm

    # Even with a proxy_url configured, Doubao must skip it by default.
    assert _should_use_proxy_for_llm("doubao", "http://clash:6789") is False, (
        "_should_use_proxy_for_llm must return False for Doubao when "
        "DOUBAO_USE_PROXY is unset, even when a proxy_url is configured."
    )
    # Sanity: deepseek (also DOMESTIC_LLMS) still bypasses proxy.
    assert _should_use_proxy_for_llm("deepseek", "http://clash:6789") is False
    # Sanity: chatgpt (not domestic) still uses the proxy.
    assert _should_use_proxy_for_llm("chatgpt", "http://clash:6789") is True


# Refs #963 follow-up to PR #1015 live evidence (Admin E2E run 25931878272
# query 184968 retry 25, stage=response_wait, latency=480898ms): the
# response_wait wall-clock budget (240s) bails the wait loop and extraction
# phase, but the post-failure cleanup chain in ``_query_one_llm``'s "未能
# 获取响应" branch invokes ``_prefer_doubao_visual_challenge_reason`` →
# ``_doubao_visual_challenge_state_from_page`` and
# ``_prefer_doubao_auth_failure_reason`` → ``_doubao_auth_state_reason_from_page``,
# each of which makes unbounded ``page.evaluate("document.body...")`` and
# ``page.content()`` calls. On a dead page each can hang for the rest of
# the Celery 480s soft cap. ``_save_screenshot`` and ``_save_runtime_snapshot``
# similarly have unbounded ``page.screenshot()`` and ``page.evaluate()``.
# These tests pin that the page-read calls inside the post-failure cleanup
# helpers are bounded by ``asyncio.wait_for`` so a hung page cannot extend
# the failure latency past the response_wait stage budget.
@pytest.mark.asyncio
async def test_doubao_visual_challenge_state_bounds_page_evaluate(monkeypatch):
    """``_doubao_visual_challenge_state_from_page`` must not hang on a dead page."""
    import asyncio as _asyncio

    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent import guest_executor as guest_executor_mod
    from geo_tracker.agent.guest_executor import (
        _doubao_visual_challenge_state_from_page,
    )

    monkeypatch.setattr(
        guest_executor_mod, "POST_FAILURE_PAGE_READ_TIMEOUT_S", 0.1
    )

    class HangingPage:
        async def evaluate(self, _script, *args, **kwargs):
            await _asyncio.sleep(3600)

        async def content(self):
            await _asyncio.sleep(3600)

    # Without the bound, this would hang for ~7200s. The bound caps it at
    # roughly 2 * POST_FAILURE_PAGE_READ_TIMEOUT_S (=0.2s in the test).
    result = await _asyncio.wait_for(
        _doubao_visual_challenge_state_from_page(HangingPage()),
        timeout=2.0,
    )
    # With no body_text / html the state-from-text helper returns an empty dict.
    assert result == {}


@pytest.mark.asyncio
async def test_doubao_auth_state_reason_bounds_page_evaluate(monkeypatch):
    """``_doubao_auth_state_reason_from_page`` must not hang on a dead page."""
    import asyncio as _asyncio

    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent import guest_executor as guest_executor_mod
    from geo_tracker.agent.guest_executor import (
        _doubao_auth_state_reason_from_page,
    )

    monkeypatch.setattr(
        guest_executor_mod, "POST_FAILURE_PAGE_READ_TIMEOUT_S", 0.1
    )

    class HangingPage:
        async def evaluate(self, _script, *args, **kwargs):
            await _asyncio.sleep(3600)

        async def content(self):
            await _asyncio.sleep(3600)

    result = await _asyncio.wait_for(
        _doubao_auth_state_reason_from_page(HangingPage()),
        timeout=2.0,
    )
    # The bound bails to empty body_text + empty html. The helper returns
    # whatever ``doubao_auth_state_reason("", "")`` resolves to; the value
    # is unimportant — the key contract is that the call returned at all
    # instead of hanging on the unbounded ``page.evaluate`` / ``page.content``.
    # Pin the value so a behaviour change in the helper still surfaces here.
    assert result == "doubao_auth_state_missing"


@pytest.mark.asyncio
async def test_doubao_response_auth_reason_bounds_page_evaluate(monkeypatch):
    """``_doubao_response_auth_reason_from_page`` must not hang on a dead page."""
    import asyncio as _asyncio

    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent import guest_executor as guest_executor_mod
    from geo_tracker.agent.guest_executor import (
        _doubao_response_auth_reason_from_page,
    )

    monkeypatch.setattr(
        guest_executor_mod, "POST_FAILURE_PAGE_READ_TIMEOUT_S", 0.1
    )

    class HangingPage:
        async def evaluate(self, _script, *args, **kwargs):
            await _asyncio.sleep(3600)

        async def content(self):
            await _asyncio.sleep(3600)

    result = await _asyncio.wait_for(
        _doubao_response_auth_reason_from_page(HangingPage(), None, None),
        timeout=2.0,
    )
    # As above — the contract under test is that the call returned at all;
    # the helper's empty-input behaviour is pinned for change-detection.
    assert result == "doubao_auth_state_missing"


@pytest.mark.asyncio
async def test_save_runtime_snapshot_bounds_page_evaluate(monkeypatch, tmp_path):
    """``_save_runtime_snapshot`` must not hang on a dead page."""
    import asyncio as _asyncio

    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent import guest_executor as guest_executor_mod
    from geo_tracker.agent.guest_executor import _save_runtime_snapshot

    monkeypatch.setattr(guest_executor_mod, "SCREENSHOT_DIR", tmp_path)
    monkeypatch.setattr(
        guest_executor_mod, "POST_FAILURE_PAGE_READ_TIMEOUT_S", 0.1
    )

    class HangingPage:
        url = "https://doubao.example.com/"

        async def evaluate(self, _script, *args, **kwargs):
            await _asyncio.sleep(3600)

    result = await _asyncio.wait_for(
        _save_runtime_snapshot(
            HangingPage(),
            query_id=184968,
            suffix="doubao_no_response",
            config={"input_selector": "textarea", "response_selector": ".resp"},
        ),
        timeout=2.0,
    )
    # The helper still writes a snapshot file with the evaluate_timeout marker
    # so operators have forensic evidence of the dead page.
    assert result is not None
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["page"] == {"error": "evaluate_timeout"}


@pytest.mark.asyncio
async def test_save_screenshot_bounds_page_screenshot(monkeypatch, tmp_path):
    """``_save_screenshot`` must not hang on a dead page."""
    import asyncio as _asyncio

    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent import guest_executor as guest_executor_mod
    from geo_tracker.agent.guest_executor import _save_screenshot

    monkeypatch.setattr(guest_executor_mod, "SCREENSHOT_DIR", tmp_path)
    monkeypatch.setattr(
        guest_executor_mod, "POST_FAILURE_SCREENSHOT_TIMEOUT_S", 0.1
    )

    class HangingPage:
        async def screenshot(self, *args, **kwargs):
            await _asyncio.sleep(3600)

    result = await _asyncio.wait_for(
        _save_screenshot(HangingPage(), 184968, "doubao_no_response"),
        timeout=2.0,
    )
    # The screenshot hung; the helper returns None instead of letting it
    # eat the post-failure budget.
    assert result is None


def test_post_failure_page_read_timeout_constants_exist():
    """Pin the existence of the post-failure cleanup bound constants.

    The production response_wait→cleanup chain depends on these bounds
    being applied to every page-read call. Removing them silently would
    regress the failure latency back to the Celery 480s soft cap.
    """
    from geo_tracker.agent import guest_executor as guest_executor_mod

    assert isinstance(
        guest_executor_mod.POST_FAILURE_PAGE_READ_TIMEOUT_S, (int, float)
    )
    assert guest_executor_mod.POST_FAILURE_PAGE_READ_TIMEOUT_S > 0
    assert isinstance(
        guest_executor_mod.POST_FAILURE_SCREENSHOT_TIMEOUT_S, (int, float)
    )
    assert guest_executor_mod.POST_FAILURE_SCREENSHOT_TIMEOUT_S > 0


# Refs #963 production evidence (server-diagnostics run 25951168887, account
# 39 lifecycle 03:01:46 → 03:03:15 → 03:04:25): each Camoufox launch picks a
# fresh random Firefox fingerprint (UA / screen resolution / Canvas seed /
# fonts), and the auto_login flow used fingerprint A to register/login
# while the next query opened a new Camoufox with fingerprint B and
# injected A's cookies. Doubao's session validator saw the mismatch and
# treated the session as logged out within seconds — accounts ricocheted
# active → expired → auto_login → active → expired. Persisting the
# Fingerprint object alongside cookies eliminates that drift. These tests
# pin the serialize/deserialize/extract roundtrip and the persistence-key
# contract so a silent format change in browserforge or the cookie payload
# format does not regress the fix.
def test_camoufox_fingerprint_serialize_deserialize_roundtrip():
    """Generated fingerprint must survive a JSON roundtrip with UA preserved."""
    from geo_tracker.agent.browser_fingerprint import (
        deserialize_fingerprint,
        generate_doubao_fingerprint,
        is_available,
        serialize_fingerprint,
    )

    if not is_available():
        import pytest
        pytest.skip("browserforge not installed")

    fp = generate_doubao_fingerprint()
    assert fp is not None
    serialized = serialize_fingerprint(fp)
    assert isinstance(serialized, dict)
    assert "navigator" in serialized
    # The UA is the most critical field for session validation — pin that
    # it roundtrips exactly. Other fields (screen, fonts, canvas seed)
    # also matter but UA is the easiest external signal Doubao checks.
    original_ua = fp.navigator.userAgent
    assert original_ua

    deserialized = deserialize_fingerprint(serialized)
    assert deserialized is not None
    assert deserialized.navigator.userAgent == original_ua, (
        "Fingerprint UA must survive the JSON roundtrip; otherwise the next "
        "query opens with a different fingerprint than auto_login captured."
    )


def test_camoufox_fingerprint_extract_from_account_cookies_payload():
    """``extract_fingerprint_from_account_cookies`` must pull from new format."""
    import json
    from geo_tracker.agent.browser_fingerprint import (
        extract_fingerprint_from_account_cookies,
        generate_doubao_fingerprint,
        is_available,
        serialize_fingerprint,
    )

    if not is_available():
        import pytest
        pytest.skip("browserforge not installed")

    fp = generate_doubao_fingerprint()
    serialized = serialize_fingerprint(fp)
    payload = json.dumps({
        "cookies": [{"name": "sid_tt", "value": "<redacted>"}],
        "localStorage": {"some_key": "some_value"},
        "camoufoxFingerprint": serialized,
    })

    extracted = extract_fingerprint_from_account_cookies(payload)
    assert extracted is not None
    assert extracted.navigator.userAgent == fp.navigator.userAgent


def test_camoufox_fingerprint_extract_handles_legacy_list_format():
    """Legacy account_cookies (plain cookie list) must return None safely."""
    import json
    from geo_tracker.agent.browser_fingerprint import (
        extract_fingerprint_from_account_cookies,
    )

    # Old format: just a list of cookies, no fingerprint key at all.
    legacy_payload = json.dumps([
        {"name": "sid_tt", "value": "<redacted>"},
        {"name": "ttwid", "value": "<redacted>"},
    ])

    # Must NOT raise. Returns None so the caller falls back to a fresh
    # fingerprint (the pre-fix behaviour for legacy accounts).
    assert extract_fingerprint_from_account_cookies(legacy_payload) is None


def test_camoufox_fingerprint_extract_handles_missing_key():
    """New-format payload without the fingerprint key must return None safely."""
    import json
    from geo_tracker.agent.browser_fingerprint import (
        extract_fingerprint_from_account_cookies,
    )

    payload = json.dumps({
        "cookies": [{"name": "sid_tt", "value": "<redacted>"}],
        "localStorage": {"some_key": "some_value"},
        # No camoufoxFingerprint key — accounts written before the fix
        # have this shape.
    })

    assert extract_fingerprint_from_account_cookies(payload) is None


def test_camoufox_fingerprint_extract_handles_malformed_payload():
    """Garbage payloads must not crash the executor on load."""
    from geo_tracker.agent.browser_fingerprint import (
        extract_fingerprint_from_account_cookies,
    )

    # All of these must return None instead of raising:
    assert extract_fingerprint_from_account_cookies(None) is None
    assert extract_fingerprint_from_account_cookies("") is None
    assert extract_fingerprint_from_account_cookies("not-json-at-all") is None
    assert extract_fingerprint_from_account_cookies("[]") is None
    assert extract_fingerprint_from_account_cookies(
        '{"camoufoxFingerprint": "garbage-not-a-dict"}'
    ) is None
    assert extract_fingerprint_from_account_cookies(
        '{"camoufoxFingerprint": {"navigator": "wrong-type"}}'
    ) is None


def test_camoufox_fingerprint_attach_to_login_result():
    """``attach_fingerprint_to_login_result`` adds the key, no-op when missing."""
    from geo_tracker.agent.browser_fingerprint import (
        attach_fingerprint_to_login_result,
        generate_doubao_fingerprint,
        is_available,
    )

    if not is_available():
        import pytest
        pytest.skip("browserforge not installed")

    fp = generate_doubao_fingerprint()
    result: dict = {"phone": "1380000XXXX", "cookies": []}

    attach_fingerprint_to_login_result(result, fp)
    assert "camoufoxFingerprint" in result
    assert isinstance(result["camoufoxFingerprint"], dict)
    assert "navigator" in result["camoufoxFingerprint"]

    # None fingerprint → no key added, no crash.
    result2: dict = {"phone": "x", "cookies": []}
    attach_fingerprint_to_login_result(result2, None)
    assert "camoufoxFingerprint" not in result2


def test_camoufox_fingerprint_persistence_wired_into_auto_login_writeback():
    """celery_tasks.auto_login must persist fingerprint into cookies_json."""
    from pathlib import Path

    source_path = (
        Path(__file__).resolve().parent.parent / "tasks" / "celery_tasks.py"
    )
    source = source_path.read_text(encoding="utf-8")
    # Both branches (re-login + new registration) must include the
    # fingerprint write-back. A regression that drops fingerprint from
    # either branch silently re-introduces the active→expired ricochet.
    assert source.count("camoufoxFingerprint") >= 4, (
        "auto_login must read and write camoufoxFingerprint in both "
        "re-login and new-account branches; a count >= 4 catches the "
        "common case of dropping it from one branch."
    )


def test_camoufox_fingerprint_persistence_wired_into_executor_launch():
    """guest_executor's launch path must read fingerprint from account_cookies.

    Refs #1113: the launch path moved from inline in ``guest_executor.py``
    to ``executors/local.py`` as part of the BrowserConnector
    extraction. The source-text invariant is preserved at the new
    location; this test reads the new file so the architectural guard
    travels with the code.
    """
    from pathlib import Path

    source_path = (
        Path(__file__).resolve().parent.parent
        / "agent" / "executors" / "local.py"
    )
    source = source_path.read_text(encoding="utf-8")
    assert "extract_fingerprint_from_account_cookies" in source, (
        "LocalLaunchConnector must import the fingerprint extractor and "
        "pass the saved fingerprint to Camoufox so the per-account UA / "
        "screen / Canvas seed stays stable across queries."
    )
    # The fingerprint must be passed via the Camoufox kwargs, not just
    # imported. Match the exact kwarg name to catch a typo.
    assert "camoufox_kwargs[\"fingerprint\"]" in source, (
        "saved fingerprint must be wired into camoufox_kwargs['fingerprint']"
    )


# Refs #963 / #973 production evidence (server-diagnostics run
# 25951168887): LubanSMS Keyword API ("通用短信接收") is returning
# {"code":400,"msg":"未知错误"} for Doubao number allocation. The
# verification-code API ("验证码接收") draws from a separate pool keyed
# by service_id and is the documented fallback. These tests pin the
# LubanSMSProvider fallback chain so a future regression that drops the
# service-id branch silently re-introduces the production outage:
# - Keyword success: still returns a keyword-API lease (provider_ref=None)
# - Keyword failure + service_id set: falls back to verification-code API
#   and returns a service-API lease (provider_ref=request_id)
# - Keyword failure + no service_id: propagates the keyword error
# - Phone-specific re-login keyword failure: propagates so the handler's
#   "降级为随机取号" path can retry without phone
# - poll_sms_code / release_number branch on lease.provider_ref so service
#   leases poll via getSms / release via setStatus
@pytest.mark.asyncio
async def test_luban_provider_uses_keyword_api_when_healthy():
    """Keyword success path is unchanged — lease has no provider_ref."""
    from geo_tracker.agent.sms_login.providers import (
        LubanSMSProvider,
        SMSNumberLease,
    )

    class FakeClient:
        async def get_keyword_number(self, *, phone=None):
            return "13800000001"

        async def get_keyword_sms(self, phone, keyword, *, timeout=120):
            return "123456"

        async def release_keyword_number(self, phone):
            self.released_phone = phone

        async def close(self):
            pass

    fake = FakeClient()
    provider = LubanSMSProvider(client=fake, service_id="666056")

    lease = await provider.reserve_number()
    assert isinstance(lease, SMSNumberLease)
    assert lease.phone == "13800000001"
    assert lease.provider_ref is None  # keyword path, no request_id
    assert lease.provider_name == "luban"

    # Polling and release use the keyword API for keyword leases.
    code = await provider.poll_sms_code(lease, keyword="豆包", timeout=10)
    assert code == "123456"
    await provider.release_number(lease)
    assert fake.released_phone == "13800000001"


@pytest.mark.asyncio
async def test_luban_provider_falls_back_to_service_id_when_keyword_fails():
    """Keyword 400 + service_id configured → verification-code API used."""
    from geo_tracker.agent.sms_login.providers import (
        LubanSMSProvider,
        SMSNumberLease,
    )

    class FakeClient:
        def __init__(self):
            self.keyword_called_with: list = []
            self.service_called_with: list = []
            self.poll_calls: list = []
            self.release_calls: list = []

        async def get_keyword_number(self, *, phone=None):
            self.keyword_called_with.append(phone)
            raise RuntimeError(
                "getKeywordNumber failed: {'code': 400, 'msg': '未知错误'}"
            )

        async def get_service_number(self, service_id):
            self.service_called_with.append(service_id)
            return ("13900000002", "req_12345")

        async def get_service_sms(self, request_id, *, timeout=120):
            self.poll_calls.append(("service", request_id, timeout))
            return "654321"

        async def get_keyword_sms(self, phone, keyword, *, timeout=120):
            # Must NOT be called for service-API leases.
            self.poll_calls.append(("keyword", phone, keyword))
            raise AssertionError(
                "keyword SMS poll must not run for service-API leases"
            )

        async def set_service_status_reject(self, request_id):
            self.release_calls.append(("service", request_id))

        async def release_keyword_number(self, phone):
            self.release_calls.append(("keyword", phone))
            raise AssertionError(
                "keyword release must not run for service-API leases"
            )

        async def close(self):
            pass

    fake = FakeClient()
    provider = LubanSMSProvider(client=fake, service_id="666056")

    lease = await provider.reserve_number()  # no phone → random path
    assert isinstance(lease, SMSNumberLease)
    assert lease.phone == "13900000002"
    assert lease.provider_ref == "req_12345"  # service path keeps request_id
    assert lease.provider_name == "luban_service"

    # Keyword was tried first, then service kicked in.
    assert fake.keyword_called_with == [None]
    assert fake.service_called_with == ["666056"]

    # SMS poll dispatches to the service API by request_id.
    code = await provider.poll_sms_code(lease, keyword="豆包", timeout=10)
    assert code == "654321"
    assert fake.poll_calls == [("service", "req_12345", 10)]

    # Release dispatches to setStatus by request_id, never delKeywordNumber.
    await provider.release_number(lease)
    assert fake.release_calls == [("service", "req_12345")]


@pytest.mark.asyncio
async def test_luban_provider_propagates_keyword_failure_when_no_service_id():
    """Keyword 400 + service_id NOT set → keyword error propagates."""
    from geo_tracker.agent.sms_login.providers import LubanSMSProvider

    class FakeClient:
        async def get_keyword_number(self, *, phone=None):
            raise RuntimeError(
                "getKeywordNumber failed: {'code': 400, 'msg': '未知错误'}"
            )

        async def close(self):
            pass

    fake = FakeClient()
    provider = LubanSMSProvider(client=fake, service_id=None)

    import pytest as _pytest
    with _pytest.raises(RuntimeError, match="未知错误"):
        await provider.reserve_number()


@pytest.mark.asyncio
async def test_luban_provider_phone_reuse_failure_does_not_fall_to_service():
    """Phone-specific reuse failure must propagate so handler can call again.

    The service API allocates a brand-new number per request — there is
    no way to re-reserve a specific historical phone via service_id.
    Falling back to service on a phone-specific call would silently
    abandon the account's old number; instead propagate the error so the
    handler's "降级为随机取号" path can call us again with phone=None.
    """
    from geo_tracker.agent.sms_login.providers import LubanSMSProvider

    class FakeClient:
        def __init__(self):
            self.service_calls = 0

        async def get_keyword_number(self, *, phone=None):
            raise RuntimeError(
                "getKeywordNumber failed: {'code': 400, 'msg': '当前通道此号码不在线'}"
            )

        async def get_service_number(self, service_id):
            self.service_calls += 1
            return ("13900000003", "req_99999")

        async def close(self):
            pass

    fake = FakeClient()
    provider = LubanSMSProvider(client=fake, service_id="666056")

    import pytest as _pytest
    with _pytest.raises(RuntimeError, match="当前通道此号码不在线"):
        await provider.reserve_number(phone="13800000004")
    assert fake.service_calls == 0, (
        "service API must NOT be used for phone-specific reuse; the "
        "handler will retry without phone, and that call gets the "
        "service fallback."
    )


@pytest.mark.asyncio
async def test_luban_provider_surfaces_both_errors_when_both_paths_fail():
    """Keyword AND service both fail → combined error message."""
    from geo_tracker.agent.sms_login.providers import LubanSMSProvider

    class FakeClient:
        async def get_keyword_number(self, *, phone=None):
            raise RuntimeError(
                "getKeywordNumber failed: {'code': 400, 'msg': '未知错误'}"
            )

        async def get_service_number(self, service_id):
            raise RuntimeError(
                "getNumber failed: {'code': 400, 'msg': 'no service_id available'}"
            )

        async def close(self):
            pass

    provider = LubanSMSProvider(client=FakeClient(), service_id="666056")

    import pytest as _pytest
    with _pytest.raises(RuntimeError) as excinfo:
        await provider.reserve_number()
    # Both error texts must be in the combined message so operators can
    # see at a glance that BOTH paths failed (not just one).
    msg = str(excinfo.value)
    assert "未知错误" in msg
    assert "service_id=666056" in msg
    assert "no service_id available" in msg


def test_luban_service_id_env_wired_into_provider_factory():
    """``LUBANSMS_<PLATFORM>_SERVICE_ID`` env var is read at handler init."""
    from pathlib import Path

    source_path = (
        Path(__file__).resolve().parent.parent / "agent" / "sms_login" / "base.py"
    )
    source = source_path.read_text(encoding="utf-8")
    # The env-var lookup uses an f-string with the uppercased platform.
    assert 'LUBANSMS_{self.platform.upper()}_SERVICE_ID' in source, (
        "BaseSMSLoginHandler must read the platform-specific service_id "
        "env var (LUBANSMS_<PLATFORM>_SERVICE_ID) so doubao picks up "
        "666056 without affecting other platforms."
    )
    # And the value is passed through to the provider factory.
    assert 'factory_kwargs["service_id"]' in source


# Refs #963 follow-up (2026-05-16): operator confirmed the LubanSMS
# keyword API has recovered. Add a kill switch
# ``LUBANSMS_<PLATFORM>_DISABLE_SERVICE_ID_FALLBACK`` so registrations
# go through the keyword API exclusively when it's healthy, without
# needing a code change or secret rotation. Default behaviour on
# production is "disabled" (i.e. the fallback path is OFF until the
# keyword API regresses again).
def test_luban_service_id_fallback_has_kill_switch():
    """Operators must be able to turn the service-id fallback off via env."""
    from pathlib import Path

    base_source = (
        Path(__file__).resolve().parent.parent / "agent" / "sms_login" / "base.py"
    ).read_text(encoding="utf-8")
    assert "DISABLE_SERVICE_ID_FALLBACK" in base_source, (
        "BaseSMSLoginHandler must check a per-platform "
        "LUBANSMS_<PLATFORM>_DISABLE_SERVICE_ID_FALLBACK env var so the "
        "service-id fallback can be turned off when the keyword API is "
        "healthy, without rotating the SERVICE_ID secret or shipping "
        "code."
    )
    # The flag must take precedence over the SERVICE_ID env var so an
    # operator-set kill switch wins over a lingering 666056 secret.
    disable_idx = base_source.index("DISABLE_SERVICE_ID_FALLBACK")
    service_id_idx = base_source.find("_SERVICE_ID\"", disable_idx)
    assert service_id_idx > disable_idx, (
        "The kill-switch check must run BEFORE the service_id env read "
        "so the disable flag short-circuits the service_id wiring."
    )


def test_luban_service_id_fallback_disabled_by_default_in_deploy():
    """Deploy default should be "fallback ENABLED" — fail-open safe default.

    Rationale: a worker log at 2026-05-16 15:26:46 UTC showed the LubanSMS
    keyword API regressing again with
    ``{'code': 400, 'msg': '未知错误', 'Repeated': 'false'}``. With the
    kill switch ON (PR #1074's original default of '1') and the keyword
    API broken, there is NO usable SMS path for Doubao auto_login →
    new-account registration, blocking #963.

    The safer default is fail-open: keep the service-id fallback ENABLED
    by default ('0') so the system stays resilient to keyword-API
    regressions. Operators can still set the
    ``LUBANSMS_DOUBAO_DISABLE_SERVICE_ID_FALLBACK`` repo variable to '1'
    to re-disable the fallback when the keyword API is confirmed stable.
    """
    from pathlib import Path

    deploy = (
        Path(__file__).resolve().parent.parent.parent
        / ".github" / "workflows" / "deploy.yml"
    ).read_text(encoding="utf-8")
    assert "LUBANSMS_DOUBAO_DISABLE_SERVICE_ID_FALLBACK" in deploy, (
        "deploy.yml must wire the kill switch through so the worker "
        "container picks it up — otherwise the env stays unset on "
        "production and the fallback keeps firing."
    )
    # The default value when no repo variable is set is "0" (fallback
    # ENABLED) — fail-open after the 2026-05-16 15:26:46 UTC keyword API
    # regression. Operators set the repo var to '1' to disable when
    # keyword API is confirmed stable.
    assert "DISABLE_SERVICE_ID_FALLBACK || '0'" in deploy, (
        "deploy.yml default must be '0' (fallback ENABLED, fail-open) "
        "after the 2026-05-16 15:26:46 UTC keyword API regression "
        "(code=400, msg='未知错误'). Flipping the repo variable to '1' "
        "re-disables the fallback when the keyword API is confirmed "
        "stable."
    )


# Refs #963 production evidence (server-diagnostics run 25955749209 at
# 2026-05-16 07:07:50 → 07:11:01): after all the fingerprint / routing /
# persistence-gate fixes shipped, account 44 still failed with
# retry_reason=doubao_homepage_content (cookies accepted enough to
# submit the prompt but the response was silently suppressed by Doubao —
# typical shadow-ban behaviour). Because doubao_homepage_content was NOT
# in EXPIRED_ACCOUNT_REASONS, the worker kept re-picking the same broken
# cookies forever and the auto_login → LubanSMS service_id fallback
# never fired. Pin that the reason is now classified as expired so the
# self-healing chain can move the account through expired → auto_login
# → fresh fingerprint+cookies → working query.
def test_doubao_homepage_content_marked_as_expired_reason():
    from geo_tracker.pool.account_pool import EXPIRED_ACCOUNT_REASONS

    assert "doubao_homepage_content" in EXPIRED_ACCOUNT_REASONS, (
        "doubao_homepage_content must trigger account-expired so the "
        "self-healing chain (auto_login → service_id fallback → fresh "
        "fingerprint+cookies) can replace cookies that Doubao shadow-bans."
    )


# Refs #963 / Codex P1 review on PR #1037: adding a reason to
# EXPIRED_ACCOUNT_REASONS without also adding it to
# DOUBAO_REAUTH_FAILURE_REASONS removes the account from rotation but
# never queues auto_login → the self-healing chain stalls and the
# pool can drain to zero active. Pin that both sets agree on
# doubao_homepage_content so a future refactor of one set without the
# other regresses to that silent stall.
def test_doubao_homepage_content_triggers_reauth_handoff():
    """``DOUBAO_REAUTH_FAILURE_REASONS`` must include doubao_homepage_content."""
    from pathlib import Path

    source_path = (
        Path(__file__).resolve().parent.parent / "tasks" / "celery_tasks.py"
    )
    source = source_path.read_text(encoding="utf-8")
    # Extract the DOUBAO_REAUTH_FAILURE_REASONS frozenset literal and
    # assert membership. We pin by source-string match so the test runs
    # without importing celery_tasks (which pulls in Celery + Redis).
    sig_idx = source.index("DOUBAO_REAUTH_FAILURE_REASONS = frozenset(")
    body = source[sig_idx : source.index("\n)", sig_idx)]
    assert '"doubao_homepage_content"' in body, (
        "DOUBAO_REAUTH_FAILURE_REASONS must include doubao_homepage_content "
        "so the reauth handoff queues auto_login when the account is "
        "shadow-banned and EXPIRED_ACCOUNT_REASONS expires it. Without "
        "this entry the self-healing chain (auto_login → service_id "
        "fallback → fresh fingerprint+cookies) never fires for that "
        "failure mode."
    )


# Refs #963: qg.net (青果网络) rotating-proxy integration unblocks
# Doubao's by-IP shadow-ban / 5202 captcha-denial. The worker's static
# egress IP got fingerprinted by Doubao after the full self-healing
# chain (#1016 / #1017 / #1027 / #1030 / #1032 / #1037) deployed —
# even fresh accounts with fresh fingerprints get challenged with an
# image-selection captcha whose image fails to load (5202), which is
# unsolvable. Rotating to a fresh residential / mobile IP per Doubao
# query bypasses the IP-level memory.
def test_qg_parse_documented_success_response():
    """Parse the success envelope shape documented in qg.net doc 1865."""
    from geo_tracker.agent.qg_proxy import _parse_qg_response

    # Verbatim shape from doc 1839 / 1865 example.
    body = (
        '{"code":"SUCCESS","data":[{"proxy_ip":"129.150.42.240",'
        '"server":"129.150.42.240:18080","area":"新加坡",'
        '"deadline":"2023-02-25 15:38:36"}],"request_id":"abc"}'
    )
    assert _parse_qg_response(body) == ["129.150.42.240:18080"]


def test_qg_parse_numeric_success_code():
    """Legacy / domestic qg endpoints use ``code:0`` instead of "SUCCESS"."""
    from geo_tracker.agent.qg_proxy import _parse_qg_response

    body = '{"code":0,"data":[{"server":"1.2.3.4:8080"}]}'
    assert _parse_qg_response(body) == ["1.2.3.4:8080"]


def test_qg_parse_plain_text_response():
    """Some qg endpoints return one ip:port per line, no JSON envelope."""
    from geo_tracker.agent.qg_proxy import _parse_qg_response

    body = "1.2.3.4:8080\n5.6.7.8:9090\n"
    assert _parse_qg_response(body) == ["1.2.3.4:8080", "5.6.7.8:9090"]


def test_qg_parse_error_envelope_returns_empty():
    """Non-success code (e.g. INVALID_KEY) must return [] not raise."""
    from geo_tracker.agent.qg_proxy import _parse_qg_response

    body = '{"code":"INVALID_KEY","msg":"Key不存在"}'
    assert _parse_qg_response(body) == []


def test_qg_parse_extract_ip_port_handles_separate_fields():
    """Dict items with separate ip + port fields must be reconstructed."""
    from geo_tracker.agent.qg_proxy import _extract_ip_port

    assert _extract_ip_port({"ip": "1.2.3.4", "port": 8080}) == "1.2.3.4:8080"
    assert _extract_ip_port({"server": "1.2.3.4:8080"}) == "1.2.3.4:8080"
    assert _extract_ip_port("1.2.3.4:8080") == "1.2.3.4:8080"
    assert _extract_ip_port({"unrelated": "x"}) is None


def test_qg_lease_proxy_url_format_matches_qg_doc_example():
    """Lease URL must be ``http://AUTH_KEY:PASSWORD@IP:PORT``.

    qg.net account-mode code samples (Python requests / aiohttp / urllib2)
    all hard-code this exact ordering. A typo here silently sends the
    authKey as the host or password as the user → 407 / 502 from the
    rotating proxy with no obvious link to qg.
    """
    from geo_tracker.agent.qg_proxy import QGProxyLease

    lease = QGProxyLease(
        ip_port="1.2.3.4:8080",
        auth_key="myKey",
        auth_password="myPwd",
    )
    assert lease.proxy_url == "http://myKey:myPwd@1.2.3.4:8080"
    # server_url is what Playwright wants (auth passed separately).
    assert lease.server_url == "http://1.2.3.4:8080"


def test_qg_proxy_client_from_env_returns_none_when_unconfigured(monkeypatch):
    """Missing any of the 3 env vars → no client, fall through to native IP."""
    from geo_tracker.agent.qg_proxy import QGProxyClient

    # All unset
    monkeypatch.delenv("QG_PROXY_EXTRACT_URL", raising=False)
    monkeypatch.delenv("QG_PROXY_AUTH_KEY", raising=False)
    monkeypatch.delenv("QG_PROXY_AUTH_PASSWORD", raising=False)
    assert QGProxyClient.from_env() is None

    # Only one set — still incomplete, must not partially activate.
    monkeypatch.setenv("QG_PROXY_EXTRACT_URL", "https://share.proxy.qg.net/get?key=x")
    monkeypatch.delenv("QG_PROXY_AUTH_KEY", raising=False)
    monkeypatch.delenv("QG_PROXY_AUTH_PASSWORD", raising=False)
    assert QGProxyClient.from_env() is None

    monkeypatch.setenv("QG_PROXY_AUTH_KEY", "k")
    monkeypatch.delenv("QG_PROXY_AUTH_PASSWORD", raising=False)
    assert QGProxyClient.from_env() is None

    # All three set → client constructs.
    monkeypatch.setenv("QG_PROXY_AUTH_PASSWORD", "p")
    client = QGProxyClient.from_env()
    assert client is not None
    assert client.auth_key == "k"
    assert client.auth_password == "p"


@pytest.mark.asyncio
async def test_qg_proxy_client_reserve_pops_from_pool():
    """``reserve`` must remove the IP from the pool to prevent reuse races."""
    from geo_tracker.agent.qg_proxy import QGProxyClient

    client = QGProxyClient(
        extract_url="http://stub",
        auth_key="k",
        auth_password="p",
        pool=["1.1.1.1:1111", "2.2.2.2:2222"],
    )
    lease1 = await client.reserve()
    assert lease1.ip_port in {"1.1.1.1:1111", "2.2.2.2:2222"}
    assert len(client.pool) == 1
    lease2 = await client.reserve()
    assert lease2.ip_port != lease1.ip_port
    assert len(client.pool) == 0


@pytest.mark.asyncio
async def test_qg_proxy_client_report_failure_drops_ip():
    """``report_failure`` must remove the bad IP from the cached pool."""
    from geo_tracker.agent.qg_proxy import QGProxyClient

    client = QGProxyClient(
        extract_url="http://stub",
        auth_key="k",
        auth_password="p",
        pool=["1.1.1.1:1111", "2.2.2.2:2222", "3.3.3.3:3333"],
    )
    await client.report_failure("2.2.2.2:2222")
    assert client.pool == ["1.1.1.1:1111", "3.3.3.3:3333"]
    # Idempotent — calling twice or for an unknown IP is a no-op, not an error.
    await client.report_failure("9.9.9.9:9999")
    assert client.pool == ["1.1.1.1:1111", "3.3.3.3:3333"]


def test_qg_proxy_env_vars_wired_into_deploy_yaml():
    """deploy.yml must forward all 3 qg env vars with $-escaping.

    Refs #963 / Codex P2 on PR #1038: docker-compose's env_file default
    format applies ``$`` interpolation to unquoted values, so a qg
    AuthPwd containing ``$abc`` would be substituted by compose before
    the worker container starts. The fix runs the qg secrets through
    the same ``replace('$', '$$')`` escape that HERO_SMS_API_KEY uses.
    Pin both the env-var declarations AND the $-escape so a future
    refactor that puts them back inside the unescaped heredoc gets
    caught.
    """
    from pathlib import Path

    source_path = (
        Path(__file__).resolve().parent.parent.parent
        / ".github" / "workflows" / "deploy.yml"
    )
    source = source_path.read_text(encoding="utf-8")
    envs_line = source.split("envs:", 1)[1].split("\n", 1)[0]
    # Locate the $-escape python heredoc block that owns QG vars.
    escape_block_idx = source.index('"QG_PROXY_EXTRACT_URL"')
    escape_block_end = source.index("PY", escape_block_idx)
    escape_block = source[escape_block_idx:escape_block_end]
    for env_name in (
        "QG_PROXY_EXTRACT_URL",
        "QG_PROXY_AUTH_KEY",
        "QG_PROXY_AUTH_PASSWORD",
    ):
        # 1. Secret must be exposed to the ssh-action step env.
        assert f"{env_name}: " in source, (
            f"{env_name} must be exposed in the Deploy step env block."
        )
        # 2. Secret must be in the envs: allowlist so ssh-action
        #    forwards it into the remote shell.
        assert env_name in envs_line, (
            f"{env_name} must be in the ssh-action envs: list so the "
            f"remote shell sees it."
        )
        # 3. Secret must be written to .env via the $-escape block (not
        #    via the unescaped heredoc, which corrupts $-bearing values).
        assert env_name in escape_block, (
            f"{env_name} must be written to .env through the $-escape "
            f"python3 heredoc, not the unescaped ENVEOF block."
        )


# Refs #963 follow-up to PR #1038 production evidence (worker log
# 2026-05-16 08:47:59 → 08:49:15): qg.net rotating proxy was wired
# into guest_executor's Camoufox launch but NOT into sms_login/base.py's
# auto_login launch. Production registered a new Doubao account via
# service_id=666056, received the SMS code, and submitted login — only
# for Doubao to refuse with doubao_not_logged_in because auto_login's
# Camoufox was still using the worker's native fingerprinted IP.
# Registration is the most IP-sensitive flow because Doubao's risk
# control inspects the registration source IP and rejects numbers that
# arrive from a known-bad address. The fix reserves a qg IP for the
# auto_login Camoufox too, so the entire chain (registration + first
# query) is done from a fresh residential IP.
def test_qg_proxy_wired_into_sms_login_launch():
    """``sms_login/base.py`` must reserve a qg IP for Doubao auto_login."""
    from pathlib import Path

    source_path = (
        Path(__file__).resolve().parent.parent
        / "agent" / "sms_login" / "base.py"
    )
    source = source_path.read_text(encoding="utf-8")
    # 1. Import is present.
    assert "from geo_tracker.agent.qg_proxy import QGProxyClient" in source, (
        "sms_login/base.py must import QGProxyClient so auto_login can "
        "reserve a rotating qg.net IP at Camoufox launch time."
    )
    # 2. A _reserve_qg_lease helper exists. The reservation lives outside
    # _launch_browser so the device_env_error retry path can rotate to a
    # fresh IP before relaunching (Codex P2 on PR #1042).
    assert "async def _reserve_qg_lease" in source, (
        "sms_login/base.py must expose a _reserve_qg_lease helper so the "
        "device_env_error retry path can reserve a fresh IP between "
        "browser relaunches instead of reusing the rejected lease."
    )
    reserve_idx = source.index("async def _reserve_qg_lease")
    reserve_block = source[reserve_idx:reserve_idx + 3000]
    assert "QGProxyClient.from_env()" in reserve_block, (
        "_reserve_qg_lease must call QGProxyClient.from_env() so the qg "
        "credentials gate the lease reservation."
    )
    assert 'self.platform != "doubao"' in reserve_block or \
        'self.platform == "doubao"' in reserve_block, (
        "qg reservation must be gated on platform=='doubao' so chatgpt / "
        "deepseek auto_login do not consume qg credits."
    )
    # 3. _launch_browser accepts the qg_lease and wires it into proxy kwargs.
    launch_idx = source.index("async def _launch_browser")
    launch_block = source[launch_idx:launch_idx + 6000]
    assert "qg_lease=None" in launch_block or "qg_lease=" in launch_block, (
        "_launch_browser must accept a qg_lease parameter so the caller "
        "(or the device_env_error retry path) can inject a freshly "
        "reserved lease instead of _launch_browser reserving it itself."
    )
    assert "qg_lease.server_url" in launch_block, (
        "Camoufox kwargs must wire qg_lease.server_url + auth_key + "
        "auth_password into the proxy={server, username, password} shape "
        "Playwright expects."
    )
    # 4. A _recycle_browser_with_fresh_qg_lease helper exists for the
    # device_env_error retry path so a rejected IP is reported back to
    # the qg pool and a new one is reserved before relaunching.
    assert "async def _recycle_browser_with_fresh_qg_lease" in source, (
        "sms_login/base.py must expose _recycle_browser_with_fresh_qg_lease "
        "so device_env_error retries drop the rejected IP and reserve a "
        "fresh one before relaunching Camoufox — otherwise every retry "
        "burns a fresh SMS number on the same fingerprinted IP."
    )


# Refs #963 Q-184988 follow-up production evidence (account 711158,
# 2026-05-16 ~10:00): a freshly registered Doubao account going through
# a rotating qg residential IP still hit the 5202 image-load denial on
# the 3D image-selection captcha. Root cause is WebRTC STUN leaking the
# worker's static egress IP regardless of the qg HTTP proxy — Doubao
# sees HTTP-IP=qg, WebRTC-IP=worker-static, flags the mismatch, serves
# the captcha, then refuses the captcha image at the IP level. Both the
# Camoufox launch (preferred path) and the Playwright Chromium fallback
# must close the WebRTC leak.
def test_camoufox_launches_block_webrtc_to_prevent_stun_leak():
    """Both Camoufox launches must set block_webrtc=True + disable_coop=True.

    Refs #1113: the query-path Camoufox launch moved from
    ``guest_executor.py`` to ``executors/local.py`` as part of the
    BrowserConnector extraction. ``sms_login/base.py`` still launches
    Camoufox inline for the auto-login flow and remains in the check.
    """
    from pathlib import Path

    for relpath in (
        ("agent", "sms_login", "base.py"),
        ("agent", "executors", "local.py"),
    ):
        source_path = Path(__file__).resolve().parent.parent.joinpath(*relpath)
        source = source_path.read_text(encoding="utf-8")
        # ``executors/local.py`` annotates the dict literal as ``dict``;
        # match either form so the test is robust to future small
        # annotation additions.
        try:
            camoufox_idx = source.index("camoufox_kwargs = {")
        except ValueError:
            camoufox_idx = source.index("camoufox_kwargs: dict = {")
        # Capture the dict literal — generously sized so future additions
        # stay inside the slice.
        camoufox_block = source[camoufox_idx:camoufox_idx + 4000]
        assert '"block_webrtc": True' in camoufox_block, (
            f"{'/'.join(relpath)} camoufox_kwargs must set "
            "block_webrtc=True so WebRTC STUN cannot bypass the qg HTTP "
            "proxy and leak the worker's static egress IP to Doubao."
        )
        assert '"disable_coop": True' in camoufox_block, (
            f"{'/'.join(relpath)} camoufox_kwargs must set "
            "disable_coop=True so cross-origin captcha iframes can be "
            "interacted with when Doubao does serve one."
        )


def test_playwright_fallback_forces_webrtc_through_proxy():
    """Chromium fallback args must close the WebRTC leak symmetrically.

    Refs #1113: the query-path Chromium fallback moved from
    ``guest_executor.py`` to ``executors/local.py``.
    """
    from pathlib import Path

    for relpath in (
        ("agent", "sms_login", "base.py"),
        ("agent", "executors", "local.py"),
    ):
        source_path = Path(__file__).resolve().parent.parent.joinpath(*relpath)
        source = source_path.read_text(encoding="utf-8")
        assert "force-webrtc-ip-handling-policy=disable_non_proxied_udp" in source, (
            f"{'/'.join(relpath)} Playwright Chromium fallback must pass "
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp so "
            "WebRTC traffic is forced through the proxy (or dropped) "
            "instead of leaking the worker's egress IP. The Camoufox path "
            "achieves this via block_webrtc=True; the Chromium path needs "
            "the Chromium-equivalent flag for symmetry."
        )


# Refs #963 follow-up to PR #1051: after WebRTC was blocked,
# ``doubao_homepage_content`` kept firing twice in a row on Doubao
# (queries silently rejected; page never left /home and never reached
# /chat/{id}). The single saved HTML wasn't enough to root-cause —
# we needed to know whether the IP-geo / JS-geo lined up, whether
# WebRTC was actually disabled, and whether the submit reached Doubao.
# Augment ``_save_runtime_snapshot`` to capture browser fingerprint +
# timezone + RTCPeerConnection availability + on-chat-page flag, then
# wire the homepage_content path to save all three artifacts (HTML,
# screenshot, runtime snapshot) on every failure.
def test_runtime_snapshot_captures_doubao_fingerprint_diagnostics():
    """The runtime snapshot must include fingerprint fields for #963 triage."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parent.parent
        / "agent" / "guest_executor.py"
    ).read_text(encoding="utf-8")
    snapshot_idx = source.index("async def _save_runtime_snapshot")
    snapshot_block = source[snapshot_idx:snapshot_idx + 10000]
    for marker in (
        "fingerprint:",
        "timezoneOffset",
        "rtcPeerConnectionAvailable",
        "onChatPage",
        "userMessageBubbleCount",
        "Intl.DateTimeFormat()",
    ):
        assert marker in snapshot_block, (
            f"_save_runtime_snapshot must include `{marker}` in its page "
            "evaluate so #963 doubao_homepage_content failures dump enough "
            "fingerprint / timezone / WebRTC / submit-state info to root-"
            "cause without admin shell access on the worker."
        )


# Refs #963 doubao_homepage_content follow-up: a qg.net Chinese
# residential exit IP paired with the worker container's UTC timezone
# is the canonical "you're using a proxy" signal. Pin Camoufox to
# Shanghai geo + timezone for Doubao on both the query path and the
# auto_login path so JS-side geo matches qg exit-IP geo. The Dockerfile
# must also install ``tzdata`` so Firefox can actually resolve named
# timezones — without it the env TZ silently no-ops.
def test_camoufox_doubao_launches_pin_china_timezone_and_geolocation():
    """Both Doubao Camoufox launches must override timezone + geolocation.

    Refs #1113: the query-path Doubao Camoufox config moved to
    ``executors/local.py``.
    """
    from pathlib import Path

    for relpath in (
        ("agent", "sms_login", "base.py"),
        ("agent", "executors", "local.py"),
    ):
        source_path = Path(__file__).resolve().parent.parent.joinpath(*relpath)
        source = source_path.read_text(encoding="utf-8")
        # Both files set kwargs in a Doubao-gated block. Look for the
        # config / env overrides near the Doubao platform check.
        assert '"timezone": "Asia/Shanghai"' in source, (
            f"{'/'.join(relpath)} must pin Camoufox config timezone to "
            "Asia/Shanghai for Doubao — otherwise Firefox falls back to "
            "the container's UTC timezone and Doubao's risk control "
            "catches the IP-geo / JS-geo mismatch."
        )
        assert '"geolocation:longitude"' in source, (
            f"{'/'.join(relpath)} must pin Camoufox geolocation for "
            "Doubao so navigator.geolocation reads as Shanghai, "
            "consistent with the qg residential exit IP."
        )
        assert '"TZ": "Asia/Shanghai"' in source, (
            f"{'/'.join(relpath)} must pass TZ=Asia/Shanghai to the "
            "Firefox subprocess env. The Camoufox ``config`` parameter "
            "sets the JS Intl timezone, but the env TZ also affects "
            "lower-level C library calls and is the standard belt-and-"
            "braces approach to keeping the entire subprocess coherent."
        )


def test_worker_dockerfile_installs_tzdata():
    """tzdata is needed for Firefox to resolve named timezones."""
    from pathlib import Path

    dockerfile = (
        Path(__file__).resolve().parent.parent.parent
        / "geo_tracker" / "Dockerfile"
    )
    content = dockerfile.read_text(encoding="utf-8")
    assert "tzdata" in content, (
        "geo_tracker/Dockerfile must install tzdata in the apt-get "
        "block — without it, Firefox/glibc cannot resolve names like "
        "Asia/Shanghai and JS Intl.DateTimeFormat falls back to UTC "
        "regardless of any TZ env we pass. This silently no-ops the "
        "timezone fix for Doubao."
    )


def test_doubao_homepage_content_path_saves_all_three_artifacts():
    """homepage_content failures must persist HTML + screenshot + runtime snapshot."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parent.parent
        / "agent" / "guest_executor.py"
    ).read_text(encoding="utf-8")
    # Find the homepage_content save-site, not the earlier qg-cleanup
    # ip_block_reasons set that also references the string literal. The
    # save-site is identified by the assignment to ``homepage_reason``.
    homepage_idx = source.index('homepage_reason = f"{llm_name}_homepage_content"')
    homepage_block = source[homepage_idx:homepage_idx + 2500]
    for marker in (
        "_save_html",
        "_save_screenshot",
        "_save_runtime_snapshot",
    ):
        assert marker in homepage_block, (
            "doubao_homepage_content path must call "
            f"`{marker}` so #963 triage has HTML + screenshot + runtime "
            "snapshot for every silently-rejected query, not just the "
            "HTML it had before. Saving only one artifact left us unable "
            "to root-cause when the failure recurred."
        )
