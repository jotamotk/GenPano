"""Admin brand submissions router (Phase R.4 — moderation queue).

Mounted at `/api/admin/brand-submissions`. Operators triage user-submitted
brand requests (Phase E user-side endpoint) and approve / reject /
mark-duplicate.

Endpoints:
- GET /                      — list with status / submitter filters
- GET /{id}                  — detail view
- POST /{id}/approve         — approve submission (audit + reviewer fields)
- POST /{id}/reject          — reject (audit + reviewer fields)
- POST /{id}/mark-duplicate  — mark as duplicate of existing brand

Each transition emits emit_audit() with severity='med' and stamps
reviewer_id + reviewed_at on the row.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from genpano_models import BrandSubmission, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.security import current_admin_operator
from app.core.errors import conflict, not_found
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Brand Submissions"])

VALID_STATUS = {"pending", "approved", "rejected", "duplicate"}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _row_to_dict(r: BrandSubmission) -> dict[str, Any]:
    return {
        "id": r.id,
        "user_id": r.user_id,
        "proposed_name": r.proposed_name,
        "proposed_industry_id": r.proposed_industry_id,
        "proposed_aliases": r.proposed_aliases,
        "proposed_official_domains": r.proposed_official_domains,
        "notes": r.notes,
        "source_url": r.source_url,
        "status": r.status,
        "reviewer_id": r.reviewer_id,
        "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        "resulting_brand_id": r.resulting_brand_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("/", response_model=None)
async def list_submissions(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
    status_filter: str | None = Query(None, alias="status"),
    user_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    stmt = select(BrandSubmission).order_by(BrandSubmission.created_at.desc())
    if status_filter:
        stmt = stmt.where(BrandSubmission.status == status_filter)
    if user_id:
        stmt = stmt.where(BrandSubmission.user_id == user_id)
    stmt = stmt.offset(offset).limit(limit)

    rows = list((await session.execute(stmt)).scalars().all())
    return {
        "items": [_row_to_dict(r) for r in rows],
        "limit": limit,
        "offset": offset,
        "returned": len(rows),
    }


@router.get("/{submission_id}", response_model=None)
async def get_submission(
    submission_id: str,
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    row = (
        await session.execute(select(BrandSubmission).where(BrandSubmission.id == submission_id))
    ).scalar_one_or_none()
    if row is None:
        raise not_found("brand submission not found")
    return _row_to_dict(row)


async def _load_pending(
    session: AsyncSession, submission_id: str, target_status: str
) -> BrandSubmission:
    row = (
        await session.execute(select(BrandSubmission).where(BrandSubmission.id == submission_id))
    ).scalar_one_or_none()
    if row is None:
        raise not_found("brand submission not found")
    if row.status != "pending":
        raise conflict(
            "invalid_state",
            f"submission already {row.status}; cannot {target_status}",
        )
    return row


@router.post("/{submission_id}/approve", response_model=None)
async def approve_submission(
    submission_id: str,
    request: Request,
    operator: Annotated[User, Depends(current_admin_operator)],
    payload: dict[str, Any] | None = None,
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Approve submission. Optional `resulting_brand_id` if it maps to an
    existing brand (otherwise the brand is to be created downstream)."""
    row = await _load_pending(session, submission_id, "approve")
    before = {"status": row.status}
    row.status = "approved"
    row.reviewer_id = operator.id
    row.reviewed_at = _now()
    if payload and "resulting_brand_id" in payload:
        row.resulting_brand_id = payload["resulting_brand_id"]
    await session.commit()
    await session.refresh(row)

    await emit_audit(
        session,
        operator=operator,
        action="brand_submission_approved",
        severity="med",
        resource_type="brand_submission",
        resource_id=submission_id,
        before=before,
        after={
            "status": "approved",
            "reviewer_id": operator.id,
            "resulting_brand_id": row.resulting_brand_id,
        },
        request=request,
    )
    return _row_to_dict(row)


@router.post("/{submission_id}/reject", response_model=None)
async def reject_submission(
    submission_id: str,
    request: Request,
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Reject submission (e.g. spam / outside scope)."""
    row = await _load_pending(session, submission_id, "reject")
    before = {"status": row.status}
    row.status = "rejected"
    row.reviewer_id = operator.id
    row.reviewed_at = _now()
    await session.commit()
    await session.refresh(row)

    await emit_audit(
        session,
        operator=operator,
        action="brand_submission_rejected",
        severity="med",
        resource_type="brand_submission",
        resource_id=submission_id,
        before=before,
        after={"status": "rejected", "reviewer_id": operator.id},
        request=request,
    )
    return _row_to_dict(row)


@router.post("/{submission_id}/mark-duplicate", response_model=None)
async def mark_duplicate(
    submission_id: str,
    request: Request,
    operator: Annotated[User, Depends(current_admin_operator)],
    payload: dict[str, Any] | None = None,
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Mark as duplicate; optional resulting_brand_id points to canonical row."""
    row = await _load_pending(session, submission_id, "mark_duplicate")
    before = {"status": row.status}
    row.status = "duplicate"
    row.reviewer_id = operator.id
    row.reviewed_at = _now()
    if payload and "resulting_brand_id" in payload:
        row.resulting_brand_id = payload["resulting_brand_id"]
    await session.commit()
    await session.refresh(row)

    await emit_audit(
        session,
        operator=operator,
        action="brand_submission_duplicate",
        severity="med",
        resource_type="brand_submission",
        resource_id=submission_id,
        before=before,
        after={
            "status": "duplicate",
            "reviewer_id": operator.id,
            "resulting_brand_id": row.resulting_brand_id,
        },
        request=request,
    )
    return _row_to_dict(row)
