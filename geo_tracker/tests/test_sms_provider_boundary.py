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


class _RecordingGotoPage(_FakePage):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.goto_calls = []

    async def goto(self, url: str, **kwargs) -> None:
        self.goto_calls.append({"url": url, **kwargs})
        self.url = url


class _TransientGotoPage(_RecordingGotoPage):
    def __init__(self, *, failures: int = 1, **kwargs) -> None:
        super().__init__(**kwargs)
        self.failures = failures

    async def goto(self, url: str, **kwargs) -> None:
        self.goto_calls.append({"url": url, **kwargs})
        if self.failures > 0:
            self.failures -= 1
            raise RuntimeError("Page.goto: NS_ERROR_NET_INTERRUPT")
        self.url = url


class _VisibleElement:
    async def is_visible(self) -> bool:
        return True


class _DetachedAfterClickElement:
    def __init__(self) -> None:
        self.clicks = 0

    async def click(self, *_args, **_kwargs) -> None:
        self.clicks += 1
        raise RuntimeError("ElementHandle.click: Element is not attached to the DOM")


class _DoubaoDetachedAfterSubmitPage(_FakePage):
    def __init__(self) -> None:
        super().__init__(
            url="https://www.doubao.com/chat",
            body_text="",
        )
        self.submit = _DetachedAfterClickElement()

    async def query_selector(self, selector: str):
        if "[data-testid='login_next_button']" in selector:
            return self.submit
        if "textarea" in selector:
            return _VisibleElement()
        return None

    async def content(self) -> str:
        return "<html><body><div class='user-avatar'></div><textarea></textarea></body></html>"


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


class _FakeDoubaoLoggedOutRuntimePage(_FakePage):
    def __init__(self) -> None:
        super().__init__(
            url="https://www.doubao.com/chat/?from_logout=1",
            body_text="bestCoffer answer text",
        )
        self._html = """
        <script>
        window.__doubao_state__ = {
          accountInfo: {data: {description: "会话过期，请重新登录", error_code: 13, user_id: 0}},
          userSetting: {data: {is_login: false}}
        };
        </script>
        <textarea placeholder="发消息"></textarea>
        <main><div class="flow-markdown-body">answer text</div></main>
        """

    async def evaluate(self, script: str):
        if "outerHTML" in script:
            return self._html
        if "innerText" in script:
            return self._body_text
        if "document.querySelectorAll('textarea')" in script:
            return {"chat": True, "loginBtn": False}
        return {}

    async def content(self) -> str:
        return self._html

    async def wait_for_selector(self, *_args, **_kwargs):
        raise TimeoutError("not found")


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


class _EmptyCookieContext(_FakeContext):
    async def cookies(self):
        return []


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


class _ReloginFallbackProvider(_FakeProvider):
    def __init__(self, *, new_phone: str, code: str = "123" + "456") -> None:
        super().__init__(code=code)
        self.new_phone = new_phone

    async def reserve_number(self, *, phone=None):
        from geo_tracker.agent.sms_login.providers import SMSNumberLease

        if phone:
            self.reserved.append(phone)
            raise RuntimeError("existing number is offline")

        self.reserved.append(self.new_phone)
        return SMSNumberLease(
            phone=self.new_phone,
            provider_name=self.provider_name,
            price_bucket="existing-luban",
        )


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


class _TimeoutHeroSMSProvider(_FakeHeroSMSProvider):
    async def reserve_number(self, *, phone=None):
        from geo_tracker.agent.sms_login.providers import SMSNumberLease

        number = "+1" + "202" + "555" + f"{198 + len(self.reserved):04d}"
        self.reserved.append(number)
        return SMSNumberLease(
            phone=number,
            provider_name=self.provider_name,
            price_bucket="usd<=0.60",
            provider_ref=f"{FAKE_PROVIDER_REF}-{len(self.reserved)}",
        )

    async def poll_sms_code(self, lease, *, keyword: str, timeout: int):
        self.polled.append((lease.phone, keyword, timeout))
        raise TimeoutError("HeroSMS SMS polling timed out")


