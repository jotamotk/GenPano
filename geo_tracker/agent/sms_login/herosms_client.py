"""Guarded HeroSMS API client for shared SMS provider flows."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from geo_tracker.agent.sms_redaction import mask_phone, redact_sensitive_text

logger = logging.getLogger(__name__)

HEROSMS_BASE_URL = "https://hero-sms.com"
HEROSMS_SERVICE_CODE = "dr"
HEROSMS_COUNTRY_ID = "187"
HEROSMS_MAX_PRICE_USD = Decimal("0.60")
HEROSMS_PRICE_BUCKET = "usd<=0.60"

_SMS_CODE_RE = re.compile(r"\b(\d{4,8})\b")


@dataclass(frozen=True)
class HeroSMSOffer:
    operator: str
    price_usd: Decimal
    count_physical: int
    price_bucket_count: int


@dataclass(frozen=True)
class HeroSMSActivation:
    activation_id: str
    phone: str
    offer: HeroSMSOffer


class HeroSMSProviderBlocked(Exception):
    """Raised when HeroSMS cannot satisfy the guarded purchase constraints."""

    def __init__(self, reason: str, diagnostics: dict[str, Any] | None = None):
        self.diagnostics = _redact_diagnostics(
            {
                "provider_name": "herosms",
                "reason": reason,
                **(diagnostics or {}),
            }
        )
        super().__init__(f"HeroSMS blocked: {self.diagnostics}")


def _safe_text(value: Any, *, api_key: str = "") -> str:
    text = redact_sensitive_text(value)
    if api_key:
        text = text.replace(api_key, "[redacted]")
    text = re.sub(
        r"(?i)api[_-]?key\s*=\s*\[redacted\]",
        "api key [redacted]",
        text,
    )
    return text


def _redact_diagnostics(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"api_key", "activation_id", "sms_text", "cookie", "cookies"}:
                redacted[key] = "[redacted]"
            elif key == "phone":
                redacted[key] = mask_phone(str(item))
            else:
                redacted[key] = _redact_diagnostics(item)
        return redacted
    if isinstance(value, list):
        return [_redact_diagnostics(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


def _as_decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _as_positive_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


class HeroSMSClient:
    """Small async wrapper around the HeroSMS public and compatible APIs."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        http_client: Any | None = None,
        base_url: str = HEROSMS_BASE_URL,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("HERO_SMS_API_KEY", "")
        if not self.api_key:
            raise ValueError("HERO_SMS_API_KEY is not configured")
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client or httpx.AsyncClient(timeout=30)

    async def discover_compliant_offer(self) -> HeroSMSOffer:
        payload = await self._public_json(
            f"/api/v1/left-menu/service/{HEROSMS_SERVICE_CODE}/country/"
            f"{HEROSMS_COUNTRY_ID}/offers"
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        service_offer = data.get(HEROSMS_SERVICE_CODE) if isinstance(data, dict) else None
        if not isinstance(service_offer, dict):
            raise HeroSMSProviderBlocked(
                "target_offer_missing",
                {
                    "service": HEROSMS_SERVICE_CODE,
                    "country": HEROSMS_COUNTRY_ID,
                },
            )

        operators = service_offer.get("operators")
        if not isinstance(operators, list):
            raise HeroSMSProviderBlocked(
                "target_offer_missing",
                {
                    "service": HEROSMS_SERVICE_CODE,
                    "country": HEROSMS_COUNTRY_ID,
                },
            )

        saw_physical = False
        saw_price = False
        candidates: list[HeroSMSOffer] = []
        for operator in operators:
            if not isinstance(operator, dict):
                continue
            name = str(operator.get("name") or "").strip()
            count_physical = _as_positive_int(operator.get("countPhysical"))
            if count_physical <= 0:
                continue
            saw_physical = True
            price_offers = operator.get("freePriceOffers")
            if not name or not isinstance(price_offers, dict):
                continue
            for price, count in price_offers.items():
                price_usd = _as_decimal(price)
                price_count = _as_positive_int(count)
                if price_usd is None or price_count <= 0:
                    continue
                saw_price = True
                if price_usd <= HEROSMS_MAX_PRICE_USD:
                    candidates.append(
                        HeroSMSOffer(
                            operator=name,
                            price_usd=price_usd,
                            count_physical=count_physical,
                            price_bucket_count=price_count,
                        )
                    )

        if candidates:
            offer = sorted(
                candidates,
                key=lambda item: (item.price_usd, -item.count_physical, item.operator),
            )[0]
            logger.info(
                "HeroSMS compliant offer found: service=%s country=%s "
                "operator=%s price_bucket=%s countPhysical=%s",
                HEROSMS_SERVICE_CODE,
                HEROSMS_COUNTRY_ID,
                offer.operator,
                HEROSMS_PRICE_BUCKET,
                offer.count_physical,
            )
            return offer

        reason = "price_above_guard" if saw_physical and saw_price else "no_physical_inventory"
        raise HeroSMSProviderBlocked(
            reason,
            {
                "service": HEROSMS_SERVICE_CODE,
                "country": HEROSMS_COUNTRY_ID,
                "max_price_usd": HEROSMS_MAX_PRICE_USD,
                "must_require_physical": True,
                "fallback_allowed": False,
            },
        )

    async def reserve_number(self) -> HeroSMSActivation:
        offer = await self.discover_compliant_offer()
        response = await self._handler_text(
            {
                "action": "getNumber",
                "service": HEROSMS_SERVICE_CODE,
                "country": HEROSMS_COUNTRY_ID,
                "operator": offer.operator,
                "maxPrice": str(HEROSMS_MAX_PRICE_USD),
            }
        )
        if response.startswith("ACCESS_NUMBER:"):
            parts = response.split(":", 2)
            if len(parts) != 3 or not parts[1] or not parts[2]:
                raise HeroSMSProviderBlocked("malformed_purchase_response")
            activation = HeroSMSActivation(
                activation_id=parts[1],
                phone=parts[2],
                offer=offer,
            )
            logger.info(
                "HeroSMS reserved guarded number: phone=%s provider=%s price_bucket=%s",
                mask_phone(activation.phone),
                "herosms",
                HEROSMS_PRICE_BUCKET,
            )
            return activation
        if response in {"NO_NUMBERS", "NO_BALANCE"} or response.startswith("WRONG_MAX_PRICE"):
            raise HeroSMSProviderBlocked(
                "provider_exhausted",
                {
                    "service": HEROSMS_SERVICE_CODE,
                    "country": HEROSMS_COUNTRY_ID,
                    "operator": offer.operator,
                    "max_price_usd": HEROSMS_MAX_PRICE_USD,
                    "provider_response": response,
                    "fallback_allowed": False,
                },
            )
        raise HeroSMSProviderBlocked(
            "purchase_rejected",
            {"provider_response": response, "fallback_allowed": False},
        )

    async def mark_ready(self, activation_id: str) -> None:
        response = await self._handler_text(
            {"action": "setStatus", "id": activation_id, "status": "1"}
        )
        if response not in {"ACCESS_READY", "ACCESS_RETRY_GET", "ACCESS_ACTIVATION"}:
            raise HeroSMSProviderBlocked(
                "mark_ready_failed",
                {"provider_response": response},
            )

    async def poll_sms_code(self, activation_id: str, *, timeout: int) -> str:
        deadline = time.monotonic() + max(timeout, 0)
        wait_seen = False
        interval = 3.0
        while True:
            response = await self._handler_text(
                {"action": "getStatus", "id": activation_id}
            )
            if response.startswith("STATUS_OK:"):
                match = _SMS_CODE_RE.search(response.split(":", 1)[1])
                if match:
                    logger.info("HeroSMS received verification code: [sms-code-redacted]")
                    return match.group(1)
                raise HeroSMSProviderBlocked("sms_code_parse_failed")
            if response in {
                "STATUS_WAIT_CODE",
                "STATUS_WAIT_RETRY",
                "STATUS_WAIT_RESEND",
            }:
                if wait_seen and time.monotonic() >= deadline:
                    break
                wait_seen = True
                if timeout <= 1:
                    await asyncio.sleep(0)
                else:
                    await asyncio.sleep(min(interval, max(deadline - time.monotonic(), 0)))
                continue
            raise HeroSMSProviderBlocked(
                "sms_poll_failed",
                {"provider_response": response},
            )
        raise TimeoutError("HeroSMS SMS polling timed out")

    async def complete_activation(self, activation_id: str) -> None:
        response = await self._handler_text(
            {"action": "setStatus", "id": activation_id, "status": "6"}
        )
        if response != "ACCESS_ACTIVATION":
            raise HeroSMSProviderBlocked(
                "complete_activation_failed",
                {"provider_response": response},
            )

    async def cancel_activation(self, activation_id: str) -> None:
        response = await self._handler_text(
            {"action": "setStatus", "id": activation_id, "status": "8"}
        )
        if response != "ACCESS_CANCEL":
            logger.warning(
                "HeroSMS cancel returned non-final response: %s",
                _safe_text(response, api_key=self.api_key),
            )

    async def close(self) -> None:
        if hasattr(self.http_client, "aclose"):
            await self.http_client.aclose()

    async def _public_json(self, path: str) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = await self.http_client.get(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "genpano-herosms-provider/1.0",
                },
            )
            response.raise_for_status()
            return response.json()
        except HeroSMSProviderBlocked:
            raise
        except Exception as exc:
            raise HeroSMSProviderBlocked(
                "api_error",
                {"detail": _safe_text(exc, api_key=self.api_key)},
            ) from None

    async def _handler_text(self, params: dict[str, Any]) -> str:
        safe_params = dict(params)
        safe_params["api_key"] = self.api_key
        try:
            response = await self.http_client.get(
                f"{self.base_url}/stubs/handler_api.php",
                params=safe_params,
                headers={"User-Agent": "genpano-herosms-provider/1.0"},
            )
            response.raise_for_status()
            return str(response.text).strip()
        except Exception as exc:
            raise HeroSMSProviderBlocked(
                "api_error",
                {"detail": _safe_text(exc, api_key=self.api_key)},
            ) from None
