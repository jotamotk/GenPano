"""/v1/projects router (Phase 1).

Endpoints:
  GET    /v1/projects                          List user's projects
  POST   /v1/projects                          Create project
  GET    /v1/projects/:id                      Project detail
  PATCH  /v1/projects/:id                      Update fields
  DELETE /v1/projects/:id                      Soft delete
  POST   /v1/projects/:id/competitors          Add competitor
  DELETE /v1/projects/:id/competitors/:brand_id Remove competitor
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from genpano_models import User
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects import service
from app.api.v1.projects._dto import (
    CompetitorIn,
    ProjectIn,
    ProjectListOut,
    ProjectOut,
    ProjectPatch,
)
from app.core.security import _DependsDb, current_user

router = APIRouter(tags=["Projects"])


@router.get("/", response_model=ProjectListOut)
async def list_projects(
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> ProjectListOut:
    rows = await service.list_user_projects(session, user)
    items = [ProjectOut.model_validate(p) for p in rows]
    return ProjectListOut(items=items, total=len(items))


@router.post("/", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectIn,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> ProjectOut:
    project = await service.create_project(
        session,
        user,
        name=payload.name,
        industry_id=payload.industry_id,
        primary_brand_id=payload.primary_brand_id,
        preferred_engines=payload.preferred_engines,
        competitor_brand_ids=payload.competitor_brand_ids,
    )
    return ProjectOut.model_validate(project)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> ProjectOut:
    project = await service.get_project_for_user(session, user, project_id)
    return ProjectOut.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: str,
    payload: ProjectPatch,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> ProjectOut:
    project = await service.get_project_for_user(session, user, project_id)
    project = await service.update_project(
        session, project, **payload.model_dump(exclude_unset=True, exclude_none=True)
    )
    return ProjectOut.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> None:
    project = await service.get_project_for_user(session, user, project_id)
    await service.soft_delete_project(session, project)


@router.post(
    "/{project_id}/competitors",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_competitor(
    project_id: str,
    payload: CompetitorIn,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> ProjectOut:
    project = await service.get_project_for_user(session, user, project_id)
    project = await service.add_competitor(session, project, brand_id=payload.brand_id, user=user)
    return ProjectOut.model_validate(project)


@router.delete(
    "/{project_id}/competitors/{brand_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_competitor(
    project_id: str,
    brand_id: int,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> None:
    project = await service.get_project_for_user(session, user, project_id)
    await service.remove_competitor(session, project, brand_id=brand_id)