async def _patch_successful_flow(monkeypatch, handler, *, verify_result):
    from geo_tracker.agent.sms_login import base

    async def _launch_browser(qg_lease=None):
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
async def test_existing_cookie_relogin_success_skips_sms_phone_form(monkeypatch) -> None:
    from geo_tracker.agent.sms_login import get_handler

    handler = get_handler("doubao")
    assert handler is not None
    from geo_tracker.agent.sms_login import base

    provider = _FakeProvider()
    monkeypatch.setattr(handler, "sms_provider_factory", lambda: provider)

    async def _launch_browser(qg_lease=None):
        return object(), None, object(), _FakeContext(_FakePage())

    async def _navigate(_page):
        return True

    async def _verify(_page):
        return True

    async def _input_phone(_page, _phone):
        raise AssertionError("phone input should be skipped for valid cookies")

    async def _none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(handler, "_launch_browser", _launch_browser)
    monkeypatch.setattr(base, "install_resource_blocker", _none)
    monkeypatch.setattr(base, "cleanup_browser_resources", _none)
    monkeypatch.setattr(handler, "_add_stealth_script", _none)
    monkeypatch.setattr(handler, "navigate_to_login", _navigate)
    monkeypatch.setattr(handler, "verify_success", _verify)
    monkeypatch.setattr(handler, "input_phone", _input_phone)

    result = await handler.login_or_register(
        existing_cookies=f'[{{"name":"session","value":"{FAKE_COOKIE_VALUE}"}}]',
        phone=FAKE_CN_PHONE,
    )

    assert result["phone"] == FAKE_CN_PHONE
    assert result["cookies"][0]["name"] == "session"
    assert provider.reserved == [FAKE_CN_PHONE]
    assert provider.polled == []
    assert provider.released == [FAKE_CN_PHONE]
    assert provider.closed is True


@pytest.mark.asyncio
async def test_doubao_relogin_fallback_continues_sms_when_inline_form_is_ready(
    monkeypatch,
) -> None:
    from geo_tracker.agent.sms_login import base, get_handler

    handler = get_handler("doubao")
    assert handler is not None
    new_phone = "139" + "1234" + "5678"
    provider = _ReloginFallbackProvider(new_phone=new_phone)
    page = _FakePage(url="https://www.doubao.com/chat", body_text="登录")
    entered_phones: list[str] = []

    monkeypatch.setattr(handler, "sms_provider_factory", lambda: provider)

    async def _launch_browser(qg_lease=None):
        return object(), None, object(), _FakeContext(page)

    async def _none(*_args, **_kwargs):
        return None

    async def _true(*_args, **_kwargs):
        return True

    async def _inline_form_ready(_page):
        return True

    verify_results = iter(["doubao_not_logged_in", True])

    async def _verify(_page):
        return next(verify_results)

    async def _input_phone(_page, phone):
        entered_phones.append(phone)
        return True

    monkeypatch.setattr(base, "install_resource_blocker", _none)
    monkeypatch.setattr(base, "cleanup_browser_resources", _none)
    monkeypatch.setattr(handler, "_launch_browser", _launch_browser)
    monkeypatch.setattr(handler, "_add_stealth_script", _none)
    monkeypatch.setattr(handler, "_handle_captcha", _none)
    monkeypatch.setattr(handler, "_detect_error_toast", _none)
    monkeypatch.setattr(handler, "navigate_to_login", _true)
    monkeypatch.setattr(handler, "_login_form_ready", _inline_form_ready)
    monkeypatch.setattr(handler, "verify_success", _verify)
    monkeypatch.setattr(handler, "input_phone", _input_phone)
    monkeypatch.setattr(handler, "click_send_sms", _true)
    monkeypatch.setattr(handler, "input_code", _true)
    monkeypatch.setattr(handler, "submit_login", _true)

    result = await handler.login_or_register(
        existing_cookies=f'[{{"name":"session","value":"{FAKE_COOKIE_VALUE}"}}]',
        phone=FAKE_CN_PHONE,
    )

    assert result["phone"] == new_phone
    assert entered_phones == [new_phone]
    assert provider.reserved == [FAKE_CN_PHONE, new_phone]
    assert provider.polled == [(new_phone, "豆包", 120)]
    assert provider.released == [new_phone]
    assert provider.closed is True


@pytest.mark.asyncio
async def test_doubao_submit_treats_detached_button_after_success_as_recoverable() -> None:
    from geo_tracker.agent.sms_login import get_handler

    handler = get_handler("doubao")
    assert handler is not None
    page = _DoubaoDetachedAfterSubmitPage()

    assert await handler.submit_login(page) is True
    assert page.submit.clicks == 1


