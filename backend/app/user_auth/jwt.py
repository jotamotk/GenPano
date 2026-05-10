"""Bearer JWTs for product users."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt  # type: ignore[import-untyped]
from jose.exceptions import ExpiredSignatureError, JWTClaimsError  # type: ignore[import-untyped]

from app.core.config import get_settings

USER_ACCESS_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "genpano"
JWT_AUDIENCE = "genpano-user-access"
_MIN_SECRET_BYTES = 32


class UserJwtSecretMissingError(RuntimeError):
    """Product auth JWT secret is missing or too short."""


class UserJwtInvalidError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class UserAccessTokenPayload:
    sub: str
    email: str
    iat: int
    exp: int
    iss: str
    aud: str


def _load_secret() -> str:
    raw = os.environ.get("USER_JWT_SECRET") or get_settings().user_jwt_secret
    if raw is None or len(raw.encode("utf-8")) < _MIN_SECRET_BYTES:
        raise UserJwtSecretMissingError(
            f"USER_JWT_SECRET must be set and >= {_MIN_SECRET_BYTES} bytes"
        )
    return raw


def sign_user_access_token(
    *,
    user_id: str,
    email: str,
    now: datetime | None = None,
) -> tuple[str, UserAccessTokenPayload]:
    issued = (now or datetime.now(UTC)).replace(microsecond=0)
    expires = issued + timedelta(seconds=USER_ACCESS_TOKEN_TTL_SECONDS)
    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "iat": int(issued.timestamp()),
        "exp": int(expires.timestamp()),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
    }
    token = jwt.encode(payload, _load_secret(), algorithm=JWT_ALGORITHM)
    return token, UserAccessTokenPayload(
        sub=user_id,
        email=email,
        iat=payload["iat"],
        exp=payload["exp"],
        iss=JWT_ISSUER,
        aud=JWT_AUDIENCE,
    )


def verify_user_access_token(token: str) -> UserAccessTokenPayload:
    try:
        decoded = jwt.decode(
            token,
            _load_secret(),
            algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
        )
    except ExpiredSignatureError as exc:
        raise UserJwtInvalidError("expired") from exc
    except JWTClaimsError as exc:
        raise UserJwtInvalidError("claims") from exc
    except JWTError as exc:
        msg = str(exc).lower()
        reason = "malformed" if "not enough segments" in msg else "signature"
        raise UserJwtInvalidError(reason) from exc

    sub = decoded.get("sub")
    email = decoded.get("email")
    if not isinstance(sub, str) or not isinstance(email, str):
        raise UserJwtInvalidError("claims")
    return UserAccessTokenPayload(
        sub=sub,
        email=email,
        iat=int(decoded["iat"]),
        exp=int(decoded["exp"]),
        iss=str(decoded["iss"]),
        aud=str(decoded["aud"]),
    )
