"""Module A user management endpoints — Y1-Y5.

ADMIN_PRD §4.1 Module A endpoint surface for super_admin operators:

  GET    /admin/api/v1/users                              (Y1) list
  GET    /admin/api/v1/users/{user_id}                    (Y2) detail
  POST   /admin/api/v1/users/{user_id}/freeze             (Y3) moderation freeze
  POST   /admin/api/v1/users/{user_id}/force-password-reset (Y4) force reset
  DELETE /admin/api/v1/users/{user_id}                    (Y5) soft delete

Round 9 / decision #30.H corrections (Path B Variant 2):

- `users` has NO `status` column. Frozen state is derived from
  `user_moderation_actions` via the EXISTS subquery formalised in
  ADMIN_PRD §4.1.2. Soft-delete state is `users.deletion_requested_at
  IS NOT NULL` per DATA_MODEL §1.1.

- Y3 freeze writes `user_moderation_actions(action='freeze', ...)`
  + audit. It does NOT touch `users`.

- Y5 soft-delete sets `users.deletion_requested_at = now()` (the only
  column on `users` that admins are permitted to write — J5 fixture
  invariant) AND inserts a `user_moderation_actions(action='soft_delete')`
  audit trail row.

Y6 (login-audit, /admin/users/login-audit) is read-only against a
table that does not yet exist (App-side login_attempts is Session 4a'
work) — deferred per the same decision.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.middleware.rbac import AuditContext, audit_context, require_role
from app.db.session import get_db
from app.models.admin import AdminUser, AdminUserModerationAction
from app.models.user import User
from app.services.admin_audit import record_audit

router = APIRouter(prefix="/admin/api/v1/users", tags=["admin-users"])


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


class UserListItem(BaseModel):
    id: str
    email: str
    name_zh: str | None
    name_en: str | None
    created_at: datetime
    is_frozen: bool
    is_deleted: bool


class UserListResponse(BaseModel):
    items: list[UserListItem]
    total: int


class ModerationEntry(BaseModel):
    id: str
    action: str
    reason: str | None
    expires_at: datetime | None
    operator_id: str
    created_at: datetime


class UserDetailResponse(BaseModel):
    id: str
    email: str
    name_zh: str | None
    name_en: str | None
    email_verified_at: datetime | None
    preferences: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    deletion_requested_at: datetime | None
    is_frozen: bool
    recent_moderation: list[ModerationEntry]


class FreezeRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
    expires_at: datetime | None = None


class ForcePasswordResetRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class SoftDeleteRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class ActionResponse(BaseModel):
    user_id: str
    action: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_frozen_subquery() -> Any:
    """EXISTS subquery for is_frozen, per ADMIN_PRD §4.1.2.

    Active freeze = most recent action='freeze' with NULL OR future
    expires_at. The subquery is correlated by user_id at call site.
    """

    return exists().where(
        AdminUserModerationAction.user_id == User.id,
        AdminUserModerationAction.action == "freeze",
        (AdminUserModerationAction.expires_at.is_(None))
        | (AdminUserModerationAction.expires_at > func.now()),
    )


async def _load_user(db: AsyncSession, user_id: str) -> User:
    stmt = select(User).where(User.id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"reason": "user_not_found"},
        )
    return user


# ---------------------------------------------------------------------------
# Y1 GET / — list
# ---------------------------------------------------------------------------


@router.get("", response_model=UserListResponse)
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[AdminUser, Depends(require_role("super_admin"))],
    limit: int = 50,
    offset: int = 0,
) -> UserListResponse:
    if limit < 1 or limit > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"reason": "invalid_limit"},
        )
    if offset < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"reason": "invalid_offset"},
        )

    is_frozen_expr = _is_frozen_subquery()

    rows_stmt = (
        select(User, is_frozen_expr.label("is_frozen"))
        .order_by(User.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(rows_stmt)).all()

    total = (await db.execute(select(func.count()).select_from(User))).scalar_one()

    items = [
        UserListItem(
            id=user.id,
            email=user.email,
            name_zh=user.name_zh,
            name_en=user.name_en,
            created_at=user.created_at,
            is_frozen=bool(is_frozen),
            is_deleted=user.deletion_requested_at is not None,
        )
        for user, is_frozen in rows
    ]
    return UserListResponse(items=items, total=int(total))


# ---------------------------------------------------------------------------
# Y2 GET /{user_id} — detail
# ---------------------------------------------------------------------------


@router.get("/{user_id}", response_model=UserDetailResponse)
async def get_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[AdminUser, Depends(require_role("super_admin"))],
    user_id: Annotated[str, Path(min_length=1)],
) -> UserDetailResponse:
    user = await _load_user(db, user_id)

    is_frozen_stmt = select(_is_frozen_subquery()).select_from(
        select(User).where(User.id == user_id).subquery()
    )
    is_frozen = bool((await db.execute(is_frozen_stmt)).scalar())

    moderation_stmt = (
        select(AdminUserModerationAction)
        .where(AdminUserModerationAction.user_id == user_id)
        .order_by(desc(AdminUserModerationAction.created_at))
        .limit(20)
    )
    moderation_rows = (await db.execute(moderation_stmt)).scalars().all()
    moderation = [
        ModerationEntry(
            id=row.id,
            action=row.action,
            reason=row.reason,
            expires_at=row.expires_at,
            operator_id=row.operator_id,
            created_at=row.created_at,
        )
        for row in moderation_rows
    ]

    return UserDetailResponse(
        id=user.id,
        email=user.email,
        name_zh=user.name_zh,
        name_en=user.name_en,
        email_verified_at=user.email_verified_at,
        preferences=user.preferences,
        created_at=user.created_at,
        updated_at=user.updated_at,
        deletion_requested_at=user.deletion_requested_at,
        is_frozen=is_frozen,
        recent_moderation=moderation,
    )


# ---------------------------------------------------------------------------
# Y3 POST /{user_id}/freeze — moderation insert (NOT a write to users)
# ---------------------------------------------------------------------------


@router.post("/{user_id}/freeze", response_model=ActionResponse)
async def freeze_user(
    payload: FreezeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_role("super_admin"))],
    ctx: Annotated[AuditContext, Depends(audit_context)],
    user_id: Annotated[str, Path(min_length=1)],
) -> ActionResponse:
    await _load_user(db, user_id)

    moderation = AdminUserModerationAction(
        user_id=user_id,
        operator_id=admin.id,
        action="freeze",
        reason=payload.reason,
        expires_at=payload.expires_at,
    )
    db.add(moderation)
    await db.commit()

    await record_audit(
        operator_id=admin.id,
        action="freeze",
        target_type="user",
        target_id=user_id,
        diff={"expires_at": payload.expires_at.isoformat() if payload.expires_at else None},
        reason=payload.reason,
        ip=ctx.ip,
        ua=ctx.ua,
    )

    return ActionResponse(user_id=user_id, action="freeze")


# ---------------------------------------------------------------------------
# Y4 POST /{user_id}/force-password-reset
# ---------------------------------------------------------------------------


@router.post("/{user_id}/force-password-reset", response_model=ActionResponse)
async def force_password_reset(
    payload: ForcePasswordResetRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_role("super_admin"))],
    ctx: Annotated[AuditContext, Depends(audit_context)],
    user_id: Annotated[str, Path(min_length=1)],
) -> ActionResponse:
    """Trigger a password-reset workflow for an App user.

    The token issuance + Resend email delivery for App users lives in
    Session 4a' (App-side `password_resets` table). Step 3 records the
    moderation row and audit trail; the email pipe joins later without
    changing this call site.
    """

    await _load_user(db, user_id)

    moderation = AdminUserModerationAction(
        user_id=user_id,
        operator_id=admin.id,
        action="force_password_reset",
        reason=payload.reason,
    )
    db.add(moderation)
    await db.commit()

    await record_audit(
        operator_id=admin.id,
        action="force_password_reset",
        target_type="user",
        target_id=user_id,
        reason=payload.reason,
        ip=ctx.ip,
        ua=ctx.ua,
    )

    return ActionResponse(user_id=user_id, action="force_password_reset")


# ---------------------------------------------------------------------------
# Y5 DELETE /{user_id} — soft delete
# ---------------------------------------------------------------------------


@router.delete("/{user_id}", response_model=ActionResponse)
async def soft_delete_user(
    payload: SoftDeleteRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_role("super_admin"))],
    ctx: Annotated[AuditContext, Depends(audit_context)],
    user_id: Annotated[str, Path(min_length=1)],
) -> ActionResponse:
    user = await _load_user(db, user_id)
    if user.deletion_requested_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"reason": "already_deleted"},
        )

    user.deletion_requested_at = datetime.now(UTC).replace(tzinfo=None)
    moderation = AdminUserModerationAction(
        user_id=user_id,
        operator_id=admin.id,
        action="soft_delete",
        reason=payload.reason,
    )
    db.add(moderation)
    await db.commit()

    await record_audit(
        operator_id=admin.id,
        action="soft_delete",
        target_type="user",
        target_id=user_id,
        diff={"deletion_requested_at": user.deletion_requested_at.isoformat()},
        reason=payload.reason,
        ip=ctx.ip,
        ua=ctx.ua,
    )

    return ActionResponse(user_id=user_id, action="soft_delete")
