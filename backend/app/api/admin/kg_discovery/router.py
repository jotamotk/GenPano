"""Admin KG discovery logs router (Phase O.1.5 — PRD §4.3.6).

Mounted at `/api/admin/kg-discovery`. Read-only — KG quality monitor.
- GET /list — paginated rows (filter by source / hallucination_flag /
  llm_model)
- GET /summary — last-N-day quality KPIs: hallucination rate, avg
  confidence, source mix, LLM model mix
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from genpano_models import DiscoveryLog, User
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.security import current_admin_operator
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · KG Discovery"])


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _row_to_dict(r: DiscoveryLog) -> dict[str, Any]:
    return {
        "id": r.id,
        "source": r.source,
        "candidate_id": r.candidate_id,
        "llm_model": r.llm_model,
        "confidence": r.confidence,
        "hallucination_flag": r.hallucination_flag,
        "hallucination_evidence": r.hallucination_evidence,
        "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
    }


@router.get("/list", response_model=None)
async def list_discovery_logs(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
    source: str | None = Query(None),
    hallucination_only: bool = Query(False),
    llm_model: str | None = Query(None),
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    cutoff = _now() - timedelta(days=days)
    stmt = (
        select(DiscoveryLog)
        .where(DiscoveryLog.occurred_at >= cutoff)
        .order_by(DiscoveryLog.occurred_at.desc())
    )
    if source:
        stmt = stmt.where(DiscoveryLog.source == source)
    if hallucination_only:
        stmt = stmt.where(DiscoveryLog.hallucination_flag.is_(True))
    if llm_model:
        stmt = stmt.where(DiscoveryLog.llm_model == llm_model)
    stmt = stmt.offset(offset).limit(limit)

    rows = list((await session.execute(stmt)).scalars().all())
    return {
        "days": days,
        "items": [_row_to_dict(r) for r in rows],
        "limit": limit,
        "offset": offset,
        "returned": len(rows),
    }


@router.get("/summary", response_model=None)
async def discovery_summary(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
    days: int = Query(7, ge=1, le=90),
) -> dict[str, Any]:
    """Quality KPI: total / hallucination_rate / avg_confidence over the window."""
    cutoff = _now() - timedelta(days=days)

    # Aggregate totals
    agg_stmt = select(
        func.count(DiscoveryLog.id),
        func.sum(case((DiscoveryLog.hallucination_flag.is_(True), 1), else_=0)),
        func.avg(DiscoveryLog.confidence),
    ).where(DiscoveryLog.occurred_at >= cutoff)
    total, hallucinations, avg_conf = (await session.execute(agg_stmt)).one()
    total = int(total or 0)
    hallucinations = int(hallucinations or 0)

    # Source mix
    src_stmt = (
        select(DiscoveryLog.source, func.count(DiscoveryLog.id))
        .where(DiscoveryLog.occurred_at >= cutoff)
        .group_by(DiscoveryLog.source)
        .order_by(func.count(DiscoveryLog.id).desc())
    )
    by_source = {row[0]: int(row[1]) for row in (await session.execute(src_stmt)).all()}

    # LLM model mix
    model_stmt = (
        select(DiscoveryLog.llm_model, func.count(DiscoveryLog.id))
        .where(
            DiscoveryLog.occurred_at >= cutoff,
            DiscoveryLog.llm_model.isnot(None),
        )
        .group_by(DiscoveryLog.llm_model)
        .order_by(func.count(DiscoveryLog.id).desc())
    )
    by_model = {row[0]: int(row[1]) for row in (await session.execute(model_stmt)).all()}

    return {
        "days": days,
        "total_events": total,
        "hallucination_count": hallucinations,
        "hallucination_rate": (round(hallucinations / total, 4) if total else 0.0),
        "avg_confidence": round(float(avg_conf), 4) if avg_conf is not None else None,
        "by_source": by_source,
        "by_model": by_model,
    }
