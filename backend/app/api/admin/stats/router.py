"""Admin stats router (Phase O.1.1 helper) — read-only operator counters.

Mounted at `/api/admin/stats`. All endpoints are GET (no audit emit needed
per ADR-014 — audit is a write-route requirement).

Provides quick operator KPI surface for the Pipeline Overview dashboard
(ADMIN_PRD §4.2.1):
  - GET /overview: total users / projects / open diagnostics / unread alerts
  - GET /audit-summary: 24h audit log volume by severity
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from genpano_models import (
    AdminAuditLog,
    Alert,
    Diagnostic,
    Project,
    User,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.security import current_admin_operator
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Stats"])


@router.get("/overview", response_model=None)
async def stats_overview(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Top-level operator KPI counts for the admin dashboard."""
    counters = {}

    counters["total_users"] = int(
        (await session.execute(select(func.count()).select_from(User))).scalar_one() or 0
    )
    counters["active_projects"] = int(
        (
            await session.execute(
                select(func.count()).select_from(Project).where(Project.deleted_at.is_(None))
            )
        ).scalar_one()
        or 0
    )
    counters["open_diagnostics"] = int(
        (
            await session.execute(
                select(func.count()).select_from(Diagnostic).where(Diagnostic.status == "open")
            )
        ).scalar_one()
        or 0
    )
    counters["unread_operator_alerts"] = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Alert)
                .where(Alert.scope == "operator", Alert.status == "unread")
            )
        ).scalar_one()
        or 0
    )

    return {
        "counters": counters,
        "as_of": datetime.now(UTC).replace(tzinfo=None).isoformat(),
    }


@router.get("/audit-summary", response_model=None)
async def stats_audit_summary(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """24h audit log volume by severity (operator forensics surface)."""
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24)
    stmt = (
        select(AdminAuditLog.severity, func.count(AdminAuditLog.id))
        .where(AdminAuditLog.occurred_at >= cutoff)
        .group_by(AdminAuditLog.severity)
    )
    rows = (await session.execute(stmt)).all()
    by_severity = {row[0]: int(row[1]) for row in rows}
    total = sum(by_severity.values())
    return {
        "window_hours": 24,
        "total": total,
        "by_severity": by_severity,
        "as_of": datetime.now(UTC).replace(tzinfo=None).isoformat(),
    }
