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


def _api_key() -> str:
    return "unit-" + "key"


def _activation_id() -> str:
    return "act-" + "unit"


def _phone() -> str:
    return "+1" + "202" + "555" + "0182"


def _access_number_response() -> str:
    return "ACCESS_" + "NUMBER:" + _activation_id() + ":" + _phone()


def _status_ok_response(code: str) -> str:
    return "STATUS_" + "OK:" + code


def _offer_payload(
    *,
    service: str = "dr",
    operator: str = "physic",
    count_physical: int = 5,
    price: str = "0.2200",
    price_count: int = 3,
) -> dict:
    return {
        "data": {
            service: {
                "operators": [
                    {
                        "name": operator,
                        "countPhysical": count_physical,
                        "freePriceOffers": {price: price_count},
                    }
                ]
            }
        }
    }


def _multi_operator_offer_payload(*, operators: list[dict]) -> dict:
    return {
        "data": {
            "dr": {
                "operators": operators,
            }
        }
    }


class _FakeResponse:
    def __init__(self, *, json_data=None, text: str = "", status_code: int = 200):
        self._json_data = json_data
        self.text = text
        self.status_code = status_code

    def json(self):
        if self._json_data is None:
            raise ValueError("not json")
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self.text}")


class _FakeHTTPClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.closed = False

    async def get(self, url: str, *, params=None, headers=None):
        self.calls.append({"url": url, "params": dict(params or {})})
        if not self.responses:
            raise AssertionError(f"unexpected request {url}")
        response = self.responses.pop(0)
        if callable(response):
            response = response(url, dict(params or {}))
        return response

    async def aclose(self) -> None:
        self.closed = True


def _handler_calls(fake: _FakeHTTPClient, action: str | None = None):
    calls = [
        call
        for call in fake.calls
        if call["url"].endswith("/stubs/handler_api.php")
    ]
    if action is not None:
        calls = [call for call in calls if call["params"].get("action") == action]
    return calls


@pytest.mark.asyncio
async def test_reserve_number_requires_compliant_us_physical_openai_offer():
    from geo_tracker.agent.sms_login.herosms_client import HeroSMSClient
    from geo_tracker.agent.sms_login.providers import HeroSMSProvider

    fake = _FakeHTTPClient(
        [
            _FakeResponse(json_data=_offer_payload()),
            _FakeResponse(text=_access_number_response()),
        ]
    )
    provider = HeroSMSProvider(
        client=HeroSMSClient(api_key=_api_key(), http_client=fake)
    )

    lease = await provider.reserve_number()

    assert lease.phone == _phone()
    assert lease.provider_name == "herosms"
    assert lease.price_bucket == "usd<=0.60"
    assert lease.redacted_diagnostics()["phone"] != _phone()

    get_number_calls = _handler_calls(fake, "getNumber")
    assert len(get_number_calls) == 1
    assert get_number_calls[0]["params"] == {
        "api_key": _api_key(),
        "action": "getNumber",
        "service": "dr",
        "country": "187",
        "operator": "physic",
        "maxPrice": "0.60",
    }


@pytest.mark.asyncio
async def test_reserve_number_requires_physic_operator_when_any_has_more_inventory():
    from geo_tracker.agent.sms_login.herosms_client import HeroSMSClient
    from geo_tracker.agent.sms_login.providers import HeroSMSProvider

    fake = _FakeHTTPClient(
        [
            _FakeResponse(
                json_data=_multi_operator_offer_payload(
                    operators=[
                        {
                            "name": "any",
                            "countPhysical": 12000,
                            "freePriceOffers": {"0.2200": 12000},
                        },
                        {
                            "name": "physic",
                            "countPhysical": 100,
                            "freePriceOffers": {"0.2200": 100},
                        },
                    ]
                )
            ),
            _FakeResponse(text=_access_number_response()),
        ]
    )
    provider = HeroSMSProvider(
        client=HeroSMSClient(api_key=_api_key(), http_client=fake)
    )

    await provider.reserve_number()

    get_number_calls = _handler_calls(fake, "getNumber")
    assert len(get_number_calls) == 1
    assert get_number_calls[0]["params"]["operator"] == "physic"


@pytest.mark.asyncio
async def test_reserve_number_blocks_any_only_inventory_as_ambiguous():
    from geo_tracker.agent.sms_login.herosms_client import (
        HeroSMSClient,
        HeroSMSProviderBlocked,
    )
    from geo_tracker.agent.sms_login.providers import HeroSMSProvider

    fake = _FakeHTTPClient(
        [
            _FakeResponse(
                json_data=_multi_operator_offer_payload(
                    operators=[
                        {
                            "name": "any",
                            "countPhysical": 12000,
                            "freePriceOffers": {"0.2200": 12000},
                        },
                    ]
                )
            ),
        ]
    )
    provider = HeroSMSProvider(
        client=HeroSMSClient(api_key=_api_key(), http_client=fake)
    )

    with pytest.raises(HeroSMSProviderBlocked) as excinfo:
        await provider.reserve_number()

    assert excinfo.value.diagnostics["reason"] == "physical_operator_missing"
    assert _handler_calls(fake, "getNumber") == []


