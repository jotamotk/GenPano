import logging
import sys
import types

import pytest


FAKE_CN_PHONE = "138" + "1234" + "5678"
FAKE_US_PHONE = "+1" + "202" + "555" + "0198"
FAKE_US_RELOGIN_PHONE = "+1" + "202" + "555" + "0197"
FAKE_SMS_CODE = "654" + "321"
FAKE_CHATGPT_SMS_CODE = "112" + "233"
FAKE_COOKIE_VALUE = "cookie-" + "secret-value"
FAKE_PROVIDER_REF = "activation-" + "redacted"


@pytest.fixture(autouse=True)
def _stub_playwright_module(monkeypatch):
    async_api = types.ModuleType("playwright.async_api")
    async_api.Page = object
    async_api.ElementHandle = object
    async_api.async_playwright = lambda: None
    playwright = types.ModuleType("playwright")
    playwright.async_api = async_api
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.async_api", async_api)


class _FakeKeyboard:
    async def press(self, _key: str) -> None:
        return None


class _FakePage:
    def __init__(
        self,
        *,
        url: str = "https://example.test/login",
        title: str = "",
        body_text: str = "",
        session: dict | None = None,
    ) -> None:
        self.url = url
        self._title = title
        self._body_text = body_text
        self._session = session or {}
        self.keyboard = _FakeKeyboard()

    async def goto(self, url: str, **_kwargs) -> None:
        self.url = url

    async def wait_for_timeout(self, _ms: int) -> None:
        return None

    async def query_selector(self, _selector: str):
        return None

    async def title(self) -> str:
        return self._title

    async def evaluate(self, script: str):
        if "fetch('/api/auth/session'" in script:
            return self._session
        if "document.body" in script or "innerText" in script:
            return self._body_text
        return {}

    def on(self, _event: str, _handler) -> None:
        return None

    def remove_listener(self, _event: str, _handler) -> None:
        return None


class _VisibleElement:
    async def is_visible(self) -> bool:
        return True


class _FakeDoubaoVerifyPage(_FakePage):
    def __init__(self, *, body_text: str, html: str) -> None:
        super().__init__(
            url="https://www.doubao.com/chat",
            body_text=body_text,
        )
        self._html = html

    async def query_selector(self, selector: str):
        if "textarea" in selector:
            return _VisibleElement()
        return None

    async def content(self) -> str:
        return self._html


class _FakeContext:
    def __init__(self, page: _FakePage | None = None) -> None:
        self._page = page or _FakePage()

    async def new_page(self) -> _FakePage:
        return self._page

    async def add_cookies(self, _cookies) -> None:
        return None

    async def cookies(self):
        return [
            {
                "name": "session",
                "value": FAKE_COOKIE_VALUE,
                "domain": "example.test",
                "path": "/",
            }
        ]


class _FakeProvider:
    provider_name = "fake-sms"

    def __init__(self, *, code: str = "123" + "456") -> None:
        self.code = code
        self.reserved = []
        self.polled = []
        self.released = []
        self.closed = False

    async def reserve_number(self, *, phone=None):
        from geo_tracker.agent.sms_login.providers import SMSNumberLease

        number = phone or FAKE_CN_PHONE
        self.reserved.append(number)
        return SMSNumberLease(
            phone=number,
            provider_name=self.provider_name,
            price_bucket="existing-luban",
        )

    async def poll_sms_code(self, lease, *, keyword: str, timeout: int):
        self.polled.append((lease.phone, keyword, timeout))
        return self.code

    async def release_number(self, lease) -> None:
        self.released.append(lease.phone)

    async def close(self) -> None:
        self.closed = True


class _FakeHeroSMSProvider(_FakeProvider):
    provider_name = "herosms"

    async def reserve_number(self, *, phone=None):
        from geo_tracker.agent.sms_login.providers import SMSNumberLease

        number = phone or FAKE_US_PHONE
        self.reserved.append(number)
        return SMSNumberLease(
            phone=number,
            provider_name=self.provider_name,
            price_bucket="usd<=0.60",
            provider_ref=FAKE_PROVIDER_REF,
        )

    async def mark_success(self, lease) -> None:
        self.completed = getattr(self, "completed", [])
        self.completed.append(lease.provider_name)


