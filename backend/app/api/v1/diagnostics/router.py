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

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from genpano_models import Diagnostic, User
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
from app.core.errors import not_found
from app.core.security import _DependsDb, current_user

router = APIRouter(tags=["Diagnostics"])


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@router.get("/", response_model=DiagnosticListOut)
async def list_diagnostics(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    status: str | None = Query(None),
    severity: str | None = Query(None),
    category: str | None = Query(None),
    type_: str | None = Query(None, alias="type"),
    limit: int = Query(50, ge=1, le=500),
) -> DiagnosticListOut:
    project = await get_project_for_user(session, user, project_id)
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
    return DiagnosticListOut(
        items=[DiagnosticOut.model_validate(r) for r in rows],
        total=len(rows),
    )


@router.get("/counts", response_model=DiagnosticCountsOut)
async def diagnostic_counts(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> DiagnosticCountsOut:
    project = await get_project_for_user(session, user, project_id)
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
    return DiagnosticCountsOut(
        total=int(total or 0),
        by_status={r[0]: int(r[1] or 0) for r in by_status_rows},
        by_severity_open={r[0]: int(r[1] or 0) for r in by_severity_rows},
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
