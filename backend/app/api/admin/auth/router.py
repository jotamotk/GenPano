"""Admin operator auth endpoints (login / logout / session-current).

Mounted at ``/api/admin/auth/*``. Replaces the legacy ``admin_console`` Flask
routes:
  POST /api/admin/login    →  POST /api/admin/auth/login
  POST /api/admin/logout   →  POST /api/admin/auth/logout
  GET  /api/admin/session  →  GET  /api/admin/auth/session

Identity model: ``AdminUser`` (separate from product ``User``). Auth carrier
is a Starlette signed-session cookie (``genpano_admin_session``) holding only
``admin_user_id``; everything else is looked up per request.

Audit: every login probe writes to ``admin_login_attempts`` with success +
failure_code. The dashboard/audit-log pages read from the same table.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

import bcrypt
from fastapi import APIRouter, Depends, Request
from genpano_models import AdminLoginAttempt, AdminUser
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import _problem
from app.core.security import _DependsDb
from app.db.session import get_db

router = APIRouter(tags=["Admin · Auth"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: str
    password: str


class AdminInfo(BaseModel):
    id: str
    email: str
    role: str
    status: str


class LoginResponse(BaseModel):
    success: bool
    admin: AdminInfo


class LogoutResponse(BaseModel):
    success: bool


# ---------------------------------------------------------------------------
# Dependency — current_admin
# ---------------------------------------------------------------------------


async def current_admin(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminUser:
    """Resolve the admin operator behind the current request, or raise 401.

    Reads the signed Starlette session cookie set by ``POST /login``,
    pulls ``admin_user_id``, looks up the row, and verifies the account is
    still active. Suspended accounts are rejected with 401 (rather than
    silently letting them through) so frozen operators get logged out
    on next request.
    """
    admin_user_id = request.session.get("admin_user_id")
    if not admin_user_id:
        raise _problem(401, "admin_session_required", "请先登录")

    admin = (
        await db.execute(select(AdminUser).where(AdminUser.id == admin_user_id))
    ).scalar_one_or_none()
    if admin is None or admin.status != "active":
        request.session.pop("admin_user_id", None)
        raise _problem(401, "admin_session_required", "请先登录")
    return admin


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else None


async def _record_login_attempt(
    db: AsyncSession,
    *,
    request: Request,
    email: str,
    success: bool,
    failure_code: str | None,
) -> None:
    """Append one row to ``admin_login_attempts`` regardless of outcome.

    Failures recorded with a coded reason (``UNKNOWN_EMAIL`` / ``WRONG_PASSWORD``
    / ``USER_SUSPENDED``); successes leave failure_code NULL.
    """
    attempt = AdminLoginAttempt(
        email=email,
        ip_address=_client_ip(request),
        success=success,
        failure_code=failure_code,
        user_agent=(request.headers.get("user-agent") or None),
    )
    db.add(attempt)
    await db.commit()


def _verify_password(password: str, password_hash: str | None) -> bool:
    """bcrypt verify — bytes-safe and tolerant of the 72-byte limit."""
    if not password or not password_hash:
        return False
    payload = password.encode("utf-8")
    if len(payload) > 72:
        return False
    try:
        return bcrypt.checkpw(payload, password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = _DependsDb,
) -> LoginResponse:
    """Validate credentials, set the session cookie, return operator identity."""
    email = payload.email.strip().lower()
    admin = (
        await db.execute(select(AdminUser).where(AdminUser.email == email))
    ).scalar_one_or_none()

    if admin is None:
        await _record_login_attempt(
            db, request=request, email=email, success=False, failure_code="UNKNOWN_EMAIL"
        )
        raise _problem(401, "invalid_credentials", "邮箱或密码错误")

    if admin.status != "active":
        await _record_login_attempt(
            db, request=request, email=email, success=False, failure_code="USER_SUSPENDED"
        )
        raise _problem(403, "admin_suspended", "账号已停用")

    if not _verify_password(payload.password, admin.password_hash):
        await _record_login_attempt(
            db, request=request, email=email, success=False, failure_code="WRONG_PASSWORD"
        )
        raise _problem(401, "invalid_credentials", "邮箱或密码错误")

    admin.last_login_at = _now()
    admin.updated_at = _now()
    await db.commit()
    await db.refresh(admin)
    await _record_login_attempt(db, request=request, email=email, success=True, failure_code=None)

    request.session.clear()
    request.session["admin_user_id"] = admin.id
    return LoginResponse(
        success=True,
        admin=AdminInfo(
            id=admin.id,
            email=admin.email,
            role=admin.role,
            status=admin.status,
        ),
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(request: Request) -> LogoutResponse:
    """Clear the session cookie. Idempotent — safe to call when not logged in."""
    request.session.clear()
    return LogoutResponse(success=True)


@router.get("/session", response_model=dict)
async def session_current(
    request: Request,
    db: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Return the current operator (if any) without raising on anonymous probes.

    The legacy admin SPA polls this on page load — it expects 200 with
    ``{"admin": null}`` for anonymous, not 401.
    """
    admin_user_id = request.session.get("admin_user_id")
    if not admin_user_id:
        return {"admin": None}
    admin = (
        await db.execute(select(AdminUser).where(AdminUser.id == admin_user_id))
    ).scalar_one_or_none()
    if admin is None or admin.status != "active":
        request.session.pop("admin_user_id", None)
        return {"admin": None}
    return {
        "admin": {
            "id": admin.id,
            "email": admin.email,
            "role": admin.role,
            "status": admin.status,
        }
    }
