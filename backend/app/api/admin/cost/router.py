"""Admin cost dashboard router (Phase O.2.1).

PRD §4.4.1 + ADR-015:
- Read endpoints (no audit emit needed):
  - GET /api/admin/cost/daily?days=7|30 — total + by-scope trend
  - GET /api/admin/cost/by-source?days=7  — top spend sources
- Write endpoints (audit emit):
  - PUT /api/admin/cost/budgets/{scope}   — set or update budget threshold

Budget overrun → triggers Phase N alert (`alerts.scope='operator'`,
source='cost_overrun', severity='P0' if hard_stop_at_pct exceeded;
'P1' if alert_at_pct exceeded but below hard stop). Fires on the next
event ingest after the threshold is crossed; simpler than periodic
sweeper. Sweep job is a Phase O.2.2 follow-up.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from genpano_models import Alert, BudgetThreshold, CostEvent, User
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.security import current_admin_operator
from app.core.errors import not_found, validation_error
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Cost"])

VALID_SCOPES = {"pipeline", "kg", "mcp", "reports"}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _new_uuid() -> str:
    import uuid

    return str(uuid.uuid4())


# ── Read endpoints ───────────────────────────────────────────────


@router.get("/daily", response_model=None)
async def cost_daily(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
    days: int = Query(7, ge=1, le=90),
) -> dict[str, Any]:
    """Cost trend over the last `days` days, grouped by scope + day."""
    cutoff = _now() - timedelta(days=days)
    stmt = (
        select(
            func.date(CostEvent.occurred_at).label("day"),
            CostEvent.scope,
            func.sum(CostEvent.amount).label("total"),
            func.count(CostEvent.id).label("event_count"),
        )
        .where(CostEvent.occurred_at >= cutoff)
        .group_by("day", CostEvent.scope)
        .order_by("day")
    )
    rows = (await session.execute(stmt)).all()

    # Pivot rows into {day: {scope: total}} for FE-friendly shape
    by_day: dict[str, dict[str, Any]] = {}
    grand_total = Decimal("0")
    for r in rows:
        day_key = str(r[0])
        slot = by_day.setdefault(day_key, {})
        slot[r[1]] = float(r[2] or 0)
        grand_total += Decimal(str(r[2] or 0))

    return {
        "days": days,
        "from": (cutoff.date()).isoformat(),
        "to": _now().date().isoformat(),
        "grand_total": float(grand_total),
        "series": [
            {"day": d, "by_scope": v, "total": sum(v.values())} for d, v in sorted(by_day.items())
        ],
    }


@router.get("/by-source", response_model=None)
async def cost_by_source(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(20, ge=1, le=200),
) -> dict[str, Any]:
    """Top spending sources over the last `days` days."""
    cutoff = _now() - timedelta(days=days)
    stmt = (
        select(
            CostEvent.source,
            CostEvent.scope,
            func.sum(CostEvent.amount).label("total"),
            func.count(CostEvent.id).label("event_count"),
        )
        .where(CostEvent.occurred_at >= cutoff)
        .group_by(CostEvent.source, CostEvent.scope)
        .order_by(func.sum(CostEvent.amount).desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return {
        "days": days,
        "items": [
            {
                "source": r[0],
                "scope": r[1],
                "total": float(r[2] or 0),
                "event_count": int(r[3] or 0),
            }
            for r in rows
        ],
    }


@router.get("/budgets", response_model=None)
async def list_budgets(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    rows = list((await session.execute(select(BudgetThreshold))).scalars().all())
    return {
        "items": [
            {
                "scope": r.scope,
                "daily_limit_cny": float(r.daily_limit_cny) if r.daily_limit_cny else None,
                "weekly_limit_cny": (float(r.weekly_limit_cny) if r.weekly_limit_cny else None),
                "monthly_limit_cny": (float(r.monthly_limit_cny) if r.monthly_limit_cny else None),
                "alert_at_pct": r.alert_at_pct,
                "hard_stop_at_pct": r.hard_stop_at_pct,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }


# ── Write endpoints ─────────────────────────────────────────────


@router.put("/budgets/{scope}", response_model=None)
async def upsert_budget(
    scope: str,
    request: Request,
    operator: Annotated[User, Depends(current_admin_operator)],
    payload: dict[str, Any],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Create or update budget threshold for a scope.

    Body keys (all optional except validation): daily_limit_cny,
    weekly_limit_cny, monthly_limit_cny, alert_at_pct, hard_stop_at_pct.
    """
    if scope not in VALID_SCOPES:
        raise validation_error("scope", f"must be one of {sorted(VALID_SCOPES)}")

    alert_pct = payload.get("alert_at_pct", 80)
    hard_pct = payload.get("hard_stop_at_pct", 100)
    if not (0 < alert_pct <= hard_pct <= 200):
        raise validation_error(
            "alert_at_pct",
            "must satisfy 0 < alert_at_pct <= hard_stop_at_pct <= 200",
        )

    existing = (
        await session.execute(select(BudgetThreshold).where(BudgetThreshold.scope == scope))
    ).scalar_one_or_none()

    before: dict[str, Any] = {}
    if existing is None:
        row = BudgetThreshold(
            scope=scope,
            daily_limit_cny=payload.get("daily_limit_cny"),
            weekly_limit_cny=payload.get("weekly_limit_cny"),
            monthly_limit_cny=payload.get("monthly_limit_cny"),
            alert_at_pct=alert_pct,
            hard_stop_at_pct=hard_pct,
        )
        session.add(row)
        action = "budget_create"
    else:
        before = {
            "daily_limit_cny": (
                float(existing.daily_limit_cny) if existing.daily_limit_cny else None
            ),
            "alert_at_pct": existing.alert_at_pct,
            "hard_stop_at_pct": existing.hard_stop_at_pct,
        }
        existing.daily_limit_cny = payload.get("daily_limit_cny", existing.daily_limit_cny)
        existing.weekly_limit_cny = payload.get("weekly_limit_cny", existing.weekly_limit_cny)
        existing.monthly_limit_cny = payload.get("monthly_limit_cny", existing.monthly_limit_cny)
        existing.alert_at_pct = alert_pct
        existing.hard_stop_at_pct = hard_pct
        existing.updated_at = _now()
        action = "budget_update"
        row = existing

    await session.commit()

    after = {
        "daily_limit_cny": (float(row.daily_limit_cny) if row.daily_limit_cny else None),
        "alert_at_pct": row.alert_at_pct,
        "hard_stop_at_pct": row.hard_stop_at_pct,
    }
    await emit_audit(
        session,
        operator=operator,
        action=action,
        severity="med",
        resource_type="budget_threshold",
        resource_id=scope,
        before=before or None,
        after=after,
        request=request,
    )

    return {"scope": scope, **after}


