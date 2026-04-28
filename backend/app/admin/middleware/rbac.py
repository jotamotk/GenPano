"""Admin RBAC + audit context dependencies.

Two FastAPI helpers that compose with every privileged endpoint:

  require_role(role)   — returns the loaded AdminUser when their role
                         matches; otherwise records `access_denied` to
                         the audit log and raises 403.
  audit_context()      — returns an `AuditContext` carrying operator id,
                         IP, and UA so the handler can pass them through
                         to `record_audit()` without re-deriving them.

Built on top of `require_admin_session` (decision #24 Step S1) so
JWT verification happens exactly once per request.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.api.v1.auth._shared import client_ip, user_agent
from app.admin.auth.jwt import AccessTokenPayload
from app.admin.auth.middleware import require_admin_session
from app.db.session import get_db
from app.models.admin import AdminUser
from app.services.admin_audit import record_audit


@dataclass(frozen=True)
class AuditContext:
    """Per-request audit envelope carried as a FastAPI Depends value."""

    operator_id: str
    ip: str | None
    ua: str | None


def audit_context(
    request: Request,
    payload: Annotated[AccessTokenPayload, Depends(require_admin_session)],
) -> AuditContext:
    return AuditContext(
        operator_id=payload.sub,
        ip=client_ip(request),
        ua=user_agent(request),
    )


def require_role(
    role: str,
) -> Callable[..., Coroutine[None, None, AdminUser]]:
    """Build a dependency that returns the admin user iff role matches.

    On role mismatch the dependency writes an `access_denied` audit row
    (so attempts to reach a privileged endpoint surface in the log) and
    raises 403 with reason='forbidden'. The same dependency also covers
    the "user was deleted between login and now" edge: if the AdminUser
    row is gone, the access token is treated as invalid (401, not 403).
    """

    async def _dependency(
        payload: Annotated[AccessTokenPayload, Depends(require_admin_session)],
        ctx: Annotated[AuditContext, Depends(audit_context)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> AdminUser:
        stmt = select(AdminUser).where(AdminUser.id == payload.sub)
        admin_user = (await db.execute(stmt)).scalar_one_or_none()
        if admin_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"reason": "no_session"},
            )
        if admin_user.role != role:
            await record_audit(
                operator_id=ctx.operator_id,
                action="access_denied",
                target_type="admin_endpoint",
                target_id=None,
                reason=f"required_role={role}, actual_role={admin_user.role}",
                ip=ctx.ip,
                ua=ctx.ua,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"reason": "forbidden"},
            )
        return admin_user

    return _dependency


__all__ = ["AuditContext", "audit_context", "require_role"]
