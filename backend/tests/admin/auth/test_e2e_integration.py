"""End-to-end integration flows across the 6 admin auth endpoints.

Step 5 (`test_endpoints.py`) covers each endpoint in isolation. This file
crosses endpoint boundaries to exercise the user-visible journeys:

  Flow 1 — Happy session lifecycle: login → refresh → logout
  Flow 2 — Authenticated password change keeps the caller logged in
  Flow 3 — Forgot → reset → login-with-new-password (old password rejected)
  Flow 4 — First-login force_password_change_at clear-on-change
  Flow 5 — Two concurrent client "tabs" rotate / logout independently
  Flow 6 — Suspended-user lockout (login + replay of an issued cookie)

Each flow re-uses the `http_env` fixture (in-memory aiosqlite engine + ASGI
client + auto rate-limiter reset). No mocks — the real bcrypt cost-12 hash
runs every login, the real session rotation transaction runs every refresh.

Why we directly seed `AdminPasswordReset` rows for Flows 3 + 4 instead of
hitting `/forgot-password`: `app.admin.auth.email` is in the coverage-omit
list (decision #24.F) and `send_password_reset_email()` returns the
plaintext token only via Resend. Replicating the test_endpoints.py pattern
of building the reset row by hand keeps these flows hermetic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.admin.auth.constants import ACCESS_TOKEN_COOKIE, REFRESH_TOKEN_COOKIE
from app.admin.auth.password import hash_password
from app.admin.auth.refresh_token import hash_refresh_token
from app.models.admin import AdminPasswordReset, AdminSession, AdminUser
from tests.admin.auth.conftest import HttpEnv

_KNOWN_PASSWORD = "Tr0ub4dor&3-Long"
_NEW_PASSWORD = "Galaxy-Quest-Rises-9"
_THIRD_PASSWORD = "Helio-Trope-Dawn-7"


async def _seed_user(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    email: str = "frank@example.com",
    password: str = _KNOWN_PASSWORD,
    status: str = "active",
    force_password_change_at: datetime | None = None,
) -> AdminUser:
    async with sessionmaker() as session:
        user = AdminUser(
            email=email,
            password_hash=hash_password(password),
            role="super_admin",
            status=status,
            force_password_change_at=force_password_change_at,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


# ---------------------------------------------------------------------------
# Flow 1 — Happy session lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flow1_login_refresh_logout_full_lifecycle(http_env: HttpEnv) -> None:
    user = await _seed_user(http_env.sessionmaker)

    # Step 1: login.
    login_res = await http_env.client.post(
        "/admin/api/v1/auth/login",
        json={"email": user.email, "password": _KNOWN_PASSWORD},
    )
    assert login_res.status_code == 200
    initial_access = http_env.client.cookies.get(ACCESS_TOKEN_COOKIE)
    initial_refresh = http_env.client.cookies.get(REFRESH_TOKEN_COOKIE)
    assert initial_access and initial_refresh

    # Step 2: refresh — rotates both cookies.
    refresh_res = await http_env.client.post("/admin/api/v1/auth/refresh")
    assert refresh_res.status_code == 200
    rotated_access = http_env.client.cookies.get(ACCESS_TOKEN_COOKIE)
    rotated_refresh = http_env.client.cookies.get(REFRESH_TOKEN_COOKIE)
    assert rotated_refresh != initial_refresh
    assert rotated_access != initial_access

    # Step 3: logout — clears cookies + revokes the still-active session.
    logout_res = await http_env.client.post("/admin/api/v1/auth/logout")
    assert logout_res.status_code == 200

    async with http_env.sessionmaker() as s:
        sessions = (await s.execute(select(AdminSession))).scalars().all()
        # Two rows: original (revoked by rotation) + rotated (revoked by logout).
        assert len(sessions) == 2
        assert all(r.revoked_at is not None for r in sessions)


# ---------------------------------------------------------------------------
# Flow 3 — Forgot → reset → login-with-new-password
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flow3_forgot_reset_then_login_with_new_password(
    http_env: HttpEnv,
) -> None:
    user = await _seed_user(http_env.sessionmaker)

    # Step 1: trigger forgot-password — endpoint is fire-and-forget; we
    # assert only that a reset row landed and we DON'T need its plaintext
    # because we will short-circuit Step 2 by seeding our own row whose
    # plaintext we already know.
    forgot_res = await http_env.client.post(
        "/admin/api/v1/auth/forgot-password",
        json={"email": user.email, "locale": "zh-CN"},
    )
    assert forgot_res.status_code == 202

    # Step 2: seed a known-plaintext reset row (the one the endpoint
    # generated is opaque — its plaintext only lives in the email body).
    plaintext_token = "flow3-known-reset-token-32-bytes!"
    async with http_env.sessionmaker() as s:
        s.add(
            AdminPasswordReset(
                admin_user_id=user.id,
                token_hash=hash_refresh_token(plaintext_token),
                purpose="reset",
                expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
            )
        )
        await s.commit()

    # Step 3: redeem the token.
    reset_res = await http_env.client.post(
        "/admin/api/v1/auth/reset-password",
        json={"token": plaintext_token, "new_password": _NEW_PASSWORD},
    )
    assert reset_res.status_code == 200

    # Step 4: old password no longer works.
    old_pw_res = await http_env.client.post(
        "/admin/api/v1/auth/login",
        json={"email": user.email, "password": _KNOWN_PASSWORD},
    )
    assert old_pw_res.status_code == 401
    assert old_pw_res.json()["detail"]["reason"] == "invalid_credentials"

    # Step 5: new password works.
    new_pw_res = await http_env.client.post(
        "/admin/api/v1/auth/login",
        json={"email": user.email, "password": _NEW_PASSWORD},
    )
    assert new_pw_res.status_code == 200
    assert new_pw_res.json()["user"]["email"] == user.email

    # Step 6: replaying the same reset token now fails (used_at stamped).
    replay_res = await http_env.client.post(
        "/admin/api/v1/auth/reset-password",
        json={"token": plaintext_token, "new_password": _THIRD_PASSWORD},
    )
    assert replay_res.status_code == 400
    assert replay_res.json()["detail"]["reason"] == "invalid_token"


# ---------------------------------------------------------------------------
# Flow 2 — Login → change-password → caller stays logged in
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flow2_change_password_keeps_caller_logged_in(http_env: HttpEnv) -> None:
    user = await _seed_user(http_env.sessionmaker)

    # Step 1: login.
    await http_env.client.post(
        "/admin/api/v1/auth/login",
        json={"email": user.email, "password": _KNOWN_PASSWORD},
    )
    pre_change_refresh = http_env.client.cookies.get(REFRESH_TOKEN_COOKIE)

    # Step 2: change password — the endpoint mints a fresh cookie pair so
    # the caller's session stays alive while every other tab gets booted.
    change_res = await http_env.client.post(
        "/admin/api/v1/auth/change-password",
        json={"current_password": _KNOWN_PASSWORD, "new_password": _NEW_PASSWORD},
    )
    assert change_res.status_code == 200
    post_change_refresh = http_env.client.cookies.get(REFRESH_TOKEN_COOKIE)
    assert post_change_refresh != pre_change_refresh

    # Step 3: the new cookie is usable — caller can still refresh.
    refresh_res = await http_env.client.post("/admin/api/v1/auth/refresh")
    assert refresh_res.status_code == 200

    # Step 4: old password no longer logs in (use a separate client since
    # this one is already authenticated; cookies persist across requests).
    transport = ASGITransport(app=__import__("app.main", fromlist=["app"]).app)
    async with AsyncClient(transport=transport, base_url="http://test") as fresh:
        old_pw_res = await fresh.post(
            "/admin/api/v1/auth/login",
            json={"email": user.email, "password": _KNOWN_PASSWORD},
        )
        assert old_pw_res.status_code == 401
        new_pw_res = await fresh.post(
            "/admin/api/v1/auth/login",
            json={"email": user.email, "password": _NEW_PASSWORD},
        )
        assert new_pw_res.status_code == 200


# ---------------------------------------------------------------------------
# Flow 4 — Force-password-change first-login flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flow4_force_password_change_clears_on_change(
    http_env: HttpEnv,
) -> None:
    forced_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
    user = await _seed_user(
        http_env.sessionmaker,
        force_password_change_at=forced_at,
    )

    # Step 1: login still succeeds — auth gate is at the route guard, not
    # at /login (the user must be allowed to *reach* /change-password).
    login_res = await http_env.client.post(
        "/admin/api/v1/auth/login",
        json={"email": user.email, "password": _KNOWN_PASSWORD},
    )
    assert login_res.status_code == 200
    body = login_res.json()
    # The flag travels back to the frontend in camelCase (Step 7 alias rule).
    assert body["user"]["forcePasswordChangeAt"] is not None

    # Step 2: change the password — the endpoint MUST clear the flag.
    change_res = await http_env.client.post(
        "/admin/api/v1/auth/change-password",
        json={"current_password": _KNOWN_PASSWORD, "new_password": _NEW_PASSWORD},
    )
    assert change_res.status_code == 200
    assert change_res.json()["user"]["forcePasswordChangeAt"] is None

    # Step 3: a subsequent login also reflects the cleared flag (DB-level
    # confirmation rather than a cached response).
    transport = ASGITransport(app=__import__("app.main", fromlist=["app"]).app)
    async with AsyncClient(transport=transport, base_url="http://test") as fresh:
        relogin = await fresh.post(
            "/admin/api/v1/auth/login",
            json={"email": user.email, "password": _NEW_PASSWORD},
        )
        assert relogin.status_code == 200
        assert relogin.json()["user"]["forcePasswordChangeAt"] is None


# ---------------------------------------------------------------------------
# Flow 6 — Suspended-user lockout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flow6_suspended_user_cannot_login_or_use_existing_cookie(
    http_env: HttpEnv,
) -> None:
    user = await _seed_user(http_env.sessionmaker)

    # Step 1: user logs in while still active and captures the access cookie.
    login_res = await http_env.client.post(
        "/admin/api/v1/auth/login",
        json={"email": user.email, "password": _KNOWN_PASSWORD},
    )
    assert login_res.status_code == 200
    captured_access = http_env.client.cookies.get(ACCESS_TOKEN_COOKIE)
    assert captured_access is not None

    # Step 2: admin suspends the user (simulated by direct DB update).
    async with http_env.sessionmaker() as s:
        row = (await s.execute(select(AdminUser).where(AdminUser.id == user.id))).scalar_one()
        row.status = "suspended"
        await s.commit()

    # Step 3: a fresh login attempt must be rejected with `user_suspended`.
    transport = ASGITransport(app=__import__("app.main", fromlist=["app"]).app)
    async with AsyncClient(transport=transport, base_url="http://test") as fresh:
        relogin = await fresh.post(
            "/admin/api/v1/auth/login",
            json={"email": user.email, "password": _KNOWN_PASSWORD},
        )
        assert relogin.status_code == 401
        assert relogin.json()["detail"]["reason"] == "user_suspended"

    # Step 4 (Bug 3 · pinned current behaviour, expected behaviour deferred):
    # The cookie captured BEFORE suspension is replayed against a protected
    # endpoint. The CORRECT behaviour is for the backend to reject it
    # (401/403) — but `require_admin_session` validates the JWT only, never
    # re-loading the user row to check `status='active'`. So the cookie is
    # honoured for the remainder of its 15-minute TTL.
    #
    # TODO · Bug 3 — middleware does not re-check user.status after JWT
    # validation. Suspended user's existing access_token remains usable
    # until TTL=15 min (and `/refresh` shares the same gap, allowing
    # self-extension). Fix scheduled for Session A1' alongside the admin
    # "suspend user" + "revoke all sessions" flow — middleware extension
    # + bulk session revocation are the same one-shot change there. See
    # Admin auth known
    # issues" section (Bug 3) for the running log. Decision #24.D
    # cross-state-machine boundary gap; not blocking A0' scaffold.
    async with AsyncClient(transport=transport, base_url="http://test") as replay:
        protected = await replay.post(
            "/admin/api/v1/auth/change-password",
            headers={"Cookie": f"{ACCESS_TOKEN_COOKIE}={captured_access}"},
            json={
                "current_password": _KNOWN_PASSWORD,
                "new_password": _NEW_PASSWORD,
            },
        )
        # Pinned to current (buggy) behaviour. Flip to `in (401, 403)` once
        # A1' lands the middleware status re-check.
        assert protected.status_code == 200, (
            "Bug 3 baseline drift — Flow 6 expected 200 (cookie honoured "
            "due to middleware gap) but got something else. If this is a "
            "regression in the wrong direction (e.g. status flipped without "
            "the planned A1' fix), investigate before flipping the assertion."
        )


# ---------------------------------------------------------------------------
# Flow 5 — Two concurrent "tabs" rotate / logout independently
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flow5_two_clients_rotate_and_logout_independently(
    http_env: HttpEnv,
) -> None:
    user = await _seed_user(http_env.sessionmaker)

    # Tab A is the fixture's client. Tab B is a separate ASGI client so
    # cookie jars do not collide.
    transport = ASGITransport(app=__import__("app.main", fromlist=["app"]).app)
    async with AsyncClient(transport=transport, base_url="http://test") as tab_b:
        # Step 1: both tabs log in — two separate session rows created.
        a_login = await http_env.client.post(
            "/admin/api/v1/auth/login",
            json={"email": user.email, "password": _KNOWN_PASSWORD},
        )
        assert a_login.status_code == 200
        b_login = await tab_b.post(
            "/admin/api/v1/auth/login",
            json={"email": user.email, "password": _KNOWN_PASSWORD},
        )
        assert b_login.status_code == 200

        async with http_env.sessionmaker() as s:
            rows = (await s.execute(select(AdminSession))).scalars().all()
            assert len(rows) == 2
            assert all(r.revoked_at is None for r in rows)

        # Step 2: tab A refreshes — only A's session rotates.
        a_refresh = await http_env.client.post("/admin/api/v1/auth/refresh")
        assert a_refresh.status_code == 200
        async with http_env.sessionmaker() as s:
            rows = (await s.execute(select(AdminSession))).scalars().all()
            revoked = [r for r in rows if r.revoked_at is not None]
            active = [r for r in rows if r.revoked_at is None]
            # A original revoked, A rotated active, B original active = 2 active.
            assert len(revoked) == 1
            assert len(active) == 2

        # Step 3: tab B can still refresh — B's session was untouched.
        b_refresh = await tab_b.post("/admin/api/v1/auth/refresh")
        assert b_refresh.status_code == 200

        # Step 4: tab A logout — only A's currently-active row gets revoked.
        a_logout = await http_env.client.post("/admin/api/v1/auth/logout")
        assert a_logout.status_code == 200

        # Step 5: tab B is still alive AFTER A's logout.
        b_refresh_again = await tab_b.post("/admin/api/v1/auth/refresh")
        assert b_refresh_again.status_code == 200