async def _patch_successful_flow(monkeypatch, handler, *, verify_result):
    from geo_tracker.agent.sms_login import base

    async def _launch_browser():
        return object(), None, object(), _FakeContext()

    async def _true(_page=None, *_args):
        return True

    async def _verify(_page):
        return verify_result

    async def _none(*_args, **_kwargs):
        return None

    async def _not_blacklisted(*_args, **_kwargs):
        return False

    monkeypatch.setattr(base, "install_resource_blocker", _none)
    monkeypatch.setattr(base, "cleanup_browser_resources", _none)
    monkeypatch.setattr(base, "is_blacklisted", _not_blacklisted)
    monkeypatch.setattr(handler, "_launch_browser", _launch_browser)
    monkeypatch.setattr(handler, "_add_stealth_script", _true)
    monkeypatch.setattr(handler, "_handle_captcha", _true)
    monkeypatch.setattr(handler, "_detect_error_toast", _none)
    monkeypatch.setattr(handler, "navigate_to_login", _true)
    monkeypatch.setattr(handler, "input_phone", _true)
    monkeypatch.setattr(handler, "click_send_sms", _true)
    monkeypatch.setattr(handler, "input_code", _true)
    monkeypatch.setattr(handler, "submit_login", _true)
    monkeypatch.setattr(handler, "verify_success", _verify)

@pytest.mark.parametrize(
    ("platform", "keyword"),
    [
        ("doubao", "豆包"),
        ("deepseek", "深度求索"),
    ],
)
@pytest.mark.asyncio
async def test_existing_handlers_use_shared_sms_provider_flow(
    monkeypatch, platform: str, keyword: str
) -> None:
    from geo_tracker.agent.sms_login import get_handler

    handler = get_handler(platform)
    assert handler is not None
    provider = _FakeProvider()
    monkeypatch.setattr(handler, "sms_provider_factory", lambda: provider)
    await _patch_successful_flow(monkeypatch, handler, verify_result=True)

    result = await handler.login_or_register()

    assert result["phone"] == FAKE_CN_PHONE
    assert result["cookies"][0]["name"] == "session"
    assert provider.reserved == [FAKE_CN_PHONE]
    assert provider.polled == [(FAKE_CN_PHONE, keyword, 120)]
    assert provider.released == [FAKE_CN_PHONE]
    assert provider.closed is True


@pytest.mark.asyncio
async def test_chatgpt_handler_uses_herosms_shared_provider(monkeypatch) -> None:
    from geo_tracker.agent.sms_login import get_handler
    from geo_tracker.agent.sms_login.providers import HeroSMSProvider

    handler = get_handler("chatgpt")
    assert handler is not None
    assert handler.sms_provider_factory is HeroSMSProvider
    provider = _FakeHeroSMSProvider()
    monkeypatch.setattr(handler, "sms_provider_factory", lambda: provider)
    await _patch_successful_flow(monkeypatch, handler, verify_result=True)

    result = await handler.login_or_register()

    assert result["phone"].startswith("+1")
    assert result["cookies"][0]["name"] == "session"
    assert provider.reserved[0].startswith("+1")
    assert provider.polled == [(provider.reserved[0], "OpenAI", 120)]
    assert provider.released == [provider.reserved[0]]
    assert provider.closed is True


@pytest.mark.asyncio
async def test_chatgpt_manual_challenge_does_not_return_cookies(monkeypatch) -> None:
    from geo_tracker.agent.sms_login import get_handler

    handler = get_handler("chatgpt")
    assert handler is not None
    provider = _FakeHeroSMSProvider()
    monkeypatch.setattr(handler, "sms_provider_factory", lambda: provider)
    await _patch_successful_flow(
        monkeypatch,
        handler,
        verify_result="requires_manual_challenge",
    )

    result = await handler.login_or_register()

    assert result == {"status": "failed", "reason": "requires_manual_challenge"}
    assert provider.released == [provider.reserved[0]]
    assert provider.closed is True


