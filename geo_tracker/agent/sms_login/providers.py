"""Shared SMS provider boundary for account registration flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from geo_tracker.agent.sms_login.herosms_client import (
    HEROSMS_PRICE_BUCKET,
    HeroSMSActivation,
    HeroSMSClient,
    HeroSMSProviderBlocked,
)
from geo_tracker.agent.sms_login.luban_client import LubanSMSClient
from geo_tracker.agent.sms_redaction import mask_phone


@dataclass(frozen=True)
class SMSNumberLease:
    """A provider-reserved number plus redacted metadata for diagnostics."""

    phone: str
    provider_name: str
    price_bucket: str | None = None
    provider_ref: str | None = None

    def redacted_diagnostics(self) -> dict[str, str | None]:
        return {
            "provider_name": self.provider_name,
            "phone": mask_phone(self.phone),
            "price_bucket": self.price_bucket,
            "provider_ref": "[activation-id-redacted]" if self.provider_ref else None,
        }


class SMSProvider(Protocol):
    provider_name: str

    async def reserve_number(self, *, phone: str | None = None) -> SMSNumberLease:
        """Reserve a new number, or re-reserve an existing number when supported."""

    async def poll_sms_code(
        self,
        lease: SMSNumberLease,
        *,
        keyword: str,
        timeout: int,
    ) -> str:
        """Poll for a verification code for the reserved number."""

    async def release_number(self, lease: SMSNumberLease) -> None:
        """Release a previously reserved number."""

    async def mark_success(self, lease: SMSNumberLease) -> None:
        """Mark a lease as successfully used after authenticated cookies are saved."""

    async def close(self) -> None:
        """Close provider resources."""


class LubanSMSProvider:
    """SMSProvider adapter for the Luban SMS APIs.

    Refs #963 / #973: tries the Keyword API ("通用短信接收") first because
    it supports phone-reuse for account re-login and shares the same
    inventory across all platforms. When the keyword API returns 400 (no
    inventory available — the current production failure mode), falls
    back to the verification-code API ("验证码接收") with a per-platform
    ``service_id``. The fallback path is the documented LubanSMS recovery
    when keyword inventory is depleted, and it draws from a separate
    service-keyed pool that stays available even when the keyword pool
    is empty.

    The platform passes its service_id via the env var
    ``LUBANSMS_<PLATFORM>_SERVICE_ID``. For Doubao the value is
    ``666056`` (provided by operator).
    """

    provider_name = "luban"
    price_bucket = "existing-luban"
    service_provider_name = "luban_service"

    def __init__(
        self,
        client: LubanSMSClient | None = None,
        service_id: str | None = None,
    ) -> None:
        self.client = client or LubanSMSClient()
        self.service_id = service_id

    async def reserve_number(self, *, phone: str | None = None) -> SMSNumberLease:
        # Primary: keyword API. Supports phone-reuse for re-login flows
        # and is cheaper when inventory is healthy.
        try:
            reserved = await self.client.get_keyword_number(phone=phone)
            return SMSNumberLease(
                phone=reserved,
                provider_name=self.provider_name,
                price_bucket=self.price_bucket,
            )
        except RuntimeError as keyword_err:
            # Phone-specific reuse can never succeed via the service API
            # (the service API allocates a brand-new number each call), so
            # we propagate this error so the handler's "降级为随机取号"
            # fallback can call us again with phone=None.
            if phone:
                raise
            # Random keyword allocation failed AND no service_id configured
            # → preserve historical behaviour: propagate the keyword error.
            if not self.service_id:
                raise
            # Random keyword allocation failed but service_id is configured
            # → fall through to the service API.
            keyword_err_text = str(keyword_err)
        try:
            phone_result, request_id = await self.client.get_service_number(
                self.service_id
            )
        except Exception as service_err:
            # Both paths failed — surface a combined error so operators can
            # see at a glance that LubanSMS is fully unavailable, not just
            # one API.
            raise RuntimeError(
                f"luban allocation failed: keyword=({keyword_err_text}); "
                f"service(service_id={self.service_id})=({service_err})"
            ) from service_err
        return SMSNumberLease(
            phone=phone_result,
            provider_name=self.service_provider_name,
            price_bucket=self.price_bucket,
            provider_ref=str(request_id),
        )

    async def poll_sms_code(
        self,
        lease: SMSNumberLease,
        *,
        keyword: str,
        timeout: int,
    ) -> str:
        # Service-API leases carry the request_id in ``provider_ref`` and
        # poll via getSms; keyword-API leases poll via getKeywordSms with
        # the platform-specific keyword filter.
        if lease.provider_ref:
            return await self.client.get_service_sms(
                lease.provider_ref,
                timeout=timeout,
            )
        return await self.client.get_keyword_sms(
            lease.phone,
            keyword,
            timeout=timeout,
        )

    async def release_number(self, lease: SMSNumberLease) -> None:
        # Service-API leases release via setStatus(status=reject) keyed
        # by request_id; keyword-API leases release via delKeywordNumber
        # keyed by phone.
        if lease.provider_ref:
            await self.client.set_service_status_reject(lease.provider_ref)
        else:
            await self.client.release_keyword_number(lease.phone)

    async def mark_success(self, lease: SMSNumberLease) -> None:
        return None

    async def close(self) -> None:
        await self.client.close()


class HeroSMSProvider:
    """Guarded SMSProvider adapter for HeroSMS OpenAI USA physical inventory."""

    provider_name = "herosms"
    price_bucket = HEROSMS_PRICE_BUCKET

    def __init__(self, client: HeroSMSClient | None = None) -> None:
        self.client = client or HeroSMSClient()
        self._completed_refs: set[str] = set()

    async def reserve_number(self, *, phone: str | None = None) -> SMSNumberLease:
        if phone:
            raise HeroSMSProviderBlocked(
                "existing_phone_not_supported",
                {"phone": phone, "fallback_allowed": False},
            )
        activation: HeroSMSActivation = await self.client.reserve_number()
        return SMSNumberLease(
            phone=activation.phone,
            provider_name=self.provider_name,
            price_bucket=self.price_bucket,
            provider_ref=activation.activation_id,
        )

    async def poll_sms_code(
        self,
        lease: SMSNumberLease,
        *,
        keyword: str,
        timeout: int,
    ) -> str:
        if not lease.provider_ref:
            raise HeroSMSProviderBlocked("missing_activation_ref")
        await self.client.mark_ready(lease.provider_ref)
        return await self.client.poll_sms_code(lease.provider_ref, timeout=timeout)

    async def release_number(self, lease: SMSNumberLease) -> None:
        if not lease.provider_ref or lease.provider_ref in self._completed_refs:
            return None
        await self.client.cancel_activation(lease.provider_ref)

    async def mark_success(self, lease: SMSNumberLease) -> None:
        if not lease.provider_ref:
            raise HeroSMSProviderBlocked("missing_activation_ref")
        await self.client.complete_activation(lease.provider_ref)
        self._completed_refs.add(lease.provider_ref)

    async def close(self) -> None:
        await self.client.close()
