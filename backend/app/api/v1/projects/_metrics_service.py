"""Services for Brand metrics / topics / sentiment / citations (Phase 2.2).

Each service function is callable independently from MCP tools + Reports
(reusable per ADR-009 design).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from genpano_models import (
    BrandMention,
    CitationSource,
    GeoScoreDaily,
    Project,
    ProjectTopicPin,
    ResponseAnalysis,
    SentimentDriver,
)
from sqlalchemy import and_, case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

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


# ─── /metrics ──────────────────────────────────────────────────────
async def get_metrics(
    session: AsyncSession,
    project: Project,
    *,
    series: list[str] | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    engines: list[str] | None = None,
) -> MetricsOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    requested = series or ["mention_rate", "sov", "rank", "sentiment", "citation"]
    requested = [m for m in requested if m in ALLOWED_METRICS]

    if project.primary_brand_id is None:
        return MetricsOut(
            project_id=project.id,
            brand_id=None,
            period=_period(from_d, to_d),
            engines=engines,
            series=[MetricSeries(metric=m, points=[]) for m in requested],
            state="empty",
        )

    out_series: list[MetricSeries] = []
    for metric in requested:
        col = METRIC_TO_COLUMN[metric]
        stmt = select(GeoScoreDaily.date, func.avg(col)).where(
            and_(
                GeoScoreDaily.brand_id == project.primary_brand_id,
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
        out_series.append(MetricSeries(metric=metric, points=points))

    has_data = any(s.points for s in out_series)
    return MetricsOut(
        project_id=project.id,
        brand_id=project.primary_brand_id,
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
    """List project topics + pin state.

    Phase 2.2 implementation reads `project_topic_pins`. The actual `topics`
    table is upstream (Tracker domain) and does not have an ORM in
    `genpano_models`; we synthesize topic_name from topic_id placeholder
    until Phase A.7 adds full Topic ORM.
    """
    stmt = (
        select(ProjectTopicPin)
        .where(ProjectTopicPin.project_id == project.id)
        .order_by(ProjectTopicPin.pinned_at.desc())
    )
    pins = list((await session.execute(stmt)).scalars().all())
    items = [
        TopicRow(
            topic_id=p.topic_id,
            topic_name=f"topic-{p.topic_id}",  # Phase A.7 fills real names
            state=p.state,
            mention_count=0,
            avg_sentiment=None,
            avg_position_rank=None,
            last_seen_at=None,
        )
        for p in pins
    ]
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

    # Top domains
    stmt_dom = (
        select(CitationSource.domain, func.count().label("cnt"))
        .join(BrandMention, BrandMention.id == CitationSource.mention_id)
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
    by_domain = [CitationDomainRow(domain=r[0], count=int(r[1] or 0)) for r in dom_rows]

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
