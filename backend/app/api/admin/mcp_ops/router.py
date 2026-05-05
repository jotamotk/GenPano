"""Admin MCP operations router (Phase O.2.3) — usage + ops surface.

Mounted at `/api/admin/mcp-ops`. PRD §4.4.6:
- GET /summary — last-24h call volume by tool + error rate
- GET /top-users — top API keys by call count
- GET /errors — recent error rows for forensics

All read-only. Future write endpoints (force-revoke key, rate-limit
override) will emit_audit and live alongside.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from genpano_models import McpCallLog, User, UserApiKey
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.security import current_admin_operator
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · MCP Ops"])


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@router.get("/summary", response_model=None)
async def mcp_ops_summary(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
    hours: int = Query(24, ge=1, le=720),
) -> dict[str, Any]:
    """Call volume + error rate by tool over the last `hours` hours."""
    cutoff = _now() - timedelta(hours=hours)
    stmt = (
        select(
            McpCallLog.tool,
            func.count(McpCallLog.id).label("calls"),
            func.sum(case((McpCallLog.status != "ok", 1), else_=0)).label("errors"),
            func.avg(McpCallLog.latency_ms).label("avg_latency_ms"),
            func.sum(McpCallLog.cost_estimate_cny).label("cost"),
        )
        .where(McpCallLog.occurred_at >= cutoff)
        .group_by(McpCallLog.tool)
        .order_by(func.count(McpCallLog.id).desc())
    )
    rows = (await session.execute(stmt)).all()

    items = []
    grand_calls = 0
    grand_errors = 0
    for r in rows:
        calls = int(r[1] or 0)
        errors = int(r[2] or 0)
        grand_calls += calls
        grand_errors += errors
        items.append(
            {
                "tool": r[0],
                "calls": calls,
                "errors": errors,
                "error_rate": round(errors / calls, 4) if calls else 0,
                "avg_latency_ms": round(float(r[3] or 0), 2),
                "total_cost_cny": float(r[4] or 0),
            }
        )

    return {
        "window_hours": hours,
        "total_calls": grand_calls,
        "total_errors": grand_errors,
        "overall_error_rate": (round(grand_errors / grand_calls, 4) if grand_calls else 0),
        "by_tool": items,
    }


@router.get("/top-users", response_model=None)
async def mcp_ops_top_users(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(20, ge=1, le=200),
) -> dict[str, Any]:
    """Top API keys by call count.

    JOINs `mcp_call_log → user_api_keys` so each row carries the prefix
    + name + user_id (we don't expose hash or revoked keys).
    """
    cutoff = _now() - timedelta(hours=hours)
    stmt = (
        select(
            McpCallLog.api_key_id,
            UserApiKey.prefix,
            UserApiKey.name,
            UserApiKey.user_id,
            func.count(McpCallLog.id).label("calls"),
            func.sum(case((McpCallLog.status != "ok", 1), else_=0)).label("errors"),
        )
        .join(
            UserApiKey,
            UserApiKey.id == McpCallLog.api_key_id,
            isouter=True,
        )
        .where(McpCallLog.occurred_at >= cutoff)
        .group_by(McpCallLog.api_key_id, UserApiKey.prefix, UserApiKey.name, UserApiKey.user_id)
        .order_by(func.count(McpCallLog.id).desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return {
        "window_hours": hours,
        "items": [
            {
                "api_key_id": r[0],
                "prefix": r[1],
                "key_name": r[2],
                "user_id": r[3],
                "calls": int(r[4] or 0),
                "errors": int(r[5] or 0),
            }
            for r in rows
        ],
    }


@router.get("/errors", response_model=None)
async def mcp_ops_errors(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(100, ge=1, le=500),
    error_code: str | None = Query(None),
) -> dict[str, Any]:
    """Recent failed calls (status != 'ok') for forensics."""
    cutoff = _now() - timedelta(hours=hours)
    stmt = (
        select(McpCallLog)
        .where(
            McpCallLog.occurred_at >= cutoff,
            McpCallLog.status != "ok",
        )
        .order_by(McpCallLog.occurred_at.desc())
        .limit(limit)
    )
    if error_code:
        stmt = stmt.where(McpCallLog.error_code == error_code)
    rows = list((await session.execute(stmt)).scalars().all())
    return {
        "window_hours": hours,
        "items": [
            {
                "id": r.id,
                "tool": r.tool,
                "resource_uri": r.resource_uri,
                "api_key_id": r.api_key_id,
                "user_id": r.user_id,
                "status": r.status,
                "http_status": r.http_status,
                "error_code": r.error_code,
                "latency_ms": r.latency_ms,
                "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }
