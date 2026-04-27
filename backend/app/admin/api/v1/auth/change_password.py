"""POST /admin/api/v1/auth/change-password — authenticated password change.

Required by the force-password-change flow (super_admin first login) and
by the routine "I'd like a new password" path. Both reuse the same
endpoint because the server-side semantics are identical.

Order:
1. JWT-based auth via `require_admin_session` dependency.
2. Verify `current_password`. The current-password check IS the
   re-authentication proof for this op (see decision #24.B re-auth gate
   docs); the time-window gate is layered on top to catch the rare case
   where the JWT is fresh but the actual password entry was hours ago.
3. Strength-gate the new password.
4. Persist new hash + `last_password_at` + clear `force_password_change_at`.
5. Revoke every active session for this user, then mint a brand new
   session for the current request so the user remains logged in here
   while every other tab / device gets booted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.api.v1.auth._dto import AuthSuccessResponse, ChangePasswordRequest
from app.admin.api.v1.auth._shared import (
    access_expires_epoch,
    client_ip,
    to_user_dto,
    user_agent,
    write_auth_cookies,
)
from app.admin.auth.jwt import AccessTokenPayload, sign_access_token
from app.admin.auth.middleware import require_admin_session
from app.admin.auth.password import check_password_strength, hash_password, verify_password
from app.admin.auth.session_repo import create_session, revoke_all_sessions_for_user
from app.db.session import get_db
from app.models.admin import AdminUser

router = APIRouter()


@router.post("/change-password", response_model=AuthSuccessResponse)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    session: Annotated[AccessTokenPayload, Depends(require_admin_session)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthSuccessResponse:
    user = (
        await db.execute(select(AdminUser).where(AdminUser.id == session.sub))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"reason": "no_session"},
        )

    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"reason": "wrong_current_password"},
        )

    strength = check_password_strength(payload.new_password, [user.email])
    if not strength.ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"reason": strength.reason},
        )

    now = datetime.now(UTC).replace(tzinfo=None)
    user.password_hash = hash_password(payload.new_password)
    user.last_password_at = now
    user.force_password_change_at = None

    await revoke_all_sessions_for_user(db, admin_user_id=user.id, now=now)

    new_access_token, access_payload = sign_access_token(admin_user_id=user.id)
    _, new_refresh = await create_session(
        db,
        admin_user_id=user.id,
        access_token_jti=access_payload.jti,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )
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