@router.delete("/budgets/{scope}", status_code=204, response_model=None)
async def delete_budget(
    scope: str,
    request: Request,
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> None:
    """Remove a budget threshold (back to unlimited)."""
    row = (
        await session.execute(select(BudgetThreshold).where(BudgetThreshold.scope == scope))
    ).scalar_one_or_none()
    if row is None:
        raise not_found("budget threshold not found")

    before = {
        "daily_limit_cny": float(row.daily_limit_cny) if row.daily_limit_cny else None,
        "alert_at_pct": row.alert_at_pct,
        "hard_stop_at_pct": row.hard_stop_at_pct,
    }
    await session.delete(row)
    await session.commit()

    await emit_audit(
        session,
        operator=operator,
        action="budget_delete",
        severity="med",
        resource_type="budget_threshold",
        resource_id=scope,
        before=before,
        request=request,
    )


# ── Cost ingest helper (used by other services + tests) ─────────


async def record_cost_event(
    session: AsyncSession,
    *,
    scope: str,
    amount: float,
    source: str,
    event_type: str,
    reference_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> CostEvent:
    """Insert a cost event and emit a budget alert if thresholds tripped.

    Other services (analyzer LLM calls, MCP tool dispatch, report
    generation, KG relation extractor) call this to record spend.
    """
    if scope not in VALID_SCOPES:
        raise validation_error("scope", f"must be one of {sorted(VALID_SCOPES)}")

    ev = CostEvent(
        id=_new_uuid(),
        scope=scope,
        amount=amount,
        source=source,
        event_type=event_type,
        reference_id=reference_id,
        event_metadata=metadata,
    )
    session.add(ev)
    await session.commit()
    await session.refresh(ev)

    # Check daily budget
    threshold = (
        await session.execute(select(BudgetThreshold).where(BudgetThreshold.scope == scope))
    ).scalar_one_or_none()
    if threshold is None or threshold.daily_limit_cny is None:
        return ev

    today_start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_total = (
        await session.execute(
            select(func.coalesce(func.sum(CostEvent.amount), 0)).where(
                CostEvent.scope == scope,
                CostEvent.occurred_at >= today_start,
            )
        )
    ).scalar_one()

    daily_limit = float(threshold.daily_limit_cny)
    pct_used = (float(today_total) / daily_limit) * 100 if daily_limit > 0 else 0
    severity: str | None = None
    if pct_used >= threshold.hard_stop_at_pct:
        severity = "P0"
    elif pct_used >= threshold.alert_at_pct:
        severity = "P1"

    if severity:
        # Suppress duplicate alerts in the same day for the same scope
        existing_alert = (
            await session.execute(
                select(Alert).where(
                    Alert.scope == "operator",
                    Alert.source == "cost_overrun",
                    Alert.source_ref_id == scope,
                    Alert.triggered_at >= today_start,
                    Alert.severity == severity,
                )
            )
        ).scalar_one_or_none()
        if existing_alert is None:
            session.add(
                Alert(
                    id=_new_uuid(),
                    scope="operator",
                    source="cost_overrun",
                    source_ref_id=scope,
                    severity=severity,
                    title=f"Budget {severity}: {scope} at {pct_used:.0f}% of daily limit",
                    body=(
                        f"Spent ¥{float(today_total):.2f} of ¥{daily_limit:.2f} today "
                        f"({pct_used:.1f}%; alert={threshold.alert_at_pct}%, "
                        f"hard_stop={threshold.hard_stop_at_pct}%)."
                    ),
                    status="unread",
                    triggered_at=_now(),
                )
            )
            await session.commit()

    return ev
