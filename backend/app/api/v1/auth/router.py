from __future__ import annotations

import asyncio
import hmac
import os
import secrets
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import quote, urlencode

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth._dto import (
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    LookupRequest,
    LookupResponse,
    OkResponse,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SetupRequest,
    SetupTokenResponse,
    UserDto,
)
from app.db.session import get_db
from app.models.user import User, UserAuthToken
from app.user_auth.email import (
    frontend_base_url,
    send_password_reset_email,
    send_verification_email,
    send_welcome_email,
)
from app.user_auth.email_rules import is_valid_email_format, normalize_email
from app.user_auth.jwt import (
    UserJwtInvalidError,
    sign_user_access_token,
    verify_user_access_token,
)
from app.user_auth.password import (
    check_user_password_policy,
    hash_password,
    verify_password,
)
from app.user_auth.rate_limiter import check_auth_limit
from app.user_auth.tokens import (
    OAUTH_SETUP_TTL_SECONDS,
    PASSWORD_RESET_TTL_SECONDS,
    VERIFY_EMAIL_TTL_SECONDS,
    hash_token,
    mint_token,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
OAUTH_STATE_TTL_SECONDS = 5 * 60
_MIN_OAUTH_STATE_SECRET_BYTES = 32


def _api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _oauth_state_secret() -> bytes | None:
    raw = os.environ.get("USER_JWT_SECRET") or os.environ.get("ADMIN_JWT_SECRET")
    if raw is None:
        return None
    encoded = raw.encode("utf-8")
    if len(encoded) < _MIN_OAUTH_STATE_SECRET_BYTES:
        return None
    return encoded


def _sign_oauth_state_body(body: str, secret: bytes) -> str:
    return hmac.new(secret, body.encode("utf-8"), digestmod="sha256").hexdigest()


def _make_oauth_state(now: datetime | None = None) -> str | None:
    secret = _oauth_state_secret()
    if secret is None:
        return None
    issued_at = int((now or datetime.now(UTC)).timestamp())
    body = f"{secrets.token_urlsafe(24)}.{issued_at}"
    return f"{body}.{_sign_oauth_state_body(body, secret)}"


def _is_valid_oauth_state(state: str | None, now: datetime | None = None) -> bool:
    secret = _oauth_state_secret()
    if not state or secret is None:
        return False
    parts = state.split(".")
    if len(parts) != 3:
        return False
    nonce, issued_raw, signature = parts
    if not nonce or not issued_raw or not signature:
        return False
    try:
        issued_at = int(issued_raw)
    except ValueError:
        return False
    now_ts = int((now or datetime.now(UTC)).timestamp())
    if issued_at > now_ts + 60 or now_ts - issued_at > OAUTH_STATE_TTL_SECONDS:
        return False
    body = f"{nonce}.{issued_raw}"
    expected = _sign_oauth_state_body(body, secret)
    return hmac.compare_digest(signature, expected)


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else None


def _to_user_dto(user: User) -> UserDto:
    return UserDto(
        id=user.id,
        email=user.email,
        name=user.name,
        company=user.company,
        role=user.role,
        provider=user.provider,
        email_verified=user.email_verified,
        locale=user.locale,  # type: ignore[arg-type]
        created_at=user.created_at,
    )


def _login_response(user: User) -> LoginResponse:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return LoginResponse(token=token, user=_to_user_dto(user))


async def _find_user_by_email(db: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(User.email == normalize_email(email))
    return (await db.execute(stmt)).scalar_one_or_none()


async def _find_token(
    db: AsyncSession,
    *,
    raw_token: str,
    token_type: str,
) -> UserAuthToken | None:
    stmt = select(UserAuthToken).where(
        UserAuthToken.token_hash == hash_token(raw_token),
        UserAuthToken.token_type == token_type,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


def _is_token_usable(row: UserAuthToken) -> bool:
    now = datetime.now(UTC).replace(tzinfo=None)
    return row.used_at is None and row.expires_at > now


async def _create_auth_token(
    db: AsyncSession,
    *,
    user: User,
    token_type: str,
    ttl_seconds: int,
) -> str:
    token = mint_token(ttl_seconds=ttl_seconds)
    db.add(
        UserAuthToken(
            user_id=user.id,
            token_hash=token.digest,
            token_type=token_type,
            expires_at=token.expires_at,
            email_snapshot=user.email,
        )
    )
    return token.value


async def _mark_token_used(row: UserAuthToken) -> None:
    row.used_at = datetime.now(UTC).replace(tzinfo=None)


def _validate_email_or_400(email: str) -> str:
    normalized = normalize_email(email)
    if not is_valid_email_format(normalized):
        raise _api_error(
            status.HTTP_400_BAD_REQUEST,
            "invalid_email",
            "请输入有效的邮箱地址 / Please enter a valid email",
        )
    return normalized


def _validate_password_or_400(password: str) -> None:
    result = check_user_password_policy(password)
    if not result.ok:
        raise _api_error(
            status.HTTP_400_BAD_REQUEST,
            "weak_password",
            (
                "密码至少 8 位, 且需包含大小写字母和数字 / "
                "Password must contain upper/lower letters and a number"
            ),
        )


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _api_error(status.HTTP_401_UNAUTHORIZED, "missing_token", "Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = verify_user_access_token(token)
    except UserJwtInvalidError as exc:
        raise _api_error(status.HTTP_401_UNAUTHORIZED, "invalid_token", exc.reason) from exc

    user = await db.get(User, payload.sub)
    if user is None:
        raise _api_error(status.HTTP_401_UNAUTHORIZED, "invalid_token", "User not found")
    return user


@router.post("/lookup", response_model=LookupResponse)
async def lookup(
    payload: LookupRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LookupResponse:
    started = asyncio.get_running_loop().time()
    normalized = normalize_email(payload.email)
    if not is_valid_email_format(normalized):
        raise _api_error(
            status.HTTP_400_BAD_REQUEST,
            "invalid_email",
            "请输入有效的邮箱地址 / Please enter a valid email",
        )

    allowed = check_auth_limit(
        "lookup",
        email=normalized,
        ip_address=_client_ip(request),
        capacity=20,
    )
    if not allowed:
        raise _api_error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate_limited",
            "请求过于频繁, 请稍后再试 / Too many attempts",
        )

    user = await _find_user_by_email(db, normalized)
    elapsed = asyncio.get_running_loop().time() - started
    if elapsed < 0.4:
        await asyncio.sleep(0.4 - elapsed)

    if user is None:
        return LookupResponse(next="register", exists=False, has_password=False)
    return LookupResponse(
        next="login",
        exists=True,
        has_password=user.password_hash is not None,
        provider=user.provider,  # type: ignore[arg-type]
        locale_hint=user.locale,  # type: ignore[arg-type]
    )


@router.get("/check-email")
async def check_email(
    email: Annotated[str, Query(min_length=3, max_length=255)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, bool]:
    normalized = normalize_email(email)
    if not is_valid_email_format(normalized):
        return {"exists": False}
    user = await _find_user_by_email(db, normalized)
    return {"exists": user is not None}


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RegisterResponse:
    email = _validate_email_or_400(payload.email)
    if not check_auth_limit("register", email=email, ip_address=_client_ip(request), capacity=10):
        raise _api_error(status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited", "请求过于频繁")

    existing = await _find_user_by_email(db, email)
    if existing is not None:
        raise _api_error(
            status.HTTP_409_CONFLICT,
            "email_exists",
            "该邮箱已注册 / Email already registered",
        )

    user = User(email=email, provider="email", locale=payload.locale)
    db.add(user)
    await db.flush()
    token = await _create_auth_token(
        db,
        user=user,
        token_type="verify_email",
        ttl_seconds=VERIFY_EMAIL_TTL_SECONDS,
    )
    send_verification_email(to=user.email, token=token, locale=payload.locale)
    await db.commit()

    return RegisterResponse(message="Verification email sent", email=user.email)


@router.post("/resend-verification", response_model=OkResponse)
async def resend_verification(
    payload: ResendVerificationRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OkResponse:
    email = _validate_email_or_400(payload.email)
    if not check_auth_limit("resend", email=email, ip_address=_client_ip(request), capacity=3):
        raise _api_error(status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited", "请求过于频繁")

    user = await _find_user_by_email(db, email)
    if user is not None and not user.email_verified:
        token = await _create_auth_token(
            db,
            user=user,
            token_type="verify_email",
            ttl_seconds=VERIFY_EMAIL_TTL_SECONDS,
        )
        send_verification_email(to=user.email, token=token, locale=payload.locale)
        await db.commit()

    return OkResponse(message="If the email exists, a verification email was sent.")


@router.get("/setup-token", response_model=SetupTokenResponse)
async def setup_token_info(
    token: Annotated[str, Query(min_length=8)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SetupTokenResponse:
    for token_type in ("verify_email", "oauth_setup"):
        row = await _find_token(db, raw_token=token, token_type=token_type)
        if row is not None:
            if not _is_token_usable(row):
                raise _api_error(status.HTTP_400_BAD_REQUEST, "invalid_token", "链接已失效或过期")
            user = await db.get(User, row.user_id)
            if user is None:
                raise _api_error(status.HTTP_404_NOT_FOUND, "user_not_found", "User not found")
            return SetupTokenResponse(
                email=user.email,
                provider=user.provider,  # type: ignore[arg-type]
                name=user.name,
                company=user.company,
                requires_password=token_type == "verify_email",
                token_type=token_type,
            )
    raise _api_error(status.HTTP_400_BAD_REQUEST, "invalid_token", "链接无效")


@router.post("/setup", response_model=LoginResponse)
async def setup_account(
    payload: SetupRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoginResponse:
    row: UserAuthToken | None = None
    token_type: str | None = None
    for candidate in ("verify_email", "oauth_setup"):
        row = await _find_token(db, raw_token=payload.token, token_type=candidate)
        if row is not None:
            token_type = candidate
            break
    if row is None or token_type is None or not _is_token_usable(row):
        raise _api_error(status.HTTP_400_BAD_REQUEST, "invalid_token", "链接已失效或过期")

    user = await db.get(User, row.user_id)
    if user is None:
        raise _api_error(status.HTTP_404_NOT_FOUND, "user_not_found", "User not found")
    if payload.email and normalize_email(payload.email) != user.email:
        raise _api_error(status.HTTP_400_BAD_REQUEST, "email_mismatch", "邮箱与验证链接不匹配")

    if token_type == "verify_email":
        if payload.password is None:
            raise _api_error(status.HTTP_400_BAD_REQUEST, "password_required", "请输入密码")
        _validate_password_or_400(payload.password)
        user.password_hash = hash_password(payload.password)

    user.name = payload.name.strip()
    user.company = payload.company.strip()
    user.newsletter_subscribed = payload.newsletter
    user.locale = payload.locale
    user.email_verified = True
    user.last_login_at = datetime.now(UTC).replace(tzinfo=None)
    await _mark_token_used(row)
    send_welcome_email(to=user.email, locale=payload.locale)
    await db.commit()
    await db.refresh(user)
    return _login_response(user)


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoginResponse:
    email = _validate_email_or_400(payload.email)
    if not check_auth_limit("login", email=email, ip_address=_client_ip(request), capacity=10):
        raise _api_error(status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited", "请求过于频繁")

    user = await _find_user_by_email(db, email)
    if user is None or user.password_hash is None:
        raise _api_error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_credentials",
            "用户名或密码不正确 / Invalid credentials",
        )
    if not user.email_verified:
        raise _api_error(status.HTTP_403_FORBIDDEN, "email_not_verified", "请先验证邮箱")
    if not verify_password(payload.password, user.password_hash):
        raise _api_error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_credentials",
            "用户名或密码不正确 / Invalid credentials",
        )
    user.last_login_at = datetime.now(UTC).replace(tzinfo=None)
    await db.commit()
    await db.refresh(user)
    return _login_response(user)


@router.post("/forgot-password", response_model=OkResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OkResponse:
    normalized = normalize_email(payload.email)
    if not is_valid_email_format(normalized):
        raise _api_error(status.HTTP_400_BAD_REQUEST, "invalid_email", "请输入有效邮箱")
    if not check_auth_limit("forgot", email=normalized, ip_address=_client_ip(request), capacity=5):
        raise _api_error(status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited", "请求过于频繁")

    user = await _find_user_by_email(db, normalized)
    if user is not None and user.password_hash is not None:
        token = await _create_auth_token(
            db,
            user=user,
            token_type="password_reset",
            ttl_seconds=PASSWORD_RESET_TTL_SECONDS,
        )
        send_password_reset_email(to=user.email, token=token, locale=payload.locale)
        await db.commit()
    return OkResponse(message="If the email is registered, a reset email was sent.")


@router.post("/forgot", response_model=OkResponse)
async def forgot_alias(
    payload: ForgotPasswordRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OkResponse:
    return await forgot_password(payload, request, db)


@router.post("/reset-password", response_model=OkResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OkResponse:
    _validate_password_or_400(payload.password)
    row = await _find_token(db, raw_token=payload.token, token_type="password_reset")
    if row is None or not _is_token_usable(row):
        raise _api_error(status.HTTP_400_BAD_REQUEST, "invalid_token", "链接已失效或过期")
    user = await db.get(User, row.user_id)
    if user is None:
        raise _api_error(status.HTTP_404_NOT_FOUND, "user_not_found", "User not found")
    user.password_hash = hash_password(payload.password)
    user.email_verified = True
    await _mark_token_used(row)
    await db.commit()
    return OkResponse(message="Password reset successfully")


@router.get("/me", response_model=UserDto)
async def me(current_user: Annotated[User, Depends(get_current_user)]) -> UserDto:
    return _to_user_dto(current_user)


@router.get("/google")
async def google_start() -> RedirectResponse:
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    callback_url = os.environ.get("GOOGLE_CALLBACK_URL") or (
        f"{frontend_base_url()}/api/auth/google/callback"
    )
    state = _make_oauth_state()
    if not client_id or state is None:
        return RedirectResponse(f"{frontend_base_url()}/login?error=oauth_not_configured")

    params = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": callback_url,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "online",
            "prompt": "select_account",
            "state": state,
        }
    )
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@router.get("/google/callback")
async def google_callback(
    db: Annotated[AsyncSession, Depends(get_db)],
    code: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    base = frontend_base_url()
    if error or not code or not _is_valid_oauth_state(state):
        return RedirectResponse(f"{base}/login?error=oauth_failed")
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.environ.get("GOOGLE_CALLBACK_URL") or f"{base}/api/auth/google/callback"
    if not client_id or not client_secret:
        return RedirectResponse(f"{base}/login?error=oauth_not_configured")

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            token_res = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
            )
            token_res.raise_for_status()
            access_token = token_res.json()["access_token"]
            profile_res = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            profile_res.raise_for_status()
            profile = profile_res.json()
    except (httpx.HTTPError, KeyError, TypeError):
        return RedirectResponse(f"{base}/login?error=oauth_failed")

    email = normalize_email(str(profile.get("email", "")))
    if not is_valid_email_format(email):
        return RedirectResponse(f"{base}/login?error=invalid_email")
    google_id = str(profile.get("id", ""))
    name = str(profile.get("name") or "").strip() or None

    user = await _find_user_by_email(db, email)
    is_new = user is None
    if user is None:
        user = User(
            email=email,
            name=name,
            provider="google",
            google_id=google_id or None,
            email_verified=True,
        )
        db.add(user)
        await db.flush()
    else:
        user.google_id = user.google_id or google_id or None
        user.email_verified = True
        if name and not user.name:
            user.name = name

    if is_new or not user.company:
        setup = await _create_auth_token(
            db,
            user=user,
            token_type="oauth_setup",
            ttl_seconds=OAUTH_SETUP_TTL_SECONDS,
        )
        await db.commit()
        return RedirectResponse(f"{base}/setup?token={quote(setup)}&oauth=google")

    user.last_login_at = datetime.now(UTC).replace(tzinfo=None)
    await db.commit()
    await db.refresh(user)
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return RedirectResponse(f"{base}/dashboard?token={quote(token)}")
