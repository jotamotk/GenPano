"""Admin users router (Phase 3 — admin_console migration).

Mounted at ``/api/admin/users`` (cookie-based ``current_admin`` auth).

Endpoints:
- GET  /                              — paginated user list with filters
- GET  /actions                       — recent moderation actions across users
- GET  /login-audit                   — recent end-user login attempts (currently
                                        always empty — no user-side audit table
                                        exists; behavior preserved from
                                        admin_console for shape compatibility)
- GET  /{user_id}                     — single user detail + projects + activity
- GET  /{user_id}/actions             — moderation history for one user
- POST /{user_id}/freeze              — freeze account (HIGH-risk audit)
- POST /{user_id}/unfreeze            — unfreeze account (HIGH-risk audit)
- POST /{user_id}/force-password-reset — issue one-time reset token (HIGH-risk)

Response shapes preserve the admin_console contract (rows/total/page/per_page)
so the existing admin.html SPA can switch its fetch base from
``/admin/api`` (Flask) to ``/api/admin`` (FastAPI) without JS changes.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from genpano_models import (
    AdminAuditLog,
    AdminUser,
    Project,
    User,
    UserAuthToken,
    UserModerationAction,
)
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.api.admin.auth.router import current_admin
from app.core.errors import not_found, validation_error
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Users"])

PASSWORD_RESET_TOKEN_TTL_HOURS = 1


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _initials_for(name: str | None, email: str | None) -> str:
    src = (name or "").replace(".", " ").strip()
    if src:
        parts = src.split()[:2]
        out = "".join(p[:1] for p in parts).upper()
        if out:
            return out[:2]
    if email:
        return email[:2].upper()
    return "U"


def _activity_level(last_login_at: datetime | None) -> str:
    if last_login_at is None:
        return "dormant"
    delta = _now() - last_login_at
    if delta <= timedelta(days=7):
        return "hot"
    if delta <= timedelta(days=30):
        return "warm"
    if delta <= timedelta(days=90):
        return "cold"
    return "dormant"


def _user_status(latest_action: str | None, expires_at: datetime | None) -> str:
    if latest_action == "freeze" and (expires_at is None or expires_at > _now()):
        return "frozen"
    return "active"


def _user_to_row(
    u: User,
    *,
    project_count: int = 0,
    latest_mod: UserModerationAction | None = None,
) -> dict[str, Any]:
    """Wire-shape row matching the legacy admin_console `_normalize_user_row`."""
    latest_action = latest_mod.action if latest_mod else None
    latest_reason = latest_mod.reason if latest_mod else None
    latest_expires = latest_mod.expires_at if latest_mod else None
    latest_created = latest_mod.created_at if latest_mod else None
    status = _user_status(latest_action, latest_expires)
    activity_level = _activity_level(u.last_login_at)
    name = u.name or (u.email.split("@", 1)[0] if u.email else u.id)
    return {
        "id": u.id,
        "email": u.email or "",
        "name": name,
        "company": u.company,
        "initials": _initials_for(u.name, u.email),
        "status": status,
        "industry": None,
        "project_count": project_count,
        "projects": project_count,
        "last_login_at": _isoformat(u.last_login_at),
        "last_active_at": None,
        "created_at": _isoformat(u.created_at),
        "updated_at": _isoformat(u.updated_at),
        "deletion_requested_at": None,
        "activity_level": activity_level,
        "login_count_30d": 0,
        "query_count_30d": 0,
        "provider": u.provider or "email",
        "locale": u.locale or "zh-CN",
        "email_verified": bool(u.email_verified),
        "moderation": {
            "is_frozen": status == "frozen",
            "latest_action": latest_action,
            "reason": latest_reason,
            "expires_at": _isoformat(latest_expires),
            "created_at": _isoformat(latest_created),
        },
    }


async def _project_counts(session: AsyncSession, user_ids: list[str]) -> dict[str, int]:
    if not user_ids:
        return {}
    stmt = (
        select(Project.user_id, func.count(Project.id))
        .where(Project.user_id.in_(user_ids))
        .group_by(Project.user_id)
    )
    rows = (await session.execute(stmt)).all()
    return {uid: int(cnt or 0) for uid, cnt in rows}


async def _latest_moderation_for_users(
    session: AsyncSession, user_ids: list[str]
) -> dict[str, UserModerationAction]:
    """Return the most recent freeze/unfreeze action per user_id."""
    if not user_ids:
        return {}
    stmt = (
        select(UserModerationAction)
        .where(
            UserModerationAction.user_id.in_(user_ids),
            UserModerationAction.action.in_(("freeze", "unfreeze")),
        )
        .order_by(UserModerationAction.user_id, desc(UserModerationAction.created_at))
    )
    rows = list((await session.execute(stmt)).scalars().all())
    out: dict[str, UserModerationAction] = {}
    for row in rows:
        if row.user_id not in out:
            out[row.user_id] = row
    return out


async def _serialize_audit_action(session: AsyncSession, row: AdminAuditLog) -> dict[str, Any]:
    """Resolve operator email by trying admin_users first, then users."""
    operator_email: str | None = None
    operator_role: str | None = None
    admin = (
        await session.execute(select(AdminUser).where(AdminUser.id == row.operator_id))
    ).scalar_one_or_none()
    if admin is not None:
        operator_email = admin.email
        operator_role = admin.role
    else:
        u = (
            await session.execute(select(User).where(User.id == row.operator_id))
        ).scalar_one_or_none()
        if u is not None:
            operator_email = u.email
            operator_role = u.role
    return {
        "id": row.id,
        "operator_id": row.operator_id,
        "operator_email": operator_email,
        "operator_role": operator_role,
        "operator": operator_email or row.operator_id or "system",
        "action": row.action,
        "target_type": row.resource_type,
        "target_id": row.resource_id,
        "diff_json": {"before": row.before, "after": row.after}
        if row.before or row.after
        else None,
        "reason": row.reason,
        "ip": row.ip,
        "ua": row.user_agent,
        "created_at": _isoformat(row.occurred_at),
        "source": "admin_audit_log",
    }


async def _serialize_moderation_action(
    session: AsyncSession, row: UserModerationAction
) -> dict[str, Any]:
    operator_email: str | None = None
    operator_role: str | None = None
    if row.operator_id:
        admin = (
            await session.execute(select(AdminUser).where(AdminUser.id == row.operator_id))
        ).scalar_one_or_none()
        if admin is not None:
            operator_email = admin.email
            operator_role = admin.role
        else:
            u = (
                await session.execute(select(User).where(User.id == row.operator_id))
            ).scalar_one_or_none()
            if u is not None:
                operator_email = u.email
                operator_role = u.role
    return {
        "id": row.id,
        "operator_id": row.operator_id,
        "operator_email": operator_email,
        "operator_role": operator_role,
        "operator": operator_email or row.operator_id or "system",
        "action": row.action,
        "target_type": "user",
        "target_id": row.user_id,
        "diff_json": None,
        "reason": row.reason,
        "ip": None,
        "ua": None,
        "created_at": _isoformat(row.created_at),
        "source": "user_moderation_actions",
    }


async def _list_user_actions(
    session: AsyncSession,
    *,
    user_id: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    """Read admin_audit_log first, fallback to user_moderation_actions if empty.

    Mirrors the legacy admin_console `_fetch_user_actions` shape so the
    admin.html SPA can switch backends without UI changes.
    """
    audit_stmt = select(AdminAuditLog).where(AdminAuditLog.resource_type == "user")
    audit_count = select(func.count(AdminAuditLog.id)).where(AdminAuditLog.resource_type == "user")
    if user_id:
        audit_stmt = audit_stmt.where(AdminAuditLog.resource_id == user_id)
        audit_count = audit_count.where(AdminAuditLog.resource_id == user_id)
    audit_stmt = audit_stmt.order_by(desc(AdminAuditLog.occurred_at)).limit(limit).offset(offset)
    audit_rows = list((await session.execute(audit_stmt)).scalars().all())
    audit_total = int(((await session.execute(audit_count)).scalar()) or 0)

    if audit_rows or audit_total:
        rows = [await _serialize_audit_action(session, r) for r in audit_rows]
        return rows, audit_total

    mod_stmt = select(UserModerationAction)
    mod_count = select(func.count(UserModerationAction.id))
    if user_id:
        mod_stmt = mod_stmt.where(UserModerationAction.user_id == user_id)
        mod_count = mod_count.where(UserModerationAction.user_id == user_id)
    mod_stmt = mod_stmt.order_by(desc(UserModerationAction.created_at)).limit(limit).offset(offset)
    mod_rows = list((await session.execute(mod_stmt)).scalars().all())
    mod_total = int(((await session.execute(mod_count)).scalar()) or 0)
    rows = [await _serialize_moderation_action(session, r) for r in mod_rows]
    return rows, mod_total


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/", response_model=None)
async def list_users(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    limit: int | None = Query(None, ge=1, le=100),
    offset: int | None = Query(None, ge=0),
    q: str | None = Query(None),
    status: str | None = Query(None),
    role: str | None = Query(None),
    activity: str | None = Query(None),
    sort: str | None = Query(None),
) -> dict[str, Any]:
    """Paginated user list. Wire-shape matches admin_console (rows/total/page/per_page)."""
    if limit is not None:
        per_page = limit
    if offset is not None:
        page = (offset // per_page) + 1
    page_offset = (page - 1) * per_page

    base_stmt = select(User)
    count_stmt = select(func.count(User.id))
    if q:
        like = f"%{q}%"
        cond = or_(
            User.email.ilike(like),
            User.name.ilike(like),
            User.company.ilike(like),
        )
        base_stmt = base_stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    if role:
        base_stmt = base_stmt.where(User.role == role)
        count_stmt = count_stmt.where(User.role == role)

    sort_key = sort or "created_at_desc"
    direction_desc = True
    if sort_key.endswith("_asc"):
        direction_desc = False
        sort_key = sort_key[:-4]
    elif sort_key.endswith("_desc"):
        sort_key = sort_key[:-5]
    sort_field: Any = (
        User.last_login_at if sort_key == "last_login_at" else User.created_at
    )
    base_stmt = base_stmt.order_by(
        desc(sort_field) if direction_desc else sort_field, User.id.asc()
    )

    total = int(((await session.execute(count_stmt)).scalar()) or 0)
    base_stmt = base_stmt.limit(per_page).offset(page_offset)
    users_rows = list((await session.execute(base_stmt)).scalars().all())
    user_ids = [u.id for u in users_rows]
    counts = await _project_counts(session, user_ids)
    latest_mods = await _latest_moderation_for_users(session, user_ids)

    rows = [
        _user_to_row(
            u,
            project_count=counts.get(u.id, 0),
            latest_mod=latest_mods.get(u.id),
        )
        for u in users_rows
    ]
    if status:
        rows = [r for r in rows if r["status"] == status]
    if activity:
        rows = [r for r in rows if r["activity_level"] == activity]

    return {
        "rows": rows,
        "total": total,
        "page": page,
        "per_page": per_page,
        "notes": [],
    }


@router.get("/actions", response_model=None)
async def list_user_actions(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Recent moderation / audit actions across all users (latest first)."""
    rows, total = await _list_user_actions(session, user_id=None, limit=limit, offset=offset)
    return {"rows": rows, "total": total, "limit": limit, "offset": offset}


