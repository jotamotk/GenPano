"""Admin diagnostics router (Phase R.4 + Phase D).

Mounted at `/api/admin/diagnostics`. Cross-tenant operator surface for
the diagnostic evaluator built in Phase D.

Endpoints:
- GET /                     — list across all projects (filter status /
                              severity / project_id / category; pagination)
- GET /counts               — aggregate counters by severity + status
- POST /refresh             — force-run evaluator for ONE project (audit
                              severity=med)
- POST /refresh-all         — force-run for all active projects (audit
                              severity=high — bulk operation)

Manual triggers are useful for: support cases (after fixing data), QA
runs after rule changes, and post-deploy verification.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from genpano_models import Diagnostic, Project, User
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.security import current_admin_operator
from app.core.errors import not_found
from app.core.security import _DependsDb
from app.diagnostics.evaluator import evaluate_project

router = APIRouter(tags=["Admin · Diagnostics"])


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _row_to_dict(d: Diagnostic) -> dict[str, Any]:
    return {
        "id": d.id,
        "project_id": d.project_id,
        "brand_id": d.brand_id,
        "category": d.category,
        "severity": d.severity,
        "type": d.type,
        "title": d.title,
        "rule_id": d.rule_id,
        "status": d.status,
        "detected_at": d.detected_at.isoformat() if d.detected_at else None,
    }


@router.get("/", response_model=None)
async def list_diagnostics(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
    status_filter: str | None = Query(None, alias="status"),
    severity: str | None = Query(None),
    project_id: str | None = Query(None),
    category: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """List diagnostics across all projects (operator-only)."""
    stmt = select(Diagnostic).order_by(Diagnostic.detected_at.desc())
    if status_filter:
        stmt = stmt.where(Diagnostic.status == status_filter)
    if severity:
        stmt = stmt.where(Diagnostic.severity == severity)
    if project_id:
        stmt = stmt.where(Diagnostic.project_id == project_id)
    if category:
        stmt = stmt.where(Diagnostic.category == category)
    stmt = stmt.offset(offset).limit(limit)

    rows = list((await session.execute(stmt)).scalars().all())
    return {
        "items": [_row_to_dict(r) for r in rows],
        "limit": limit,
        "offset": offset,
        "returned": len(rows),
    }


@router.get("/counts", response_model=None)
async def diagnostic_counts(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Aggregate counters: total / by_severity (open) / by_status."""
    total = (await session.execute(select(func.count(Diagnostic.id)))).scalar_one()

    by_severity_stmt = (
        select(Diagnostic.severity, func.count(Diagnostic.id))
        .where(Diagnostic.status == "open")
        .group_by(Diagnostic.severity)
    )
    by_severity = {
        row[0]: int(row[1] or 0) for row in (await session.execute(by_severity_stmt)).all()
    }

    by_status_stmt = select(Diagnostic.status, func.count(Diagnostic.id)).group_by(
        Diagnostic.status
    )
    by_status = {row[0]: int(row[1] or 0) for row in (await session.execute(by_status_stmt)).all()}

    high_open = (
        await session.execute(
            select(func.count(Diagnostic.id)).where(
                Diagnostic.status == "open",
                Diagnostic.severity.in_(["P0", "P1"]),
            )
        )
    ).scalar_one()

    return {
        "as_of": _now().isoformat(),
        "total": int(total or 0),
        "open_high_severity": int(high_open or 0),
        "open_by_severity": by_severity,
        "by_status": by_status,
    }


@router.post("/refresh", response_model=None)
async def refresh_one_project(
    request: Request,
    operator: Annotated[User, Depends(current_admin_operator)],
    payload: dict[str, Any],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Force-run evaluator for a single project. Returns inserted count."""
    project_id = payload.get("project_id")
    if not project_id:
        from app.core.errors import validation_error

        raise validation_error("project_id", "required")

    project = (
        await session.execute(
            select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if project is None:
        raise not_found("project not found")

    inserted = await evaluate_project(session, project)

    await emit_audit(
        session,
        operator=operator,
        action="diagnostics_refresh",
        severity="med",
        resource_type="project",
        resource_id=project.id,
        after={"new_diagnostics": len(inserted)},
        request=request,
    )

    return {
        "project_id": project.id,
        "new_diagnostics": len(inserted),
        "ids": [d.id for d in inserted],
    }


@router.post("/refresh-all", response_model=None)
async def refresh_all_projects(
    request: Request,
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Force-run evaluator for all active projects (audit severity=high).

    High-risk: scans + writes diagnostics across the whole fleet, can take
    seconds to minutes. Use sparingly (post-rule-change verification).
    """
    projects = list(
        (await session.execute(select(Project).where(Project.deleted_at.is_(None)))).scalars().all()
    )

    total_inserted = 0
    per_project: list[dict[str, Any]] = []
    for p in projects:
        inserted = await evaluate_project(session, p)
        total_inserted += len(inserted)
        per_project.append({"project_id": p.id, "new_diagnostics": len(inserted)})

    await emit_audit(
        session,
        operator=operator,
        action="diagnostics_refresh_all",
        severity="high",
        resource_type="project",
        resource_id=None,
        after={
            "projects_scanned": len(projects),
            "total_new_diagnostics": total_inserted,
        },
        request=request,
    )

    return {
        "projects_scanned": len(projects),
        "total_new_diagnostics": total_inserted,
        "per_project": per_project,
    }
