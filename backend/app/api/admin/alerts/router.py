"""Admin alerts router (Phase O.3.1) — operator-scope alerts CRUD.

Mounted at `/api/admin/alerts`. Per ADR-013, alerts.scope='operator' is
the operator subset; admin views differ from the user-scope view in
`app/api/v1/alerts/router.py`.

Per ADR-014, every write endpoint emits `admin_audit_log`. The Phase O.2
CI gate (`tests/test_audit_emit_coverage.py`) enforces this.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from genpano_models import Alert, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.security import current_admin_operator
from app.core.errors import not_found, validation_error
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Alerts"])


@router.get("/", response_model=None)
async def list_operator_alerts(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
    status_filter: str | None = Query(None, alias="status"),
    severity: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    """List operator-scope alerts (ADR-013)."""
    stmt = (
        select(Alert)
        .where(Alert.scope == "operator")
        .order_by(Alert.triggered_at.desc())
        .limit(limit)
    )
    if status_filter:
        stmt = stmt.where(Alert.status == status_filter)
    if severity:
        stmt = stmt.where(Alert.severity == severity)
    rows = list((await session.execute(stmt)).scalars().all())
    items = [
        {
            "id": r.id,
            "source": r.source,
            "source_ref_id": r.source_ref_id,
            "severity": r.severity,
            "title": r.title,
            "body": r.body,
            "status": r.status,
            "triggered_at": r.triggered_at.isoformat() if r.triggered_at else None,
            "read_at": r.read_at.isoformat() if r.read_at else None,
        }
        for r in rows
    ]
    return {"items": items, "total": len(items)}


@router.patch("/{alert_id}", response_model=None)
async def update_operator_alert(
    alert_id: str,
    request: Request,
    operator: Annotated[User, Depends(current_admin_operator)],
    payload: dict[str, Any],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Update alert status (acknowledged / ignored / resolved)."""
    new_status = payload.get("status")
    if new_status not in {"read", "acknowledged", "ignored", "resolved"}:
        raise validation_error("status", "must be read|acknowledged|ignored|resolved")

    row = (
        await session.execute(
            select(Alert).where(Alert.id == alert_id, Alert.scope == "operator")
        )
    ).scalar_one_or_none()
    if row is None:
        raise not_found("alert not found")

    before = {"status": row.status}
    row.status = new_status
    await session.commit()
    await session.refresh(row)

    await emit_audit(
        session,
        operator=operator,
        action="alert_update",
        severity="med",
        resource_type="alert",
        resource_id=alert_id,
        before=before,
        after={"status": new_status},
        request=request,
    )

    return {"id": row.id, "status": row.status}


@router.post("/mark-all-read", response_model=None, status_code=status.HTTP_200_OK)
async def mark_all_operator_alerts_read(
    request: Request,
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, int]:
    """Bulk mark unread operator alerts as read."""
    rows = list(
        (
            await session.execute(
                select(Alert).where(
                    Alert.scope == "operator", Alert.status == "unread"
                )
            )
        )
        .scalars()
        .all()
    )
    for r in rows:
        r.status = "read"
    await session.commit()

    await emit_audit(
        session,
        operator=operator,
        action="alerts_bulk_read",
        severity="low",
        resource_type="alert",
        resource_id=None,
        after={"updated_count": len(rows)},
        request=request,
    )

    return {"updated": len(rows)}
