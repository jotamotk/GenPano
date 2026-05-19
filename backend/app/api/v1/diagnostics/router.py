"""User-facing diagnostics router (Phase D.7).

Mounted at `/v1/projects/{project_id}/diagnostics`. The diagnostics
themselves are produced by the rule engine in `app.diagnostics.evaluator`
which Celery (or admin UI) runs against each active project; this router
exposes them to the project owner.

Endpoints:
- GET    /                         list with filters
- GET    /counts                   aggregate counters (open by severity / status)
- GET    /{diag_id}                detail
- PATCH  /{diag_id}                status transition (acknowledge / ignore / resolve)
- POST   /refresh                  on-demand evaluator run for this project
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from genpano_models import Diagnostic, GeoScoreDaily, Project, ProjectCompetitor, User
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.diagnostics._dto import (
    DiagnosticCountsOut,
    DiagnosticListOut,
    DiagnosticOut,
    DiagnosticPatchIn,
    DiagnosticRefreshOut,
)
from app.api.v1.projects.service import get_project_for_user
from app.core.errors import not_found, validation_error
from app.core.security import _DependsDb, current_user

router = APIRouter(tags=["Diagnostics"])
logger = logging.getLogger(__name__)
DEFAULT_ANALYTICS_WINDOW_DAYS = 30
LOW_KPI_THRESHOLDS = {
    "geo_score": 1.0,
    "mention_rate": 1.0,
    "sov": 1.0,
}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _date_window(from_date: date | None, to_date: date | None) -> tuple[date, date]:
    end = to_date or date.today()
    start = from_date or (end - timedelta(days=DEFAULT_ANALYTICS_WINDOW_DAYS - 1))
    return start, end


async def _project_scoped_brand_id(
    session: AsyncSession,
    project: Project,
    brand_id: int | None,
) -> int | None:
    if brand_id is None:
        return None
    if project.primary_brand_id == brand_id:
        return brand_id

    stmt = select(ProjectCompetitor.brand_id).where(
        ProjectCompetitor.project_id == project.id,
        ProjectCompetitor.brand_id == brand_id,
    )
    if (await session.execute(stmt)).scalar_one_or_none() == brand_id:
        return brand_id

    raise validation_error(
        "brand_id",
        "must match project primary brand or pinned competitor",
    )


async def _open_p0_p1_count(session: AsyncSession, project_id: str) -> int:
    total = (
        await session.execute(
            select(func.count(Diagnostic.id)).where(
                and_(
                    Diagnostic.project_id == project_id,
                    Diagnostic.status == "open",
                    Diagnostic.severity.in_(["P0", "P1"]),
                )
            )
        )
    ).scalar_one()
    return int(total or 0)


def _active_diagnostics_summary(open_p0_p1_count: int) -> dict[str, Any]:
    return {
        "state": "active",
        "state_reason": "open_p0_p1_diagnostics",
        "state_detail": "Open P0/P1 diagnostics exist for this project.",
        "open_p0_p1_count": open_p0_p1_count,
        "analytics_state": None,
        "analytics_state_reason": None,
        "formula_status": None,
        "missing_inputs": [],
        "evidence_counts": {},
        "analytics_signals": {"low_kpis": [], "freshness": {}},
    }


def _unavailable_summary(open_p0_p1_count: int) -> dict[str, Any]:
    return {
        "state": "unavailable",
        "state_reason": "diagnostics_state_unavailable",
        "state_detail": "No open P0/P1 diagnostics, but analytics state could not be evaluated.",
        "open_p0_p1_count": open_p0_p1_count,
        "analytics_state": None,
        "analytics_state_reason": None,
        "formula_status": None,
        "missing_inputs": [],
        "evidence_counts": {},
        "analytics_signals": {"low_kpis": [], "freshness": {}},
    }


async def _geo_kpi_snapshot(
    session: AsyncSession,
    *,
    brand_id: int,
    from_date: date,
    to_date: date,
) -> dict[str, Any]:
    row = (
        await session.execute(
            select(
                func.count(GeoScoreDaily.id).label("row_count"),
                func.avg(GeoScoreDaily.avg_geo_score).label("avg_geo_score"),
                func.avg(GeoScoreDaily.mention_rate).label("mention_rate"),
                func.avg(GeoScoreDaily.avg_sov).label("sov"),
                func.max(GeoScoreDaily.date).label("latest_date"),
            ).where(
                and_(
                    GeoScoreDaily.brand_id == brand_id,
                    GeoScoreDaily.date >= datetime.combine(from_date, datetime.min.time()),
                    GeoScoreDaily.date <= datetime.combine(to_date, datetime.max.time()),
                )
            )
        )
    ).one()
    latest = row.latest_date
    if isinstance(latest, datetime):
        latest_value = latest.date().isoformat()
    elif isinstance(latest, date):
        latest_value = latest.isoformat()
    else:
        latest_value = None
    return {
        "row_count": int(row.row_count or 0),
        "latest_geo_score_daily_date": latest_value,
        "values": {
            "geo_score": _score_0_100(row.avg_geo_score),
            "mention_rate": _percent_display(row.mention_rate),
            "sov": _percent_display(row.sov),
        },
    }


def _score_0_100(value: Any) -> float | None:
    if value is None:
        return None
    score = float(value)
    if 0.0 <= score <= 1.0:
        score *= 100.0
    return round(score, 2)


def _percent_display(value: Any) -> float | None:
    if value is None:
        return None
    raw = float(value)
    if abs(raw) > 1.0 and abs(raw) <= 100.0:
        return round(raw, 1)
    return round(raw * 100.0, 1)


async def _analytics_contract_summary(
    session: AsyncSession,
    project: Project,
    *,
    brand_id: int | None,
    from_date: date | None,
    to_date: date | None,
) -> dict[str, Any]:
    from app.api.v1.projects._analytics_contract import (
        FORMULA_NO_EVIDENCE_STATUS,
        FORMULA_OK_STATUS,
        build_contract_context,
    )

    from_d, to_d = _date_window(from_date, to_date)
    scoped_brand_id = brand_id if brand_id is not None else project.primary_brand_id
    snapshot = (
        await _geo_kpi_snapshot(
            session,
            brand_id=scoped_brand_id,
            from_date=from_d,
            to_date=to_d,
        )
        if scoped_brand_id is not None
        else {"row_count": 0, "latest_geo_score_daily_date": None, "values": {}}
    )
    context = await build_contract_context(
        session,
        project,
        brand_id=scoped_brand_id,
        from_date=from_d,
        to_date=to_d,
        has_data=snapshot["row_count"] > 0,
        base_state="ok" if snapshot["row_count"] > 0 else "empty",
        base_state_reason="data_available" if snapshot["row_count"] > 0 else "no_metric_data",
    )
    low_kpis = [
        {
            "metric_key": metric_key,
            "value": value,
            "state_reason": "low_kpi_value",
        }
        for metric_key, value in snapshot["values"].items()
        if value is not None and value <= LOW_KPI_THRESHOLDS[metric_key]
    ]
    signals = {
        "low_kpis": low_kpis,
        "freshness": {
            "latest_geo_score_daily_date": snapshot["latest_geo_score_daily_date"],
        },
    }
    summary: dict[str, Any] = {
        "open_p0_p1_count": 0,
        "analytics_state": context.state,
        "analytics_state_reason": context.state_reason,
        "formula_status": context.formula_status,
        "missing_inputs": context.missing_inputs,
        "evidence_counts": context.evidence_counts,
        "analytics_signals": signals,
    }
    if context.state == "partial" or (
        context.formula_status
        and context.formula_status not in {FORMULA_OK_STATUS, FORMULA_NO_EVIDENCE_STATUS}
    ):
        return {
            **summary,
            "state": "partial",
            "state_reason": context.state_reason or "analytics_incomplete",
            "state_detail": (
                "No open P0/P1 diagnostics, but analytics evidence is partial "
                "or missing required formula inputs."
            ),
        }
    if context.state == "empty" or context.formula_status == FORMULA_NO_EVIDENCE_STATUS:
        return {
            **summary,
            "state": "unavailable",
            "state_reason": context.state_reason or "analytics_unavailable",
            "state_detail": "No open P0/P1 diagnostics, but analytics evidence is unavailable.",
        }
    if low_kpis:
        return {
            **summary,
            "state": "attention",
            "state_reason": "low_kpi_value",
            "state_detail": "No open P0/P1 diagnostics, but KPI values need attention.",
        }
    return {
        **summary,
        "state": "no_diagnostics",
        "state_reason": "no_open_p0_p1_diagnostics",
        "state_detail": "No open P0/P1 diagnostics and analytics contract is complete.",
    }


async def _diagnostic_summary(
    session: AsyncSession,
    project: Project,
    *,
    open_p0_p1_count: int,
    brand_id: int | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict[str, Any]:
    if open_p0_p1_count > 0:
        return _active_diagnostics_summary(open_p0_p1_count)
    try:
        summary = await _analytics_contract_summary(
            session,
            project,
            brand_id=brand_id,
            from_date=from_date,
            to_date=to_date,
        )
    except Exception:
        logger.exception(
            "Failed to evaluate diagnostics analytics state (project_id=%s)",
            project.id,
        )
        return _unavailable_summary(open_p0_p1_count)
    return {**summary, "open_p0_p1_count": open_p0_p1_count}


async def diagnostics_response_for_project(
    session: AsyncSession,
    project: Project,
    *,
    status: str | None = None,
    severity: str | None = None,
    category: str | None = None,
    type_: str | None = None,
    brand_id: int | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    limit: int = 50,
) -> DiagnosticListOut:
    stmt = (
        select(Diagnostic)
        .where(Diagnostic.project_id == project.id)
        .order_by(Diagnostic.detected_at.desc())
        .limit(limit)
    )
    if status:
        stmt = stmt.where(Diagnostic.status == status)
    if severity:
        stmt = stmt.where(Diagnostic.severity == severity)
    if category:
        stmt = stmt.where(Diagnostic.category == category)
    if type_:
        stmt = stmt.where(Diagnostic.type == type_)
    rows = list((await session.execute(stmt)).scalars().all())
    open_p0_p1_count = await _open_p0_p1_count(session, project.id)
    summary = await _diagnostic_summary(
        session,
        project,
        open_p0_p1_count=open_p0_p1_count,
        brand_id=brand_id,
        from_date=from_date,
        to_date=to_date,
    )
    return DiagnosticListOut(
        items=[DiagnosticOut.model_validate(r) for r in rows],
        total=len(rows),
        **summary,
    )


@router.get("/", response_model=DiagnosticListOut)
async def list_diagnostics(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    status: str | None = Query(None),
    severity: str | None = Query(None),
    category: str | None = Query(None),
    type_: str | None = Query(None, alias="type"),
    brand_id: Annotated[int | None, Query()] = None,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
    limit: int = Query(50, ge=1, le=500),
) -> DiagnosticListOut:
    project = await get_project_for_user(session, user, project_id)
    scoped_brand_id = await _project_scoped_brand_id(session, project, brand_id)
    return await diagnostics_response_for_project(
        session,
        project,
        status=status,
        severity=severity,
        category=category,
        type_=type_,
        brand_id=scoped_brand_id,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
    )


@router.get("/counts", response_model=DiagnosticCountsOut)
async def diagnostic_counts(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    brand_id: Annotated[int | None, Query()] = None,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
) -> DiagnosticCountsOut:
    project = await get_project_for_user(session, user, project_id)
    scoped_brand_id = await _project_scoped_brand_id(session, project, brand_id)
    total = (
        await session.execute(
            select(func.count(Diagnostic.id)).where(Diagnostic.project_id == project.id)
        )
    ).scalar_one()
    by_status_rows = (
        await session.execute(
            select(Diagnostic.status, func.count(Diagnostic.id))
            .where(Diagnostic.project_id == project.id)
            .group_by(Diagnostic.status)
        )
    ).all()
    by_severity_rows = (
        await session.execute(
            select(Diagnostic.severity, func.count(Diagnostic.id))
            .where(
                and_(
                    Diagnostic.project_id == project.id,
                    Diagnostic.status == "open",
                )
            )
            .group_by(Diagnostic.severity)
        )
    ).all()
    by_severity_open = {r[0]: int(r[1] or 0) for r in by_severity_rows}
    open_p0_p1_count = int(by_severity_open.get("P0", 0) + by_severity_open.get("P1", 0))
    summary = await _diagnostic_summary(
        session,
        project,
        open_p0_p1_count=open_p0_p1_count,
        brand_id=scoped_brand_id,
        from_date=from_date,
        to_date=to_date,
    )
    return DiagnosticCountsOut(
        total=int(total or 0),
        by_status={r[0]: int(r[1] or 0) for r in by_status_rows},
        by_severity_open=by_severity_open,
        **summary,
    )


@router.get("/{diag_id}", response_model=DiagnosticOut)
async def get_diagnostic(
    project_id: str,
    diag_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> DiagnosticOut:
    project = await get_project_for_user(session, user, project_id)
    row = (
        await session.execute(
            select(Diagnostic).where(
                and_(Diagnostic.id == diag_id, Diagnostic.project_id == project.id)
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise not_found("diagnostic not found")
    return DiagnosticOut.model_validate(row)


@router.patch("/{diag_id}", response_model=DiagnosticOut)
async def patch_diagnostic(
    project_id: str,
    diag_id: str,
    payload: DiagnosticPatchIn,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> DiagnosticOut:
    """Status transition. acknowledged / resolved record the user + ts."""
    project = await get_project_for_user(session, user, project_id)
    row = (
        await session.execute(
            select(Diagnostic).where(
                and_(Diagnostic.id == diag_id, Diagnostic.project_id == project.id)
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise not_found("diagnostic not found")

    new_status = payload.status
    now = _now()
    row.status = new_status
    if new_status == "acknowledged":
        row.acknowledged_at = now
        row.acknowledged_by = user.id
    elif new_status == "resolved":
        row.resolved_at = now
        row.resolved_by = user.id
    await session.commit()
    await session.refresh(row)

    # Phase D.8 link — when the diagnostic resolves, mark linked alerts
    # resolved too. Best-effort; don't roll back the diagnostic update.
    if new_status == "resolved":
        try:
            from app.alerts.triggers import resolve_alert_for_diagnostic

            await resolve_alert_for_diagnostic(session, row)
        except Exception:
            try:
                await session.rollback()
            except Exception:
                pass

    return DiagnosticOut.model_validate(row)


@router.post("/refresh", response_model=DiagnosticRefreshOut)
async def refresh_diagnostics(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> DiagnosticRefreshOut:
    """Re-run the evaluator on demand. Returns the count of newly-inserted rows."""
    from app.diagnostics.evaluator import evaluate_project

    project = await get_project_for_user(session, user, project_id)
    inserted = await evaluate_project(session, project)
    return DiagnosticRefreshOut(inserted=len(inserted), project_id=project.id)
