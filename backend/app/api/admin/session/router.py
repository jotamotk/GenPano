"""Admin session router (Phase R.4) — operator identity + dashboard top-bar meta.

Mounted at `/api/admin/session`. Read-only — surfaces:
- GET /me — current operator identity + role + last_login + recent activity
- GET /dashboard-meta — top-bar counters used by ALL admin pages (unread
  operator alerts / open diagnostics across all projects / today's
  operator audit entries / pending high-risk audits)

The auth-related routes (login / logout / OAuth) stay on the user-side
auth router; admins use the same session token. This sub-router is the
operator's "who am I + what should I look at first" surface.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from genpano_models import AdminAuditLog, Alert, Diagnostic, User
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import HIGH_RISK_ACTIONS
from app.admin.security import current_admin_operator
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Session"])


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@router.get("/me", response_model=None)
async def admin_me(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Current operator identity + recent activity.

    Used by admin dashboard top bar to render avatar / display name +
    "last 24h: N audited mutations".
    """
    cutoff = _now() - timedelta(hours=24)
    own_audit_24h = (
        await session.execute(
            select(func.count(AdminAuditLog.id)).where(
                AdminAuditLog.operator_id == operator.id,
                AdminAuditLog.occurred_at >= cutoff,
            )
        )
    ).scalar_one()

    last_audit = (
        await session.execute(
            select(AdminAuditLog)
            .where(AdminAuditLog.operator_id == operator.id)
            .order_by(AdminAuditLog.occurred_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    return {
        "id": operator.id,
        "email": operator.email,
        "name": operator.name,
        "role": operator.role,
        "locale": operator.locale,
        "last_login_at": (operator.last_login_at.isoformat() if operator.last_login_at else None),
        "audit_actions_24h": int(own_audit_24h or 0),
        "last_audit_at": (
            last_audit.occurred_at.isoformat() if last_audit and last_audit.occurred_at else None
        ),
        "as_of": _now().isoformat(),
    }


@router.get("/dashboard-meta", response_model=None)
async def admin_dashboard_meta(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Top-bar counters used by every admin page for badges + alerts.

    All counts are operator-global (not scoped to current operator) since
    these are the inbox shared across the operator team:
      - unread_operator_alerts: alerts.scope='operator' AND status='unread'
      - open_p0_p1_diagnostics: diagnostics.severity in (P0,P1) AND status='open'
      - audits_24h_total: total admin_audit_log writes in last 24h
      - high_risk_audits_24h: high-risk action audits in last 24h
    """
    cutoff = _now() - timedelta(hours=24)

    unread_alerts = (
        await session.execute(
            select(func.count(Alert.id)).where(
                Alert.scope == "operator",
                Alert.status == "unread",
            )
        )
    ).scalar_one()

    open_high_severity = (
        await session.execute(
            select(func.count(Diagnostic.id)).where(
                Diagnostic.status == "open",
                Diagnostic.severity.in_(["P0", "P1"]),
            )
        )
    ).scalar_one()

    audits_24h = (
        await session.execute(
            select(
                func.count(AdminAuditLog.id),
                func.sum(
                    case(
                        (
                            AdminAuditLog.action.in_(list(HIGH_RISK_ACTIONS)),
                            1,
                        ),
                        else_=0,
                    )
                ),
            ).where(AdminAuditLog.occurred_at >= cutoff)
        )
    ).one()
    audits_total = int(audits_24h[0] or 0)
    high_risk_count = int(audits_24h[1] or 0)

    return {
        "as_of": _now().isoformat(),
        "counters": {
            "unread_operator_alerts": int(unread_alerts or 0),
            "open_p0_p1_diagnostics": int(open_high_severity or 0),
            "audits_24h_total": audits_total,
            "high_risk_audits_24h": high_risk_count,
        },
    }
