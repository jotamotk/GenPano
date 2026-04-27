"""Integration tests for the 6 admin auth endpoints — 18 cases.

Each test spins up an isolated in-memory engine via the `http_env`
fixture (see `conftest.py`) so the cookie state, the audit log, and the
session table are all freshly created per case. The tests use the real
ASGI stack: FastAPI app + Starlette + dependency injection. We never mock
the password hash; bcrypt cost=12 is real and adds ~50 ms / hash but the
suite runs in well under 30 s on CI.

Layout:
- 5 login cases  (success / unknown email / wrong password / suspended / rate limit)
- 3 refresh cases  (rotation / no cookie / replay revoked)
- 2 logout cases  (revoke + clear / no cookie no-op)
- 2 forgot-password cases  (known active user / unknown email silent 202)
- 3 reset-password cases  (happy path / invalid token / weak password)
- 3 change-password cases  (happy path / wrong current / no session)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.admin.auth.constants import (
    ACCESS_TOKEN_COOKIE,
    REFRESH_TOKEN_COOKIE,
)
from app.admin.auth.password import hash_password
from app.admin.auth.refresh_token import hash_refresh_token
from app.models.admin import (
    AdminLoginAttempt,
    AdminPasswordReset,
    AdminSession,
    AdminUser,
)
from tests.admin.auth.conftest import HttpEnv

# A zxcvbn score-3 password 12+ chars long; reused so the bcrypt hash is
# computed once per test rather than per assertion.
_KNOWN_PASSWORD = "Tr0ub4dor&3-Long"
_NEW_PASSWORD = "Galaxy-Quest-Rises-9"


async def _seed_user(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    email: str = "frank@example.com",
    password: str = _KNOWN_PASSWORD,
    status: str = "active",
    force_password_change_at: datetime | None = None,
    last_password_at: datetime | None = None,
) -> AdminUser:
    async with sessionmaker() as session:
        user = AdminUser(
            email=email,
            password_hash=hash_password(password),
            role="super_admin",
            status=status,
            force_password_change_at=force_password_change_at,
            last_password_at=last_password_at,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


# ---------------------------------------------------------------------------
# /login (5 cases)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_success_sets_cookies_and_returns_user(http_env: HttpEnv) -> None:
    user = await _seed_user(http_env.sessionmaker)

    res = await http_env.client.post(
        "/admin/api/v1/auth/login",
        json={"email": user.email, "password": _KNOWN_PASSWORD},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["user"]["email"] == user.email
    assert body["user"]["role"] == "super_admin"
    assert body["accessExpiresAt"] > 0
    # Both auth cookies present, both HttpOnly + SameSite=Strict + Path=/admin
    cookies = res.headers.get_list("set-cookie")
    assert any(c.startswith(f"{ACCESS_TOKEN_COOKIE}=") for c in cookies)
    assert any(c.startswith(f"{REFRESH_TOKEN_COOKIE}=") for c in cookies)
    assert all(("HttpOnly" in c and "samesite=strict" in c.lower()) for c in cookies)
    # Audit row records the success
    async with http_env.sessionmaker() as s:
        attempts = (await s.execute(select(AdminLoginAttempt))).scalars().all()
        assert len(attempts) == 1
        assert attempts[0].success is True


@pytest.mark.asyncio
async def test_login_unknown_email_returns_401_and_audits_unknown(
    http_env: HttpEnv,
) -> None:
    res = await http_env.client.post(
        "/admin/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "irrelevant"},
    )

    assert res.status_code == 401
    assert res.json()["detail"]["reason"] == "invalid_credentials"
    async with http_env.sessionmaker() as s:
        [row] = (await s.execute(select(AdminLoginAttempt))).scalars().all()
        assert row.failure_code == "UNKNOWN_EMAIL"
        assert row.success is False


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401_and_audits_wrong_password(
    http_env: HttpEnv,
) -> None:
    user = await _seed_user(http_env.sessionmaker)

    res = await http_env.client.post(
        "/admin/api/v1/auth/login",
        json={"email": user.email, "password": "definitely-wrong"},
    )

    assert res.status_code == 401
    assert res.json()["detail"]["reason"] == "invalid_credentials"
    async with http_env.sessionmaker() as s:
        [row] = (await s.execute(select(AdminLoginAttempt))).scalars().all()
        assert row.failure_code == "WRONG_PASSWORD"


@pytest.mark.asyncio
async def test_login_suspended_user_returns_401_and_audits_user_suspended(
    http_env: HttpEnv,
) -> None:
    user = await _seed_user(http_env.sessionmaker, status="suspended")

    res = await http_env.client.post(
        "/admin/api/v1/auth/login",
        json={"email": user.email, "password": _KNOWN_PASSWORD},
    )

    assert res.status_code == 401
    assert res.json()["detail"]["reason"] == "user_suspended"
    async with http_env.sessionmaker() as s:
        [row] = (await s.execute(select(AdminLoginAttempt))).scalars().all()
        assert row.failure_code == "USER_SUSPENDED"


@pytest.mark.asyncio
async def test_login_rate_limit_kicks_in_after_five_email_attempts(
    http_env: HttpEnv,
) -> None:
    user = await _seed_user(http_env.sessionmaker)
    bad = {"email": user.email, "password": "wrong"}

    # Attempts 1-5 each return 401 wrong_password; attempt 6+ must return 429.
    for _ in range(5):
        res = await http_env.client.post("/admin/api/v1/auth/login", json=bad)
        assert res.status_code == 401

    res = await http_env.client.post("/admin/api/v1/auth/login", json=bad)
    assert res.status_code == 429
    assert res.json()["detail"]["reason"] == "rate_limited"
    async with http_env.sessionmaker() as s:
        codes = [
            r.failure_code
            for r in (await s.execute(select(AdminLoginAttempt))).scalars().all()
        ]
        assert codes.count("RATE_LIMITED") >= 1


# ---------------------------------------------------------------------------
# /refresh (3 cases)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_with_valid_cookie_rotates_session(http_env: HttpEnv) -> None:
    user = await _seed_user(http_env.sessionmaker)
    login_res = await http_env.client.post(
        "/admin/api/v1/auth/login",
        json={"email": user.email, "password": _KNOWN_PASSWORD},
    )
    assert login_res.status_code == 200
    # The httpx client retains cookies, so /refresh sees the refresh cookie.

    refresh_res = await http_env.client.post("/admin/api/v1/auth/refresh")

    assert refresh_res.status_code == 200
    assert refresh_res.json()["user"]["email"] == user.email

    async with http_env.sessionmaker() as s:
        sessions = (await s.execute(select(AdminSession))).scalars().all()
        # 2 rows: the original (now revoked) + the newly minted one.
        assert len(sessions) == 2
        revoked = [r for r in sessions if r.revoked_at is not None]
        active = [r for r in sessions if r.revoked_at is None]
        assert len(revoked) == 1
        assert len(active) == 1


@pytest.mark.asyncio
async def test_refresh_without_cookie_returns_401(http_env: HttpEnv) -> None:
    res = await http_env.client.post("/admin/api/v1/auth/refresh")
    assert res.status_code == 401
    assert res.json()["detail"]["reason"] == "no_session"


@pytest.mark.asyncio
async def test_refresh_replay_after_rotation_returns_401(http_env: HttpEnv) -> None:
    user = await _seed_user(http_env.sessionmaker)
    await http_env.client.post(
        "/admin/api/v1/auth/login",
        json={"email": user.email, "password": _KNOWN_PASSWORD},
    )
    captured_refresh = http_env.client.cookies.get(REFRESH_TOKEN_COOKIE)
    assert captured_refresh is not None

    # First /refresh rotates the token — the new cookie replaces the old.
    first = await http_env.client.post("/admin/api/v1/auth/refresh")
    assert first.status_code == 200

    # Replay the original refresh token on a fresh client by injecting the
    # cookie via the request `Cookie` header — bypasses httpx's cookie-jar
    # domain-matching quirks while still exercising the real revoked-token
    # rejection path on the server.
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as alt:
        replay = await alt.post(
            "/admin/api/v1/auth/refresh",
            headers={"Cookie": f"{REFRESH_TOKEN_COOKIE}={captured_refresh}"},
        )

    assert replay.status_code == 401
    assert replay.json()["detail"]["reason"] == "invalid_refresh"


# ---------------------------------------------------------------------------
# /logout (2 cases)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logout_clears_cookies_and_revokes_session(http_env: HttpEnv) -> None:
    user = await _seed_user(http_env.sessionmaker)
    await http_env.client.post(
        "/admin/api/v1/auth/login",
        json={"email": user.email, "password": _KNOWN_PASSWORD},
    )

    res = await http_env.client.post("/admin/api/v1/auth/logout")

    assert res.status_code == 200
    cookies = res.headers.get_list("set-cookie")
    # Both cookies emit a deletion (Max-Age=0 / empty value).
    assert any(ACCESS_TOKEN_COOKIE in c and "Max-Age=0" in c for c in cookies)
    assert any(REFRESH_TOKEN_COOKIE in c and "Max-Age=0" in c for c in cookies)

    async with http_env.sessionmaker() as s:
        [row] = (await s.execute(select(AdminSession))).scalars().all()
        assert row.revoked_at is not None


@pytest.mark.asyncio
async def test_logout_without_cookie_still_returns_200(http_env: HttpEnv) -> None:
    res = await http_env.client.post("/admin/api/v1/auth/logout")
    assert res.status_code == 200
    assert res.json() == {"ok": True}


# ---------------------------------------------------------------------------
# /forgot-password (2 cases)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forgot_password_for_known_email_creates_reset_row(
    http_env: HttpEnv,
) -> None:
    user = await _seed_user(http_env.sessionmaker)

    res = await http_env.client.post(
        "/admin/api/v1/auth/forgot-password",
        json={"email": user.email, "locale": "zh-CN"},
    )

    assert res.status_code == 202
    async with http_env.sessionmaker() as s:
        [row] = (await s.execute(select(AdminPasswordReset))).scalars().all()
        assert row.admin_user_id == user.id
        assert row.purpose == "reset"
        assert row.used_at is None
        assert row.expires_at > datetime.now(UTC).replace(tzinfo=None)


@pytest.mark.asyncio
async def test_forgot_password_for_unknown_email_returns_202_silently(
    http_env: HttpEnv,
) -> None:
    res = await http_env.client.post(
        "/admin/api/v1/auth/forgot-password",
        json={"email": "ghost@example.com", "locale": "en-US"},
    )
    assert res.status_code == 202
    async with http_env.sessionmaker() as s:
        rows = (await s.execute(select(AdminPasswordReset))).scalars().all()
        assert rows == []  # no enumeration leak


# ---------------------------------------------------------------------------
# /reset-password (3 cases)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_password_happy_path_revokes_all_sessions(
    http_env: HttpEnv,
) -> None:
    user = await _seed_user(http_env.sessionmaker)
    # Pre-existing active session that must be revoked by reset.
    await http_env.client.post(
        "/admin/api/v1/auth/login",
        json={"email": user.email, "password": _KNOWN_PASSWORD},
    )
    # Create a known reset token directly so we have its plaintext.
    plaintext_token = "reset-plaintext-token-value-32"
    digest = hash_refresh_token(plaintext_token)
    async with http_env.sessionmaker() as s:
        s.add(
            AdminPasswordReset(
                admin_user_id=user.id,
                token_hash=digest,
                purpose="reset",
                expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
            )
        )
        await s.commit()

    res = await http_env.client.post(
        "/admin/api/v1/auth/reset-password",
        json={"token": plaintext_token, "new_password": _NEW_PASSWORD},
    )

    assert res.status_code == 200
    async with http_env.sessionmaker() as s:
        refreshed = (
            await s.execute(select(AdminUser).where(AdminUser.id == user.id))
        ).scalar_one()
        # New password sets last_password_at + clears force_password_change_at.
        assert refreshed.last_password_at is not None
        assert refreshed.force_password_change_at is None
        # Reset row marked used.
        [reset_row] = (await s.execute(select(AdminPasswordReset))).scalars().all()
        assert reset_row.used_at is not None
        # The login session minted earlier is now revoked.
        sessions = (await s.execute(select(AdminSession))).scalars().all()
        assert all(r.revoked_at is not None for r in sessions)


@pytest.mark.asyncio
async def test_reset_password_with_invalid_token_returns_400(
    http_env: HttpEnv,
) -> None:
    await _seed_user(http_env.sessionmaker)

    res = await http_env.client.post(
        "/admin/api/v1/auth/reset-password",
        json={"token": "nope-not-a-real-token-string", "new_password": _NEW_PASSWORD},
    )

    assert res.status_code == 400
    assert res.json()["detail"]["reason"] == "invalid_token"


@pytest.mark.asyncio
async def test_reset_password_rejects_too_short_password(http_env: HttpEnv) -> None:
    user = await _seed_user(http_env.sessionmaker)
    plaintext_token = "another-known-reset-token-32-bytes"
    digest = hash_refresh_token(plaintext_token)
    async with http_env.sessionmaker() as s:
        s.add(
            AdminPasswordReset(
                admin_user_id=user.id,
                token_hash=digest,
                purpose="reset",
                expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
            )
        )
        await s.commit()

    res = await http_env.client.post(
        "/admin/api/v1/auth/reset-password",
        json={"token": plaintext_token, "new_password": "short1"},
    )

    assert res.status_code == 400
    assert res.json()["detail"]["reason"] == "too_short"


# ---------------------------------------------------------------------------
# /change-password (3 cases)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_change_password_happy_path_keeps_caller_logged_in(
    http_env: HttpEnv,
) -> None:
    user = await _seed_user(http_env.sessionmaker)
    await http_env.client.post(
        "/admin/api/v1/auth/login",
        json={"email": user.email, "password": _KNOWN_PASSWORD},
    )

    res = await http_env.client.post(
        "/admin/api/v1/auth/change-password",
        json={"current_password": _KNOWN_PASSWORD, "new_password": _NEW_PASSWORD},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["user"]["forcePasswordChangeAt"] is None
    # The response sets a NEW pair of cookies — caller stays logged in.
    cookies = res.headers.get_list("set-cookie")
    assert any(c.startswith(f"{ACCESS_TOKEN_COOKIE}=") for c in cookies)
    assert any(c.startswith(f"{REFRESH_TOKEN_COOKIE}=") for c in cookies)

    async with http_env.sessionmaker() as s:
        sessions = (await s.execute(select(AdminSession))).scalars().all()
        # Original login session revoked, fresh one active.
        active = [r for r in sessions if r.revoked_at is None]
        assert len(active) == 1
        # last_password_at must be set after the change.
        refreshed = (
            await s.execute(select(AdminUser).where(AdminUser.id == user.id))
        ).scalar_one()
        assert refreshed.last_password_at is not None


@pytest.mark.asyncio
async def test_change_password_wrong_current_returns_400(http_env: HttpEnv) -> None:
    user = await _seed_user(http_env.sessionmaker)
    await http_env.client.post(
        "/admin/api/v1/auth/login",
        json={"email": user.email, "password": _KNOWN_PASSWORD},
    )

    res = await http_env.client.post(
        "/admin/api/v1/auth/change-password",
        json={"current_password": "definitely-wrong", "new_password": _NEW_PASSWORD},
    )

    assert res.status_code == 400
    assert res.json()["detail"]["reason"] == "wrong_current_password"


@pytest.mark.asyncio
async def test_change_password_without_session_returns_401(http_env: HttpEnv) -> None:
    # No /login first — change-password requires a valid access cookie.
    res = await http_env.client.post(
        "/admin/api/v1/auth/change-password",
        json={"current_password": _KNOWN_PASSWORD, "new_password": _NEW_PASSWORD},
    )
    assert res.status_code == 401
    assert res.json()["detail"]["reason"] == "no_session"