@router.get("/login-audit", response_model=None)
async def list_user_login_audit(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user_id: str | None = Query(None),
    ip: str | None = Query(None),
) -> dict[str, Any]:
    """Recent end-user login attempts.

    No user-side login audit table exists in the current schema (admin_console
    historically probed for ``user_login_audit`` / ``user_login_attempts`` and
    fell through to an empty list). Shape preserved so the SPA tab renders
    its empty state cleanly until a future phase introduces persistence.
    """
    return {
        "rows": [],
        "total": 0,
        "available": False,
        "message": "No user login audit table is present yet.",
        "limit": limit,
        "offset": offset,
    }


@router.get("/{user_id}", response_model=None)
async def get_user(
    user_id: str,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """User detail + projects + activity + moderation + recent admin actions."""
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise not_found("user_not_found")

    counts = await _project_counts(session, [user.id])
    latest_mods = await _latest_moderation_for_users(session, [user.id])
    row = _user_to_row(
        user,
        project_count=counts.get(user.id, 0),
        latest_mod=latest_mods.get(user.id),
    )

    project_stmt = (
        select(Project)
        .where(Project.user_id == user.id)
        .order_by(desc(Project.created_at), Project.id.asc())
        .limit(100)
    )
    projects_rows = list((await session.execute(project_stmt)).scalars().all())
    projects = [
        {
            "id": p.id,
            "name": p.name,
            "status": "active" if p.is_active else "inactive",
            "description": None,
            "industry_id": str(p.industry_id) if p.industry_id is not None else None,
            "primary_brand_id": str(p.primary_brand_id) if p.primary_brand_id is not None else None,
            "competitor_brand_ids": None,
            "preferences": None,
            "created_at": _isoformat(p.created_at),
            "updated_at": _isoformat(p.updated_at),
            "primary_brand_name": None,
        }
        for p in projects_rows
    ]

    actions, _ = await _list_user_actions(session, user_id=user.id, limit=10, offset=0)

    return {
        "user": row,
        "projects": projects,
        "activity": {
            "level": row["activity_level"],
            "last_login_at": row["last_login_at"],
            "last_active_at": row["last_active_at"],
            "login_count_30d": row["login_count_30d"],
            "query_count_30d": row["query_count_30d"],
        },
        "moderation": row["moderation"],
        "recent_admin_actions": actions,
        "notes": [],
    }


@router.get("/{user_id}/actions", response_model=None)
async def list_one_user_actions(
    user_id: str,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Moderation history for one user (does not 404 on unknown user — just empty)."""
    rows, total = await _list_user_actions(session, user_id=user_id, limit=limit, offset=offset)
    return {"rows": rows, "total": total, "limit": limit, "offset": offset}


async def _load_user_for_moderation(session: AsyncSession, user_id: str) -> tuple[User, str]:
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise not_found("user_not_found")
    latest_mods = await _latest_moderation_for_users(session, [user.id])
    latest = latest_mods.get(user.id)
    before_status = _user_status(
        latest.action if latest else None,
        latest.expires_at if latest else None,
    )
    return user, before_status


async def _read_reason(request: Request) -> str:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    reason = (payload.get("reason") or "").strip()
    if not reason:
        raise validation_error("reason", "required")
    return reason


@router.post("/{user_id}/freeze", response_model=None)
async def freeze_user(
    user_id: str,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Freeze a user account. HIGH severity audit + user_moderation_actions row."""
    reason = await _read_reason(request)
    user, before_status = await _load_user_for_moderation(session, user_id)

    mod_row = UserModerationAction(
        id=_new_uuid(),
        user_id=user.id,
        operator_id=operator.id,
        action="freeze",
        reason=reason,
    )
    session.add(mod_row)
    await session.commit()
    await session.refresh(mod_row)

    await emit_audit(
        session,
        operator=operator,
        action="freeze_user",
        severity="high",
        resource_type="user",
        resource_id=user.id,
        before={"status": before_status},
        after={"status": "frozen", "moderation_action_id": mod_row.id},
        request=request,
        reason=reason,
    )
    return {"success": True, "user_id": user.id, "status": "frozen"}


@router.post("/{user_id}/unfreeze", response_model=None)
async def unfreeze_user(
    user_id: str,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Unfreeze a user account. HIGH severity audit + user_moderation_actions row."""
    reason = await _read_reason(request)
    user, before_status = await _load_user_for_moderation(session, user_id)

    mod_row = UserModerationAction(
        id=_new_uuid(),
        user_id=user.id,
        operator_id=operator.id,
        action="unfreeze",
        reason=reason,
    )
    session.add(mod_row)
    await session.commit()
    await session.refresh(mod_row)

    await emit_audit(
        session,
        operator=operator,
        action="unfreeze_user",
        severity="high",
        resource_type="user",
        resource_id=user.id,
        before={"status": before_status},
        after={"status": "active", "moderation_action_id": mod_row.id},
        request=request,
        reason=reason,
    )
    return {"success": True, "user_id": user.id, "status": "active"}


@router.post("/{user_id}/force-password-reset", response_model=None)
async def force_password_reset(
    user_id: str,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Issue a one-time password-reset token + emit HIGH severity audit.

    Returns the token (sent to the user's email in production; admin sees
    it once for OOB delivery in dev/preview). The token's hash is stored;
    plaintext is never persisted.
    """
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise not_found("user_not_found")

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
