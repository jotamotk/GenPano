"""Hotfix #3 — admin session endpoint contract preserves ``authenticated``.

The admin SPA's ``checkAdminSession`` reads ``body.authenticated`` to
decide whether to render the login form or the main app:

    this.isLoggedIn = !!body.authenticated;

Phase 2 of the admin_console → backend migration rewrote ``GET
/api/admin/session`` (Flask) into FastAPI's ``GET /api/admin/auth/session``
but silently dropped the ``authenticated`` field — the new endpoint
returned only ``{"admin": {...}}`` or ``{"admin": null}``. Result:
``body.authenticated === undefined`` on every probe, so
``isLoggedIn`` flipped to ``false`` on every page reload AND right after
a successful login the next admin tab loader's 401 (or even just a
re-render that re-ran ``checkAdminSession``) bounced the user back to
the login screen — making it look like "logged in but every admin
request 401s, even after re-login".

This test fixes the contract by asserting both the legacy-shape
``authenticated`` boolean and the ``admin`` object are present on the
response, for both the anonymous and the signed-in cases.
"""

from __future__ import annotations

import os
import uuid

import pytest
from genpano_models import AdminUser
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest.mark.asyncio
async def test_session_anonymous_returns_authenticated_false(client):
    """No cookie at all → 200 with {authenticated: False, admin: None}.

    The SPA polls this on page load; it MUST be 200 (not 401) and MUST
    expose ``authenticated`` so ``!!body.authenticated`` reads correctly.
    """
    resp = await client.get("/api/admin/auth/session")
    assert resp.status_code == 200
    body = resp.json()
    assert "authenticated" in body, (
        "session endpoint must return 'authenticated' field "
        "(legacy admin_console Flask contract); SPA reads "
        "this.isLoggedIn = !!body.authenticated"
    )
    assert body["authenticated"] is False
    assert body["admin"] is None


@pytest.mark.asyncio
async def test_session_logged_in_returns_authenticated_true(
    client, db_session: AsyncSession
):
    """Valid signed-cookie session → 200 with authenticated=True
    AND a populated admin object.

    Uses ``client.cookies.set`` to mount a real Starlette-signed cookie
    so we exercise SessionMiddleware end-to-end (rather than mocking
    ``current_admin``). Login happens through ``POST /auth/login``
    so the cookie is signed by the same SessionMiddleware secret the
    session endpoint reads through.
    """
    # bcrypt hash of "test-password" — we need a real hash because login
    # invokes bcrypt.checkpw. Generated via bcrypt.hashpw for test fixture.
    import bcrypt

    password = "test-password-1234"
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()

    admin = AdminUser(
        id=_new_id(),
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=password_hash,
        role="super_admin",
        status="active",
    )
    db_session.add(admin)
    await db_session.commit()

    login_resp = await client.post(
        "/api/admin/auth/login",
        json={"email": admin.email, "password": password},
    )
    assert login_resp.status_code == 200, login_resp.text
    assert login_resp.json()["success"] is True

    # The login response sets a signed Starlette session cookie.
    # AsyncClient holds it on its cookie jar, so the next request
    # exercises the real SessionMiddleware decode path.
    resp = await client.get("/api/admin/auth/session")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("authenticated") is True, (
        f"expected authenticated=True after login; got body={body}. "
        "Without this field the SPA's checkAdminSession silently "
        "logs the user out on every page reload."
    )
    assert body["admin"] is not None
    assert body["admin"]["id"] == admin.id
    assert body["admin"]["email"] == admin.email
    assert body["admin"]["status"] == "active"


@pytest.mark.asyncio
async def test_session_suspended_admin_returns_authenticated_false(
    client, db_session: AsyncSession
):
    """If the admin row was suspended after the cookie was issued, the
    session endpoint must report authenticated=False (and pop the stale
    admin_user_id from request.session) so the SPA doesn't render the
    main app for a frozen operator."""
    import bcrypt

    password = "test-password-1234"
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()

    admin = AdminUser(
        id=_new_id(),
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=password_hash,
        role="super_admin",
        status="active",
    )
    db_session.add(admin)
    await db_session.commit()

    login_resp = await client.post(
        "/api/admin/auth/login",
        json={"email": admin.email, "password": password},
    )
    assert login_resp.status_code == 200

    # Suspend the admin out-of-band.
    admin.status = "suspended"
    await db_session.commit()

    resp = await client.get("/api/admin/auth/session")
    assert resp.status_code == 200
    body = resp.json()
    assert body["authenticated"] is False
    assert body["admin"] is None