@pytest.mark.asyncio
async def test_chatgpt_pre_login_logged_out_shell_can_reach_phone_entry(
    monkeypatch,
) -> None:
    from geo_tracker.agent.sms_login import get_handler

    handler = get_handler("chatgpt")
    assert handler is not None
    page = _FakePage(
        url="https://chatgpt.com/",
        body_text=(
            "Log in to get answers based on saved chats. "
            "Sign up for free. Stay logged out."
        ),
    )

    async def _authenticated(_page):
        return False

    async def _phone_ready(_page):
        return True

    monkeypatch.setattr(handler, "_authenticated", _authenticated)
    monkeypatch.setattr(handler, "_phone_input_ready", _phone_ready)

    result = await handler.navigate_to_login(page)

    assert result is True


@pytest.mark.asyncio
async def test_chatgpt_pre_login_auth_redirect_can_reach_phone_entry(
    monkeypatch,
) -> None:
    from geo_tracker.agent.sms_login import get_handler

    handler = get_handler("chatgpt")
    assert handler is not None
    page = _FakePage(
        url="https://auth0.openai.com/u/login/identifier",
        title="Log in | OpenAI",
        body_text="Continue with phone Log in to OpenAI",
    )

    async def _authenticated(_page):
        return False

    async def _phone_ready(_page):
        return True

    monkeypatch.setattr(handler, "_authenticated", _authenticated)
    monkeypatch.setattr(handler, "_phone_input_ready", _phone_ready)

    result = await handler.navigate_to_login(page)

    assert result is True


@pytest.mark.asyncio
async def test_chatgpt_pre_login_manual_challenge_still_blocks_navigation(
    monkeypatch,
) -> None:
    from geo_tracker.agent.sms_login import get_handler

    handler = get_handler("chatgpt")
    assert handler is not None
    page = _FakePage(
        url="https://chatgpt.com/",
        body_text="Verify you are human before continuing.",
    )

    async def _authenticated(_page):
        return False

    monkeypatch.setattr(handler, "_authenticated", _authenticated)

    result = await handler.navigate_to_login(page)

    assert result == "requires_manual_challenge"


@pytest.mark.asyncio
async def test_chatgpt_post_submit_logged_out_shell_is_rejected(
    monkeypatch,
) -> None:
    from geo_tracker.agent.sms_login import get_handler

    handler = get_handler("chatgpt")
    assert handler is not None
    page = _FakePage(
        url="https://chatgpt.com/",
        body_text=(
            "Log in to get answers based on saved chats. "
            "Sign up for free. Stay logged out."
        ),
    )

    async def _authenticated(_page):
        return False

    monkeypatch.setattr(handler, "_authenticated", _authenticated)

    result = await handler.verify_success(page)

    assert result == "chatgpt_not_logged_in"


@pytest.mark.asyncio
async def test_chatgpt_post_submit_auth_redirect_is_rejected(monkeypatch) -> None:
    from geo_tracker.agent.sms_login import get_handler

    handler = get_handler("chatgpt")
    assert handler is not None
    page = _FakePage(
        url="https://auth0.openai.com/u/login/identifier",
        title="Log in | OpenAI",
        body_text="Log in to ChatGPT. Continue with phone.",
    )

    async def _authenticated(_page):
        return False

    monkeypatch.setattr(handler, "_authenticated", _authenticated)

    result = await handler.verify_success(page)

    assert result == "chatgpt_auth_redirect"


@pytest.mark.asyncio
async def test_doubao_post_submit_login_chrome_rejects_chat_input_false_success(
    monkeypatch,
) -> None:
    from geo_tracker.agent.sms_login import get_handler

    handler = get_handler("doubao")
    assert handler is not None
    page = _FakeDoubaoVerifyPage(
        body_text="bestCoffer answer text\n\u767b\u5f55",
        html="""
        <header><button data-testid="header_login_button">\u767b\u5f55</button></header>
        <main><textarea class="semi-input-textarea"></textarea></main>
        """,
    )

    async def _noop(_page):
        return None

    monkeypatch.setattr(handler, "_handle_captcha", _noop)

    result = await handler.verify_success(page)

    assert result == "doubao_not_logged_in"


