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
    """SMSProvider adapter for the existing Luban Keyword API behavior."""

    provider_name = "luban"
    price_bucket = "existing-luban"

    def __init__(self, client: LubanSMSClient | None = None) -> None:
        self.client = client or LubanSMSClient()

    async def reserve_number(self, *, phone: str | None = None) -> SMSNumberLease:
        reserved = await self.client.get_keyword_number(phone=phone)
        return SMSNumberLease(
            phone=reserved,
            provider_name=self.provider_name,
            price_bucket=self.price_bucket,
        )

    async def poll_sms_code(
        self,
        lease: SMSNumberLease,
        *,
        keyword: str,
        timeout: int,
    ) -> str:
        return await self.client.get_keyword_sms(
            lease.phone,
            keyword,
            timeout=timeout,
        )

    async def release_number(self, lease: SMSNumberLease) -> None:
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
