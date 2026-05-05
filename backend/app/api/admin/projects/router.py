"""Admin projects router (Phase R.4) — cross-tenant project visibility.

Mounted at `/api/admin/projects`. Operator-only; bypasses the multi-tenant
404 contract enforced on `/api/v1/projects/*` (which scopes to current user).
This sub-router lets ops staff:
  - inspect any user's projects for support / bug investigation
  - find inactive / soft-deleted projects (lifecycle hygiene)
  - filter by industry_id / primary_brand_id when triaging a complaint

Read-only. Admins do not edit user projects from here — that goes through
the user-side flow (or a future Phase R.4 takeover ops endpoint).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from genpano_models import Project, User
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.admin.security import current_admin_operator
from app.core.errors import not_found
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Projects"])


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _project_to_dict(p: Project, *, include_competitors: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": p.id,
        "user_id": p.user_id,
        "name": p.name,
        "industry_id": p.industry_id,
        "primary_brand_id": p.primary_brand_id,
        "is_active": p.is_active,
        "preferred_engines": p.preferred_engines,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        "deleted_at": p.deleted_at.isoformat() if p.deleted_at else None,
    }
    if include_competitors:
        out["competitors"] = [
            {"brand_id": c.brand_id, "pinned_at": c.pinned_at.isoformat() if c.pinned_at else None}
            for c in (p.competitors or [])
        ]
    return out


@router.get("/", response_model=None)
async def list_projects(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
    user_id: str | None = Query(None),
    industry_id: int | None = Query(None),
    is_active: bool | None = Query(None),
    include_deleted: bool = Query(False),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """List projects across all users (operator-only)."""
    stmt = select(Project).order_by(Project.created_at.desc())
    if not include_deleted:
        stmt = stmt.where(Project.deleted_at.is_(None))
    if user_id:
        stmt = stmt.where(Project.user_id == user_id)
    if industry_id is not None:
        stmt = stmt.where(Project.industry_id == industry_id)
    if is_active is not None:
        stmt = stmt.where(Project.is_active == is_active)
    stmt = stmt.offset(offset).limit(limit)

    rows = list((await session.execute(stmt)).scalars().all())
    return {
        "items": [_project_to_dict(p) for p in rows],
        "limit": limit,
        "offset": offset,
        "returned": len(rows),
    }


@router.get("/stats", response_model=None)
async def project_stats(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Aggregate counters for the projects fleet (operator dashboard surface)."""
    # Total / active / deleted / no-brand counts
    counters = (
        await session.execute(
            select(
                func.count(Project.id),
                func.sum(
                    case(
                        (Project.deleted_at.is_(None), 1),
                        else_=0,
                    )
                ),
                func.sum(
                    case(
                        (Project.deleted_at.isnot(None), 1),
                        else_=0,
                    )
                ),
                func.sum(
                    case(
                        (Project.primary_brand_id.is_(None), 1),
                        else_=0,
                    )
                ),
            )
        )
    ).one()
    total = int(counters[0] or 0)
    active = int(counters[1] or 0)
    deleted = int(counters[2] or 0)
    no_brand = int(counters[3] or 0)

    # Top user by project count (top 10)
    top_users = (
        await session.execute(
            select(Project.user_id, func.count(Project.id).label("ct"))
            .where(Project.deleted_at.is_(None))
            .group_by(Project.user_id)
            .order_by(func.count(Project.id).desc())
            .limit(10)
        )
    ).all()

    return {
        "as_of": _now().isoformat(),
        "counters": {
            "total": total,
            "active": active,
            "soft_deleted": deleted,
            "missing_primary_brand": no_brand,
        },
        "top_users_by_project_count": [
            {"user_id": r[0], "project_count": int(r[1] or 0)} for r in top_users
        ],
    }


@router.get("/{project_id}", response_model=None)
async def get_project(
    project_id: str,
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Project detail with competitors. Includes soft-deleted rows."""
    stmt = (
        select(Project).where(Project.id == project_id).options(selectinload(Project.competitors))
    )
    p = (await session.execute(stmt)).scalar_one_or_none()
    if p is None:
        raise not_found("project not found")
    return _project_to_dict(p, include_competitors=True)
