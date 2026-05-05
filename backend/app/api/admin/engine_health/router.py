"""Admin engine health router (Phase O.1.2 — PRD §4.2.2).

Mounted at `/api/admin/engine-health`. Read-only — operator dashboard
surface for the per-engine daily aggregates table.

Endpoints:
- GET /current — latest day's row per engine (today's summary card)
- GET /trends?engine=&days= — N-day series for one engine
- GET /alerts — engines whose latest success_rate is below threshold
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from genpano_models import EngineHealthDaily, User
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.security import current_admin_operator
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Engine Health"])

DEFAULT_LOW_SUCCESS_RATE = 0.80


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@router.get("/current", response_model=None)
async def engine_health_current(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Latest daily row per engine."""
    # Subquery: max(date) per engine
    latest = (
        select(
            EngineHealthDaily.engine,
            func.max(EngineHealthDaily.date).label("max_date"),
        )
        .group_by(EngineHealthDaily.engine)
        .subquery()
    )
    stmt = (
        select(EngineHealthDaily)
        .join(
            latest,
            (EngineHealthDaily.engine == latest.c.engine)
            & (EngineHealthDaily.date == latest.c.max_date),
        )
        .order_by(EngineHealthDaily.engine)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return {
        "as_of": _now().isoformat(),
        "engines": [_row_to_dict(r) for r in rows],
    }


@router.get("/trends", response_model=None)
async def engine_health_trends(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
    engine: str = Query(..., description="Engine name (e.g. chatgpt, doubao, deepseek)"),
    days: int = Query(30, ge=1, le=180),
) -> dict[str, Any]:
    """Per-engine N-day trend (oldest → newest)."""
    cutoff = _now() - timedelta(days=days)
    stmt = (
        select(EngineHealthDaily)
        .where(
            EngineHealthDaily.engine == engine,
            EngineHealthDaily.date >= cutoff,
        )
        .order_by(EngineHealthDaily.date)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    if not rows:
        # Engine name might still be valid; return empty series rather than 404
        return {
            "engine": engine,
            "days": days,
            "series": [],
            "summary": {"avg_success_rate": None, "total_attempts": 0},
        }
    total_attempts = sum(r.total_attempts for r in rows)
    weighted_success = sum((r.success_rate or 0) * r.total_attempts for r in rows)
    return {
        "engine": engine,
        "days": days,
        "series": [_row_to_dict(r) for r in rows],
        "summary": {
            "avg_success_rate": (
                round(weighted_success / total_attempts, 4) if total_attempts else None
            ),
            "total_attempts": total_attempts,
        },
    }


@router.get("/alerts", response_model=None)
async def engine_health_alerts(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
    threshold: float = Query(
        DEFAULT_LOW_SUCCESS_RATE,
        ge=0.0,
        le=1.0,
        description="Engines with latest success_rate below this trigger alerts",
    ),
) -> dict[str, Any]:
    """Engines whose latest day's success_rate is below the threshold.

    Operator triages here when daily ops cron flags low-health engines.
    Threshold default 0.80 matches the Phase N alerting hint.
    """
    latest = (
        select(
            EngineHealthDaily.engine,
            func.max(EngineHealthDaily.date).label("max_date"),
        )
        .group_by(EngineHealthDaily.engine)
        .subquery()
    )
    stmt = (
        select(EngineHealthDaily)
        .join(
            latest,
            (EngineHealthDaily.engine == latest.c.engine)
            & (EngineHealthDaily.date == latest.c.max_date),
        )
        .where(EngineHealthDaily.success_rate < threshold)
        .order_by(desc(EngineHealthDaily.total_attempts))
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return {
        "threshold": threshold,
        "as_of": _now().isoformat(),
        "items": [_row_to_dict(r) for r in rows],
        "total": len(rows),
    }


def _row_to_dict(r: EngineHealthDaily) -> dict[str, Any]:
    return {
        "id": r.id,
        "engine": r.engine,
        "date": r.date.isoformat() if r.date else None,
        "total_attempts": r.total_attempts,
        "success_count": r.success_count,
        "failed_count": r.failed_count,
        "success_rate": r.success_rate,
        "p50_latency_ms": r.p50_latency_ms,
        "p95_latency_ms": r.p95_latency_ms,
        "cookie_status": r.cookie_status,
        "captcha_count": r.captcha_count,
        "ip_blocked_count": r.ip_blocked_count,
        "rate_limited_count": r.rate_limited_count,
        "last_updated": r.last_updated.isoformat() if r.last_updated else None,
    }
