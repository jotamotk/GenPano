"""HttpOnly + SameSite=Strict cookie helpers for admin auth.

Single source for the cookie-attribute discipline mandated by master
decision #24.B:

- Both cookies use `HttpOnly + SameSite=Strict + Path=/admin`.
- `Secure` follows the `secure=` argument: True in production (https), False
  for the dev FastAPI loopback. Caller is responsible for picking the right
  value based on `Settings.environment`.
- `Max-Age` mirrors `ACCESS_TOKEN_TTL_SECONDS` / `REFRESH_TOKEN_TTL_SECONDS`.

Two surfaces exposed:

1. `set_access_token_cookie(response, token, *, secure)` etc — operate on a
   FastAPI/Starlette `Response`. The 99% path for endpoint handlers.
2. `serialize_set_cookie(...)` — RFC 6265 ASCII Set-Cookie string for the
   rare hand-rolled response (e.g. middleware that writes raw headers).

Decision references:
- Admin auth cookie discipline
- Harness D10 (admin-session-cookie-samesite-strict, Step 6 will land it)
"""

from __future__ import annotations

from typing import Literal

from starlette.responses import Response

from app.admin.auth.constants import (
    ACCESS_TOKEN_COOKIE,
    ACCESS_TOKEN_TTL_SECONDS,
    COOKIE_PATH,
    REFRESH_TOKEN_COOKIE,
    REFRESH_TOKEN_TTL_SECONDS,
)

SameSiteValue = Literal["strict"]
_SAMESITE: SameSiteValue = "strict"


def set_access_token_cookie(response: Response, token: str, *, secure: bool) -> None:
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=token,
        max_age=ACCESS_TOKEN_TTL_SECONDS,
        path=COOKIE_PATH,
        httponly=True,
        secure=secure,
        samesite=_SAMESITE,
    )


def set_refresh_token_cookie(response: Response, token: str, *, secure: bool) -> None:
    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE,
        value=token,
        max_age=REFRESH_TOKEN_TTL_SECONDS,
        path=COOKIE_PATH,
        httponly=True,
        secure=secure,
        samesite=_SAMESITE,
    )


def clear_auth_cookies(response: Response) -> None:
    """Delete both auth cookies in the same response.

    `delete_cookie` emits a Set-Cookie with Max-Age=0 and the same Path —
    Path must match the original or the browser will not clear the entry.
    """

    response.delete_cookie(key=ACCESS_TOKEN_COOKIE, path=COOKIE_PATH)
    response.delete_cookie(key=REFRESH_TOKEN_COOKIE, path=COOKIE_PATH)


def serialize_set_cookie(
    name: str,
    value: str,
    *,
    max_age: int,
    secure: bool,
) -> str:
    """RFC 6265 Set-Cookie string with the admin-cookie attribute discipline.

    Manual emission path — used only when a handler builds a raw response
    instead of returning a Starlette `Response`. Always emits HttpOnly +
    SameSite=Strict + Path=/admin; Secure follows the flag.
    """

    parts = [
        f"{name}={value}",
        f"Path={COOKIE_PATH}",
        f"Max-Age={max_age}",
        "HttpOnly",
        "SameSite=Strict",
    ]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)
