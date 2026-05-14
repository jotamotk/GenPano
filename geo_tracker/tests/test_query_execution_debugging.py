from __future__ import annotations

import sys
import types
import asyncio
import json
from datetime import UTC, datetime, timedelta

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


def test_doubao_persistence_gate_rejects_answer_html_with_login_chrome():
    from geo_tracker.agent.response_validation import doubao_persistence_auth_reason

    raw_text = "bestCoffer 的核心优势包括便携、电池续航和户外咖啡场景。"
    response_html = """
    <header>
      <div class="avatar-placeholder"></div>
      <div class="toolbar-action">登录</div>
    </header>
    <main>
      <div class="flow-markdown-body">bestCoffer 的核心优势包括便携、电池续航和户外咖啡场景。</div>
    </main>
    """

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


def test_execute_query_skips_failed_row_after_state_reconciliation(
    monkeypatch,
    tmp_path,
):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.tasks import celery_tasks

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'skip-reconciled-failed.db'}"
    query_id = 184974

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
                    query_text="bestCoffer stale dispatch",
                    status=QueryStatus.FAILED.value,
                    retry_reason="pending_dispatch_timeout",
                )
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(seed_database())

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    async def fail_if_account_path_runs(*_args, **_kwargs):
        raise AssertionError("reconciled failed query should not enter execution")

    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    monkeypatch.setattr(celery_tasks, "acquire_query_account", fail_if_account_path_runs)

    result = celery_tasks.execute_query.run(query_id)

    assert result == {
        "skipped": True,
        "reason": "status_not_pending",
        "query_id": query_id,
        "status": QueryStatus.FAILED.value,
    }


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


def test_execute_query_persists_doubao_auth_failure_before_done(monkeypatch, tmp_path):
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
        "status": "failed",
        "reason": "doubao_not_logged_in",
    }
    assert state["status"] == QueryStatus.FAILED.value
    assert state["retry_reason"] == "doubao_not_logged_in"
    assert state["response"] is None
    assert state["account_status"] == AccountStatus.EXPIRED.value
    assert state["account_cooldown_until"] is None
    assert relogin_calls == [
        {
            "kwargs": {"account_id": account_id, "query_id": query_id},
            "queue": "account_login",
        }
    ]


def test_doubao_auto_login_success_requeues_failed_query_once(monkeypatch, tmp_path):
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


def test_doubao_auto_login_does_not_requeue_after_retry_budget(monkeypatch, tmp_path):
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
    monkeypatch.setenv("DOUBAO_REAUTH_QUERY_RETRY_MAX", "1")

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
