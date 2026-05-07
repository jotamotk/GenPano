"""Audit emit for admin write operations (ADR-014).

Per ADR-014, every admin write route must emit an `admin_audit_log` row.
Routes call `emit_audit(session, operator, ...)` explicitly inside the
handler. CI test `test_audit_emit_coverage.py` will scan
`app.api.admin` for write methods and ensure each calls `emit_audit`.

Usage:

    @router.post("/users/{user_id}/freeze")
    async def freeze_user(
        user_id: int,
        request: Request,
        operator: AdminUser = Depends(current_admin),
        session: AsyncSession = _DependsDb,
    ) -> dict:
        ... do the freeze ...
        await emit_audit(
            session,
            operator=operator,
            action="freeze_user",
            severity="high",
            resource_type="user",
            resource_id=str(user_id),
            request=request,
        )
        return {"status": "ok"}
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from fastapi import Request
from genpano_models import AdminAuditLog, AdminUser, User
from sqlalchemy.ext.asyncio import AsyncSession

Severity = Literal["low", "med", "high"]


def _new_id() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def emit_audit(
    session: AsyncSession,
    *,
    operator: User | AdminUser,
    action: str,
    severity: Severity = "med",
    resource_type: str | None = None,
    resource_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str | None = None,
    request: Request | None = None,
) -> AdminAuditLog:
    """Insert an admin_audit_log row + commit."""
    ip: str | None = None
    user_agent: str | None = None
    if request is not None:
        if request.client:
            ip = request.client.host
        user_agent = request.headers.get("user-agent")

    row = AdminAuditLog(
        id=_new_id(),
        operator_id=operator.id,
        action=action,
        resource_type=resource_type or "unknown",
        resource_id=resource_id,
        severity=severity,
        before=before,
        after=after,
        ip=ip,
        user_agent=user_agent,
        reason=reason,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


# High-risk action allowlist (PRD addendum §5.7) — CI verifies severity='high'
HIGH_RISK_ACTIONS: frozenset[str] = frozenset(
    {
        "freeze_user",
        "unfreeze_user",
        "soft_delete_user",
        "force_password_reset",
        "brand_merge",
        "brand_delete",
        "brand_approve_with_low_confidence",
        "batch_retry",
        "account_pool_purge",
        "account_disable_all_for_engine",
        "config_change",
        "cookies_import",
        "api_key_revoke",
    }
)
