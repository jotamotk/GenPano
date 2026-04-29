"""Module C KG admin endpoints — Y24-Y27 (Option Z scope, 决策 #30.J).

ADMIN_PRD §4.3 Module C surface for super_admin operators, A1' Step 4
limited to the admin-side 3-table footprint already in Step 1 baseline:
alias_conflicts / brand_submissions / kg_review_queue.

  GET    /admin/api/v1/kg/alias-conflicts                       (Y24) list
  POST   /admin/api/v1/kg/alias-conflicts/{conflict_id}/resolve (Y25) resolve
  GET    /admin/api/v1/kg/submissions                           (Y26) inbox
  POST   /admin/api/v1/kg/submissions/{submission_id}/approve   (Y27.1)
  POST   /admin/api/v1/kg/submissions/{submission_id}/reject    (Y27.2)

KG main-table CRUD (kg_industries / kg_categories / kg_brands /
kg_products / kg_brand_relations / kg_product_relations /
kg_mined_relations) is owned by Session 1.5' per 决策 #30.J + §0.5
transfer row T9.

Round 9 / 决策 #30.H Path B Variant 2 invariant — Y25 must validate the
chosen resolved_to_id ∈ alias_conflicts.candidate_ids. Picking an id
outside the stored N-候ates is a programmer / spoof error, not a UX one,
and is rejected with 422 before any UPDATE.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import asc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.middleware.rbac import AuditContext, audit_context, require_role
from app.db.session import get_db
from app.models.admin import AdminUser, AliasConflict, BrandSubmission
from app.services.admin_audit import record_audit

router = APIRouter(prefix="/admin/api/v1/kg", tags=["admin-kg"])

SLA_HOURS = 24


# ---------------------------------------------------------------------------
# DTOs — alias conflicts (Y24 / Y25)
# ---------------------------------------------------------------------------


class AliasConflictItem(BaseModel):
    id: str
    alias_value: str
    language: str
    candidate_ids: list[str]
    candidate_count: int
    is_resolved: bool
    resolved_to_id: str | None
    resolved_admin_id: str | None
    resolved_at: datetime | None


class AliasConflictListResponse(BaseModel):
    items: list[AliasConflictItem]
    total: int


class ResolveAliasRequest(BaseModel):
    resolved_to_id: str = Field(min_length=1, max_length=36)


class ResolveAliasResponse(BaseModel):
    conflict_id: str
    resolved_to_id: str


# ---------------------------------------------------------------------------
# DTOs — brand submissions (Y26 / Y27)
# ---------------------------------------------------------------------------


class BrandSubmissionItem(BaseModel):
    id: str
    submitter_user_id: str | None
    brand_name_zh: str | None
    brand_name_en: str | None
    aliases: list[str] | None
    trust_score: float | None
    status: str
    sla_started_at: datetime
    sla_overdue: bool
    hours_since_submission: int
    resolved_at: datetime | None
    resolved_admin_id: str | None


class BrandSubmissionListResponse(BaseModel):
    items: list[BrandSubmissionItem]
    total: int


class ApproveSubmissionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class RejectSubmissionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class SubmissionActionResponse(BaseModel):
    submission_id: str
    action: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_naive_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _load_alias_conflict(db: AsyncSession, conflict_id: str) -> AliasConflict:
    stmt = select(AliasConflict).where(AliasConflict.id == conflict_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"reason": "alias_conflict_not_found"},
        )
    return row


async def _load_submission(db: AsyncSession, submission_id: str) -> BrandSubmission:
    stmt = select(BrandSubmission).where(BrandSubmission.id == submission_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"reason": "submission_not_found"},
        )
    return row


# ---------------------------------------------------------------------------
# Y24 GET /alias-conflicts — list with derived status filter
# ---------------------------------------------------------------------------


@router.get("/alias-conflicts", response_model=AliasConflictListResponse)
async def list_alias_conflicts(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[AdminUser, Depends(require_role("super_admin"))],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: int = 50,
    offset: int = 0,
) -> AliasConflictListResponse:
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
    if status_filter is not None and status_filter not in {"pending", "resolved"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"reason": "invalid_status_filter"},
        )

    stmt = select(AliasConflict)
    if status_filter == "pending":
        stmt = stmt.where(AliasConflict.resolved_to_id.is_(None))
    elif status_filter == "resolved":
        stmt = stmt.where(AliasConflict.resolved_to_id.is_not(None))

    rows_stmt = stmt.order_by(asc(AliasConflict.id)).limit(limit).offset(offset)
    rows = (await db.execute(rows_stmt)).scalars().all()

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    items = [
        AliasConflictItem(
            id=row.id,
            alias_value=row.alias_value,
            language=row.language,
            candidate_ids=list(row.candidate_ids or []),
            candidate_count=len(row.candidate_ids or []),
            is_resolved=row.resolved_to_id is not None,
            resolved_to_id=row.resolved_to_id,
            resolved_admin_id=row.resolved_admin_id,
            resolved_at=row.resolved_at,
        )
        for row in rows
    ]
    return AliasConflictListResponse(items=items, total=int(total))


# ---------------------------------------------------------------------------
# Y25 POST /alias-conflicts/{conflict_id}/resolve — N-候选 selection
# ---------------------------------------------------------------------------


@router.post("/alias-conflicts/{conflict_id}/resolve", response_model=ResolveAliasResponse)
async def resolve_alias_conflict(
    payload: ResolveAliasRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_role("super_admin"))],
    ctx: Annotated[AuditContext, Depends(audit_context)],
    conflict_id: Annotated[str, Path(min_length=1)],
) -> ResolveAliasResponse:
    conflict = await _load_alias_conflict(db, conflict_id)

    if conflict.resolved_to_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"reason": "already_resolved"},
        )

    candidates = list(conflict.candidate_ids or [])
    if payload.resolved_to_id not in candidates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"reason": "resolved_to_id_not_in_candidates"},
        )

    now = _utc_naive_now()
    conflict.resolved_to_id = payload.resolved_to_id
    conflict.resolved_admin_id = admin.id
    conflict.resolved_at = now
    await db.commit()

    await record_audit(
        operator_id=admin.id,
        action="alias_resolve",
        target_type="alias_conflict",
        target_id=conflict_id,
        diff={
            "resolved_to_id": payload.resolved_to_id,
            "candidate_ids": candidates,
        },
        ip=ctx.ip,
        ua=ctx.ua,
    )

    return ResolveAliasResponse(
        conflict_id=conflict_id,
        resolved_to_id=payload.resolved_to_id,
    )


# ---------------------------------------------------------------------------
# Y26 GET /submissions — inbox with 24h SLA highlight
# ---------------------------------------------------------------------------


@router.get("/submissions", response_model=BrandSubmissionListResponse)
async def list_brand_submissions(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[AdminUser, Depends(require_role("super_admin"))],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    sla_overdue: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> BrandSubmissionListResponse:
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
    if status_filter is not None and status_filter not in {
        "pending",
        "approved",
        "rejected",
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"reason": "invalid_status_filter"},
        )

    now = _utc_naive_now()
    sla_cutoff = now - timedelta(hours=SLA_HOURS)

    stmt = select(BrandSubmission)
    if status_filter is not None:
        stmt = stmt.where(BrandSubmission.status == status_filter)
    if sla_overdue is True:
        stmt = stmt.where(
            BrandSubmission.status == "pending",
            BrandSubmission.sla_started_at < sla_cutoff,
        )
    elif sla_overdue is False:
        stmt = stmt.where(
            (BrandSubmission.status != "pending") | (BrandSubmission.sla_started_at >= sla_cutoff)
        )

    rows_stmt = stmt.order_by(asc(BrandSubmission.sla_started_at)).limit(limit).offset(offset)
    rows = (await db.execute(rows_stmt)).scalars().all()

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    items = []
    for row in rows:
        elapsed = now - row.sla_started_at
        hours = max(int(elapsed.total_seconds() // 3600), 0)
        is_overdue = row.status == "pending" and row.sla_started_at < sla_cutoff
        items.append(
            BrandSubmissionItem(
                id=row.id,
                submitter_user_id=row.submitter_user_id,
                brand_name_zh=row.brand_name_zh,
                brand_name_en=row.brand_name_en,
                aliases=list(row.aliases) if row.aliases else None,
                trust_score=float(row.trust_score) if row.trust_score is not None else None,
                status=row.status,
                sla_started_at=row.sla_started_at,
                sla_overdue=is_overdue,
                hours_since_submission=hours,
                resolved_at=row.resolved_at,
                resolved_admin_id=row.resolved_admin_id,
            )
        )

    return BrandSubmissionListResponse(items=items, total=int(total))


# ---------------------------------------------------------------------------
# Y27.1 POST /submissions/{submission_id}/approve — pending → approved
# ---------------------------------------------------------------------------


@router.post(
    "/submissions/{submission_id}/approve",
    response_model=SubmissionActionResponse,
)
async def approve_submission(
    payload: ApproveSubmissionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_role("super_admin"))],
    ctx: Annotated[AuditContext, Depends(audit_context)],
    submission_id: Annotated[str, Path(min_length=1)],
) -> SubmissionActionResponse:
    submission = await _load_submission(db, submission_id)
    if submission.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"reason": "not_pending", "current_status": submission.status},
        )

    submission.status = "approved"
    submission.resolved_admin_id = admin.id
    submission.resolved_at = _utc_naive_now()
    await db.commit()

    await record_audit(
        operator_id=admin.id,
        action="submission_approve",
        target_type="brand_submission",
        target_id=submission_id,
        diff={"from": "pending", "to": "approved"},
        reason=payload.reason,
        ip=ctx.ip,
        ua=ctx.ua,
    )

    return SubmissionActionResponse(submission_id=submission_id, action="approve")


# ---------------------------------------------------------------------------
# Y27.2 POST /submissions/{submission_id}/reject — pending → rejected
# ---------------------------------------------------------------------------


@router.post(
    "/submissions/{submission_id}/reject",
    response_model=SubmissionActionResponse,
)
async def reject_submission(
    payload: RejectSubmissionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_role("super_admin"))],
    ctx: Annotated[AuditContext, Depends(audit_context)],
    submission_id: Annotated[str, Path(min_length=1)],
) -> SubmissionActionResponse:
    submission = await _load_submission(db, submission_id)
    if submission.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"reason": "not_pending", "current_status": submission.status},
        )

    submission.status = "rejected"
    submission.resolved_admin_id = admin.id
    submission.resolved_at = _utc_naive_now()
    await db.commit()

    await record_audit(
        operator_id=admin.id,
        action="submission_reject",
        target_type="brand_submission",
        target_id=submission_id,
        diff={"from": "pending", "to": "rejected"},
        reason=payload.reason,
        ip=ctx.ip,
        ua=ctx.ua,
    )

    return SubmissionActionResponse(submission_id=submission_id, action="reject")
