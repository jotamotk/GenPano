"""/v1/projects router (Phase 1 + 2.1 + 2.2).

Endpoints:
  GET    /v1/projects                          List user's projects
  POST   /v1/projects                          Create project
  GET    /v1/projects/:id                      Project detail
  PATCH  /v1/projects/:id                      Update fields
  DELETE /v1/projects/:id                      Soft delete
  POST   /v1/projects/:id/competitors          Add competitor
  DELETE /v1/projects/:id/competitors/:brand_id Remove competitor
  GET    /v1/projects/:id/overview             Brand Overview composite (Phase 2.1)
  GET    /v1/projects/:id/metrics              Brand metrics time series (Phase 2.2)
  GET    /v1/projects/:id/topics               Project topics + pin state
  GET    /v1/projects/:id/sentiment            Sentiment distribution + drivers
  GET    /v1/projects/:id/citations            Citation list + top domains
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
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
from app.api.v1.projects._metrics_dto import (
    CitationsOut,
    MetricsOut,
    SentimentOut,
    TopicsOut,
)
from app.api.v1.projects._metrics_service import (
    get_citations,
    get_metrics,
    get_sentiment,
    get_topics,
)
from app.api.v1.projects._overview_dto import BrandOverviewOut
from app.api.v1.projects._overview_service import get_brand_overview
from app.core.errors import validation_error
from app.core.security import _DependsDb, current_user

router = APIRouter(tags=["Projects"])


def _parse_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [s.strip() for s in value.split(",") if s.strip()]


def _parse_date(value: str | None, field: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise validation_error(field, "must be ISO date YYYY-MM-DD") from exc


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


# ── Phase 2.1 ────────────────────────────────────────────────────


@router.get("/{project_id}/overview", response_model=BrandOverviewOut)
async def project_overview(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> BrandOverviewOut:
    """Brand Overview composite — KPI cards + 30d trends + top prompts (PRD §4.6.1a)."""
    project = await service.get_project_for_user(session, user, project_id)
    return await get_brand_overview(session, project)


# ── Phase 2.2 endpoints ──────────────────────────────────────────


@router.get("/{project_id}/metrics", response_model=MetricsOut)
async def project_metrics(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    series: str | None = Query(
        None,
        description="csv subset of: mention_rate,sov,rank,sentiment,citation",
    ),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    engine: str | None = Query(None, description="csv: chatgpt,doubao,deepseek"),
) -> MetricsOut:
    """Per-metric time series for the project's primary brand (PRD §4.6.1b)."""
    project = await service.get_project_for_user(session, user, project_id)
    return await get_metrics(
        session,
        project,
        series=_parse_csv(series),
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        engines=_parse_csv(engine),
    )


@router.get("/{project_id}/topics", response_model=TopicsOut)
async def project_topics(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> TopicsOut:
    """Topics tracked / ignored on the project (PRD §4.6.1c)."""
    project = await service.get_project_for_user(session, user, project_id)
    return await get_topics(session, project)


@router.get("/{project_id}/sentiment", response_model=SentimentOut)
async def project_sentiment(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
) -> SentimentOut:
    """Sentiment distribution + 30d trend + top keywords / drivers (PRD §4.6.1d)."""
    project = await service.get_project_for_user(session, user, project_id)
    return await get_sentiment(
        session,
        project,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
    )


@router.get("/{project_id}/citations", response_model=CitationsOut)
async def project_citations(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    page_size: int = Query(50, ge=1, le=500),
) -> CitationsOut:
    """Citation list + top cited domains (PRD §4.6.1e)."""
    project = await service.get_project_for_user(session, user, project_id)
    return await get_citations(
        session,
        project,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        page_size=page_size,
    )