@pytest.mark.asyncio
async def test_doubao_already_logged_in_rejects_runtime_logged_out_markers(
    monkeypatch,
) -> None:
    from geo_tracker.agent.sms_login import get_handler

    handler = get_handler("doubao")
    assert handler is not None
    page = _FakeDoubaoLoggedOutRuntimePage()

    assert await handler._already_logged_in(page) is False


@pytest.mark.asyncio
async def test_doubao_existing_cookie_relogin_does_not_succeed_on_logged_out_runtime(
    monkeypatch,
) -> None:
    from geo_tracker.agent.sms_login import base, get_handler

    handler = get_handler("doubao")
    assert handler is not None
    provider = _FakeProvider()
    page = _FakeDoubaoLoggedOutRuntimePage()
    monkeypatch.setattr(handler, "sms_provider_factory", lambda: provider)

    async def _launch_browser(qg_lease=None):
        return object(), None, object(), _FakeContext(page)

    async def _none(*_args, **_kwargs):
        return None

    async def _empty_candidates(_page):
        return []

    monkeypatch.setattr(base, "install_resource_blocker", _none)
    monkeypatch.setattr(base, "cleanup_browser_resources", _none)
    monkeypatch.setattr(handler, "_launch_browser", _launch_browser)
    monkeypatch.setattr(handler, "_add_stealth_script", _none)
    monkeypatch.setattr(handler, "_save_debug", _none)
    monkeypatch.setattr(handler, "_collect_login_candidates", _empty_candidates)

    result = await handler.login_or_register(
        existing_cookies=f'[{{"name":"session","value":"{FAKE_COOKIE_VALUE}"}}]',
        phone=FAKE_CN_PHONE,
    )

    assert result["status"] == "failed"
    assert "cookies" not in result
    assert provider.polled == []
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


def test_chatgpt_herosms_attempt_budget_is_bounded_without_changing_others() -> None:
    from geo_tracker.agent.sms_login import get_handler

    chatgpt = get_handler("chatgpt")
    doubao = get_handler("doubao")
    deepseek = get_handler("deepseek")

    assert chatgpt is not None
    assert doubao is not None
    assert deepseek is not None
    assert chatgpt.MAX_PHONE_RETRIES == 2
    assert doubao.MAX_PHONE_RETRIES == 5
    assert deepseek.MAX_PHONE_RETRIES == 5


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
async def test_chatgpt_success_requires_persistable_cookies(monkeypatch) -> None:
    from geo_tracker.agent.sms_login import base, get_handler

    handler = get_handler("chatgpt")
    assert handler is not None
    page = _RecordingGotoPage()
    provider = _FakeHeroSMSProvider()
    monkeypatch.setattr(handler, "sms_provider_factory", lambda: provider)
    await _patch_successful_flow(monkeypatch, handler, verify_result=True)

    async def _launch_browser(qg_lease=None):
        return object(), None, object(), _EmptyCookieContext(page)

    async def _none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(handler, "_launch_browser", _launch_browser)
    monkeypatch.setattr(base, "install_resource_blocker", _none)
    monkeypatch.setattr(base, "cleanup_browser_resources", _none)

    result = await handler.login_or_register()

    assert result == {"status": "failed", "reason": "cookies_missing_after_success"}
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


class _FakeDoubaoLoggedOutLandingPage(_FakePage):
    """Refs #963: Doubao 2026 landing page that passes
    ``doubao_auth_state_reason`` (positive ``user-avatar`` marker present
    in HTML) AND has chat input visible, but ALSO still renders a
    plain-text "登录" button — the exact false-success shape that
    triggered the ``doubao_post_reauth_doubao_not_logged_in`` failure
    after PR #1000 deploy. The OLD ``verify_success`` accepted this
    because positive markers + chat input were enough; the fix reuses
    the strict ``_already_logged_in`` proof which additionally requires
    the login button to be absent.
    """

    def __init__(self, *, login_button_visible: bool) -> None:
        super().__init__(
            url="https://www.doubao.com/chat",
            # Includes a positive auth marker so the inner
            # _post_login_auth_failure_reason short-circuit does NOT
            # reject this case before the strict proof runs.
            body_text="user-avatar 我的账号",
        )
        self._login_button_visible = login_button_visible

    async def query_selector(self, selector: str):
        # Modal probe returns None (modal not visible), textarea probe
        # returns the visible chat input.
        if "login_content" in selector:
            return None
        if "textarea" in selector:
            return _VisibleElement()
        return None

    async def content(self) -> str:
        # Positive auth marker keeps _post_login_auth_failure_reason None.
        return """
        <body>
          <header>
            <div class="user-avatar"></div>
          </header>
          <main><textarea class="semi-input-textarea"></textarea></main>
        </body>
        """

    async def evaluate(self, script: str):
        if "innerText" in script:
            return self._body_text
        # _already_logged_in's JS check returns {chat, loginBtn}.
        if "textarea" in script and "loginBtn" in script:
            return {"chat": True, "loginBtn": self._login_button_visible}
        return {}


