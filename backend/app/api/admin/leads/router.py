"""Admin commercial leads router (Phase O.3.3 — PRD §4.4.5).

Mounted at `/api/admin/leads`. Operator surface for the BD pipeline:
- GET /api/admin/leads — list with status / source filter
- GET /api/admin/leads/{id} — detail
- PATCH /api/admin/leads/{id} — transition status (new → contacted →
  closed / ignored). Audit emit severity=med.

State machine:
  new ──contact→ contacted ──close→ closed
   │                              ↑
   └────────ignore→ ignored ──────┘
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from genpano_models import CommercialLead, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.security import current_admin_operator
from app.core.errors import not_found, validation_error
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Leads"])

VALID_STATUS = {"new", "contacted", "closed", "ignored"}


def _row_to_dict(r: CommercialLead) -> dict[str, Any]:
    return {
        "id": r.id,
        "user_id": r.user_id,
        "project_id": r.project_id,
        "source": r.source,
        "context": r.context,
        "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("/", response_model=None)
async def list_leads(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
    status_filter: str | None = Query(None, alias="status"),
    source: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    stmt = select(CommercialLead).order_by(CommercialLead.created_at.desc())
    if status_filter:
        stmt = stmt.where(CommercialLead.status == status_filter)
    if source:
        stmt = stmt.where(CommercialLead.source == source)
    stmt = stmt.offset(offset).limit(limit)

    rows = list((await session.execute(stmt)).scalars().all())
    return {
        "items": [_row_to_dict(r) for r in rows],
        "limit": limit,
        "offset": offset,
        "returned": len(rows),
    }


@router.get("/{lead_id}", response_model=None)
async def get_lead(
    lead_id: str,
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    row = (
        await session.execute(select(CommercialLead).where(CommercialLead.id == lead_id))
    ).scalar_one_or_none()
    if row is None:
        raise not_found("lead not found")
    return _row_to_dict(row)


@router.patch("/{lead_id}", response_model=None)
async def update_lead_status(
    lead_id: str,
    request: Request,
    operator: Annotated[User, Depends(current_admin_operator)],
    payload: dict[str, Any],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Transition a lead's status. State must be a valid status enum value."""
    new_status = payload.get("status")
    if new_status not in VALID_STATUS:
        raise validation_error("status", f"must be one of {sorted(VALID_STATUS)}")

    row = (
        await session.execute(select(CommercialLead).where(CommercialLead.id == lead_id))
    ).scalar_one_or_none()
    if row is None:
        raise not_found("lead not found")

    before = {"status": row.status}
    row.status = new_status
    await session.commit()

    await emit_audit(
        session,
        operator=operator,
        action="lead_status_update",
        severity="med",
        resource_type="commercial_lead",
        resource_id=lead_id,
        before=before,
        after={"status": new_status},
        request=request,
    )

    return _row_to_dict(row)
