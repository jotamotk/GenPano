"""Admin KG relation candidate queue (Phase K.5 review).

Mounted at `/api/admin/kg-candidates`. Operators triage relation edges
inferred by `app.kg.relation_extractor` (regex / LLM versions both feed
the same `kg_relation_candidates` table) and approve / reject / mark
merged into `kg_brand_relations` / `kg_product_relations` (Phase K.3).

Endpoints:
- GET /                         — paginated queue with filters
- GET /counts                   — aggregate by status / entity_kind / type
- GET /{candidate_id}           — detail view (full evidence)
- POST /{id}/approve            — accept; later worker promotes it to
                                  the canonical relation table
- POST /{id}/reject              — discard
- POST /{id}/mark-merged        — operator manually merged it via the
                                  KG admin (sets merged_into_relation_id)

All writes audit emit (severity='med' / action=kg_candidate_*).
Pending → terminal status transitions are one-way: 409 if status != 'pending'.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from genpano_models import KgRelationCandidate, User
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.security import current_admin_operator
from app.core.errors import conflict, not_found, validation_error
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · KG Candidates"])

VALID_STATUS = {"pending", "approved", "rejected", "merged"}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _row_to_dict(c: KgRelationCandidate) -> dict[str, Any]:
    return {
        "id": c.id,
        "entity_kind": c.entity_kind,
        "a_id": c.a_id,
        "b_id": c.b_id,
        "type": c.type,
        "confidence": c.confidence,
        "evidence": c.evidence,
        "status": c.status,
        "llm_model": c.llm_model,
        "reviewer_id": c.reviewed_by,
        "reviewed_at": c.reviewed_at.isoformat() if c.reviewed_at else None,
        "merged_into_relation_id": c.merged_into_relation_id,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.get("/", response_model=None)
async def list_candidates(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
    status_filter: str | None = Query(None, alias="status"),
    entity_kind: str | None = Query(None),
    type_filter: str | None = Query(None, alias="type"),
    min_confidence: float | None = Query(None, ge=0.0, le=1.0),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    stmt = select(KgRelationCandidate).order_by(KgRelationCandidate.created_at.desc())
    if status_filter:
        if status_filter not in VALID_STATUS:
            raise validation_error("status", f"must be one of {sorted(VALID_STATUS)}")
        stmt = stmt.where(KgRelationCandidate.status == status_filter)
    if entity_kind:
        stmt = stmt.where(KgRelationCandidate.entity_kind == entity_kind)
    if type_filter:
        stmt = stmt.where(KgRelationCandidate.type == type_filter)
    if min_confidence is not None:
        stmt = stmt.where(KgRelationCandidate.confidence >= min_confidence)
    stmt = stmt.offset(offset).limit(limit)

    rows = list((await session.execute(stmt)).scalars().all())
    return {
        "items": [_row_to_dict(c) for c in rows],
        "limit": limit,
        "offset": offset,
        "returned": len(rows),
    }


@router.get("/counts", response_model=None)
async def candidate_counts(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Aggregate counters for the candidate queue."""
    by_status_stmt = select(
        KgRelationCandidate.status, func.count(KgRelationCandidate.id)
    ).group_by(KgRelationCandidate.status)
    by_status = {r[0]: int(r[1] or 0) for r in (await session.execute(by_status_stmt)).all()}

    by_type_stmt = (
        select(KgRelationCandidate.type, func.count(KgRelationCandidate.id))
        .where(KgRelationCandidate.status == "pending")
        .group_by(KgRelationCandidate.type)
    )
    pending_by_type = {r[0]: int(r[1] or 0) for r in (await session.execute(by_type_stmt)).all()}

    by_kind_stmt = (
        select(KgRelationCandidate.entity_kind, func.count(KgRelationCandidate.id))
        .where(KgRelationCandidate.status == "pending")
        .group_by(KgRelationCandidate.entity_kind)
    )
    pending_by_kind = {r[0]: int(r[1] or 0) for r in (await session.execute(by_kind_stmt)).all()}

    return {
        "as_of": _now().isoformat(),
        "by_status": by_status,
        "pending_by_type": pending_by_type,
        "pending_by_entity_kind": pending_by_kind,
    }


@router.get("/{candidate_id}", response_model=None)
async def get_candidate(
    candidate_id: str,
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    row = (
        await session.execute(
            select(KgRelationCandidate).where(KgRelationCandidate.id == candidate_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise not_found("candidate not found")
    return _row_to_dict(row)


async def _load_pending(
    session: AsyncSession, candidate_id: str, target: str
) -> KgRelationCandidate:
    row = (
        await session.execute(
            select(KgRelationCandidate).where(KgRelationCandidate.id == candidate_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise not_found("candidate not found")
    if row.status != "pending":
        raise conflict(
            "invalid_state",
            f"candidate already {row.status}; cannot {target}",
        )
    return row


@router.post("/{candidate_id}/approve", response_model=None)
async def approve_candidate(
    candidate_id: str,
    request: Request,
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Approve candidate. A downstream worker promotes it into the
    canonical kg_brand_relations / kg_product_relations table.
    """
    row = await _load_pending(session, candidate_id, "approve")
    before = {"status": row.status}
    row.status = "approved"
    row.reviewed_by = operator.id
    row.reviewed_at = _now()
    await session.commit()
    await session.refresh(row)

    await emit_audit(
        session,
        operator=operator,
        action="kg_candidate_approved",
        severity="med",
        resource_type="kg_relation_candidate",
        resource_id=candidate_id,
        before=before,
        after={"status": "approved", "reviewer_id": operator.id},
        request=request,
    )
    return _row_to_dict(row)


@router.post("/{candidate_id}/reject", response_model=None)
async def reject_candidate(
    candidate_id: str,
    request: Request,
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Discard a hallucinated / wrong / spammy candidate."""
    row = await _load_pending(session, candidate_id, "reject")
    before = {"status": row.status}
    row.status = "rejected"
    row.reviewed_by = operator.id
    row.reviewed_at = _now()
    await session.commit()
    await session.refresh(row)

    await emit_audit(
        session,
        operator=operator,
        action="kg_candidate_rejected",
        severity="med",
        resource_type="kg_relation_candidate",
        resource_id=candidate_id,
        before=before,
        after={"status": "rejected", "reviewer_id": operator.id},
        request=request,
    )
    return _row_to_dict(row)


@router.post("/{candidate_id}/mark-merged", response_model=None)
async def mark_merged(
    candidate_id: str,
    request: Request,
    operator: Annotated[User, Depends(current_admin_operator)],
    payload: dict[str, Any],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Mark candidate as merged into a canonical relation row.

    Requires `relation_id` (id of the kg_brand_relations /
    kg_product_relations row the candidate was merged into).
    """
    relation_id = payload.get("relation_id")
    if not relation_id:
        raise validation_error("relation_id", "required")
    row = await _load_pending(session, candidate_id, "mark_merged")

    before = {"status": row.status}
    row.status = "merged"
    row.merged_into_relation_id = relation_id
    row.reviewed_by = operator.id
    row.reviewed_at = _now()
    await session.commit()
    await session.refresh(row)

    await emit_audit(
        session,
        operator=operator,
        action="kg_candidate_merged",
        severity="med",
        resource_type="kg_relation_candidate",
        resource_id=candidate_id,
        before=before,
        after={
            "status": "merged",
            "reviewer_id": operator.id,
            "merged_into_relation_id": relation_id,
        },
        request=request,
    )
    return _row_to_dict(row)
