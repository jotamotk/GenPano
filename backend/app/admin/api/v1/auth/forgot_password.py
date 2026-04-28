"""POST /admin/api/v1/auth/forgot-password — issue reset-token + email.

Always returns 202 regardless of whether the email matched a row, so the
endpoint is not a user-enumeration oracle. When the email IS known we
insert an `admin_password_resets` row (purpose='reset', 24h TTL) and
trigger the Resend send. When it is not, we silently no-op.

Suspended users are treated as unknown — refusing a reset for them on a
distinct branch would also leak status. The Admin who suspended them can
restore the account first if a reset is genuinely intended.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.api.v1.auth._dto import ForgotPasswordRequest, OkResponse
from app.admin.auth.email import send_password_reset_email
from app.admin.auth.refresh_token import hash_refresh_token
from app.db.session import get_db
from app.models.admin import AdminPasswordReset, AdminUser

router = APIRouter()

# 24h reset window — matches the master TS implementation.
_RESET_TTL_SECONDS = 24 * 60 * 60
_TOKEN_BYTES = 32


@router.post(
    "/forgot-password",
    response_model=OkResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OkResponse:
    email_normalised = payload.email.strip().lower()

    user = (
        await db.execute(select(AdminUser).where(AdminUser.email == email_normalised))
    ).scalar_one_or_none()

    if user is None or user.status != "active":
        # Silent no-op: do NOT reveal whether the email matched.
        return OkResponse()

    token = secrets.token_urlsafe(_TOKEN_BYTES)
    token_hash = hash_refresh_token(token)
    now = datetime.now(UTC).replace(tzinfo=None)
    expires_at = now + timedelta(seconds=_RESET_TTL_SECONDS)

    db.add(
        AdminPasswordReset(
            admin_user_id=user.id,
            token_hash=token_hash,
            purpose="reset",
            expires_at=expires_at,
        )
    )
    await db.commit()

    send_password_reset_email(to=user.email, reset_token=token, locale=payload.locale)
    return OkResponse()
