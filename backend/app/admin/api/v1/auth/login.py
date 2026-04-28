"""POST /admin/api/v1/auth/login — credential check + cookie set + audit row.

Order of operations is **load-bearing**:

1. Rate-limit check — denied attempts are recorded by the limiter and an
   audit row is written with `failure_code='RATE_LIMITED'` BEFORE we touch
   the DB. This lets us surface 429 without doing a user lookup, and the
   limiter does not need to discriminate between "real user" and "bogus".
2. User lookup — if the email is unknown, we still write an audit row with
   `failure_code='UNKNOWN_EMAIL'` so a brute-force pattern is visible in
   the log. The error returned to the caller is *not* enumerable: the
   frontend gets the same `'invalid_credentials'` reason as a wrong
   password.
3. Suspended check — `status='suspended'` returns `'user_suspended'`
   explicitly so the frontend can render a distinct message; this is *not*
   an enumeration leak because the user knows they were suspended.
4. Password verify — wrong password → `'invalid_credentials'` (matches
   unknown email).
5. Session create — sign access JWT, mint refresh, persist row, set both
   cookies, write success audit, stamp `last_login_at`.

The handler returns a JSON body shaped by `AuthSuccessResponse`. Cookies
are set on the same response (Starlette merges them with the body).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.api.v1.auth._dto import AuthSuccessResponse, LoginRequest
from app.admin.api.v1.auth._shared import (
    access_expires_epoch,
    client_ip,
    to_user_dto,
    user_agent,
    write_auth_cookies,
)
from app.admin.auth.audit import record_login_failure, record_login_success
from app.admin.auth.jwt import sign_access_token
from app.admin.auth.password import verify_password
from app.admin.auth.rate_limiter import check_email_limit, check_ip_limit
from app.admin.auth.session_repo import create_session
from app.db.session import get_db
from app.models.admin import AdminUser

router = APIRouter()


@router.post("/login", response_model=AuthSuccessResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthSuccessResponse:
    email_normalised = payload.email.strip().lower()
    ip = client_ip(request)
    ua = user_agent(request)

    if not check_email_limit(email_normalised) or not check_ip_limit(ip):
        await record_login_failure(
            db,
            email=email_normalised,
            ip_address=ip,
            user_agent=ua,
            failure_code="RATE_LIMITED",
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"reason": "rate_limited"},
        )

    stmt = select(AdminUser).where(AdminUser.email == email_normalised)
    user = (await db.execute(stmt)).scalar_one_or_none()

    if user is None:
        await record_login_failure(
            db,
            email=email_normalised,
            ip_address=ip,
            user_agent=ua,
            failure_code="UNKNOWN_EMAIL",
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"reason": "invalid_credentials"},
        )

    if user.status == "suspended":
        await record_login_failure(
            db,
            email=email_normalised,
            ip_address=ip,
            user_agent=ua,
            failure_code="USER_SUSPENDED",
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"reason": "user_suspended"},
        )

    if not verify_password(payload.password, user.password_hash):
        await record_login_failure(
            db,
            email=email_normalised,
            ip_address=ip,
            user_agent=ua,
            failure_code="WRONG_PASSWORD",
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"reason": "invalid_credentials"},
        )

    # Happy path — mint access token, persist session, set cookies.
    access_token, access_payload = sign_access_token(admin_user_id=user.id)
    _, refresh = await create_session(
        db,
        admin_user_id=user.id,
        access_token_jti=access_payload.jti,
        ip_address=ip,
        user_agent=ua,
    )
    user.last_login_at = datetime.now(UTC).replace(tzinfo=None)
    await record_login_success(
        db,
        email=email_normalised,
        ip_address=ip,
        user_agent=ua,
    )
    await db.commit()
    await db.refresh(user)

    write_auth_cookies(response, access_token=access_token, refresh_token=refresh.token)
    return AuthSuccessResponse(
        user=to_user_dto(user),
        access_expires_at=access_expires_epoch(),
    )
