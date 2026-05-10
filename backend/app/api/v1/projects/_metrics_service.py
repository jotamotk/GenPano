"""Services for Brand metrics / topics / sentiment / citations (Phase 2.2).

Each service function is callable independently from MCP tools + Reports
(reusable per ADR-009 design).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import TypedDict

from genpano_models import (
    BrandMention,
    CitationSource,
    DomainAuthority,
    GeoScoreDaily,
    Project,
    ProjectTopicPin,
    ResponseAnalysis,
    SentimentDriver,
    TopicScoreDaily,
)
from sqlalchemy import and_, case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._legacy_lookups import resolve_topic_names
from app.api.v1.projects._mention_rollups import (
    brand_mention_daily_rollups,
    metric_value,
)
from app.api.v1.projects._topic_analysis_service import (
    AnalysisFilters,
    _as_float,
    _as_int,
    _date_key,
    _fact_all_mention_count,
    _fact_rows,
    _fact_target_mention_count,
    _has_admin_chain,
    _is_non_branded_row,
)
from app.api.v1.projects._metrics_dto import (
    CitationDomainRow,
    CitationRow,
    CitationsOut,
    MetricSeries,
    MetricSeriesPoint,
    MetricsOut,
    SentimentDistribution,
    SentimentDriverRow,
    SentimentKeywordRow,
    SentimentOut,
    SentimentTrendPoint,
    TopicRow,
    TopicsOut,
)

DEFAULT_WINDOW_DAYS = 30
ALLOWED_METRICS = {"mention_rate", "sov", "rank", "sentiment", "citation"}
METRIC_TO_COLUMN = {
    "mention_rate": GeoScoreDaily.mention_rate,
    "sov": GeoScoreDaily.avg_sov,
    "rank": GeoScoreDaily.avg_position_rank,
    "sentiment": GeoScoreDaily.avg_sentiment,
    "citation": GeoScoreDaily.citation_rate,
}


def _period(from_d: date, to_d: date) -> dict[str, str]:
    return {"from": from_d.isoformat(), "to": to_d.isoformat()}


def _resolve_window(from_date: date | None, to_date: date | None) -> tuple[date, date]:
    today = date.today()
    to_d = to_date or today
    from_d = from_date or (to_d - timedelta(days=DEFAULT_WINDOW_DAYS - 1))
    return from_d, to_d


def _metric_filters(
    filters: AnalysisFilters | None,
    *,
    from_d: date,
    to_d: date,
    engines: list[str] | None,
) -> AnalysisFilters:
    base = filters or AnalysisFilters()
    engine_tuple = base.engines
    if engine_tuple is None and engines:
        engine_tuple = tuple(engines)
    return replace(
        base,
        from_date=base.from_date or from_d,
        to_date=base.to_date or to_d,
        engines=engine_tuple,
    )


def _fact_metric_value(metric: str, bucket: dict[str, object]) -> float | None:
    if metric == "mention_rate":
        denominator = len(bucket["mention_denominator_response_ids"])  # type: ignore[arg-type]
        if denominator <= 0:
            return None
        return round(
            len(bucket["target_mention_response_ids"]) / denominator, 4,  # type: ignore[arg-type]
        )
    if metric == "sov":
        all_mentions = int(bucket["all_mentions"] or 0)
        if all_mentions <= 0:
            return None
        return round(float(bucket["target_mentions"] or 0) / all_mentions, 4)
    if metric == "rank":
        ranks = bucket["ranks"]  # type: ignore[assignment]
        if not ranks:
            return None
        return round(sum(ranks) / len(ranks), 4)
    if metric == "sentiment":
        scores = bucket["sentiment_scores"]  # type: ignore[assignment]
        if not scores:
            return None
        return round(sum(scores) / len(scores), 4)
    if metric == "citation":
        response_count = len(bucket["response_ids"])  # type: ignore[arg-type]
        if response_count <= 0:
            return None
        return round(float(bucket["citation_count"] or 0) / response_count, 4)
    return None


async def _metrics_from_admin_facts(
    session: AsyncSession,
    project: Project,
    *,
    brand_id: int,
    brand_id_override: int | None,
    requested: list[str],
    from_d: date,
    to_d: date,
    filters: AnalysisFilters,
) -> MetricsOut:
    rows = await _fact_rows(
        session,
        project,
        filters=filters,
        brand_id_override=brand_id_override,
    )
    buckets: dict[str, dict[str, object]] = {}
    seen_response_ids: set[int] = set()

    for row in rows:
        response_id = _as_int(row.get("response_id"))
        if response_id is None or response_id in seen_response_ids:
            continue
        seen_response_ids.add(response_id)
        day = _date_key(
            row.get("response_created_at")
            or row.get("query_finished_at")
            or row.get("query_created_at")
        )
        if day is None:
            continue
        bucket = buckets.setdefault(
            day,
            {
                "response_ids": set(),
                "mention_denominator_response_ids": set(),
                "target_mention_response_ids": set(),
                "target_mentions": 0,
                "all_mentions": 0,
                "ranks": [],
                "sentiment_scores": [],
                "citation_count": 0,
            },
        )
        bucket["response_ids"].add(response_id)  # type: ignore[attr-defined]
        target_mentions = _fact_target_mention_count(row)
        all_mentions = _fact_all_mention_count(row, target_mentions)
        bucket["target_mentions"] = int(bucket["target_mentions"] or 0) + target_mentions
        bucket["all_mentions"] = int(bucket["all_mentions"] or 0) + all_mentions
        if _is_non_branded_row(row):
            bucket["mention_denominator_response_ids"].add(response_id)  # type: ignore[attr-defined]
            if target_mentions > 0:
                bucket["target_mention_response_ids"].add(response_id)  # type: ignore[attr-defined]
        rank = _as_int(row.get("min_position_rank") or row.get("target_brand_rank"))
        if rank is not None:
            bucket["ranks"].append(float(rank))  # type: ignore[attr-defined]
        sentiment = _as_float(row.get("sentiment_score"))
        if sentiment is not None:
            bucket["sentiment_scores"].append(sentiment)  # type: ignore[attr-defined]
        bucket["citation_count"] = int(bucket["citation_count"] or 0) + int(
            row.get("citation_count") or 0
        )

    out_series: list[MetricSeries] = []
    for metric in requested:
        points: list[MetricSeriesPoint] = []
        for day in sorted(buckets):
            value = _fact_metric_value(metric, buckets[day])
            if value is None:
                continue
            points.append(MetricSeriesPoint(date=date.fromisoformat(day), value=value))
        out_series.append(MetricSeries(metric=metric, points=points))

    return MetricsOut(
        project_id=project.id,
        brand_id=brand_id,
        period=_period(from_d, to_d),
        engines=list(filters.engines) if filters.engines else None,
        series=out_series,
        state="ok" if any(series.points for series in out_series) else "empty",
    )


# ─── /metrics ──────────────────────────────────────────────────────
async def get_metrics(
    session: AsyncSession,
    project: Project,
    *,
    series: list[str] | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    engines: list[str] | None = None,
    brand_id_override: int | None = None,
    filters: AnalysisFilters | None = None,
) -> MetricsOut:
    """`brand_id_override` lets the dashboard brand picker swap the
    primary brand for KPI / trend pulls without leaving the project."""
    from_d, to_d = _resolve_window(from_date, to_date)
    requested = series or ["mention_rate", "sov", "rank", "sentiment", "citation"]
    requested = [m for m in requested if m in ALLOWED_METRICS]

    primary_brand_id = (
        brand_id_override if brand_id_override is not None else project.primary_brand_id
    )
    if primary_brand_id is None:
        return MetricsOut(
            project_id=project.id,
            brand_id=None,
            period=_period(from_d, to_d),
            engines=engines,
            series=[MetricSeries(metric=m, points=[]) for m in requested],
            state="empty",
        )

    analysis_filters = _metric_filters(
        filters,
        from_d=from_d,
        to_d=to_d,
        engines=engines,
    )
    if await _has_admin_chain(session):
        fact_metrics = await _metrics_from_admin_facts(
            session,
            project,
            brand_id=primary_brand_id,
            brand_id_override=brand_id_override,
            requested=requested,
            from_d=from_d,
            to_d=to_d,
            filters=analysis_filters,
        )
        if fact_metrics.state != "empty":
            return fact_metrics

    out_series: list[MetricSeries] = []
    for metric in requested:
        col = METRIC_TO_COLUMN[metric]
        stmt = select(GeoScoreDaily.date, func.avg(col)).where(
            and_(
                GeoScoreDaily.brand_id == primary_brand_id,
                GeoScoreDaily.date >= datetime.combine(from_d, datetime.min.time()),
                GeoScoreDaily.date <= datetime.combine(to_d, datetime.max.time()),
            )
        )
        if engines:
            stmt = stmt.where(GeoScoreDaily.target_llm.in_(engines))
        stmt = stmt.group_by(GeoScoreDaily.date).order_by(GeoScoreDaily.date)
        rows = (await session.execute(stmt)).all()
        points = []
        for r in rows:
            d = r[0]
            if isinstance(d, datetime):
                d = d.date()
            elif isinstance(d, str):
                d = date.fromisoformat(d)
            points.append(MetricSeriesPoint(date=d, value=round(r[1] or 0, 4)))
        if not points:
            rollups = await brand_mention_daily_rollups(
                session,
                primary_brand_id,
                from_d,
                to_d,
            )
            points = [
                MetricSeriesPoint(
                    date=date.fromisoformat(day),
                    value=metric_value(rollup, metric),
                )
                for day, rollup in sorted(rollups.items())
                if rollup.has_data
            ]
        out_series.append(MetricSeries(metric=metric, points=points))

    has_data = any(s.points for s in out_series)
    return MetricsOut(
        project_id=project.id,
        brand_id=primary_brand_id,
        period=_period(from_d, to_d),
        engines=engines,
        series=out_series,
        state="ok" if has_data else "empty",
    )


# ─── /topics ───────────────────────────────────────────────────────
async def get_topics(
    session: AsyncSession,
    project: Project,
) -> TopicsOut:
    """List project topics + pin state with real mention/sentiment/position aggregates.

    Pin state still comes from `project_topic_pins`. Mention stats now come from
    `topic_score_daily` (populated by Aggregator._aggregate_topic_daily) for the
    project's primary brand over the most recent 30-day window.
    """
    stmt = (
        select(ProjectTopicPin)
        .where(ProjectTopicPin.project_id == project.id)
        .order_by(ProjectTopicPin.pinned_at.desc())
    )
    pins = list((await session.execute(stmt)).scalars().all())

    # Aggregate per topic over the last 30 days for the project's primary brand.
    class _TopicAgg(TypedDict):
        mention_count: int
        avg_sentiment: float | None
        avg_position_rank: float | None
        last_seen_at: str | None

    aggregates: dict[int, _TopicAgg] = {}
    if pins and project.primary_brand_id is not None:
        topic_ids = [p.topic_id for p in pins]
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=DEFAULT_WINDOW_DAYS)
        stmt_agg = (
            select(
                TopicScoreDaily.topic_id,
                func.sum(TopicScoreDaily.mention_count).label("mention_count"),
                func.avg(TopicScoreDaily.avg_sentiment_score).label("avg_sentiment"),
                func.avg(TopicScoreDaily.avg_position_rank).label("avg_position_rank"),
                func.max(TopicScoreDaily.date).label("last_seen_at"),
            )
            .where(
                TopicScoreDaily.brand_id == project.primary_brand_id,
                TopicScoreDaily.topic_id.in_(topic_ids),
                TopicScoreDaily.date >= cutoff,
            )
            .group_by(TopicScoreDaily.topic_id)
        )
        for row in (await session.execute(stmt_agg)).all():
            avg_sent = float(row.avg_sentiment) if row.avg_sentiment is not None else None
            avg_rank = float(row.avg_position_rank) if row.avg_position_rank is not None else None
            last_seen = row.last_seen_at.isoformat() if row.last_seen_at is not None else None
            aggregates[row.topic_id] = _TopicAgg(
                mention_count=int(row.mention_count or 0),
                avg_sentiment=avg_sent,
                avg_position_rank=avg_rank,
                last_seen_at=last_seen,
            )

    name_map = await resolve_topic_names(session, [p.topic_id for p in pins])
    items = []
    for p in pins:
        agg = aggregates.get(p.topic_id)
        items.append(
            TopicRow(
                topic_id=p.topic_id,
                topic_name=name_map.get(p.topic_id) or f"topic-{p.topic_id}",
                state=p.state,
                mention_count=agg["mention_count"] if agg else 0,
                avg_sentiment=agg["avg_sentiment"] if agg else None,
                avg_position_rank=agg["avg_position_rank"] if agg else None,
                last_seen_at=agg["last_seen_at"] if agg else None,
            )
        )
    return TopicsOut(
        project_id=project.id,
        items=items,
        total=len(items),
        state="ok" if items else "empty",
    )


# ─── /sentiment ────────────────────────────────────────────────────
async def get_sentiment(
    session: AsyncSession,
    project: Project,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> SentimentOut:
    from_d, to_d = _resolve_window(from_date, to_date)

    if project.primary_brand_id is None:
        return SentimentOut(
            project_id=project.id,
            brand_id=None,
            period=_period(from_d, to_d),
            distribution=SentimentDistribution(
                positive_count=0,
                neutral_count=0,
                negative_count=0,
                positive_pct=0.0,
                neutral_pct=0.0,
                negative_pct=0.0,
                avg_sentiment_score=0.0,
            ),
            trend_30d=[],
            top_keywords=[],
            top_drivers=[],
            state="empty",
        )

    brand_id = project.primary_brand_id

    # ── distribution: aggregate brand_mentions.sentiment for this brand ─
    stmt_dist = (
        select(
            BrandMention.sentiment,
            func.count().label("cnt"),
            func.avg(BrandMention.sentiment_score).label("avg_score"),
        )
        .where(
            and_(
                BrandMention.brand_id == brand_id,
                BrandMention.created_at >= datetime.combine(from_d, datetime.min.time()),
                BrandMention.created_at <= datetime.combine(to_d, datetime.max.time()),
            )
        )
        .group_by(BrandMention.sentiment)
    )
    dist_rows = (await session.execute(stmt_dist)).all()

    pos = neu = neg = 0
    total_score = 0.0
    n_for_avg = 0
    for r in dist_rows:
        sent, cnt, avg = r[0], int(r[1] or 0), r[2]
        if sent == "positive":
            pos = cnt
        elif sent == "negative":
            neg = cnt
        elif sent == "neutral":
            neu = cnt
        if avg is not None and cnt:
            total_score += float(avg) * cnt
            n_for_avg += cnt
    total = pos + neu + neg
    dist = SentimentDistribution(
        positive_count=pos,
        neutral_count=neu,
        negative_count=neg,
        positive_pct=round(pos / total * 100, 1) if total else 0.0,
        neutral_pct=round(neu / total * 100, 1) if total else 0.0,
        negative_pct=round(neg / total * 100, 1) if total else 0.0,
        avg_sentiment_score=round(total_score / n_for_avg, 3) if n_for_avg else 0.0,
    )

    # ── trend_30d: per-day pos pct + neg pct + avg score ─────────────
    bucket = func.date(BrandMention.created_at)
    stmt_trend = (
        select(
            bucket.label("d"),
            func.sum(case((BrandMention.sentiment == "positive", 1), else_=0)).label("pos"),
            func.sum(case((BrandMention.sentiment == "negative", 1), else_=0)).label("neg"),
            func.count().label("total"),
            func.avg(BrandMention.sentiment_score).label("avg_score"),
        )
        .where(
            and_(
                BrandMention.brand_id == brand_id,
                BrandMention.created_at >= datetime.combine(from_d, datetime.min.time()),
                BrandMention.created_at <= datetime.combine(to_d, datetime.max.time()),
            )
        )
        .group_by(bucket)
        .order_by(bucket)
    )
    trend_rows = (await session.execute(stmt_trend)).all()
    trend = []
    for r in trend_rows:
        d = r[0]
        if isinstance(d, str):
            d = date.fromisoformat(d)
        elif isinstance(d, datetime):
            d = d.date()
        t = r[3] or 1
        trend.append(
            SentimentTrendPoint(
                date=d,
                positive_pct=round((r[1] or 0) / t * 100, 1),
                negative_pct=round((r[2] or 0) / t * 100, 1),
                avg_score=round(r[4] or 0, 3),
            )
        )

    # ── top_keywords: from sentiment_drivers (driver_text aggregated) ─
    stmt_kw = (
        select(
            SentimentDriver.driver_text,
            SentimentDriver.polarity,
            func.count().label("cnt"),
            func.avg(SentimentDriver.strength).label("avg_strength"),
        )
        .where(
            and_(
                SentimentDriver.brand_name.isnot(None),
                SentimentDriver.created_at >= datetime.combine(from_d, datetime.min.time()),
                SentimentDriver.created_at <= datetime.combine(to_d, datetime.max.time()),
            )
        )
        .group_by(SentimentDriver.driver_text, SentimentDriver.polarity)
        .order_by(desc("cnt"))
        .limit(10)
    )
    kw_rows = (await session.execute(stmt_kw)).all()
    top_keywords = [
        SentimentKeywordRow(
            keyword=r[0],
            polarity=r[1],
            count=int(r[2] or 0),
            avg_strength=round(r[3], 2) if r[3] else None,
        )
        for r in kw_rows
    ]

    # ── top_drivers: same source, group by category instead ──────────
    stmt_drv = (
        select(
            SentimentDriver.driver_text,
            SentimentDriver.polarity,
            SentimentDriver.category,
            func.count().label("cnt"),
            func.avg(SentimentDriver.strength).label("avg_strength"),
        )
        .where(
            and_(
                SentimentDriver.brand_name.isnot(None),
                SentimentDriver.created_at >= datetime.combine(from_d, datetime.min.time()),
                SentimentDriver.created_at <= datetime.combine(to_d, datetime.max.time()),
            )
        )
        .group_by(
            SentimentDriver.driver_text,
            SentimentDriver.polarity,
            SentimentDriver.category,
        )
        .order_by(desc("cnt"))
        .limit(10)
    )
    drv_rows = (await session.execute(stmt_drv)).all()
    top_drivers = [
        SentimentDriverRow(
            driver_text=r[0],
            polarity=r[1],
            category=r[2],
            count=int(r[3] or 0),
            avg_strength=round(r[4], 2) if r[4] else None,
        )
        for r in drv_rows
    ]

    has_data = total > 0
    return SentimentOut(
        project_id=project.id,
        brand_id=brand_id,
        period=_period(from_d, to_d),
        distribution=dist,
        trend_30d=trend,
        top_keywords=top_keywords,
        top_drivers=top_drivers,
        state="ok" if has_data else "empty",
    )


# ─── /citations ────────────────────────────────────────────────────
async def get_citations(
    session: AsyncSession,
    project: Project,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    page_size: int = 50,
) -> CitationsOut:
    from_d, to_d = _resolve_window(from_date, to_date)

    if project.primary_brand_id is None:
        return CitationsOut(
            project_id=project.id,
            brand_id=None,
            period=_period(from_d, to_d),
            items=[],
            next_cursor=None,
            total=0,
            by_domain_top=[],
            state="empty",
        )

    brand_id = project.primary_brand_id

    # JOIN citation_sources via brand_mentions.id (mention_id FK)
    stmt = (
        select(CitationSource)
        .join(BrandMention, BrandMention.id == CitationSource.mention_id)
        .where(
            and_(
                BrandMention.brand_id == brand_id,
                CitationSource.created_at >= datetime.combine(from_d, datetime.min.time()),
                CitationSource.created_at <= datetime.combine(to_d, datetime.max.time()),
            )
        )
        .order_by(CitationSource.created_at.desc())
        .limit(page_size + 1)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > page_size
    items_raw = rows[:page_size]
    items = [
        CitationRow(
            citation_id=c.id,
            response_id=c.response_id,
            url=c.url,
            domain=c.domain,
            title=c.title,
            source_type=c.source_type,
            occurred_at=c.created_at.isoformat() if c.created_at else None,
        )
        for c in items_raw
    ]

    # Top domains (with tier from domain_authorities)
    stmt_dom = (
        select(
            CitationSource.domain,
            func.count().label("cnt"),
            func.max(DomainAuthority.tier).label("tier"),
        )
        .join(BrandMention, BrandMention.id == CitationSource.mention_id)
        .outerjoin(DomainAuthority, DomainAuthority.domain == CitationSource.domain)
        .where(
            and_(
                BrandMention.brand_id == brand_id,
                CitationSource.created_at >= datetime.combine(from_d, datetime.min.time()),
                CitationSource.created_at <= datetime.combine(to_d, datetime.max.time()),
                CitationSource.domain.isnot(None),
            )
        )
        .group_by(CitationSource.domain)
        .order_by(desc("cnt"))
        .limit(10)
    )
    dom_rows = (await session.execute(stmt_dom)).all()
    by_domain = [
        CitationDomainRow(
            domain=r[0],
            count=int(r[1] or 0),
            tier=int(r[2]) if r[2] is not None else None,
        )
        for r in dom_rows
    ]

    # Total count
    stmt_total = (
        select(func.count())
        .select_from(CitationSource)
        .join(BrandMention, BrandMention.id == CitationSource.mention_id)
        .where(
            and_(
                BrandMention.brand_id == brand_id,
                CitationSource.created_at >= datetime.combine(from_d, datetime.min.time()),
                CitationSource.created_at <= datetime.combine(to_d, datetime.max.time()),
            )
        )
    )
    total = int((await session.execute(stmt_total)).scalar_one() or 0)

    return CitationsOut(
        project_id=project.id,
        brand_id=brand_id,
        period=_period(from_d, to_d),
        items=items,
        next_cursor=str(items[-1].citation_id) if has_more and items else None,
        total=total,
        by_domain_top=by_domain,
        state="ok" if total else "empty",
    )


# Minor service: ResponseAnalysis-based mention rate for /sentiment trend
# (kept here for interest; not exposed in DTO above)
__all__ = [
    "ResponseAnalysis",  # re-export for downstream MCP tools
    "get_citations",
    "get_metrics",
    "get_sentiment",
    "get_topics",
]
