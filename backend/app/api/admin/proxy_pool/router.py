"""Admin proxy pool router (Phase O.1.4 — PRD §4.2.4).

Mounted at `/api/admin/proxy-pool`. Read-only health surface for the
collection proxy pool. Reads `proxy_health_daily` aggregates.

Endpoints:
- GET /current — latest day's row per proxy_id
- GET /trends?proxy_id=&days= — N-day series for one proxy
- GET /alerts?threshold=0.85 — proxies whose latest success_rate is below
  threshold OR is_blocked=True
- GET /blocked — proxies currently flagged blocked
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from genpano_models import ProxyHealthDaily, User
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.security import current_admin_operator
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Proxy Pool"])

DEFAULT_LOW_SUCCESS_RATE = 0.85


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _row_to_dict(r: ProxyHealthDaily) -> dict[str, Any]:
    return {
        "id": r.id,
        "proxy_id": r.proxy_id,
        "date": r.date.isoformat() if r.date else None,
        "total_requests": r.total_requests,
        "success_count": r.success_count,
        "success_rate": r.success_rate,
        "avg_latency_ms": r.avg_latency_ms,
        "is_blocked": r.is_blocked,
        "notes": r.notes,
    }


@router.get("/current", response_model=None)
async def proxy_current(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Latest daily row per proxy_id."""
    latest = (
        select(
            ProxyHealthDaily.proxy_id,
            func.max(ProxyHealthDaily.date).label("max_date"),
        )
        .group_by(ProxyHealthDaily.proxy_id)
        .subquery()
    )
    stmt = (
        select(ProxyHealthDaily)
        .join(
            latest,
            (ProxyHealthDaily.proxy_id == latest.c.proxy_id)
            & (ProxyHealthDaily.date == latest.c.max_date),
        )
        .order_by(ProxyHealthDaily.proxy_id)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return {
        "as_of": _now().isoformat(),
        "proxies": [_row_to_dict(r) for r in rows],
    }


@router.get("/trends", response_model=None)
async def proxy_trends(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
    proxy_id: int = Query(..., ge=1),
    days: int = Query(30, ge=1, le=180),
) -> dict[str, Any]:
    cutoff = _now() - timedelta(days=days)
    stmt = (
        select(ProxyHealthDaily)
        .where(
            ProxyHealthDaily.proxy_id == proxy_id,
            ProxyHealthDaily.date >= cutoff,
        )
        .order_by(ProxyHealthDaily.date)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    if not rows:
        return {
            "proxy_id": proxy_id,
            "days": days,
            "series": [],
            "summary": {"avg_success_rate": None, "total_requests": 0},
        }
    total = sum(r.total_requests for r in rows)
    weighted = sum((r.success_rate or 0) * r.total_requests for r in rows)
    return {
        "proxy_id": proxy_id,
        "days": days,
        "series": [_row_to_dict(r) for r in rows],
        "summary": {
            "avg_success_rate": (round(weighted / total, 4) if total else None),
            "total_requests": total,
        },
    }


@router.get("/alerts", response_model=None)
async def proxy_alerts(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
    threshold: float = Query(DEFAULT_LOW_SUCCESS_RATE, ge=0.0, le=1.0),
) -> dict[str, Any]:
    """Latest-day proxies that are blocked OR below threshold."""
    latest = (
        select(
            ProxyHealthDaily.proxy_id,
            func.max(ProxyHealthDaily.date).label("max_date"),
        )
        .group_by(ProxyHealthDaily.proxy_id)
        .subquery()
    )
    stmt = (
        select(ProxyHealthDaily)
        .join(
            latest,
            (ProxyHealthDaily.proxy_id == latest.c.proxy_id)
            & (ProxyHealthDaily.date == latest.c.max_date),
        )
        .where(
            or_(
                ProxyHealthDaily.is_blocked.is_(True),
                ProxyHealthDaily.success_rate < threshold,
            )
        )
        .order_by(desc(ProxyHealthDaily.total_requests))
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return {
        "threshold": threshold,
        "as_of": _now().isoformat(),
        "items": [_row_to_dict(r) for r in rows],
        "total": len(rows),
    }


@router.get("/blocked", response_model=None)
async def proxy_blocked_list(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Latest-day proxies currently flagged blocked."""
    latest = (
        select(
            ProxyHealthDaily.proxy_id,
            func.max(ProxyHealthDaily.date).label("max_date"),
        )
        .group_by(ProxyHealthDaily.proxy_id)
        .subquery()
    )
    stmt = (
        select(ProxyHealthDaily)
        .join(
            latest,
            (ProxyHealthDaily.proxy_id == latest.c.proxy_id)
            & (ProxyHealthDaily.date == latest.c.max_date),
        )
        .where(ProxyHealthDaily.is_blocked.is_(True))
        .order_by(ProxyHealthDaily.proxy_id)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return {
        "as_of": _now().isoformat(),
        "items": [_row_to_dict(r) for r in rows],
        "total": len(rows),
    }
