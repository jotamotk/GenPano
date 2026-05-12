import logging
import sys
import types

import pytest


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
    def __init__(self) -> None:
        self.url = "https://example.test/login"
        self.keyboard = _FakeKeyboard()

    async def goto(self, url: str, **_kwargs) -> None:
        self.url = url

    async def wait_for_timeout(self, _ms: int) -> None:
        return None

    async def query_selector(self, _selector: str):
        return None

    async def evaluate(self, _script: str):
        return {}

    def on(self, _event: str, _handler) -> None:
        return None

    def remove_listener(self, _event: str, _handler) -> None:
        return None


class _FakeContext:
    async def new_page(self) -> _FakePage:
        return _FakePage()

    async def add_cookies(self, _cookies) -> None:
        return None

    async def cookies(self):
        return [
            {
                "name": "session",
                "value": "cookie-secret-value",
                "domain": "example.test",
                "path": "/",
            }
        ]


class _FakeProvider:
    provider_name = "fake-sms"

    def __init__(self, *, code: str = "123456") -> None:
        self.code = code
        self.reserved = []
        self.polled = []
        self.released = []
        self.closed = False

    async def reserve_number(self, *, phone=None):
        from geo_tracker.agent.sms_login.providers import SMSNumberLease

        number = phone or "13812345678"
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

    assert result["phone"] == "13812345678"
    assert result["cookies"][0]["name"] == "session"
    assert provider.reserved == ["13812345678"]
    assert provider.polled == [("13812345678", keyword, 120)]
    assert provider.released == ["13812345678"]
    assert provider.closed is True


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
    assert provider.released == ["13812345678"]
    assert provider.closed is True


@pytest.mark.asyncio
async def test_sms_provider_flow_redacts_phone_code_and_cookie_from_logs(
    monkeypatch, caplog
) -> None:
    from geo_tracker.agent.sms_login import get_handler

    handler = get_handler("doubao")
    assert handler is not None
    provider = _FakeProvider(code="654321")
    monkeypatch.setattr(handler, "sms_provider_factory", lambda: provider)
    await _patch_successful_flow(monkeypatch, handler, verify_result=True)

    caplog.set_level(logging.INFO)
    await handler.login_or_register(
        existing_cookies='[{"name":"session","value":"cookie-secret-value"}]'
    )

    logs = caplog.text
    assert "13812345678" not in logs
    assert "654321" not in logs
    assert "cookie-secret-value" not in logs


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
            "browser failed phone=13812345678 code=654321 "
            "cookie=cookie-secret-value"
        )

    monkeypatch.setattr(handler, "input_phone", _raise_sensitive_exception)
    caplog.set_level(logging.ERROR)
    result = await handler.login_or_register()

    logs = caplog.text
    reason = result["reason"]
    assert result["status"] == "failed"
    assert "13812345678" not in logs
    assert "654321" not in logs
    assert "cookie-secret-value" not in logs
    assert "13812345678" not in reason
    assert "654321" not in reason
    assert "cookie-secret-value" not in reason
