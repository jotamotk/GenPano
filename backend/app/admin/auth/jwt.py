"""HS256 JWT for admin access tokens.

Wraps `python-jose` with two strict invariants:

1. Secret discipline — `ADMIN_JWT_SECRET` env var must exist AND be ≥ 32 bytes.
   Missing → `AdminJwtSecretMissingError` (boot-time fast-fail per decision
   #24 Step S4 evidence). Short → same error type with explicit reason.

2. Failure-code surface — `verify_access_token()` raises one of four
   sub-classes of `AdminJwtInvalidError` so callers can distinguish expired
   vs. signature vs. malformed vs. claim-mismatch (audience / issuer).

Algorithm / issuer / audience are pulled from `constants.py` only; literal
strings here would silently fork the truth source.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt  # type: ignore[import-untyped]
from jose.exceptions import (  # type: ignore[import-untyped]
    ExpiredSignatureError,
    JWTClaimsError,
)

from app.admin.auth.constants import (
    ACCESS_TOKEN_TTL_SECONDS,
    JWT_ALGORITHM,
    JWT_AUDIENCE_ACCESS,
    JWT_ISSUER,
)

_MIN_SECRET_BYTES = 32
_ENV_VAR = "ADMIN_JWT_SECRET"


class AdminJwtSecretMissingError(RuntimeError):
    """Boot-time fast-fail: secret missing or too short."""


class AdminJwtInvalidError(Exception):
    """Token verification failure — one of four reasons."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class AccessTokenPayload:
    sub: str  # admin_user_id
    jti: str  # unique token id (used as access_token_jti in admin_sessions)
    iat: int
    exp: int
    iss: str
    aud: str


def _load_secret() -> str:
    raw = os.environ.get(_ENV_VAR)
    if raw is None or len(raw.encode("utf-8")) < _MIN_SECRET_BYTES:
        raise AdminJwtSecretMissingError(
            f"{_ENV_VAR} must be set and ≥ {_MIN_SECRET_BYTES} bytes"
        )
    return raw


def sign_access_token(
    *,
    admin_user_id: str,
    now: datetime | None = None,
    jti: str | None = None,
) -> tuple[str, AccessTokenPayload]:
    """Mint a short-lived access token for an admin session.

    `now` is injectable for deterministic tests. `jti` defaults to a fresh
    UUID4 — pass an explicit one only when minting against a pre-allocated
    `admin_sessions.access_token_jti` row (decision #24 Step S2 rotation).
    """

    secret = _load_secret()
    issued = (now or datetime.now(UTC)).replace(microsecond=0)
    expires = issued + timedelta(seconds=ACCESS_TOKEN_TTL_SECONDS)
    token_jti = jti or str(uuid.uuid4())

    payload: dict[str, Any] = {
        "sub": admin_user_id,
        "jti": token_jti,
        "iat": int(issued.timestamp()),
        "exp": int(expires.timestamp()),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE_ACCESS,
    }
    token = jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)
    return token, AccessTokenPayload(
        sub=admin_user_id,
        jti=token_jti,
        iat=payload["iat"],
        exp=payload["exp"],
        iss=JWT_ISSUER,
        aud=JWT_AUDIENCE_ACCESS,
    )


def verify_access_token(token: str) -> AccessTokenPayload:
    """Decode + verify; raise `AdminJwtInvalidError` on any failure."""

    secret = _load_secret()
    try:
        decoded = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE_ACCESS,
            issuer=JWT_ISSUER,
        )
    except ExpiredSignatureError as exc:
        raise AdminJwtInvalidError("expired") from exc
    except JWTClaimsError as exc:
        raise AdminJwtInvalidError("claims") from exc
    except JWTError as exc:
        # python-jose lumps signature + structural errors into JWTError; we
        # surface "signature" as the user-visible reason because the most
        # common path that lands here is a flipped HMAC byte. Truly malformed
        # base64 input also lands here.
        msg = str(exc).lower()
        reason = "malformed" if "not enough segments" in msg else "signature"
        raise AdminJwtInvalidError(reason) from exc

    sub = decoded.get("sub")
    jti = decoded.get("jti")
    if not isinstance(sub, str) or not isinstance(jti, str):
        raise AdminJwtInvalidError("claims")
    return AccessTokenPayload(
        sub=sub,
        jti=jti,
        iat=int(decoded["iat"]),
        exp=int(decoded["exp"]),
        iss=str(decoded["iss"]),
        aud=str(decoded["aud"]),
    )