@pytest.mark.asyncio
async def test_doubao_verify_success_rejects_visible_login_button_false_success(
    monkeypatch,
) -> None:
    """Refs #963 follow-up: the previous ``verify_success`` accepted a
    chat-input + no-auth-chrome page as logged-in, but Doubao's 2026
    logged-out landing also renders the chat input (for guest preview)
    while a plain-text "登录" button stays visible in the header. Account
    42 reauth on 2026-05-15 wrote cookies on the back of this false
    success, then the very next ``execute_query`` page load classified
    the row as ``doubao_post_reauth_doubao_not_logged_in`` because the
    session token was never actually established. ``verify_success``
    must reuse the stricter ``_already_logged_in`` proof and reject this
    state, so the SMS handler returns failed instead of writing a
    half-baked cookie set."""
    from geo_tracker.agent.sms_login import get_handler

    handler = get_handler("doubao")
    assert handler is not None

    async def _noop(_page):
        return None

    monkeypatch.setattr(handler, "_handle_captcha", _noop)

    page = _FakeDoubaoLoggedOutLandingPage(login_button_visible=True)
    result = await handler.verify_success(page)
    assert result is False, (
        "verify_success must reject when a visible 登录 button proves "
        "the session was not actually established, even if the chat "
        "input is visible and the body has no strong auth-chrome markers"
    )


@pytest.mark.asyncio
async def test_doubao_verify_success_accepts_strict_logged_in_state(
    monkeypatch,
) -> None:
    """Refs #963 follow-up: the strict ``_already_logged_in`` proof must
    still accept a real logged-in state — chat input visible AND no
    visible "登录" button. Regression cover for the stricter
    ``verify_success`` so it does not over-reject legitimate logins."""
    from geo_tracker.agent.sms_login import get_handler

    handler = get_handler("doubao")
    assert handler is not None

    async def _noop(_page):
        return None

    monkeypatch.setattr(handler, "_handle_captcha", _noop)

    page = _FakeDoubaoLoggedOutLandingPage(login_button_visible=False)
    result = await handler.verify_success(page)
    assert result is True


@pytest.mark.asyncio
async def test_doubao_already_logged_in_accepts_stable_selector_chat_input_without_placeholder(
    monkeypatch,
) -> None:
    """Refs #963 / PR #1005 review (Codex P2): the chat-input detector
    must accept Doubao's 2026 stable id/class selectors (``#input-engine-
    container textarea.semi-input-textarea`` / ``textarea.semi-input-
    textarea``) even when the textarea ``placeholder`` is empty after
    login. Without this, a real post-SMS logged-in page where Doubao left
    the placeholder blank would fail ``_already_logged_in`` and the
    stricter ``verify_success`` (PR #1005) would over-reject the real
    login."""
    from geo_tracker.agent.sms_login import get_handler

    handler = get_handler("doubao")
    assert handler is not None

    class _StableSelectorLoggedInPage(_FakePage):
        def __init__(self) -> None:
            super().__init__(
                url="https://www.doubao.com/chat",
                body_text="user-avatar 我的账号",
            )

        async def query_selector(self, selector: str):
            if "login_content" in selector:
                return None
            if "textarea" in selector:
                return _VisibleElement()
            return None

        async def content(self) -> str:
            return """
            <body>
              <header><div class="user-avatar"></div></header>
              <main>
                <div id="input-engine-container">
                  <textarea class="semi-input-textarea"></textarea>
                </div>
              </main>
            </body>
            """

        async def evaluate(self, script: str):
            if "innerText" in script:
                return self._body_text
            # The new _already_logged_in JS finds the chat input via the
            # stable id/class selector even though placeholder is blank.
            if "isVisibleTextarea" in script or "stableSelectors" in script:
                return {"chat": True, "loginBtn": False}
            # Backwards compat: pre-fix JS only matched placeholder, so
            # it would return {chat: false} — proves we are not relying
            # on the old path.
            if "placeholder" in script and "loginBtn" in script:
                return {"chat": False, "loginBtn": False}
            return {}

    async def _noop(_page):
        return None

    monkeypatch.setattr(handler, "_handle_captcha", _noop)

    result = await handler._already_logged_in(_StableSelectorLoggedInPage())
    assert result is True, (
        "_already_logged_in must accept the stable id/class chat input "
        "even when textarea.placeholder is blank"
    )


def test_doubao_sms_login_uses_configured_proxy(monkeypatch) -> None:
    # Refs #963: DOUBAO_USE_PROXY now defaults to False (direct connect from
    # the China-hosted worker). This test exercises the opt-in proxy path,
    # so enable it explicitly to verify the SMS login wiring still picks up
    # the configured proxy when an operator chooses to route through it.
    from geo_tracker.agent.sms_login.base import _sms_login_proxy_url
    from geo_tracker.agent.sms_login.base import _should_use_proxy_for_sms_login

    monkeypatch.setenv("CLASH_PROXY_URL", "http://proxy.internal:6789")
    monkeypatch.setenv("DOUBAO_USE_PROXY", "1")

    proxy_url = _sms_login_proxy_url()

    assert proxy_url == "http://proxy.internal:6789"
    assert _should_use_proxy_for_sms_login("doubao", proxy_url) is True


def test_doubao_sms_login_proxy_flag_still_disables_proxy(monkeypatch) -> None:
    from geo_tracker.agent.sms_login.base import _sms_login_proxy_url
    from geo_tracker.agent.sms_login.base import _should_use_proxy_for_sms_login

    monkeypatch.setenv("CLASH_PROXY_URL", "http://proxy.internal:6789")
    monkeypatch.setenv("DOUBAO_USE_PROXY", "false")

    proxy_url = _sms_login_proxy_url()

    assert _should_use_proxy_for_sms_login("doubao", proxy_url) is False


def test_chatgpt_sms_login_uses_configured_proxy_by_default(monkeypatch) -> None:
    from geo_tracker.agent.sms_login.base import _sms_login_proxy_url
    from geo_tracker.agent.sms_login.base import _should_use_proxy_for_sms_login

    monkeypatch.setenv("CLASH_PROXY_URL", "http://user:secret@proxy.internal:6789")
    monkeypatch.delenv("CHATGPT_SMS_USE_PROXY", raising=False)

    proxy_url = _sms_login_proxy_url()

    assert proxy_url == "http://user:secret@proxy.internal:6789"
    assert _should_use_proxy_for_sms_login("chatgpt", proxy_url) is True


def test_chatgpt_sms_login_proxy_flag_can_disable_proxy(monkeypatch) -> None:
    from geo_tracker.agent.sms_login.base import _sms_login_proxy_url
    from geo_tracker.agent.sms_login.base import _should_use_proxy_for_sms_login

    monkeypatch.setenv("CLASH_PROXY_URL", "http://proxy.internal:6789")
    monkeypatch.setenv("CHATGPT_SMS_USE_PROXY", "false")

    proxy_url = _sms_login_proxy_url()

    assert _should_use_proxy_for_sms_login("chatgpt", proxy_url) is False


def test_sms_redaction_masks_proxy_credentials() -> None:
    from geo_tracker.agent.sms_redaction import redact_sensitive_text

    text = redact_sensitive_text(
        "proxy=http://proxy-user:proxy-secret@proxy.internal:6789"
    )

    assert "proxy-user" not in text
    assert "proxy-secret" not in text
    assert "proxy.internal" in text


