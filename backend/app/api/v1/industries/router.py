"""/v1/industries router (Phase 3)."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from genpano_models import User
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.industries._dto import (
    IndustriesListOut,
    IndustryKgOut,
    IndustryOverviewOut,
    IndustryRankingOut,
    IndustryTopicsOut,
    TopBrandRow,
)
from app.api.v1.industries.service import (
    get_industry_kg,
    get_industry_overview,
    get_industry_ranking,
    get_industry_topics,
    get_top_brands,
    list_industries,
)
from app.core.errors import validation_error
from app.core.security import _DependsDb, current_user

router = APIRouter(tags=["Industries"])


def _parse_date(value: str | None, field: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise validation_error(field, "must be ISO date YYYY-MM-DD") from exc


@router.get("/", response_model=IndustriesListOut)
async def list_industries_endpoint(
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> IndustriesListOut:
    return await list_industries(session)


@router.get("/{industry_id}/top-brands", response_model=list[TopBrandRow])
async def industry_top_brands(
    industry_id: int,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    n: int = Query(3, ge=1, le=20),
) -> list[TopBrandRow]:
    return await get_top_brands(session, industry_id, n=n)


@router.get("/{industry_id}/overview", response_model=IndustryOverviewOut)
async def industry_overview(
    industry_id: int,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    name: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
) -> IndustryOverviewOut:
    return await get_industry_overview(
        session,
        industry_id,
        industry_name=name,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
    )


@router.get("/{industry_id}/ranking", response_model=IndustryRankingOut)
async def industry_ranking(
    industry_id: int,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    name: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> IndustryRankingOut:
    return await get_industry_ranking(
        session,
        industry_id,
        industry_name=name,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        offset=offset,
        limit=limit,
    )


@router.get("/{industry_id}/topics", response_model=IndustryTopicsOut)
async def industry_topics(
    industry_id: int,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    name: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> IndustryTopicsOut:
    return await get_industry_topics(
        session,
        industry_id,
        industry_name=name,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        limit=limit,
    )


@router.get("/{industry_id}/kg", response_model=IndustryKgOut)
async def industry_kg(
    industry_id: int,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    name: str | None = Query(None),
    focus: str | None = Query(None),
    depth: int = Query(2, ge=1, le=5),
) -> IndustryKgOut:
    return await get_industry_kg(
        session,
        industry_id,
        industry_name=name,
        focus=focus,
        depth=depth,
    )
