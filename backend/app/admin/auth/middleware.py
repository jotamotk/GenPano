"""Admin auth middleware — pure decision function + FastAPI dependency.

Two layers of admin auth enforcement, both consuming this module:

1. Edge / FastAPI middleware — `decide_admin_auth()` is a pure function
   over `(pathname, access_token_cookie, force_password_change_at)`. It does
   NOT read the DB. At the edge `force_password_change_at` is always passed
   as None because Edge cannot query Postgres; the *real* force-change
   gating runs in the React `AdminRouteGuard.jsx` (layer 2) after refresh
   has populated the user payload. Decision #24.E pinned this two-layer
   trade-off explicitly.

2. Endpoint protection — `require_admin_session()` is a FastAPI dependency
   that reads the access token cookie, calls `verify_access_token()`, and
   returns the typed `AccessTokenPayload`. Failures raise HTTPException 401
   with a Set-Cookie clear instruction (handled in endpoints).

Whitelist contract:
- `AUTH_WHITELIST_PREFIXES` — anonymous routes (login page / forgot /
  reset / login API / refresh API). Always `allow`.
- `FORCE_CHANGE_WHITELIST_PREFIXES` — routes still reachable when
  force_password_change_at is set (change-password page itself, change-
  password API, logout API). Without this whitelist a forced user could
  not even submit the new password.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from fastapi import Cookie, HTTPException, status

from app.admin.auth.constants import ACCESS_TOKEN_COOKIE
from app.admin.auth.jwt import (
    AccessTokenPayload,
    AdminJwtInvalidError,
    verify_access_token,
)

AdminAuthAction = Literal["allow", "redirect", "unauthorized"]


@dataclass(frozen=True)
class AdminAuthDecision:
    """Outcome of `decide_admin_auth`.

    `action='allow'` → request proceeds.
    `action='redirect'` → page route, send 302/307 to `target`.
    `action='unauthorized'` → API route, return 401 JSON; `reason` is the
    machine-readable code consumed by the React error boundary.
    """

    action: AdminAuthAction
    target: str | None = None
    reason: str | None = None


# Anonymous routes — login / forgot-password / reset-password and their
# matching API endpoints + the refresh endpoint (which needs to work
# without a valid access cookie because the access TTL has expired).
AUTH_WHITELIST_PREFIXES: tuple[str, ...] = (
    "/admin/login",
    "/admin/forgot-password",
    "/admin/reset-password",
    "/admin/api/v1/auth/login",
    "/admin/api/v1/auth/forgot-password",
    "/admin/api/v1/auth/reset-password",
    "/admin/api/v1/auth/refresh",
)

# Reachable while `force_password_change_at` is set — the change-password
# page, the change-password API, and logout (so users can bail out).
FORCE_CHANGE_WHITELIST_PREFIXES: tuple[str, ...] = (
    "/admin/change-password",
    "/admin/api/v1/auth/change-password",
    "/admin/api/v1/auth/logout",
)

_LOGIN_PAGE = "/admin/login"
_CHANGE_PASSWORD_PAGE = "/admin/change-password"


def is_api_path(pathname: str) -> bool:
    """An /admin/api/* path returns 401 JSON; everything else under /admin
    redirects to the login page on auth failure."""

    return pathname.startswith("/admin/api/")


def is_whitelisted(pathname: str) -> bool:
    """Anonymous-allowed prefix match (login / forgot / reset / refresh)."""

    return any(pathname.startswith(prefix) for prefix in AUTH_WHITELIST_PREFIXES)


def _is_force_change_whitelisted(pathname: str) -> bool:
    return any(pathname.startswith(prefix) for prefix in FORCE_CHANGE_WHITELIST_PREFIXES)


def decide_admin_auth(
    *,
    pathname: str,
    access_token_cookie: str | None,
    force_password_change_at: datetime | None,
) -> AdminAuthDecision:
    """Pure decision matrix for /admin/* requests.

    Order matters:
    1. Anonymous-whitelist short-circuits (login page, refresh API, etc.).
    2. No / invalid cookie → API gets 401, page gets 302 to /admin/login.
    3. Cookie present + force-change set + path NOT in force-change
       whitelist → redirect to /admin/change-password (page) or 401 with
       reason='force_password_change' (API).
    4. Otherwise → allow.

    Note: this function does NOT verify the JWT signature. Verification is
    layered above (FastAPI dependency `require_admin_session`). The pure
    function only checks presence; treating a malformed cookie as missing
    keeps the matrix decidable even at the Edge where signature checks are
    expensive.
    """

    if is_whitelisted(pathname):
        return AdminAuthDecision(action="allow")

    has_token = bool(access_token_cookie)

    if not has_token:
        if is_api_path(pathname):
            return AdminAuthDecision(action="unauthorized", reason="no_session")
        return AdminAuthDecision(action="redirect", target=_LOGIN_PAGE, reason="no_session")

    if force_password_change_at is not None and not _is_force_change_whitelisted(pathname):
        if is_api_path(pathname):
            return AdminAuthDecision(action="unauthorized", reason="force_password_change")
        return AdminAuthDecision(
            action="redirect",
            target=_CHANGE_PASSWORD_PAGE,
            reason="force_password_change",
        )

    return AdminAuthDecision(action="allow")


def require_admin_session(
    access_token: str | None = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE),
) -> AccessTokenPayload:
    """FastAPI dependency: extract + verify admin access token.

    Returns the decoded `AccessTokenPayload` on success; raises
    HTTPException(401) with a typed reason header on any failure.
    The endpoint layer is responsible for wiring `clear_auth_cookies`
    on the outbound response when this raises (decision #24.B).
    """

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"reason": "no_session"},
        )

    try:
        return verify_access_token(access_token)
    except AdminJwtInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"reason": exc.reason},
        ) from exc