@pytest.mark.parametrize(
    ("payload", "expected_reason"),
    [
        (_offer_payload(count_physical=0), "no_physical_inventory"),
        (_offer_payload(price="0.6100"), "price_above_guard"),
        (_offer_payload(service="wa"), "target_offer_missing"),
    ],
)
@pytest.mark.asyncio
async def test_reserve_number_blocks_non_compliant_offers_without_purchase(
    payload, expected_reason
):
    from geo_tracker.agent.sms_login.herosms_client import (
        HeroSMSClient,
        HeroSMSProviderBlocked,
    )
    from geo_tracker.agent.sms_login.providers import HeroSMSProvider

    fake = _FakeHTTPClient([_FakeResponse(json_data=payload)])
    provider = HeroSMSProvider(
        client=HeroSMSClient(api_key=_api_key(), http_client=fake)
    )

    with pytest.raises(HeroSMSProviderBlocked) as excinfo:
        await provider.reserve_number()

    assert excinfo.value.diagnostics["reason"] == expected_reason
    assert _handler_calls(fake, "getNumber") == []
    assert _api_key() not in str(excinfo.value)
    assert _phone() not in str(excinfo.value)


@pytest.mark.asyncio
async def test_reserve_number_blocks_provider_exhaustion_without_fallback():
    from geo_tracker.agent.sms_login.herosms_client import (
        HeroSMSClient,
        HeroSMSProviderBlocked,
    )
    from geo_tracker.agent.sms_login.providers import HeroSMSProvider

    fake = _FakeHTTPClient(
        [
            _FakeResponse(json_data=_offer_payload()),
            _FakeResponse(text="NO_NUMBERS"),
        ]
    )
    provider = HeroSMSProvider(
        client=HeroSMSClient(api_key=_api_key(), http_client=fake)
    )

    with pytest.raises(HeroSMSProviderBlocked) as excinfo:
        await provider.reserve_number()

    assert excinfo.value.diagnostics["reason"] == "provider_exhausted"
    get_number_calls = _handler_calls(fake, "getNumber")
    assert len(get_number_calls) == 1
    assert get_number_calls[0]["params"]["service"] == "dr"
    assert get_number_calls[0]["params"]["country"] == "187"
    assert get_number_calls[0]["params"]["maxPrice"] == "0.60"


@pytest.mark.asyncio
async def test_api_errors_are_redacted_and_do_not_purchase_after_discovery_failure():
    from geo_tracker.agent.sms_login.herosms_client import (
        HeroSMSClient,
        HeroSMSProviderBlocked,
    )
    from geo_tracker.agent.sms_login.providers import HeroSMSProvider

    fake = _FakeHTTPClient(
        [
            _FakeResponse(
                text=f"api_key={_api_key()} phone={_phone()}",
                status_code=500,
            )
        ]
    )
    provider = HeroSMSProvider(
        client=HeroSMSClient(api_key=_api_key(), http_client=fake)
    )

    with pytest.raises(HeroSMSProviderBlocked) as excinfo:
        await provider.reserve_number()

    message = str(excinfo.value)
    assert "api_key=" not in message
    assert _api_key() not in message
    assert _phone() not in message
    assert _handler_calls(fake, "getNumber") == []


@pytest.mark.asyncio
async def test_poll_success_release_and_close_use_activation_statuses():
    from geo_tracker.agent.sms_login.herosms_client import HeroSMSClient
    from geo_tracker.agent.sms_login.providers import HeroSMSProvider

    fake = _FakeHTTPClient(
        [
            _FakeResponse(json_data=_offer_payload()),
            _FakeResponse(text=_access_number_response()),
            _FakeResponse(text="ACCESS_READY"),
            _FakeResponse(text="STATUS_WAIT_CODE"),
            _FakeResponse(text=_status_ok_response("112233")),
            _FakeResponse(text="ACCESS_ACTIVATION"),
        ]
    )
    provider = HeroSMSProvider(
        client=HeroSMSClient(api_key=_api_key(), http_client=fake)
    )
    lease = await provider.reserve_number()

    code = await provider.poll_sms_code(lease, keyword="OpenAI", timeout=1)
    await provider.mark_success(lease)
    await provider.release_number(lease)
    await provider.close()

    assert code == "112233"
    assert fake.closed is True
    actions = [call["params"]["action"] for call in _handler_calls(fake)]
    statuses = [
        call["params"]["status"]
        for call in _handler_calls(fake, "setStatus")
    ]
    assert actions == ["getNumber", "setStatus", "getStatus", "getStatus", "setStatus"]
    assert statuses == ["1", "6"]


@pytest.mark.asyncio
async def test_provider_logs_redact_phone_code_activation_and_api_key(caplog):
    from geo_tracker.agent.sms_login.herosms_client import HeroSMSClient
    from geo_tracker.agent.sms_login.providers import HeroSMSProvider

    fake = _FakeHTTPClient(
        [
            _FakeResponse(json_data=_offer_payload()),
            _FakeResponse(text=_access_number_response()),
            _FakeResponse(text="ACCESS_READY"),
            _FakeResponse(text=_status_ok_response("445566")),
            _FakeResponse(text="ACCESS_CANCEL"),
        ]
    )
    provider = HeroSMSProvider(
        client=HeroSMSClient(api_key=_api_key(), http_client=fake)
    )

    caplog.set_level(logging.INFO)
    lease = await provider.reserve_number()
    await provider.poll_sms_code(lease, keyword="OpenAI", timeout=1)
    await provider.release_number(lease)

    logs = caplog.text
    assert _api_key() not in logs
    assert _phone() not in logs
    assert _activation_id() not in logs
    assert "445566" not in logs
    assert "[sms-code-redacted]" in logs
