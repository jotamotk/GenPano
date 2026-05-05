"""Phase 5 — production security headers + trusted host guard.

Two pieces:

  1. `SecurityHeadersMiddleware`: stamps every response with industry-
     standard hardening headers (HSTS, X-Content-Type-Options,
     X-Frame-Options, Referrer-Policy, Permissions-Policy). Idempotent —
     skips a header if upstream already set it.

  2. `setup_trusted_hosts(app)`: adds Starlette's TrustedHostMiddleware
     keyed off `GENPANO_ALLOWED_HOSTS` (comma-separated). Default `*`
     (permissive, dev-friendly). Production should set explicit
     hostnames so Host-header attacks 400 instead of being routed.

Activation: `setup_security(app)` in `app.main` wires both. Tests
verify header presence + that overrides aren't clobbered.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware

_DEFAULT_HEADERS: dict[str, str] = {
    # Force HTTPS for 2 years; preload for browser preload list.
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    # Don't sniff MIME — limits XSS via Content-Type confusion.
    "X-Content-Type-Options": "nosniff",
    # Block clickjacking via iframe embedding.
    "X-Frame-Options": "DENY",
    # Don't leak referrer to cross-origin GETs.
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # Disable browser features we don't use (camera / microphone / geo etc.).
    "Permissions-Policy": (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), "
        "microphone=(), payment=(), usb=()"
    ),
}


def setup_security_headers(app: FastAPI) -> None:
    """Attach the security-headers middleware to `app`.

    The middleware is opt-out via `GENPANO_SECURITY_HEADERS_DISABLED=1`
    (used by the test client to keep responses lean). Otherwise it
    stamps every response with the hardening headers, skipping any
    already-set keys so upstream overrides win.
    """

    @app.middleware("http")
    async def _security_headers_mw(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        if os.environ.get("GENPANO_SECURITY_HEADERS_DISABLED") == "1":
            return response
        # HSTS only over HTTPS — sending it on plain HTTP is invalid.
        is_https = (
            request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        )
        for name, value in _DEFAULT_HEADERS.items():
            if name == "Strict-Transport-Security" and not is_https:
                continue
            if name not in response.headers:
                response.headers[name] = value
        return response


def setup_trusted_hosts(app: FastAPI) -> None:
    """Attach Starlette's TrustedHostMiddleware keyed off env var.

    `GENPANO_ALLOWED_HOSTS=foo.com,bar.com` (comma-separated). Default
    `*` (any). Production should set explicit hostnames so a request
    with a forged Host header gets a 400 instead of being routed.
    """
    raw = os.environ.get("GENPANO_ALLOWED_HOSTS", "*").strip()
    if not raw:
        raw = "*"
    hosts = [h.strip() for h in raw.split(",") if h.strip()]
    if hosts == ["*"]:
        # No-op when fully open.
        return
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)


def setup_security(app: FastAPI) -> None:
    """Wire both pieces. Order matters — TrustedHost must run before
    security headers so a 400 host rejection still has the headers.
    """
    setup_trusted_hosts(app)
    setup_security_headers(app)
