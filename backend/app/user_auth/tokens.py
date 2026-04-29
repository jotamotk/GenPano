"""One-time token generation and hashing for product auth flows."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

VERIFY_EMAIL_TTL_SECONDS = 24 * 60 * 60
PASSWORD_RESET_TTL_SECONDS = 60 * 60
OAUTH_SETUP_TTL_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class RawToken:
    value: str
    digest: str
    expires_at: datetime


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def equal_token_hash(raw: str, digest: str) -> bool:
    return hmac.compare_digest(hash_token(raw), digest)


def mint_token(*, ttl_seconds: int) -> RawToken:
    value = secrets.token_urlsafe(32)
    expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=ttl_seconds)
    return RawToken(value=value, digest=hash_token(value), expires_at=expires)