@pytest.mark.asyncio
async def test_phone_blacklist_log_masks_phone(monkeypatch, caplog) -> None:
    from geo_tracker.agent.sms_login import phone_blacklist
    from geo_tracker.agent.sms_redaction import mask_phone

    class _FakeRedisClient:
        async def set(self, *_args, **_kwargs) -> None:
            return None

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(
        phone_blacklist.aioredis,
        "from_url",
        lambda *_args, **_kwargs: _FakeRedisClient(),
    )

    caplog.set_level(logging.INFO, logger="geo_tracker.agent.sms_login.phone_blacklist")
    await phone_blacklist.add_to_blacklist("chatgpt", FAKE_US_PHONE, reason="sms_timeout")

    logs = caplog.text
    assert FAKE_US_PHONE not in logs
    assert mask_phone(FAKE_US_PHONE) in logs


def test_sms_login_keeps_deepseek_direct_when_doubao_proxy_enabled(monkeypatch) -> None:
    from geo_tracker.agent.sms_login.base import _sms_login_proxy_url
    from geo_tracker.agent.sms_login.base import _should_use_proxy_for_sms_login

    monkeypatch.setenv("CLASH_PROXY_URL", "http://proxy.internal:6789")
    monkeypatch.delenv("DOUBAO_USE_PROXY", raising=False)

    proxy_url = _sms_login_proxy_url()

    assert _should_use_proxy_for_sms_login("deepseek", proxy_url) is False


@pytest.mark.asyncio
async def test_chatgpt_initial_navigation_waits_for_domcontentloaded(
    monkeypatch,
) -> None:
    from geo_tracker.agent.sms_login import base, get_handler

    handler = get_handler("chatgpt")
    assert handler is not None
    page = _RecordingGotoPage()
    provider = _FakeHeroSMSProvider()
    monkeypatch.setattr(handler, "sms_provider_factory", lambda: provider)
    await _patch_successful_flow(monkeypatch, handler, verify_result=True)

    async def _launch_browser(qg_lease=None):
        return object(), None, object(), _FakeContext(page)

    async def _none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(handler, "_launch_browser", _launch_browser)
    monkeypatch.setattr(base, "install_resource_blocker", _none)
    monkeypatch.setattr(base, "cleanup_browser_resources", _none)

    result = await handler.login_or_register()

    assert "cookies" in result
    assert page.goto_calls[0]["url"] == "https://chatgpt.com/"
    assert page.goto_calls[0]["wait_until"] == "domcontentloaded"


@pytest.mark.asyncio
async def test_chatgpt_initial_navigation_recovers_from_transient_interrupt(
    monkeypatch,
) -> None:
    from geo_tracker.agent.sms_login import base, get_handler

    handler = get_handler("chatgpt")
    assert handler is not None
    page = _TransientGotoPage(failures=1)
    provider = _FakeHeroSMSProvider()
    monkeypatch.setattr(handler, "sms_provider_factory", lambda: provider)
    await _patch_successful_flow(monkeypatch, handler, verify_result=True)

    async def _launch_browser(qg_lease=None):
        return object(), None, object(), _FakeContext(page)

    async def _none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(handler, "_launch_browser", _launch_browser)
    monkeypatch.setattr(base, "install_resource_blocker", _none)
    monkeypatch.setattr(base, "cleanup_browser_resources", _none)

    result = await handler.login_or_register()

    assert "cookies" in result
    assert len(page.goto_calls) == 2
    assert all(call["wait_until"] == "domcontentloaded" for call in page.goto_calls)


@pytest.mark.asyncio
async def test_doubao_initial_navigation_still_waits_for_load(monkeypatch) -> None:
    from geo_tracker.agent.sms_login import base, get_handler

    handler = get_handler("doubao")
    assert handler is not None
    page = _RecordingGotoPage()
    provider = _FakeProvider()
    monkeypatch.setattr(handler, "sms_provider_factory", lambda: provider)
    await _patch_successful_flow(monkeypatch, handler, verify_result=True)

    async def _launch_browser(qg_lease=None):
        return object(), None, object(), _FakeContext(page)

    async def _none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(handler, "_launch_browser", _launch_browser)
    monkeypatch.setattr(base, "install_resource_blocker", _none)
    monkeypatch.setattr(base, "cleanup_browser_resources", _none)

    result = await handler.login_or_register()

    assert "cookies" in result
    assert page.goto_calls[0]["wait_until"] == "load"


