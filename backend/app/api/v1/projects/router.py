"""/v1/projects router (Phase 1 + 2.1 + 2.2 + 2.3).

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
  GET    /v1/projects/:id/products             SKU rollup (Phase 2.3)
  GET    /v1/projects/:id/competitors/metrics  Competitor matrix (Phase 2.3)
  GET    /v1/projects/:id/diagnostics          Derived diagnostics (Phase 2.3)
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from genpano_models import User
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects import service
from app.api.v1.projects._brand_dto import (
    CompetitorMetricsOut,
    CompetitorTrendsOut,
    DiagnosticsOut,
    ProductsOut,
)
from app.api.v1.projects._brand_service import (
    get_competitor_metrics,
    get_competitor_trends,
    get_diagnostics,
    get_products,
)
from app.api.v1.projects._charts_dto import (
    AuthorityRadarOut,
    AuthorityTrendOut,
    CitationCompositionOut,
    ContentGapOut,
    EngineMetricsOut,
    GroupSharedDomainsOut,
    MentionSamplesOut,
    PositionDistributionOut,
    ProductRelationsOut,
    PrTargetsOut,
    SentimentByEngineOut,
    SentimentTrendByEngineOut,
    SimulatorBaselineOut,
    TopicAttributionOut,
    TopicHeatmapOut,
)
from app.api.v1.projects._charts_service import (
    get_authority_radar,
    get_authority_trend,
    get_citation_composition,
    get_content_gap,
    get_engine_metrics,
    get_group_shared_domains,
    get_mention_samples,
    get_position_distribution,
    get_pr_targets,
    get_product_relations,
    get_sentiment_by_engine,
    get_sentiment_trend_by_engine,
    get_simulator_baseline,
    get_topic_attribution,
    get_topic_heatmap,
)
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
from app.api.v1.projects._topic_analysis_dto import (
    ProjectSegmentsOut,
    PromptQueriesOut,
    QueryActivityOut,
    QueryResponseDetailOut,
    TopicMonitoringOut,
    TopicPromptsOut,
)
from app.api.v1.projects._topic_analysis_service import (
    AnalysisFilters,
    get_project_segments,
    get_prompt_queries,
    get_query_activity,
    get_query_response_detail,
    get_topic_monitoring,
    get_topic_prompts,
)
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


def _analysis_filters(
    *,
    from_: str | None,
    to: str | None,
    engine: str | None,
    segment_id: str | None,
    profile_id: str | None,
    dimension: str | None = None,
    intent: str | None = None,
    prompt_scope: str | None = None,
) -> AnalysisFilters:
    engines = _parse_csv(engine)
    dimensions = _parse_csv(dimension)
    intents = _parse_csv(intent)
    return AnalysisFilters(
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        engines=tuple(engines) if engines else None,
        segment_id=segment_id or None,
        profile_id=profile_id or None,
        dimensions=tuple(dimensions) if dimensions else None,
        intents=tuple(intents) if intents else None,
        prompt_scope=prompt_scope or None,
    )


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
    brand_id: int | None = Query(None),
) -> BrandOverviewOut:
    """Brand Overview composite — KPI cards + 30d trends + top prompts.

    Optional `brand_id` overrides the project's primary brand for the
    duration of this request — feeds the dashboard's brand picker
    (cross-industry brand viewing). Project ownership is still
    enforced; the override only swaps which brand's metrics are pulled.
    """
    project = await service.get_project_for_user(session, user, project_id)
    return await get_brand_overview(session, project, brand_id_override=brand_id)


# ── Phase 2.2 ────────────────────────────────────────────────────


@router.get("/{project_id}/metrics", response_model=MetricsOut)
async def project_metrics(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    series: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    engine: str | None = Query(None),
    brand_id: int | None = Query(None),
    segment_id: str | None = Query(None),
    profile_id: str | None = Query(None),
    dimension: str | None = Query(None),
    intent: str | None = Query(None),
    prompt_scope: str | None = Query(None),
) -> MetricsOut:
    """Optional `brand_id` overrides the project's primary brand —
    same semantics as `/overview` (dashboard brand picker)."""
    project = await service.get_project_for_user(session, user, project_id)
    return await get_metrics(
        session,
        project,
        series=_parse_csv(series),
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        engines=_parse_csv(engine),
        brand_id_override=brand_id,
        filters=_analysis_filters(
            from_=from_,
            to=to,
            engine=engine,
            segment_id=segment_id,
            profile_id=profile_id,
            dimension=dimension,
            intent=intent,
            prompt_scope=prompt_scope,
        ),
    )


@router.get("/{project_id}/topics", response_model=TopicsOut)
async def project_topics(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> TopicsOut:
    project = await service.get_project_for_user(session, user, project_id)
    return await get_topics(session, project)


@router.get("/{project_id}/topics/monitoring", response_model=TopicMonitoringOut)
async def project_topic_monitoring(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    engine: str | None = Query(None),
    segment_id: str | None = Query(None),
    profile_id: str | None = Query(None),
    dimension: str | None = Query(None),
    intent: str | None = Query(None),
    prompt_scope: str | None = Query(None),
    brand_id: int | None = Query(None),
) -> TopicMonitoringOut:
    project = await service.get_project_for_user(session, user, project_id)
    return await get_topic_monitoring(
        session,
        project,
        filters=_analysis_filters(
            from_=from_,
            to=to,
            engine=engine,
            segment_id=segment_id,
            profile_id=profile_id,
            dimension=dimension,
            intent=intent,
            prompt_scope=prompt_scope,
        ),
        brand_id_override=brand_id,
    )


@router.get("/{project_id}/topics/{topic_id}/prompts", response_model=TopicPromptsOut)
async def project_topic_prompts(
    project_id: str,
    topic_id: int,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    engine: str | None = Query(None),
    segment_id: str | None = Query(None),
    profile_id: str | None = Query(None),
    dimension: str | None = Query(None),
    intent: str | None = Query(None),
    prompt_scope: str | None = Query(None),
    brand_id: int | None = Query(None),
) -> TopicPromptsOut:
    project = await service.get_project_for_user(session, user, project_id)
    return await get_topic_prompts(
        session,
        project,
        topic_id=topic_id,
        filters=_analysis_filters(
            from_=from_,
            to=to,
            engine=engine,
            segment_id=segment_id,
            profile_id=profile_id,
            dimension=dimension,
            intent=intent,
            prompt_scope=prompt_scope,
        ),
        brand_id_override=brand_id,
    )


@router.get("/{project_id}/prompts/{prompt_id}/queries", response_model=PromptQueriesOut)
async def project_prompt_queries(
    project_id: str,
    prompt_id: int,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    engine: str | None = Query(None),
    segment_id: str | None = Query(None),
    profile_id: str | None = Query(None),
    dimension: str | None = Query(None),
    intent: str | None = Query(None),
    prompt_scope: str | None = Query(None),
    brand_id: int | None = Query(None),
) -> PromptQueriesOut:
    project = await service.get_project_for_user(session, user, project_id)
    return await get_prompt_queries(
        session,
        project,
        prompt_id=prompt_id,
        filters=_analysis_filters(
            from_=from_,
            to=to,
            engine=engine,
            segment_id=segment_id,
            profile_id=profile_id,
            dimension=dimension,
            intent=intent,
            prompt_scope=prompt_scope,
        ),
        brand_id_override=brand_id,
    )


@router.get("/{project_id}/queries/{query_id}/response", response_model=QueryResponseDetailOut)
async def project_query_response(
    project_id: str,
    query_id: int,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    brand_id: int | None = Query(None),
) -> QueryResponseDetailOut:
    project = await service.get_project_for_user(session, user, project_id)
    return await get_query_response_detail(
        session,
        project,
        query_id=query_id,
        brand_id_override=brand_id,
    )


@router.get("/{project_id}/query-activity", response_model=QueryActivityOut)
async def project_query_activity(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    engine: str | None = Query(None),
    segment_id: str | None = Query(None),
    profile_id: str | None = Query(None),
    dimension: str | None = Query(None),
    intent: str | None = Query(None),
    prompt_scope: str | None = Query(None),
    brand_id: int | None = Query(None),
) -> QueryActivityOut:
    project = await service.get_project_for_user(session, user, project_id)
    return await get_query_activity(
        session,
        project,
        filters=_analysis_filters(
            from_=from_,
            to=to,
            engine=engine,
            segment_id=segment_id,
            profile_id=profile_id,
            dimension=dimension,
            intent=intent,
            prompt_scope=prompt_scope,
        ),
        brand_id_override=brand_id,
    )


@router.get("/{project_id}/segments", response_model=ProjectSegmentsOut)
async def project_segments(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    brand_id: int | None = Query(None),
) -> ProjectSegmentsOut:
    project = await service.get_project_for_user(session, user, project_id)
    return await get_project_segments(session, project, brand_id_override=brand_id)


@router.get("/{project_id}/sentiment", response_model=SentimentOut)
async def project_sentiment(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    brand_id: int | None = Query(None),
) -> SentimentOut:
    project = await service.get_project_for_user(session, user, project_id)
    return await get_sentiment(
        session,
        project,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        brand_id_override=brand_id,
    )


@router.get("/{project_id}/citations", response_model=CitationsOut)
async def project_citations(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    brand_id: int | None = Query(None),
    page_size: int = Query(50, ge=1, le=500),
) -> CitationsOut:
    project = await service.get_project_for_user(session, user, project_id)
    return await get_citations(
        session,
        project,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        brand_id_override=brand_id,
        page_size=page_size,
    )


# ── Phase 2.3 ────────────────────────────────────────────────────


@router.get("/{project_id}/products", response_model=ProductsOut)
async def project_products(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    brand_id: int | None = Query(None),
) -> ProductsOut:
    """SKU-level rollup with top features + scenarios (PRD §4.6.1f)."""
    project = await service.get_project_for_user(session, user, project_id)
    return await get_products(
        session,
        project,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        brand_id_override=brand_id,
    )


@router.get(
    "/{project_id}/competitors/metrics",
    response_model=CompetitorMetricsOut,
)
async def project_competitor_metrics(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    brand_id: int | None = Query(None),
    engine: str | None = Query(None),
    segment_id: str | None = Query(None),
    profile_id: str | None = Query(None),
    dimension: str | None = Query(None),
    intent: str | None = Query(None),
    prompt_scope: str | None = Query(None),
) -> CompetitorMetricsOut:
    """Primary brand vs each pinned competitor across 4 metrics (PRD §4.6.1g)."""
    project = await service.get_project_for_user(session, user, project_id)
    return await get_competitor_metrics(
        session,
        project,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        brand_id_override=brand_id,
        filters=_analysis_filters(
            from_=from_,
            to=to,
            engine=engine,
            segment_id=segment_id,
            profile_id=profile_id,
            dimension=dimension,
            intent=intent,
            prompt_scope=prompt_scope,
        ),
    )


@router.get(
    "/{project_id}/competitors/trends",
    response_model=CompetitorTrendsOut,
)
async def project_competitor_trends(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    metric: str = Query("geo_score"),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    brand_id: int | None = Query(None),
    engine: str | None = Query(None),
    segment_id: str | None = Query(None),
    profile_id: str | None = Query(None),
    dimension: str | None = Query(None),
    intent: str | None = Query(None),
    prompt_scope: str | None = Query(None),
) -> CompetitorTrendsOut:
    """Per-brand 30-day trend for primary + each pinned competitor.

    Reads geo_score_daily so the FE PanoTrendChart can plot real
    pipeline data with one series per available competitor.
    """
    project = await service.get_project_for_user(session, user, project_id)
    return await get_competitor_trends(
        session,
        project,
        metric=metric,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        brand_id_override=brand_id,
    )


@router.get("/{project_id}/diagnostics", response_model=DiagnosticsOut)
async def project_diagnostics(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
) -> DiagnosticsOut:
    """Derived diagnostics list (Phase 2.3 stub; Phase D wires real engine)."""
    project = await service.get_project_for_user(session, user, project_id)
    return await get_diagnostics(
        session,
        project,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
    )


# ── Phase 5: Chart-data endpoints ────────────────────────────────


@router.get("/{project_id}/metrics/by-engine", response_model=EngineMetricsOut)
async def project_engine_metrics(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    engine: str | None = Query(None),
    segment_id: str | None = Query(None),
    profile_id: str | None = Query(None),
    brand_id: int | None = Query(None),
) -> EngineMetricsOut:
    project = await service.get_project_for_user(session, user, project_id)
    return await get_engine_metrics(
        session,
        project,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        engines=_parse_csv(engine),
        segment_id=segment_id,
        profile_id=profile_id,
        brand_id_override=brand_id,
    )


@router.get(
    "/{project_id}/position-distribution",
    response_model=PositionDistributionOut,
)
async def project_position_distribution(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    engine: str | None = Query(None),
    segment_id: str | None = Query(None),
    profile_id: str | None = Query(None),
    brand_id: int | None = Query(None),
) -> PositionDistributionOut:
    project = await service.get_project_for_user(session, user, project_id)
    return await get_position_distribution(
        session,
        project,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        engines=_parse_csv(engine),
        segment_id=segment_id,
        profile_id=profile_id,
        brand_id_override=brand_id,
    )


@router.get("/{project_id}/topic-heatmap", response_model=TopicHeatmapOut)
async def project_topic_heatmap(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    metric: str = Query("mention_rate"),
    compare_with: str | None = Query(None),
    top_n: int = Query(8, ge=1, le=30),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    brand_id: int | None = Query(None),
) -> TopicHeatmapOut:
    project = await service.get_project_for_user(session, user, project_id)
    cw = None
    if compare_with:
        try:
            cw = [int(x) for x in compare_with.split(",") if x.strip()]
        except ValueError as exc:
            raise validation_error("compare_with", "must be CSV of integer brand_ids") from exc
    return await get_topic_heatmap(
        session,
        project,
        metric=metric,
        compare_with=cw,
        top_n=top_n,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        brand_id_override=brand_id,
    )


@router.get("/{project_id}/sentiment/by-engine", response_model=SentimentByEngineOut)
async def project_sentiment_by_engine(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    engine: str | None = Query(None),
    segment_id: str | None = Query(None),
    profile_id: str | None = Query(None),
    brand_id: int | None = Query(None),
) -> SentimentByEngineOut:
    project = await service.get_project_for_user(session, user, project_id)
    return await get_sentiment_by_engine(
        session,
        project,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        engines=_parse_csv(engine),
        segment_id=segment_id,
        profile_id=profile_id,
        brand_id_override=brand_id,
    )


@router.get(
    "/{project_id}/sentiment/trend-by-engine",
    response_model=SentimentTrendByEngineOut,
)
async def project_sentiment_trend_by_engine(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    engine: str | None = Query(None),
    segment_id: str | None = Query(None),
    profile_id: str | None = Query(None),
    brand_id: int | None = Query(None),
) -> SentimentTrendByEngineOut:
    project = await service.get_project_for_user(session, user, project_id)
    return await get_sentiment_trend_by_engine(
        session,
        project,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        engines=_parse_csv(engine),
        segment_id=segment_id,
        profile_id=profile_id,
        brand_id_override=brand_id,
    )


@router.get(
    "/{project_id}/sentiment/topic-attribution",
    response_model=TopicAttributionOut,
)
async def project_topic_attribution(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    engine: str | None = Query(None),
    segment_id: str | None = Query(None),
    profile_id: str | None = Query(None),
    brand_id: int | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
) -> TopicAttributionOut:
    project = await service.get_project_for_user(session, user, project_id)
    return await get_topic_attribution(
        session,
        project,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        engines=_parse_csv(engine),
        segment_id=segment_id,
        profile_id=profile_id,
        brand_id_override=brand_id,
        limit=limit,
    )


@router.get("/{project_id}/mention-samples", response_model=MentionSamplesOut)
async def project_mention_samples(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    polarity: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
) -> MentionSamplesOut:
    project = await service.get_project_for_user(session, user, project_id)
    return await get_mention_samples(
        session,
        project,
        polarity=polarity,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        limit=limit,
    )


@router.get(
    "/{project_id}/citations/authority-trend",
    response_model=AuthorityTrendOut,
)
async def project_authority_trend(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    engine: str | None = Query(None),
    segment_id: str | None = Query(None),
    profile_id: str | None = Query(None),
) -> AuthorityTrendOut:
    project = await service.get_project_for_user(session, user, project_id)
    return await get_authority_trend(
        session,
        project,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        engines=_parse_csv(engine),
        segment_id=segment_id,
        profile_id=profile_id,
    )


@router.get(
    "/{project_id}/citations/composition",
    response_model=CitationCompositionOut,
)
async def project_citation_composition(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    engine: str | None = Query(None),
    segment_id: str | None = Query(None),
    profile_id: str | None = Query(None),
    brand_id: int | None = Query(None),
) -> CitationCompositionOut:
    project = await service.get_project_for_user(session, user, project_id)
    return await get_citation_composition(
        session,
        project,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        engines=_parse_csv(engine),
        segment_id=segment_id,
        profile_id=profile_id,
        brand_id_override=brand_id,
    )


@router.get("/{project_id}/citations/content-gap", response_model=ContentGapOut)
async def project_content_gap(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    engine: str | None = Query(None),
    segment_id: str | None = Query(None),
    profile_id: str | None = Query(None),
    limit: int = Query(12, ge=1, le=50),
) -> ContentGapOut:
    project = await service.get_project_for_user(session, user, project_id)
    return await get_content_gap(
        session,
        project,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
        engines=_parse_csv(engine),
        segment_id=segment_id,
        profile_id=profile_id,
        limit=limit,
    )


@router.get("/{project_id}/citations/pr-targets", response_model=PrTargetsOut)
async def project_pr_targets(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
) -> PrTargetsOut:
    project = await service.get_project_for_user(session, user, project_id)
    return await get_pr_targets(
        session,
        project,
        from_date=_parse_date(from_, "from"),
        to_date=_parse_date(to, "to"),
    )


@router.get(
    "/{project_id}/citations/simulator-baseline",
    response_model=SimulatorBaselineOut,
)
async def project_simulator_baseline(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> SimulatorBaselineOut:
    project = await service.get_project_for_user(session, user, project_id)
    return await get_simulator_baseline(session, project)


@router.get(
    "/{project_id}/competitors/authority-radar",
    response_model=AuthorityRadarOut,
)
async def project_authority_radar(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> AuthorityRadarOut:
    project = await service.get_project_for_user(session, user, project_id)
    return await get_authority_radar(session, project)


@router.get(
    "/{project_id}/group-shared-domains",
    response_model=GroupSharedDomainsOut,
)
async def project_group_shared_domains(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> GroupSharedDomainsOut:
    project = await service.get_project_for_user(session, user, project_id)
    return await get_group_shared_domains(session, project)


@router.get(
    "/{project_id}/products/relations",
    response_model=ProductRelationsOut,
)
async def project_product_relations(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> ProductRelationsOut:
    project = await service.get_project_for_user(session, user, project_id)
    return await get_product_relations(session, project)
