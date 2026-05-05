"""Phase 5 — security headers + trusted host middleware."""

from __future__ import annotations

import os

import pytest
from fastapi import FastAPI

from app.core.security_headers import (
    _DEFAULT_HEADERS,
    setup_security,
    setup_security_headers,
    setup_trusted_hosts,
)

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _build_app(env: dict[str, str] | None = None, *, with_trusted: bool = False) -> FastAPI:
    """Build a minimal FastAPI app with the middleware wired."""
    if env:
        for k, v in env.items():
            os.environ[k] = v
    app = FastAPI()

    @app.get("/health")
    async def _health() -> dict[str, str]:
        return {"ok": "1"}

    if with_trusted:
        setup_security(app)
    else:
        setup_security_headers(app)
    return app


# ── headers stamped on every response ─────────────────────────────


@pytest.mark.asyncio
async def test_security_headers_present_on_http_response():
    """When the disabled env-var is unset, every response carries the
    non-HSTS headers. (HSTS is HTTPS-only.)"""
    os.environ.pop("GENPANO_SECURITY_HEADERS_DISABLED", None)
    app = _build_app()
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/health")
    assert resp.status_code == 200
    for name in (
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Permissions-Policy",
    ):
        assert resp.headers.get(name) == _DEFAULT_HEADERS[name]
    # HSTS should NOT be set on http
    assert "Strict-Transport-Security" not in resp.headers


@pytest.mark.asyncio
async def test_hsts_set_when_x_forwarded_proto_https():
    """Behind a TLS terminator the X-Forwarded-Proto header signals
    upstream HTTPS — HSTS should be stamped."""
    os.environ.pop("GENPANO_SECURITY_HEADERS_DISABLED", None)
    app = _build_app()
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/health", headers={"x-forwarded-proto": "https"})
    assert (
        resp.headers.get("Strict-Transport-Security")
        == _DEFAULT_HEADERS["Strict-Transport-Security"]
    )


@pytest.mark.asyncio
async def test_disabled_env_skips_all_headers():
    os.environ["GENPANO_SECURITY_HEADERS_DISABLED"] = "1"
    try:
        app = _build_app()
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/health")
        for name in _DEFAULT_HEADERS:
            assert name not in resp.headers
    finally:
        os.environ.pop("GENPANO_SECURITY_HEADERS_DISABLED", None)


@pytest.mark.asyncio
async def test_upstream_header_override_wins():
    """If a route explicitly sets one of the headers, the middleware
    must NOT overwrite it."""
    os.environ.pop("GENPANO_SECURITY_HEADERS_DISABLED", None)
    app = FastAPI()

    @app.get("/custom")
    async def _custom() -> dict[str, str]:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            content={"ok": "1"},
            headers={"X-Frame-Options": "SAMEORIGIN"},
        )

    setup_security_headers(app)
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/custom")
    assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
    # other defaults still applied
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"


# ── TrustedHostMiddleware via GENPANO_ALLOWED_HOSTS ──────────────


@pytest.mark.asyncio
async def test_trusted_hosts_default_wildcard_allows_anything():
    """Default GENPANO_ALLOWED_HOSTS=* (or unset) → all hosts allowed."""
    os.environ.pop("GENPANO_ALLOWED_HOSTS", None)
    app = FastAPI()

    @app.get("/health")
    async def _health() -> dict[str, str]:
        return {"ok": "1"}

    setup_trusted_hosts(app)
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://anything.example"
    ) as ac:
        resp = await ac.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_trusted_hosts_explicit_allowlist_blocks_other_hosts():
    os.environ["GENPANO_ALLOWED_HOSTS"] = "allowed.example,foo.example"
    try:
        app = FastAPI()

        @app.get("/health")
        async def _health() -> dict[str, str]:
            return {"ok": "1"}

        setup_trusted_hosts(app)
        from httpx import ASGITransport, AsyncClient

        # forbidden host
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://evil.example"
        ) as ac:
            resp = await ac.get("/health")
        assert resp.status_code == 400
        # allowed host
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://allowed.example"
        ) as ac:
            resp = await ac.get("/health")
        assert resp.status_code == 200
    finally:
        os.environ.pop("GENPANO_ALLOWED_HOSTS", None)


@pytest.mark.asyncio
async def test_setup_security_wires_both():
    os.environ.pop("GENPANO_SECURITY_HEADERS_DISABLED", None)
    os.environ.pop("GENPANO_ALLOWED_HOSTS", None)
    app = _build_app(with_trusted=True)
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
