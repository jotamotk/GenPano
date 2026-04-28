"""POST /admin/api/v1/auth/refresh — refresh-token rotation.

Decision #24.B mandate (single transaction):
- The presented refresh-token is matched against `admin_sessions` by sha256
  hex, and only an active (`revoked_at IS NULL` AND not expired) row is
  acceptable. Any failure → 401 + cookies cleared so the client cleanly
  drops to /admin/login.
- On success: rotate via `session_repo.rotate_session()` which marks the
  old row revoked AND inserts the new row in the same transaction. A
  replayed (already-revoked) refresh token therefore returns 401 even if
  it was valid one second ago.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.api.v1.auth._dto import AuthSuccessResponse
from app.admin.api.v1.auth._shared import (
    access_expires_epoch,
    client_ip,
    to_user_dto,
    user_agent,
    write_auth_cookies,
)
from app.admin.auth.constants import REFRESH_TOKEN_COOKIE
from app.admin.auth.cookies import clear_auth_cookies
from app.admin.auth.jwt import sign_access_token
from app.admin.auth.refresh_token import hash_refresh_token
from app.admin.auth.session_repo import find_active_by_refresh_token, rotate_session
from app.db.session import get_db
from app.models.admin import AdminUser

router = APIRouter()


@router.post("/refresh", response_model=AuthSuccessResponse)
async def refresh(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    refresh_cookie: Annotated[str | None, Cookie(alias=REFRESH_TOKEN_COOKIE)] = None,
) -> AuthSuccessResponse:
    if not refresh_cookie:
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"reason": "no_session"},
        )

    digest = hash_refresh_token(refresh_cookie)
    old = await find_active_by_refresh_token(db, digest)
    if old is None:
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"reason": "invalid_refresh"},
        )

    new_access_token, access_payload = sign_access_token(admin_user_id=old.admin_user_id)
    _, new_refresh = await rotate_session(
        db,
        old=old,
        new_access_token_jti=access_payload.jti,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )

    user = (
        await db.execute(select(AdminUser).where(AdminUser.id == old.admin_user_id))
    ).scalar_one()
    await db.commit()
    await db.refresh(user)

    write_auth_cookies(
        response,
        access_token=new_access_token,
        refresh_token=new_refresh.token,
    )
    return AuthSuccessResponse(
        user=to_user_dto(user),
        access_expires_at=access_expires_epoch(),
    )
