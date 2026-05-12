"""Shared SMS provider boundary for account registration flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from geo_tracker.agent.sms_login.luban_client import LubanSMSClient
from geo_tracker.agent.sms_redaction import mask_phone


@dataclass(frozen=True)
class SMSNumberLease:
    """A provider-reserved number plus redacted metadata for diagnostics."""

    phone: str
    provider_name: str
    price_bucket: str | None = None

    def redacted_diagnostics(self) -> dict[str, str | None]:
        return {
            "provider_name": self.provider_name,
            "phone": mask_phone(self.phone),
            "price_bucket": self.price_bucket,
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

    async def close(self) -> None:
        await self.client.close()
