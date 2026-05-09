"""/v1/industries router (Phase 3)."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from genpano_models import User
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.industries._dto import (
    IndustriesListOut,
    IndustryAvgGeoOut,
    IndustryDistributionOut,
    IndustryGroupsOut,
    IndustryKgOut,
    IndustryMoversOut,
    IndustryOverviewOut,
    IndustryRankingByEngineOut,
    IndustryRankingOut,
    IndustrySegmentsOut,
    IndustryTopDomainsOut,
    IndustryTopicDetailOut,
    IndustryTopicsOut,
    TopBrandRow,
    TopicIntentMatrixOut,
)
from app.api.v1.industries.service import (
    get_industry_avg_geo_score,
    get_industry_distribution,
    get_industry_groups,
    get_industry_kg,
    get_industry_movers,
    get_industry_overview,
    get_industry_ranking,
    get_industry_ranking_by_engine,
    get_industry_segments,
    get_industry_top_domains,
    get_industry_topic_detail,
    get_industry_topic_intent_matrix,
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
    primary_brand_id: int | None = Query(None, description="Resolve my_rank for this brand"),
) -> IndustryRankingOut:
    return await get_industry_ranking(
        session,
        industry_id,
        industry_name=name,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        offset=offset,
        limit=limit,
        primary_brand_id=primary_brand_id,
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


@router.get("/{industry_id}/avg-geo-score", response_model=IndustryAvgGeoOut)
async def industry_avg_geo_score(
    industry_id: int,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    name: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
) -> IndustryAvgGeoOut:
    """30-day industry GEO benchmark (avg / median / top10) from
    industry_benchmark_daily. Replaces the FE mock fallback used by
    BrandPanoramaPanel's hero industry-comparison bar."""
    return await get_industry_avg_geo_score(
        session,
        industry_id,
        industry_name=name,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
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


# ── Phase 5: Chart endpoints ────────────────────────────────


@router.get("/{industry_id}/distribution", response_model=IndustryDistributionOut)
async def industry_distribution(
    industry_id: int,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    name: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
) -> IndustryDistributionOut:
    return await get_industry_distribution(
        session,
        industry_id,
        industry_name=name,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
    )


@router.get("/{industry_id}/movers", response_model=IndustryMoversOut)
async def industry_movers(
    industry_id: int,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    name: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    limit: int = Query(5, ge=1, le=20),
) -> IndustryMoversOut:
    return await get_industry_movers(
        session,
        industry_id,
        industry_name=name,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        limit=limit,
    )


@router.get("/{industry_id}/groups", response_model=IndustryGroupsOut)
async def industry_groups(
    industry_id: int,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    name: str | None = Query(None),
    limit: int = Query(8, ge=1, le=30),
) -> IndustryGroupsOut:
    return await get_industry_groups(session, industry_id, industry_name=name, limit=limit)


@router.get("/{industry_id}/top-domains", response_model=IndustryTopDomainsOut)
async def industry_top_domains(
    industry_id: int,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    name: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
) -> IndustryTopDomainsOut:
    return await get_industry_top_domains(
        session,
        industry_id,
        industry_name=name,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        limit=limit,
    )


@router.get("/{industry_id}/segments", response_model=IndustrySegmentsOut)
async def industry_segments(
    industry_id: int,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    name: str | None = Query(None),
    limit: int = Query(5, ge=1, le=20),
) -> IndustrySegmentsOut:
    return await get_industry_segments(session, industry_id, industry_name=name, limit=limit)


@router.get(
    "/{industry_id}/ranking-by-engine",
    response_model=IndustryRankingByEngineOut,
)
async def industry_ranking_by_engine(
    industry_id: int,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    name: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    limit: int = Query(10, ge=1, le=30),
) -> IndustryRankingByEngineOut:
    return await get_industry_ranking_by_engine(
        session,
        industry_id,
        industry_name=name,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        limit=limit,
    )


@router.get(
    "/{industry_id}/topic-intent-matrix",
    response_model=TopicIntentMatrixOut,
)
async def industry_topic_intent(
    industry_id: int,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    name: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    limit: int = Query(8, ge=1, le=30),
) -> TopicIntentMatrixOut:
    return await get_industry_topic_intent_matrix(
        session,
        industry_id,
        industry_name=name,
        limit=limit,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
    )


@router.get(
    "/{industry_id}/topics/{topic_id}",
    response_model=IndustryTopicDetailOut,
)
async def industry_topic_detail(
    industry_id: int,
    topic_id: int,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    name: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
) -> IndustryTopicDetailOut:
    return await get_industry_topic_detail(
        session,
        industry_id,
        topic_id,
        industry_name=name,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
    )