@pytest.mark.parametrize("platform", ["doubao", "deepseek"])
@pytest.mark.asyncio
async def test_existing_handlers_preserve_navigation_exception_reason(
    monkeypatch, platform: str
) -> None:
    from geo_tracker.agent.sms_login import base, get_handler

    handler = get_handler(platform)
    assert handler is not None
    page = _TransientGotoPage(failures=1)
    provider = _FakeProvider()
    monkeypatch.setattr(handler, "sms_provider_factory", lambda: provider)
    await _patch_successful_flow(monkeypatch, handler, verify_result=True)

    async def _launch_browser(qg_lease=None):
        return object(), None, object(), _FakeContext(page)

    async def _none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(handler, "_launch_browser", _launch_browser)
    monkeypatch.setattr(base, "install_resource_blocker", _none)
    monkeypatch.setattr(base, "cleanup_browser_resources", _none)

    result = await handler.login_or_register()

    assert result["status"] == "failed"
    assert result["reason"] != "browser_timeout"
    assert "NS_ERROR_NET_INTERRUPT" in result["reason"]
    assert "cookies" not in result
    assert len(page.goto_calls) == 1


@pytest.mark.asyncio
async def test_chatgpt_sms_poll_timeout_returns_sms_timeout_without_cookies(
    monkeypatch,
) -> None:
    from geo_tracker.agent.sms_login import base, get_handler

    handler = get_handler("chatgpt")
    assert handler is not None
    provider = _TimeoutHeroSMSProvider()
    blacklist_reasons = []
    monkeypatch.setattr(handler, "sms_provider_factory", lambda: provider)
    monkeypatch.setattr(handler, "MAX_PHONE_RETRIES", 2)
    await _patch_successful_flow(monkeypatch, handler, verify_result=True)

    async def _blacklist(platform, phone, *, reason, permanent=False):
        blacklist_reasons.append((platform, phone, reason, permanent))

    monkeypatch.setattr(base, "add_to_blacklist", _blacklist)

    result = await handler.login_or_register()

    assert result == {"status": "failed", "reason": "sms_timeout"}
    assert "cookies" not in result
    assert len(provider.reserved) == 2
    assert provider.polled == [
        (provider.reserved[0], "OpenAI", 120),
        (provider.reserved[1], "OpenAI", 120),
    ]
    assert provider.released == provider.reserved
    assert [item[2] for item in blacklist_reasons] == ["sms_timeout", "sms_timeout"]


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


@pytest.mark.asyncio
async def test_luban_get_keyword_sms_raises_with_length_and_sha8_when_no_digits(
    monkeypatch,
) -> None:
    """Refs #963: when the SMS body has no extractable digits, the
    RuntimeError raised by ``get_keyword_sms`` must include ``len=<N>``
    and ``sha8=<8-hex-chars>`` so worker logs can distinguish failure
    modes (empty body vs non-empty-no-digit vs a specific recurring
    template) across iterations WITHOUT leaking the body itself. This is
    diagnostic-only instrumentation — auto-fallback to the service_id
    pool must remain off until anti-scraping + SMS-to-DB are proven."""
    import hashlib
    import re

    monkeypatch.setenv("LUBANSMS_TOKEN", "unit-token")
    from geo_tracker.agent.sms_login.luban_client import LubanSMSClient

    fixture_body = "欢迎使用豆包，请激活账号"
    expected_len = len(fixture_body)
    expected_sha8 = hashlib.sha256(fixture_body.encode()).hexdigest()[:8]

    class _FakeResponse:
        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def json(self) -> dict:
            return self._payload

    class _FakeHttpxClient:
        def __init__(self) -> None:
            self.calls = 0

        async def get(self, _url: str, params=None) -> _FakeResponse:
            self.calls += 1
            return _FakeResponse({"code": 0, "msg": fixture_body})

        async def aclose(self) -> None:
            return None

    client = LubanSMSClient()
    client.client = _FakeHttpxClient()

    with pytest.raises(RuntimeError) as excinfo:
        await client.get_keyword_sms("13800000000", "豆包", timeout=5)

    message = str(excinfo.value)
    assert "无法从短信中提取验证码" in message
    assert "[sms-text-redacted" in message
    assert f"len={expected_len}" in message
    # Refs PR #1101 Codex P2 review
    # (https://github.com/jotamotk/trash_test/pull/1101#discussion_r3253891280):
    # the sha8 must be emitted with a leading ``h`` so the downstream
    # ``redact_sensitive_text`` cannot match it as a 4–8 digit SMS code.
    assert f"sha8=h{expected_sha8}" in message
    # sha8 must be exactly 8 hex chars after the ``h`` prefix (not raw
    # body, not the full digest).
    sha8_match = re.search(r"sha8=h([0-9a-f]+)", message)
    assert sha8_match is not None
    assert len(sha8_match.group(1)) == 8
    # And the body itself must NOT leak into the error message.
    assert fixture_body not in message


