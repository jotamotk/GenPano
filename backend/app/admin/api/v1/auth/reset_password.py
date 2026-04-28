"""POST /admin/api/v1/auth/reset-password — consume reset token + set password.

Hard rules:
- The reset row must exist, be unused, and not yet expired. Each is a
  distinct failure code so the frontend can render a precise message; this
  is **not** an enumeration leak because the user is presenting a token
  they got via email — they already know the email exists.
- New password must clear `check_password_strength` against the user's
  email as a vocabulary hint.
- Successful reset (a) marks the row used, (b) updates `password_hash` +
  `last_password_at`, (c) clears `force_password_change_at` (the reset
  flow itself is the proof of fresh credential), (d) revokes every active
  session for the user — anyone logged in via the leaked-then-rotated
  password gets booted at next refresh.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.api.v1.auth._dto import OkResponse, ResetPasswordRequest
from app.admin.auth.password import check_password_strength, hash_password
from app.admin.auth.refresh_token import hash_refresh_token
from app.admin.auth.session_repo import revoke_all_sessions_for_user
from app.db.session import get_db
from app.models.admin import AdminPasswordReset, AdminUser

router = APIRouter()


@router.post("/reset-password", response_model=OkResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OkResponse:
    digest = hash_refresh_token(payload.token)

    reset_row = (
        await db.execute(select(AdminPasswordReset).where(AdminPasswordReset.token_hash == digest))
    ).scalar_one_or_none()

    now = datetime.now(UTC).replace(tzinfo=None)

    if reset_row is None or reset_row.used_at is not None or reset_row.expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"reason": "invalid_token"},
        )

    user = (
        await db.execute(select(AdminUser).where(AdminUser.id == reset_row.admin_user_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"reason": "invalid_token"},
        )

    strength = check_password_strength(payload.new_password, [user.email])
    if not strength.ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"reason": strength.reason},
        )

    user.password_hash = hash_password(payload.new_password)
    user.last_password_at = now
    user.force_password_change_at = None
    reset_row.used_at = now
    await revoke_all_sessions_for_user(db, admin_user_id=user.id, now=now)
    await db.commit()

    return OkResponse()
