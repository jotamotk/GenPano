"""Service layer for /v1/projects (Phase 1).

Reusable from MCP tools (Phase M) and Reports (Phase RP) without going through
the HTTP layer.
"""

from __future__ import annotations

from datetime import UTC, datetime

from genpano_models import Project, ProjectCompetitor, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import conflict, not_found

COMPETITOR_CAP = 10  # PRD §4.1.2a


async def list_user_projects(session: AsyncSession, user: User) -> list[Project]:
    """Return all (non-deleted) projects owned by `user`, active first."""
    stmt = (
        select(Project)
        .where(Project.user_id == user.id, Project.deleted_at.is_(None))
        .order_by(Project.is_active.desc(), Project.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_project_for_user(
    session: AsyncSession, user: User, project_id: str
) -> Project:
    """Return project iff `user` owns it; else raise 404 (not 403, ADR-005)."""
    stmt = select(Project).where(
        Project.id == project_id,
        Project.user_id == user.id,
        Project.deleted_at.is_(None),
    )
    result = await session.execute(stmt)
    project = result.scalar_one_or_none()
    if project is None:
        raise not_found("project not found")
    return project


async def create_project(
    session: AsyncSession,
    user: User,
    *,
    name: str,
    industry_id: int | None = None,
    primary_brand_id: int | None = None,
    preferred_engines: list[str] | None = None,
    competitor_brand_ids: list[int] | None = None,
) -> Project:
    """Create a project + initial competitor pins.

    Raises 409 if name conflicts with another project owned by the same user.
    """
    stmt = select(Project.id).where(
        Project.user_id == user.id,
        Project.name == name,
        Project.deleted_at.is_(None),
    )
    if (await session.execute(stmt)).scalar_one_or_none():
        raise conflict("project_name_taken", f"name '{name}' already used")

    if competitor_brand_ids and len(competitor_brand_ids) > COMPETITOR_CAP:
        raise conflict(
            "competitor_capacity_full",
            f"competitor_brand_ids exceeds capacity {COMPETITOR_CAP}",
        )

    project = Project(
        user_id=user.id,
        name=name,
        industry_id=industry_id,
        primary_brand_id=primary_brand_id,
        preferred_engines=preferred_engines,
    )
    session.add(project)
    await session.flush()

    if competitor_brand_ids:
        for brand_id in competitor_brand_ids:
            session.add(
                ProjectCompetitor(
                    project_id=project.id, brand_id=brand_id, pinned_by=user.id
                )
            )

    await session.commit()
    await session.refresh(project, ["competitors"])
    return project


async def update_project(
    session: AsyncSession,
    project: Project,
    **fields: object,
) -> Project:
    """Patch arbitrary `fields` onto an already-resolved project."""
    name_changed_to = fields.get("name")
    if name_changed_to and name_changed_to != project.name:
        stmt = select(Project.id).where(
            Project.user_id == project.user_id,
            Project.name == name_changed_to,
            Project.id != project.id,
            Project.deleted_at.is_(None),
        )
        if (await session.execute(stmt)).scalar_one_or_none():
            raise conflict(
                "project_name_taken", f"name '{name_changed_to}' already used"
            )

    for k, v in fields.items():
        if v is not None:
            setattr(project, k, v)
    await session.commit()
    await session.refresh(project, ["competitors"])
    return project


async def soft_delete_project(session: AsyncSession, project: Project) -> None:
    project.deleted_at = datetime.now(UTC).replace(tzinfo=None)
    project.is_active = False
    await session.commit()


async def add_competitor(
    session: AsyncSession,
    project: Project,
    *,
    brand_id: int,
    user: User,
) -> Project:
    """Pin `brand_id` as a competitor on `project`. Enforces capacity 10."""
    if len(project.competitors) >= COMPETITOR_CAP:
        raise conflict(
            "competitor_capacity_full",
            f"max {COMPETITOR_CAP} competitors per project",
        )
    if any(c.brand_id == brand_id for c in project.competitors):
        return project

    session.add(
        ProjectCompetitor(project_id=project.id, brand_id=brand_id, pinned_by=user.id)
    )
    await session.commit()
    await session.refresh(project, ["competitors"])
    return project


async def remove_competitor(
    session: AsyncSession,
    project: Project,
    *,
    brand_id: int,
) -> None:
    """Remove a competitor pin. Idempotent (404 only if project itself missing)."""
    stmt = select(ProjectCompetitor).where(
        ProjectCompetitor.project_id == project.id,
        ProjectCompetitor.brand_id == brand_id,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is not None:
        await session.delete(row)
        await session.commit()