@pytest.mark.asyncio
async def test_luban_sha8_survives_redact_sensitive_text_for_all_digit_hash(
    monkeypatch,
) -> None:
    """Refs PR #1101 Codex P2 review
    (https://github.com/jotamotk/trash_test/pull/1101#discussion_r3253891280):
    the ``sha8=`` diagnostic suffix is emitted by ``get_keyword_sms`` and
    then wrapped in ``base.py`` through ``redact_sensitive_text``, whose
    ``SMS_CODE_RE = re.compile(r"(?<!\\*)\\b\\d{4,8}\\b")`` would replace
    a bare all-digit 8-char sha8 with ``[sms-code-redacted]`` — silently
    dropping ~10% of diagnostic samples (probability
    ``(10/16)^8 ≈ 10%``). This test pins the worker log path: it picks a
    deterministic fixture whose ``sha256[:8]`` is all digits (the worst
    case Codex flagged), runs the full RuntimeError string through
    ``redact_sensitive_text``, and asserts the ``sha8=h<hex>`` token
    survives intact. If the production code ever regresses to emitting
    a bare ``sha8={hex}`` (no ``h`` prefix), this test fails for the same
    reason Codex flagged: the 8-digit run is matched and clobbered."""
    import hashlib
    import re

    from geo_tracker.agent.sms_redaction import redact_sensitive_text

    monkeypatch.setenv("LUBANSMS_TOKEN", "unit-token")
    from geo_tracker.agent.sms_login.luban_client import LubanSMSClient

    # Deterministic fixture: ``sha256("欢迎使用豆包，请激活账号 126")[:8] ==
    # "39752629"`` (all digits). Chosen by brute force over integer
    # suffixes so a future reader can re-derive it offline.
    fixture_body = "欢迎使用豆包，请激活账号 126"
    expected_sha8 = hashlib.sha256(fixture_body.encode()).hexdigest()[:8]
    assert expected_sha8.isdigit(), (
        "fixture must produce an all-digit sha8 so the test exercises "
        "the redact_sensitive_text SMS_CODE_RE worst case"
    )
    assert expected_sha8 == "39752629"

    class _FakeResponse:
        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def json(self) -> dict:
            return self._payload

    class _FakeHttpxClient:
        async def get(self, _url: str, params=None) -> _FakeResponse:
            return _FakeResponse({"code": 0, "msg": fixture_body})

        async def aclose(self) -> None:
            return None

    client = LubanSMSClient()
    client.client = _FakeHttpxClient()

    with pytest.raises(RuntimeError) as excinfo:
        await client.get_keyword_sms("13800000000", "豆包", timeout=5)

    raw_message = str(excinfo.value)
    # Sanity: production string carries the h-prefixed sha8.
    assert f"sha8=h{expected_sha8}" in raw_message

    # The actual regression check: run the RuntimeError text through the
    # exact redaction hop used by ``base.py`` and confirm the ``sha8=h``
    # token is preserved end-to-end.
    redacted = redact_sensitive_text(excinfo.value)
    assert f"sha8=h{expected_sha8}" in redacted, (
        "h-prefixed sha8 must survive redact_sensitive_text even when "
        f"sha8 is all-digits; got: {redacted!r}"
    )
    assert "[sms-code-redacted]" not in redacted.split("sha8=", 1)[1], (
        "the sha8 token must NOT be clobbered by SMS_CODE_RE; if this "
        "fails the production code likely regressed to emitting bare "
        "sha8={hex} without the leading h"
    )
    # Belt-and-braces: extracting the sha8 from the redacted string must
    # still yield the exact 8-digit hash.
    match = re.search(r"sha8=h([0-9a-f]{8})", redacted)
    assert match is not None
    assert match.group(1) == expected_sha8
