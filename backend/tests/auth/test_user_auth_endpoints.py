from __future__ import annotations

from importlib import import_module

from sqlalchemy import select
from tests.auth.conftest import UserAuthHttpEnv

from app.models.user import User, UserAuthToken
from app.user_auth.password import hash_password, verify_password

auth_router_module = import_module("app.api.v1.auth.router")


async def test_lookup_returns_register_for_new_email(
    user_auth_http_env: UserAuthHttpEnv,
) -> None:
    res = await user_auth_http_env.client.post(
        "/api/auth/lookup",
        json={"email": "new@company.com"},
    )
    assert res.status_code == 200
    assert res.json()["next"] == "register"
    assert res.json()["exists"] is False


async def test_register_accepts_gmail_address(user_auth_http_env: UserAuthHttpEnv) -> None:
    res = await user_auth_http_env.client.post(
        "/api/auth/register",
        json={"email": "person@gmail.com"},
    )
    assert res.status_code == 201
    assert res.json()["email"] == "person@gmail.com"


async def test_register_setup_and_me_flow(
    user_auth_http_env: UserAuthHttpEnv,
    monkeypatch,
) -> None:
    captured: dict[str, str] = {}

    def _capture_email(*, to: str, token: str, **_kwargs):
        captured["to"] = to
        captured["token"] = token

    monkeypatch.setattr(auth_router_module, "send_verification_email", _capture_email)
    monkeypatch.setattr(auth_router_module, "send_welcome_email", lambda **_kwargs: None)

    register = await user_auth_http_env.client.post(
        "/api/auth/register",
        json={"email": "User@Gmail.com", "locale": "en-US"},
    )
    assert register.status_code == 201
    assert register.json()["email"] == "user@gmail.com"
    assert captured["to"] == "user@gmail.com"

    info = await user_auth_http_env.client.get(
        "/api/auth/setup-token",
        params={"token": captured["token"]},
    )
    assert info.status_code == 200
    assert info.json()["email"] == "user@gmail.com"
    assert info.json()["requiresPassword"] is True

    setup = await user_auth_http_env.client.post(
        "/api/auth/setup",
        json={
            "token": captured["token"],
            "email": "user@gmail.com",
            "password": "Strong123",
            "name": "User Name",
            "company": "Company",
            "newsletter": False,
            "locale": "en-US",
        },
    )
    assert setup.status_code == 200
    body = setup.json()
    assert body["token"]
    assert body["user"]["emailVerified"] is True
    assert body["user"]["company"] == "Company"

    me = await user_auth_http_env.client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {body['token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "user@gmail.com"

    reused = await user_auth_http_env.client.post(
        "/api/auth/setup",
        json={
            "token": captured["token"],
            "email": "user@gmail.com",
            "password": "Strong123",
            "name": "User Name",
            "company": "Company",
        },
    )
    assert reused.status_code == 400


async def test_login_success_and_bad_password(user_auth_http_env: UserAuthHttpEnv) -> None:
    async with user_auth_http_env.sessionmaker() as session:
        session.add(
            User(
                email="login@company.com",
                password_hash=hash_password("Strong123"),
                name="Login User",
                company="Company",
                email_verified=True,
            )
        )
        await session.commit()

    ok = await user_auth_http_env.client.post(
        "/api/auth/login",
        json={"email": "LOGIN@company.com", "password": "Strong123"},
    )
    assert ok.status_code == 200
    assert ok.json()["user"]["email"] == "login@company.com"

    bad = await user_auth_http_env.client.post(
        "/api/auth/login",
        json={"email": "login@company.com", "password": "Wrong123"},
    )
    assert bad.status_code == 401
    assert bad.json()["detail"]["code"] == "invalid_credentials"


async def test_forgot_password_is_non_enumerable_for_unknown_email(
    user_auth_http_env: UserAuthHttpEnv,
) -> None:
    res = await user_auth_http_env.client.post(
        "/api/auth/forgot-password",
        json={"email": "unknown@company.com"},
    )
    assert res.status_code == 200
    assert "reset email" in res.json()["message"]


async def test_reset_password_uses_one_time_token(
    user_auth_http_env: UserAuthHttpEnv,
    monkeypatch,
) -> None:
    captured: dict[str, str] = {}

    def _capture_email(*, to: str, token: str, **_kwargs):
        captured["to"] = to
        captured["token"] = token

    monkeypatch.setattr(auth_router_module, "send_password_reset_email", _capture_email)

    async with user_auth_http_env.sessionmaker() as session:
        session.add(
            User(
                email="reset@company.com",
                password_hash=hash_password("Strong123"),
                name="Reset User",
                company="Company",
                email_verified=True,
            )
        )
        await session.commit()

    forgot = await user_auth_http_env.client.post(
        "/api/auth/forgot-password",
        json={"email": "reset@company.com"},
    )
    assert forgot.status_code == 200
    assert captured["to"] == "reset@company.com"

    reset = await user_auth_http_env.client.post(
        "/api/auth/reset-password",
        json={"token": captured["token"], "password": "Newpass123"},
    )
    assert reset.status_code == 200

    async with user_auth_http_env.sessionmaker() as session:
        user = (
            await session.execute(select(User).where(User.email == "reset@company.com"))
        ).scalar_one()
        used_token = (
            await session.execute(select(UserAuthToken).where(UserAuthToken.user_id == user.id))
        ).scalar_one()
        assert used_token.used_at is not None
        assert verify_password("Newpass123", user.password_hash or "") is True

    reused = await user_auth_http_env.client.post(
        "/api/auth/reset-password",
        json={"token": captured["token"], "password": "Again123"},
    )
    assert reused.status_code == 400
