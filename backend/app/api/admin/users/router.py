"""Admin users router (Phase R.4 sub-router migration).

Provides operator-side user moderation surface.
- GET /api/admin/users — list with filters
- GET /api/admin/users/{user_id} — detail (no PII beyond what admin needs)
- POST /api/admin/users/{user_id}/force-password-reset — HIGH-risk audit
  per ADR-014 + HIGH_RISK_ACTIONS allowlist (PRD §5.7).

freeze_user / unfreeze_user / soft_delete_user need a `frozen_at`/
`deleted_at` column migration on `users` — deferred to a follow-up PR
where schema changes are bundled with admin operations.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from genpano_models import User, UserAuthToken
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.security import current_admin_operator
from app.core.errors import not_found
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Users"])

PASSWORD_RESET_TOKEN_TTL_HOURS = 1


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _user_to_dict(u: User) -> dict[str, Any]:
    return {
        "id": u.id,
        "email": u.email,
        "name": u.name,
        "company": u.company,
        "role": u.role,
        "provider": u.provider,
        "email_verified": u.email_verified,
        "locale": u.locale,
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


@router.get("/", response_model=None)
async def list_users(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
    q: str | None = Query(None, description="Search email or name (case-insensitive)"),
    role: str | None = Query(None),
    provider: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    stmt = select(User).order_by(User.created_at.desc())
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                User.email.ilike(like),
                User.name.ilike(like),
            )
        )
    if role:
        stmt = stmt.where(User.role == role)
    if provider:
        stmt = stmt.where(User.provider == provider)
    stmt = stmt.offset(offset).limit(limit)

    rows = list((await session.execute(stmt)).scalars().all())
    return {
        "items": [_user_to_dict(u) for u in rows],
        "limit": limit,
        "offset": offset,
        "returned": len(rows),
    }


@router.get("/{user_id}", response_model=None)
async def get_user(
    user_id: str,
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    row = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if row is None:
        raise not_found("user not found")
    return _user_to_dict(row)


@router.post("/{user_id}/force-password-reset", response_model=None)
async def force_password_reset(
    user_id: str,
    request: Request,
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Issue a one-time password-reset token + emit HIGH severity audit.

    Returns the token (sent to the user's email in production; admin sees
    it once for OOB delivery in dev/preview). The token's hash is stored;
    plaintext is never persisted.

    Audit action='force_password_reset' is in HIGH_RISK_ACTIONS — Phase
    O.2.2 audit dashboard will surface this distinctly.
    """
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise not_found("user not found")

    token_plaintext = secrets.token_urlsafe(32)
    token_row = UserAuthToken(
        id=_new_uuid(),
        user_id=user.id,
        token_hash=_hash_token(token_plaintext),
        token_type="password_reset",
        expires_at=_now() + timedelta(hours=PASSWORD_RESET_TOKEN_TTL_HOURS),
        email_snapshot=user.email,
    )
    session.add(token_row)
    await session.commit()

    await emit_audit(
        session,
        operator=operator,
        action="force_password_reset",
        severity="high",
        resource_type="user",
        resource_id=user.id,
        after={"token_id": token_row.id},
        request=request,
        reason="admin-initiated password reset",
    )

    return {
        "user_id": user.id,
        "token_id": token_row.id,
        "token": token_plaintext,
        "expires_at": token_row.expires_at.isoformat(),
        "ttl_hours": PASSWORD_RESET_TOKEN_TTL_HOURS,
    }