def test_doubao_sms_login_uses_configured_proxy(monkeypatch) -> None:
    from geo_tracker.agent.sms_login.base import _sms_login_proxy_url
    from geo_tracker.agent.sms_login.base import _should_use_proxy_for_sms_login

    monkeypatch.setenv("CLASH_PROXY_URL", "http://proxy.internal:6789")
    monkeypatch.delenv("DOUBAO_USE_PROXY", raising=False)

    proxy_url = _sms_login_proxy_url()

    assert proxy_url == "http://proxy.internal:6789"
    assert _should_use_proxy_for_sms_login("doubao", proxy_url) is True


def test_sms_login_keeps_deepseek_direct_when_doubao_proxy_enabled(monkeypatch) -> None:
    from geo_tracker.agent.sms_login.base import _sms_login_proxy_url
    from geo_tracker.agent.sms_login.base import _should_use_proxy_for_sms_login

    monkeypatch.setenv("CLASH_PROXY_URL", "http://proxy.internal:6789")
    monkeypatch.delenv("DOUBAO_USE_PROXY", raising=False)

    proxy_url = _sms_login_proxy_url()

    assert _should_use_proxy_for_sms_login("deepseek", proxy_url) is False


@pytest.mark.parametrize("platform", ["doubao", "deepseek"])
@pytest.mark.asyncio
async def test_existing_handlers_reject_false_success_and_release_number(
    monkeypatch, platform: str
) -> None:
    from geo_tracker.agent.sms_login import get_handler

    handler = get_handler(platform)
    assert handler is not None
    provider = _FakeProvider()
    monkeypatch.setattr(handler, "sms_provider_factory", lambda: provider)
    await _patch_successful_flow(monkeypatch, handler, verify_result=False)

    result = await handler.login_or_register()

    assert result["status"] == "failed"
    assert "登录验证失败" in result["reason"]
    assert "cookies" not in result
    assert provider.released == [FAKE_CN_PHONE]
    assert provider.closed is True


@pytest.mark.asyncio
async def test_sms_provider_flow_redacts_phone_code_and_cookie_from_logs(
    monkeypatch, caplog
) -> None:
    from geo_tracker.agent.sms_login import get_handler

    handler = get_handler("doubao")
    assert handler is not None
    provider = _FakeProvider(code=FAKE_SMS_CODE)
    monkeypatch.setattr(handler, "sms_provider_factory", lambda: provider)
    await _patch_successful_flow(monkeypatch, handler, verify_result=True)

    caplog.set_level(logging.INFO)
    await handler.login_or_register(
        existing_cookies=f'[{{"name":"session","value":"{FAKE_COOKIE_VALUE}"}}]'
    )

    logs = caplog.text
    assert FAKE_CN_PHONE not in logs
    assert FAKE_SMS_CODE not in logs
    assert FAKE_COOKIE_VALUE not in logs


@pytest.mark.asyncio
async def test_sms_registration_exception_redacts_logs_and_returned_reason(
    monkeypatch, caplog
) -> None:
    from geo_tracker.agent.sms_login import get_handler

    handler = get_handler("doubao")
    assert handler is not None
    provider = _FakeProvider()
    monkeypatch.setattr(handler, "sms_provider_factory", lambda: provider)
    await _patch_successful_flow(monkeypatch, handler, verify_result=True)

    async def _raise_sensitive_exception(_page, _phone):
        raise RuntimeError(
            f"browser failed phone={FAKE_CN_PHONE} code={FAKE_SMS_CODE} "
            f"cookie={FAKE_COOKIE_VALUE}"
        )

    monkeypatch.setattr(handler, "input_phone", _raise_sensitive_exception)
    caplog.set_level(logging.ERROR)
    result = await handler.login_or_register()

    logs = caplog.text
    reason = result["reason"]
    assert result["status"] == "failed"
    assert FAKE_CN_PHONE not in logs
    assert FAKE_SMS_CODE not in logs
    assert FAKE_COOKIE_VALUE not in logs
    assert FAKE_CN_PHONE not in reason
    assert FAKE_SMS_CODE not in reason
    assert FAKE_COOKIE_VALUE not in reason
