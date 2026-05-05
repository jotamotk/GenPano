"""/v1/projects/:id/crawl-requests router (Phase 4)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from genpano_models import User
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.crawl._dto import CrawlRequestIn, CrawlRequestOut
from app.api.v1.crawl.service import create_crawl_request, get_crawl_request
from app.api.v1.projects.service import get_project_for_user
from app.core.security import _DependsDb, current_user

router = APIRouter(tags=["Crawl"])


@router.post(
    "/{project_id}/crawl-requests",
    response_model=CrawlRequestOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_crawl(
    project_id: str,
    payload: CrawlRequestIn,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> CrawlRequestOut:
    """User-triggered manual crawl (HIGH priority + 5/day quota)."""
    project = await get_project_for_user(session, user, project_id)
    cr = await create_crawl_request(
        session,
        project=project,
        user=user,
        brand_id=payload.brand_id,
        scope=payload.scope,
    )
    return CrawlRequestOut.model_validate(cr)


@router.get(
    "/{project_id}/crawl-requests/{crawl_id}",
    response_model=CrawlRequestOut,
)
async def get_crawl(
    project_id: str,
    crawl_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> CrawlRequestOut:
    """Status polling for a manual crawl."""
    project = await get_project_for_user(session, user, project_id)
    cr = await get_crawl_request(session, project=project, crawl_id=crawl_id)
    return CrawlRequestOut.model_validate(cr)
