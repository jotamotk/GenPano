"""Cross-handler helpers — IP extraction, response shaping, cookie security.

Kept tiny and inlined-against-imports so each endpoint module reads as a
flat narrative. None of this is generic enough to hoist out of the auth
package.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from fastapi import Request
from starlette.responses import Response

from app.admin.api.v1.auth._dto import AdminUserDto
from app.admin.auth.constants import ACCESS_TOKEN_TTL_SECONDS
from app.admin.auth.cookies import set_access_token_cookie, set_refresh_token_cookie
from app.models.admin import AdminUser


def cookie_secure_flag() -> bool:
    """`Secure` follows the runtime environment.

    Production must always set Secure (TLS-only). Development on the FastAPI
    loopback must NOT set Secure (the cookie would not stick on http://).
    The decision is centralised here so a handler cannot accidentally flip
    one cookie's Secure flag while leaving the other off.
    """

    env = os.environ.get("GENPANO_ENVIRONMENT", "development").lower()
    return env in {"production", "staging"}


def client_ip(request: Request) -> str | None:
    """Resolve the client's IP, honouring X-Forwarded-For when present.

    Behind a reverse proxy the leftmost token of XFF is the original client.
    Without a proxy `request.client.host` is the loopback peer. Returning
    None for a totally absent client lets the limiter normalise to
    `0.0.0.0` rather than synthesising an arbitrary placeholder.
    """

    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip() or None
    if request.client is None:
        return None
    return request.client.host


def user_agent(request: Request) -> str | None:
    raw = request.headers.get("user-agent")
    if not raw:
        return None
    # admin_sessions.user_agent is VARCHAR(512); truncate defensively so a
    # genuinely huge UA from a fuzzer cannot blow up the insert.
    return raw[:512]


def to_user_dto(user: AdminUser) -> AdminUserDto:
    return AdminUserDto(
        id=user.id,
        email=user.email,
        role=user.role,
        status=user.status,
        force_password_change_at=user.force_password_change_at,
        last_password_at=user.last_password_at,
        last_login_at=user.last_login_at,
    )


def access_expires_epoch(now: datetime | None = None) -> int:
    """Epoch seconds at which the access token issued *now* will expire.

    Mirrors the JWT `exp` claim so the frontend can schedule its 14-min
    silent refresh against the same boundary the server enforces.
    """

    issued = (now or datetime.now(UTC)).replace(microsecond=0)
    expires = issued + timedelta(seconds=ACCESS_TOKEN_TTL_SECONDS)
    return int(expires.timestamp())


def write_auth_cookies(response: Response, *, access_token: str, refresh_token: str) -> None:
    secure = cookie_secure_flag()
    set_access_token_cookie(response, access_token, secure=secure)
    set_refresh_token_cookie(response, refresh_token, secure=secure)


__all__ = [
    "access_expires_epoch",
    "client_ip",
    "cookie_secure_flag",
    "to_user_dto",
    "user_agent",
    "write_auth_cookies",
]
