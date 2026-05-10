"""Services backing the chart-data endpoints (Phase 5 — Chart Wiring).

All endpoints below pull from existing tables (`geo_score_daily`,
`brand_mentions`, `topic_score_daily`, `citation_sources`, `domain_authorities`,
`geo_score_weekly`, `industry_benchmark_daily`, `brand_group_shared_domains`,
`kg_product_relations`). No new tables are introduced here; Phase 3 only adds
`kg_brands.positioning` for the segment ranking.
"""

from __future__ import annotations

from collections import OrderedDict, defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from genpano_models import (
    BrandGroup,
    BrandGroupMember,
    BrandGroupSharedDomain,
    BrandMention,
    CitationSource,
    DomainAuthority,
    GeoScoreDaily,
    GeoScoreWeekly,
    IndustryBenchmarkDaily,
    KgProduct,
    KgProductRelation,
    Project,
    ProjectCompetitor,
    TopicScoreDaily,
)
from sqlalchemy import and_, case, desc, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._charts_dto import (
    AuthorityRadarOut,
    AuthorityRadarRow,
    AuthorityTrendOut,
    AuthorityTrendPoint,
    CitationCompositionOut,
    CitationCompositionRow,
    ContentGapOut,
    ContentGapPageTypeRow,
    ContentGapTopicRow,
    EngineMetricRow,
    EngineMetricsOut,
    GroupSharedDomainEntry,
    GroupSharedDomainsOut,
    HeatmapCell,
    HeatmapRow,
    KolScorecard,
    MentionSampleRow,
    MentionSamplesOut,
    PositionBucketRow,
    PositionDistributionOut,
    ProductRelationRow,
    ProductRelationsOut,
    PrTargetRow,
    PrTargetsOut,
    SentimentByEngineOut,
    SentimentByEngineRow,
    SentimentTrendByEngineOut,
    SentimentTrendByEngineRow,
    SimulatorBaselineOut,
    SimulatorTierWeight,
    Tier2MatrixOut,
    Tier2MatrixRow,
    TopicAttributionOut,
    TopicAttributionRow,
    TopicHeatmapOut,
)
from app.api.v1.projects._legacy_lookups import (
    resolve_brand_industry,
    resolve_brand_names,
    resolve_topic_names,
)
from app.api.v1.projects._topic_analysis_service import (
    AnalysisFilters,
    _fact_rows,
    get_topic_monitoring,
)

DEFAULT_WINDOW_DAYS = 30


def _resolve_window(from_date: date | None, to_date: date | None) -> tuple[date, date]:
    today = date.today()
    to_d = to_date or today
    from_d = from_date or (to_d - timedelta(days=DEFAULT_WINDOW_DAYS - 1))
    return from_d, to_d


def _period(from_d: date, to_d: date) -> dict[str, str]:
    return {"from": from_d.isoformat(), "to": to_d.isoformat()}


def _dt_range(from_d: date, to_d: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(from_d, datetime.min.time()),
        datetime.combine(to_d, datetime.max.time()),
    )


def _admin_filters(
    from_d: date,
    to_d: date,
    *,
    engines: list[str] | None = None,
    segment_id: str | None = None,
    profile_id: str | None = None,
) -> AnalysisFilters:
    return AnalysisFilters(
        from_date=from_d,
        to_date=to_d,
        engines=tuple(engines) if engines else None,
        segment_id=segment_id,
        profile_id=profile_id,
    )


def _needs_admin_filter(
    *,
    engines: list[str] | None = None,
    segment_id: str | None = None,
    profile_id: str | None = None,
) -> bool:
    return bool(engines or segment_id or profile_id)


# ── /metrics/by-engine ──────────────────────────────────────────────
async def get_engine_metrics(
    session: AsyncSession,
    project: Project,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    engines: list[str] | None = None,
    segment_id: str | None = None,
    profile_id: str | None = None,
) -> EngineMetricsOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    if project.primary_brand_id is None:
        return EngineMetricsOut(
            project_id=project.id, period=_period(from_d, to_d), items=[], state="empty"
        )
    f, t = _dt_range(from_d, to_d)
    if _needs_admin_filter(engines=engines, segment_id=segment_id, profile_id=profile_id):
        rows = await _fact_rows(
            session,
            project,
            filters=_admin_filters(
                from_d,
                to_d,
                engines=engines,
                segment_id=segment_id,
                profile_id=profile_id,
            ),
        )
        bucket: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "responses": set(),
                "target_mentions": 0,
                "all_mentions": 0,
                "citations": 0,
                "sentiment": [],
            }
        )
        seen: set[int] = set()
        for row in rows:
            rid = row.get("response_id")
            if rid is None or int(rid) in seen:
                continue
            seen.add(int(rid))
            engine = str(row.get("target_llm") or row.get("response_target_llm") or "unknown")
            bucket[engine]["responses"].add(int(rid))
            bucket[engine]["target_mentions"] += int(row.get("target_mention_count") or 0)
            bucket[engine]["all_mentions"] += int(row.get("all_mention_count") or 0)
            bucket[engine]["citations"] += int(row.get("citation_count") or 0)
            if row.get("sentiment_score") is not None:
                bucket[engine]["sentiment"].append(float(row["sentiment_score"]))
        items = [
            EngineMetricRow(
                engine=engine,
                mention_rate=round(values["target_mentions"] / len(values["responses"]), 4)
                if values["responses"]
                else None,
                sov=round(values["target_mentions"] / values["all_mentions"], 4)
                if values["all_mentions"]
                else None,
                citation_rate=round(values["citations"] / len(values["responses"]), 4)
                if values["responses"]
                else None,
                sentiment=round(sum(values["sentiment"]) / len(values["sentiment"]), 3)
                if values["sentiment"]
                else None,
            )
            for engine, values in sorted(bucket.items())
        ]
        return EngineMetricsOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            items=items,
            state="ok" if items else "empty",
        )
    stmt = (
        select(
            GeoScoreDaily.target_llm,
            func.avg(GeoScoreDaily.mention_rate),
            func.avg(GeoScoreDaily.avg_sov),
            func.avg(GeoScoreDaily.citation_rate),
            func.avg(GeoScoreDaily.avg_sentiment),
        )
        .where(
            and_(
                GeoScoreDaily.brand_id == project.primary_brand_id,
                GeoScoreDaily.date >= f,
                GeoScoreDaily.date <= t,
                GeoScoreDaily.target_llm.isnot(None),
            )
        )
        .group_by(GeoScoreDaily.target_llm)
        .order_by(GeoScoreDaily.target_llm)
    )
    rows = (await session.execute(stmt)).all()
    items = [
        EngineMetricRow(
            engine=r[0] or "(unknown)",
            mention_rate=round(float(r[1]), 4) if r[1] is not None else None,
            sov=round(float(r[2]), 4) if r[2] is not None else None,
            citation_rate=round(float(r[3]), 4) if r[3] is not None else None,
            sentiment=round(float(r[4]), 3) if r[4] is not None else None,
        )
        for r in rows
    ]
    return EngineMetricsOut(
        project_id=project.id,
        period=_period(from_d, to_d),
        items=items,
        state="ok" if items else "empty",
    )


# ── /position-distribution ──────────────────────────────────────────
async def get_position_distribution(
    session: AsyncSession,
    project: Project,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    engines: list[str] | None = None,
    segment_id: str | None = None,
    profile_id: str | None = None,
) -> PositionDistributionOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    if project.primary_brand_id is None:
        return PositionDistributionOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            items=[],
            total_mentions=0,
            state="empty",
        )
    f, t = _dt_range(from_d, to_d)
    if _needs_admin_filter(engines=engines, segment_id=segment_id, profile_id=profile_id):
        rows = await _fact_rows(
            session,
            project,
            filters=_admin_filters(
                from_d,
                to_d,
                engines=engines,
                segment_id=segment_id,
                profile_id=profile_id,
            ),
        )
        buckets: OrderedDict[str, int] = OrderedDict(
            [("Top1", 0), ("Top3", 0), ("Top5", 0), ("Top10", 0), ("11+", 0), ("Unmentioned", 0)]
        )
        seen: set[int] = set()
        for row in rows:
            rid = row.get("response_id")
            if rid is None or int(rid) in seen:
                continue
            seen.add(int(rid))
            rank = row.get("min_position_rank") or row.get("target_brand_rank")
            if rank is None:
                buckets["Unmentioned"] += 1
            elif int(rank) == 1:
                buckets["Top1"] += 1
            elif int(rank) <= 3:
                buckets["Top3"] += 1
            elif int(rank) <= 5:
                buckets["Top5"] += 1
            elif int(rank) <= 10:
                buckets["Top10"] += 1
            else:
                buckets["11+"] += 1
        total = sum(buckets.values())
        return PositionDistributionOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            items=[
                PositionBucketRow(
                    bucket=k,
                    count=v,
                    pct=round((v / total * 100) if total else 0.0, 2),
                )
                for k, v in buckets.items()
            ],
            total_mentions=total,
            state="ok" if total else "empty",
        )
    stmt = (
        select(BrandMention.position_rank, func.count())
        .where(
            and_(
                BrandMention.brand_id == project.primary_brand_id,
                BrandMention.created_at >= f,
                BrandMention.created_at <= t,
            )
        )
        .group_by(BrandMention.position_rank)
    )
    rows = (await session.execute(stmt)).all()
    buckets: OrderedDict[str, int] = OrderedDict(
        [("Top1", 0), ("Top3", 0), ("Top5", 0), ("Top10", 0), ("11+", 0), ("Unmentioned", 0)]
    )
    total = 0
    for r in rows:
        rank = r[0]
        cnt = int(r[1] or 0)
        total += cnt
        if rank is None:
            buckets["Unmentioned"] += cnt
        elif rank == 1:
            buckets["Top1"] += cnt
        elif rank <= 3:
            buckets["Top3"] += cnt
        elif rank <= 5:
            buckets["Top5"] += cnt
        elif rank <= 10:
            buckets["Top10"] += cnt
        else:
            buckets["11+"] += cnt
    items = [
        PositionBucketRow(bucket=k, count=v, pct=round((v / total * 100) if total else 0.0, 2))
        for k, v in buckets.items()
    ]
    return PositionDistributionOut(
        project_id=project.id,
        period=_period(from_d, to_d),
        items=items,
        total_mentions=total,
        state="ok" if total else "empty",
    )


# ── /topic-heatmap ──────────────────────────────────────────────────
async def get_topic_heatmap(
    session: AsyncSession,
    project: Project,
    *,
    metric: str = "mention_rate",
    compare_with: list[int] | None = None,
    top_n: int = 8,
    from_date: date | None = None,
    to_date: date | None = None,
) -> TopicHeatmapOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    primary = project.primary_brand_id
    if primary is None:
        return TopicHeatmapOut(project_id=project.id, metric=metric, rows=[], state="empty")

    # If no explicit comparison list supplied, use pinned competitors (top 4).
    if compare_with is None:
        comp_stmt = select(ProjectCompetitor.brand_id).where(
            ProjectCompetitor.project_id == project.id
        )
        compare_with = [r[0] for r in (await session.execute(comp_stmt)).all()][:4]

    brand_ids = [primary, *compare_with]
    f, t = _dt_range(from_d, to_d)

    # Pick top N topics by total mention count for this brand set.
    top_topic_stmt = (
        select(TopicScoreDaily.topic_id, func.sum(TopicScoreDaily.mention_count).label("c"))
        .where(
            and_(
                TopicScoreDaily.brand_id.in_(brand_ids),
                TopicScoreDaily.date >= f,
                TopicScoreDaily.date <= t,
            )
        )
        .group_by(TopicScoreDaily.topic_id)
        .order_by(desc("c"))
        .limit(top_n)
    )
    top_topics = [int(r[0]) for r in (await session.execute(top_topic_stmt)).all()]
    if not top_topics:
        return TopicHeatmapOut(project_id=project.id, metric=metric, rows=[], state="empty")

    metric_col = (
        TopicScoreDaily.avg_sentiment_score
        if metric == "sentiment"
        else TopicScoreDaily.mention_rate
    )
    cell_stmt = (
        select(
            TopicScoreDaily.brand_id,
            TopicScoreDaily.topic_id,
            func.avg(metric_col),
            func.sum(TopicScoreDaily.mention_count),
        )
        .where(
            and_(
                TopicScoreDaily.brand_id.in_(brand_ids),
                TopicScoreDaily.topic_id.in_(top_topics),
                TopicScoreDaily.date >= f,
                TopicScoreDaily.date <= t,
            )
        )
        .group_by(TopicScoreDaily.brand_id, TopicScoreDaily.topic_id)
    )
    cell_data: dict[tuple[int, int], tuple[float | None, int]] = {}
    for bid, tid, val, cnt in (await session.execute(cell_stmt)).all():
        cell_data[(int(bid), int(tid))] = (
            float(val) if val is not None else None,
            int(cnt or 0),
        )

    topic_names = await resolve_topic_names(session, top_topics)
    brand_names = await resolve_brand_names(session, brand_ids)

    rows: list[HeatmapRow] = []
    for bid in brand_ids:
        cells: list[HeatmapCell] = []
        for tid in top_topics:
            v, c = cell_data.get((bid, tid), (None, 0))
            cells.append(
                HeatmapCell(
                    topic_id=tid,
                    topic_label=topic_names.get(tid) or f"topic-{tid}",
                    value=round(v, 4) if v is not None else None,
                    sample=c,
                )
            )
        rows.append(HeatmapRow(brand_id=bid, brand_name=brand_names.get(bid), values=cells))

    return TopicHeatmapOut(
        project_id=project.id,
        metric=metric,
        rows=rows,
        state="ok" if any(any(c.value is not None for c in r.values) for r in rows) else "empty",
    )


# ── /sentiment/by-engine ────────────────────────────────────────────
async def get_sentiment_by_engine(
    session: AsyncSession,
    project: Project,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    engines: list[str] | None = None,
    segment_id: str | None = None,
    profile_id: str | None = None,
) -> SentimentByEngineOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    if project.primary_brand_id is None:
        return SentimentByEngineOut(
            project_id=project.id, period=_period(from_d, to_d), items=[], state="empty"
        )
    f, t = _dt_range(from_d, to_d)
    if _needs_admin_filter(engines=engines, segment_id=segment_id, profile_id=profile_id):
        rows = await _fact_rows(
            session,
            project,
            filters=_admin_filters(
                from_d,
                to_d,
                engines=engines,
                segment_id=segment_id,
                profile_id=profile_id,
            ),
        )
        bucket: dict[str, dict[str, int]] = defaultdict(
            lambda: {"positive": 0, "neutral": 0, "negative": 0}
        )
        seen: set[int] = set()
        for row in rows:
            rid = row.get("response_id")
            if rid is None or int(rid) in seen:
                continue
            seen.add(int(rid))
            engine = str(row.get("target_llm") or row.get("response_target_llm") or "unknown")
            bucket[engine]["positive"] += int(row.get("positive_mentions") or 0)
            bucket[engine]["neutral"] += int(row.get("neutral_mentions") or 0)
            bucket[engine]["negative"] += int(row.get("negative_mentions") or 0)
        items = [
            SentimentByEngineRow(
                engine=engine,
                positive=v["positive"],
                neutral=v["neutral"],
                negative=v["negative"],
            )
            for engine, v in sorted(bucket.items())
        ]
        return SentimentByEngineOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            items=items,
            state="ok" if items else "empty",
        )
    # JOIN brand_mentions → llm_responses to get target_llm. SQLite tests fall
    # back to "all" engine bucket if join unavailable.
    try:
        result = await session.execute(
            text(
                """
                SELECT r.target_llm AS engine, bm.sentiment, COUNT(*)::int AS cnt
                FROM brand_mentions bm
                JOIN llm_responses r ON r.id = bm.response_id
                WHERE bm.brand_id = :bid
                  AND bm.created_at >= :f
                  AND bm.created_at <= :t
                GROUP BY r.target_llm, bm.sentiment
                """
            ),
            {"bid": project.primary_brand_id, "f": f, "t": t},
        )
        rows = result.all()
    except Exception:
        rows = []

    bucket: dict[str, dict[str, int]] = defaultdict(
        lambda: {"positive": 0, "neutral": 0, "negative": 0}
    )
    for r in rows:
        engine = r[0] or "unknown"
        sent = r[1] or "neutral"
        cnt = int(r[2] or 0)
        if sent in bucket[engine]:
            bucket[engine][sent] += cnt

    items = [
        SentimentByEngineRow(
            engine=engine,
            positive=v["positive"],
            neutral=v["neutral"],
            negative=v["negative"],
        )
        for engine, v in sorted(bucket.items())
    ]
    return SentimentByEngineOut(
        project_id=project.id,
        period=_period(from_d, to_d),
        items=items,
        state="ok" if items else "empty",
    )


# ── /sentiment/trend-by-engine ──────────────────────────────────────
async def get_sentiment_trend_by_engine(
    session: AsyncSession,
    project: Project,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    engines: list[str] | None = None,
    segment_id: str | None = None,
    profile_id: str | None = None,
) -> SentimentTrendByEngineOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    if project.primary_brand_id is None:
        return SentimentTrendByEngineOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            engines=[],
            items=[],
            state="empty",
        )
    f, t = _dt_range(from_d, to_d)
    if _needs_admin_filter(engines=engines, segment_id=segment_id, profile_id=profile_id):
        rows = await _fact_rows(
            session,
            project,
            filters=_admin_filters(
                from_d,
                to_d,
                engines=engines,
                segment_id=segment_id,
                profile_id=profile_id,
            ),
        )
        by_day_engine: dict[str, dict[str, list[float]]] = OrderedDict()
        engines_seen: set[str] = set()
        seen: set[int] = set()
        for row in rows:
            rid = row.get("response_id")
            if rid is None or int(rid) in seen or row.get("sentiment_score") is None:
                continue
            seen.add(int(rid))
            day = str(row.get("query_created_at") or row.get("response_created_at") or "")[:10]
            if not day:
                continue
            engine = str(row.get("target_llm") or row.get("response_target_llm") or "unknown")
            engines_seen.add(engine)
            by_day_engine.setdefault(day, defaultdict(list))[engine].append(
                float(row["sentiment_score"])
            )
        engine_list = sorted(engines_seen)
        items = [
            SentimentTrendByEngineRow(
                date=day,
                by_engine={
                    engine: round(sum(values.get(engine, [])) / len(values.get(engine, [])), 4)
                    if values.get(engine)
                    else None
                    for engine in engine_list
                },
            )
            for day, values in by_day_engine.items()
        ]
        return SentimentTrendByEngineOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            engines=engine_list,
            items=items,
            state="ok" if items else "empty",
        )
    stmt = (
        select(
            GeoScoreDaily.date,
            GeoScoreDaily.target_llm,
            func.avg(GeoScoreDaily.avg_sentiment),
        )
        .where(
            and_(
                GeoScoreDaily.brand_id == project.primary_brand_id,
                GeoScoreDaily.date >= f,
                GeoScoreDaily.date <= t,
                GeoScoreDaily.target_llm.isnot(None),
            )
        )
        .group_by(GeoScoreDaily.date, GeoScoreDaily.target_llm)
        .order_by(GeoScoreDaily.date)
    )
    rows = (await session.execute(stmt)).all()

    by_date: dict[str, dict[str, float | None]] = OrderedDict()
    engines_seen: set[str] = set()
    for d, eng, v in rows:
        d_iso = d.date().isoformat() if isinstance(d, datetime) else str(d)[:10]
        engines_seen.add(eng or "unknown")
        by_date.setdefault(d_iso, {})[eng or "unknown"] = float(v) if v is not None else None

    engines = sorted(engines_seen)
    items = [
        SentimentTrendByEngineRow(date=d_iso, by_engine={e: by_date[d_iso].get(e) for e in engines})
        for d_iso in by_date
    ]
    return SentimentTrendByEngineOut(
        project_id=project.id,
        period=_period(from_d, to_d),
        engines=engines,
        items=items,
        state="ok" if items else "empty",
    )


# ── /sentiment/topic-attribution ────────────────────────────────────
async def get_topic_attribution(
    session: AsyncSession,
    project: Project,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    engines: list[str] | None = None,
    segment_id: str | None = None,
    profile_id: str | None = None,
    limit: int = 10,
) -> TopicAttributionOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    primary = project.primary_brand_id
    if primary is None:
        return TopicAttributionOut(project_id=project.id, items=[], state="empty")
    f, t = _dt_range(from_d, to_d)

    admin_filters = AnalysisFilters(
        from_date=from_d,
        to_date=to_d,
        engines=tuple(engines) if engines else None,
        segment_id=segment_id,
        profile_id=profile_id,
    )
    admin_rows = await _fact_rows(session, project, filters=admin_filters)
    by_topic: OrderedDict[int, dict[str, Any]] = OrderedDict()
    seen_responses: set[int] = set()
    for row in admin_rows:
        tid = row.get("topic_id")
        if tid is None:
            continue
        tid = int(tid)
        if tid not in by_topic:
            by_topic[tid] = {
                "name": row.get("topic_name") or f"topic-{tid}",
                "positive": 0,
                "neutral": 0,
                "negative": 0,
                "sample": None,
            }
        rid = row.get("response_id")
        if rid is None or int(rid) in seen_responses:
            continue
        seen_responses.add(int(rid))
        bucket = by_topic[tid]
        bucket["positive"] += int(row.get("positive_mentions") or 0)
        bucket["neutral"] += int(row.get("neutral_mentions") or 0)
        bucket["negative"] += int(row.get("negative_mentions") or 0)
        if bucket["sample"] is None and row.get("negative_sample_snippet"):
            bucket["sample"] = row.get("negative_sample_snippet")

    admin_items: list[TopicAttributionRow] = []
    for tid, bucket in by_topic.items():
        total = int(bucket["positive"] + bucket["neutral"] + bucket["negative"])
        negative = int(bucket["negative"])
        if total <= 0 or negative <= 0:
            continue
        admin_items.append(
            TopicAttributionRow(
                topic_id=tid,
                topic_name=bucket["name"],
                negative_count=negative,
                negative_ratio=round(negative / total, 3),
                sample_snippet=bucket["sample"],
            )
        )
    admin_items.sort(key=lambda item: (-item.negative_ratio, -item.negative_count, item.topic_id))
    if admin_items or admin_rows:
        return TopicAttributionOut(
            project_id=project.id,
            items=admin_items[:limit],
            state="ok" if admin_items else "empty",
        )

    stmt = (
        select(
            TopicScoreDaily.topic_id,
            func.sum(TopicScoreDaily.mention_count).label("total"),
            func.avg(TopicScoreDaily.avg_sentiment_score).label("avg_sent"),
        )
        .where(
            and_(
                TopicScoreDaily.brand_id == primary,
                TopicScoreDaily.date >= f,
                TopicScoreDaily.date <= t,
            )
        )
        .group_by(TopicScoreDaily.topic_id)
        .having(func.avg(TopicScoreDaily.avg_sentiment_score) < 0.5)
        .order_by("avg_sent")
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    topic_ids = [int(r[0]) for r in rows]
    name_map = await resolve_topic_names(session, topic_ids)

    items: list[TopicAttributionRow] = []
    for r in rows:
        tid = int(r[0])
        total = int(r[1] or 0)
        avg_sent = float(r[2] or 0)
        # Approx: negative_ratio = (1 - avg_sent) clamped to 0..1
        neg_ratio = max(0.0, min(1.0, 1.0 - avg_sent))
        neg_count = round(total * neg_ratio)
        items.append(
            TopicAttributionRow(
                topic_id=tid,
                topic_name=name_map.get(tid) or f"topic-{tid}",
                negative_count=neg_count,
                negative_ratio=round(neg_ratio, 3),
                sample_snippet=None,
            )
        )
    return TopicAttributionOut(project_id=project.id, items=items, state="ok" if items else "empty")


# ── /mention-samples ────────────────────────────────────────────────
async def get_mention_samples(
    session: AsyncSession,
    project: Project,
    *,
    polarity: str | None = None,
    limit: int = 20,
    from_date: date | None = None,
    to_date: date | None = None,
) -> MentionSamplesOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    if project.primary_brand_id is None:
        return MentionSamplesOut(project_id=project.id, items=[], state="empty")
    f, t = _dt_range(from_d, to_d)

    where = [
        BrandMention.brand_id == project.primary_brand_id,
        BrandMention.created_at >= f,
        BrandMention.created_at <= t,
    ]
    if polarity in ("positive", "negative", "neutral"):
        where.append(BrandMention.sentiment == polarity)

    stmt = (
        select(BrandMention)
        .where(and_(*where))
        .order_by(BrandMention.created_at.desc())
        .limit(limit)
    )
    rows = list((await session.execute(stmt)).scalars().all())

    # Engine + topic enrichment via llm_responses (best-effort).
    engine_by_resp: dict[int, str] = {}
    topic_by_resp: dict[int, str] = {}
    if rows:
        resp_ids = list({m.response_id for m in rows})
        try:
            r = await session.execute(
                text(
                    """
                    SELECT r.id, r.target_llm, t.text
                    FROM llm_responses r
                    LEFT JOIN prompts p ON p.id = r.prompt_id
                    LEFT JOIN topics t ON t.id = p.topic_id
                    WHERE r.id = ANY(:ids)
                    """
                ),
                {"ids": resp_ids},
            )
            for rid, eng, topic in r.all():
                if eng:
                    engine_by_resp[int(rid)] = eng
                if topic:
                    topic_by_resp[int(rid)] = topic
        except Exception:
            pass

    label_map = {"positive": "正面", "negative": "负面", "neutral": "中性"}
    items = [
        MentionSampleRow(
            mention_id=m.id,
            response_id=m.response_id,
            label=label_map.get(m.sentiment or "neutral", "中性"),
            polarity=m.sentiment or "neutral",
            summary=(m.context_snippet or "")[:280],
            snippet=m.context_snippet,
            engine=engine_by_resp.get(m.response_id),
            topic=topic_by_resp.get(m.response_id),
            occurred_at=m.created_at.isoformat() if m.created_at else None,
        )
        for m in rows
    ]
    return MentionSamplesOut(project_id=project.id, items=items, state="ok" if items else "empty")


# ── /citations/authority-trend ──────────────────────────────────────
async def get_authority_trend(
    session: AsyncSession,
    project: Project,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    engines: list[str] | None = None,
    segment_id: str | None = None,
    profile_id: str | None = None,
) -> AuthorityTrendOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    primary = project.primary_brand_id
    if primary is None:
        return AuthorityTrendOut(
            project_id=project.id, period=_period(from_d, to_d), points=[], state="empty"
        )
    f, t = _dt_range(from_d, to_d)
    if _needs_admin_filter(engines=engines, segment_id=segment_id, profile_id=profile_id):
        fact_rows = await _fact_rows(
            session,
            project,
            filters=_admin_filters(
                from_d,
                to_d,
                engines=engines,
                segment_id=segment_id,
                profile_id=profile_id,
            ),
        )
        response_ids = sorted(
            {int(r["response_id"]) for r in fact_rows if r.get("response_id") is not None}
        )
        if not response_ids:
            return AuthorityTrendOut(
                project_id=project.id, period=_period(from_d, to_d), points=[], state="empty"
            )
        stmt = (
            select(
                func.date(CitationSource.created_at).label("d"),
                DomainAuthority.tier,
                func.count().label("cnt"),
            )
            .select_from(CitationSource)
            .outerjoin(BrandMention, BrandMention.id == CitationSource.mention_id)
            .outerjoin(DomainAuthority, DomainAuthority.domain == CitationSource.domain)
            .where(
                and_(
                    CitationSource.response_id.in_(response_ids),
                    or_(CitationSource.mention_id.is_(None), BrandMention.brand_id == primary),
                )
            )
            .group_by("d", DomainAuthority.tier)
            .order_by("d")
        )
        rows = (await session.execute(stmt)).all()
        by_day: dict[str, dict[int | None, int]] = OrderedDict()
        for d, tier, cnt in rows:
            d_iso = d.isoformat() if hasattr(d, "isoformat") else str(d)[:10]
            by_day.setdefault(d_iso, defaultdict(int))[tier] += int(cnt or 0)
        points = []
        for d_iso, tier_map in by_day.items():
            total = sum(tier_map.values()) or 1
            points.append(
                AuthorityTrendPoint(
                    date=d_iso,
                    tier1_pct=round(tier_map.get(1, 0) / total * 100, 1),
                    tier2_pct=round(tier_map.get(2, 0) / total * 100, 1),
                    tier3_pct=round(tier_map.get(3, 0) / total * 100, 1),
                    tier4_pct=round(tier_map.get(4, 0) / total * 100, 1),
                    untiered_pct=round(tier_map.get(None, 0) / total * 100, 1),
                )
            )
        return AuthorityTrendOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            points=points,
            state="ok" if points else "empty",
        )
    # Per-day count of citations grouped by tier.
    stmt = (
        select(
            func.date(CitationSource.created_at).label("d"),
            DomainAuthority.tier,
            func.count().label("cnt"),
        )
        .select_from(CitationSource)
        .join(BrandMention, BrandMention.id == CitationSource.mention_id)
        .outerjoin(DomainAuthority, DomainAuthority.domain == CitationSource.domain)
        .where(
            and_(
                BrandMention.brand_id == primary,
                CitationSource.created_at >= f,
                CitationSource.created_at <= t,
                CitationSource.domain.isnot(None),
            )
        )
        .group_by("d", DomainAuthority.tier)
        .order_by("d")
    )
    rows = (await session.execute(stmt)).all()

    by_day: dict[str, dict[int | None, int]] = OrderedDict()
    for d, tier, cnt in rows:
        d_iso = d.isoformat() if hasattr(d, "isoformat") else str(d)[:10]
        by_day.setdefault(d_iso, defaultdict(int))[tier] += int(cnt or 0)

    points: list[AuthorityTrendPoint] = []
    for d_iso, tier_map in by_day.items():
        total = sum(tier_map.values()) or 1
        points.append(
            AuthorityTrendPoint(
                date=d_iso,
                tier1_pct=round(tier_map.get(1, 0) / total * 100, 1),
                tier2_pct=round(tier_map.get(2, 0) / total * 100, 1),
                tier3_pct=round(tier_map.get(3, 0) / total * 100, 1),
                tier4_pct=round(tier_map.get(4, 0) / total * 100, 1),
                untiered_pct=round(tier_map.get(None, 0) / total * 100, 1),
            )
        )
    return AuthorityTrendOut(
        project_id=project.id,
        period=_period(from_d, to_d),
        points=points,
        state="ok" if points else "empty",
    )


# ── /citations/composition ──────────────────────────────────────────
async def get_citation_composition(
    session: AsyncSession,
    project: Project,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    engines: list[str] | None = None,
    segment_id: str | None = None,
    profile_id: str | None = None,
) -> CitationCompositionOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    primary = project.primary_brand_id
    if primary is None:
        return CitationCompositionOut(
            project_id=project.id, period=_period(from_d, to_d), segments=[], total=0, state="empty"
        )
    f, t = _dt_range(from_d, to_d)
    if _needs_admin_filter(engines=engines, segment_id=segment_id, profile_id=profile_id):
        fact_rows = await _fact_rows(
            session,
            project,
            filters=_admin_filters(
                from_d,
                to_d,
                engines=engines,
                segment_id=segment_id,
                profile_id=profile_id,
            ),
        )
        response_ids = sorted(
            {int(r["response_id"]) for r in fact_rows if r.get("response_id") is not None}
        )
        if not response_ids:
            return CitationCompositionOut(
                project_id=project.id,
                period=_period(from_d, to_d),
                segments=[],
                total=0,
                state="empty",
            )
        stmt = (
            select(DomainAuthority.tier, func.count())
            .select_from(CitationSource)
            .outerjoin(BrandMention, BrandMention.id == CitationSource.mention_id)
            .outerjoin(DomainAuthority, DomainAuthority.domain == CitationSource.domain)
            .where(
                and_(
                    CitationSource.response_id.in_(response_ids),
                    CitationSource.domain.isnot(None),
                    or_(CitationSource.mention_id.is_(None), BrandMention.brand_id == primary),
                )
            )
            .group_by(DomainAuthority.tier)
        )
        rows = (await session.execute(stmt)).all()
        total = sum(int(r[1] or 0) for r in rows)
        label_for = {
            1: "Tier 1",
            2: "Tier 2",
            3: "Tier 3",
            4: "Tier 4",
            None: "Untiered",
        }
        by_tier = {r[0]: int(r[1] or 0) for r in rows}
        return CitationCompositionOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            segments=[
                CitationCompositionRow(
                    label=label_for[tier],
                    tier=tier,
                    count=count,
                    pct=round(count / total * 100, 1) if total else 0.0,
                )
                for tier in (1, 2, 3, 4, None)
                if (count := by_tier.get(tier, 0)) or tier is not None
            ],
            total=total,
            state="ok" if total else "empty",
        )
    stmt = (
        select(DomainAuthority.tier, func.count())
        .select_from(CitationSource)
        .join(BrandMention, BrandMention.id == CitationSource.mention_id)
        .outerjoin(DomainAuthority, DomainAuthority.domain == CitationSource.domain)
        .where(
            and_(
                BrandMention.brand_id == primary,
                CitationSource.created_at >= f,
                CitationSource.created_at <= t,
                CitationSource.domain.isnot(None),
            )
        )
        .group_by(DomainAuthority.tier)
    )
    rows = (await session.execute(stmt)).all()
    total = sum(int(r[1] or 0) for r in rows)
    label_for = {
        1: "Tier 1 · 官方",
        2: "Tier 2 · 权威媒体",
        3: "Tier 3 · KOL",
        4: "Tier 4 · UGC",
        None: "未分类",
    }
    segments = []
    # Stable order Tier1→4 then untiered.
    rows_by_tier = {r[0]: int(r[1] or 0) for r in rows}
    for tier in (1, 2, 3, 4, None):
        cnt = rows_by_tier.get(tier, 0)
        if cnt == 0 and tier is None:
            continue
        segments.append(
            CitationCompositionRow(
                label=label_for[tier],
                tier=tier,
                count=cnt,
                pct=round(cnt / total * 100, 1) if total else 0.0,
            )
        )
    return CitationCompositionOut(
        project_id=project.id,
        period=_period(from_d, to_d),
        segments=segments,
        total=total,
        state="ok" if total else "empty",
    )


# ── /citations/content-gap ──────────────────────────────────────────
async def get_content_gap(
    session: AsyncSession,
    project: Project,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    engines: list[str] | None = None,
    segment_id: str | None = None,
    profile_id: str | None = None,
    limit: int = 12,
) -> ContentGapOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    primary = project.primary_brand_id
    if primary is None:
        return ContentGapOut(
            project_id=project.id,
            topics=[],
            page_type_distribution=[],
            state="empty",
        )
    f, t = _dt_range(from_d, to_d)

    admin_filters = AnalysisFilters(
        from_date=from_d,
        to_date=to_d,
        engines=tuple(engines) if engines else None,
        segment_id=segment_id,
        profile_id=profile_id,
    )
    monitoring = await get_topic_monitoring(session, project, filters=admin_filters)
    if monitoring.topics:
        topics: list[ContentGapTopicRow] = []
        for row in monitoring.topics:
            mention_rate = float(row.mention_rate or 0)
            citation_rate = float(row.citation_rate or 0)
            gap = round(mention_rate - citation_rate, 4)
            if gap <= 0:
                continue
            topics.append(
                ContentGapTopicRow(
                    topic_id=row.topic_id,
                    topic_name=row.topic_name,
                    mention_rate=round(mention_rate, 4),
                    citation_rate=round(citation_rate, 4),
                    gap_score=gap,
                    suggestion="Increase authoritative/owned citations for this topic.",
                )
            )
            if len(topics) >= limit:
                break

        admin_rows = await _fact_rows(session, project, filters=admin_filters)
        response_ids = sorted(
            {int(r["response_id"]) for r in admin_rows if r.get("response_id") is not None}
        )
        page_types: list[ContentGapPageTypeRow] = []
        if response_ids:
            pt_stmt = (
                select(CitationSource.source_type, func.count())
                .select_from(CitationSource)
                .outerjoin(BrandMention, BrandMention.id == CitationSource.mention_id)
                .where(
                    and_(
                        CitationSource.response_id.in_(response_ids),
                        or_(CitationSource.mention_id.is_(None), BrandMention.brand_id == primary),
                    )
                )
                .group_by(CitationSource.source_type)
                .order_by(desc(func.count()))
            )
            pt_rows = (await session.execute(pt_stmt)).all()
            pt_total = sum(int(r[1] or 0) for r in pt_rows) or 1
            page_types = [
                ContentGapPageTypeRow(
                    page_type=r[0] or "other",
                    count=int(r[1] or 0),
                    pct=round(int(r[1] or 0) / pt_total * 100, 1),
                )
                for r in pt_rows
            ]
        return ContentGapOut(
            project_id=project.id,
            topics=topics,
            page_type_distribution=page_types,
            state="ok" if topics else "empty",
        )

    # Topics where mention_rate > industry median but citation_rate is low.
    stmt = (
        select(
            TopicScoreDaily.topic_id,
            func.avg(TopicScoreDaily.mention_rate).label("mr"),
        )
        .where(
            and_(
                TopicScoreDaily.brand_id == primary,
                TopicScoreDaily.date >= f,
                TopicScoreDaily.date <= t,
            )
        )
        .group_by(TopicScoreDaily.topic_id)
        .order_by(desc("mr"))
        .limit(50)
    )
    topic_rows = (await session.execute(stmt)).all()
    if not topic_rows:
        return ContentGapOut(
            project_id=project.id, topics=[], page_type_distribution=[], state="empty"
        )

    topic_ids = [int(r[0]) for r in topic_rows]
    name_map = await resolve_topic_names(session, topic_ids)

    # citation_rate per topic from geo_score_daily (no per-topic citation table,
    # so we approximate with a brand-level citation_rate scalar attenuated by
    # mention_rate share of the topic).
    cite_stmt = select(func.avg(GeoScoreDaily.citation_rate)).where(
        and_(
            GeoScoreDaily.brand_id == primary,
            GeoScoreDaily.date >= f,
            GeoScoreDaily.date <= t,
        )
    )
    brand_citation_rate = float((await session.execute(cite_stmt)).scalar_one_or_none() or 0)

    topics: list[ContentGapTopicRow] = []
    for r in topic_rows:
        tid = int(r[0])
        mr = float(r[1] or 0)
        approx_citation = round(brand_citation_rate * (1.0 - min(mr, 1.0)), 4)
        gap = round(mr - approx_citation, 4)
        if gap <= 0:
            continue
        topics.append(
            ContentGapTopicRow(
                topic_id=tid,
                topic_name=name_map.get(tid) or f"topic-{tid}",
                mention_rate=round(mr, 4),
                citation_rate=approx_citation,
                gap_score=gap,
                suggestion="增加权威媒体/官方域引用, 弥补 citation gap",
            )
        )
        if len(topics) >= limit:
            break

    # Page type distribution from citation_sources.source_type.
    pt_stmt = (
        select(CitationSource.source_type, func.count())
        .select_from(CitationSource)
        .join(BrandMention, BrandMention.id == CitationSource.mention_id)
        .where(
            and_(
                BrandMention.brand_id == primary,
                CitationSource.created_at >= f,
                CitationSource.created_at <= t,
            )
        )
        .group_by(CitationSource.source_type)
        .order_by(desc(func.count()))
    )
    pt_rows = (await session.execute(pt_stmt)).all()
    pt_total = sum(int(r[1] or 0) for r in pt_rows) or 1
    page_types = [
        ContentGapPageTypeRow(
            page_type=r[0] or "other",
            count=int(r[1] or 0),
            pct=round(int(r[1] or 0) / pt_total * 100, 1),
        )
        for r in pt_rows
    ]

    return ContentGapOut(
        project_id=project.id,
        topics=topics,
        page_type_distribution=page_types,
        state="ok" if topics else "empty",
    )


# ── /citations/pr-targets ───────────────────────────────────────────
async def get_pr_targets(
    session: AsyncSession,
    project: Project,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> PrTargetsOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    primary = project.primary_brand_id
    if primary is None:
        return PrTargetsOut(
            project_id=project.id,
            targets=[],
            kol_scorecards=[],
            tier2_matrix=Tier2MatrixOut(domains=[], brands=[]),
            state="empty",
        )
    f, t = _dt_range(from_d, to_d)

    competitor_ids = [
        r[0]
        for r in (
            await session.execute(
                select(ProjectCompetitor.brand_id).where(ProjectCompetitor.project_id == project.id)
            )
        ).all()
    ][:3]

    # Tier 2 domain x brand citation matrix.
    matrix_brands = [primary, *competitor_ids]
    domain_stmt = (
        select(CitationSource.domain, func.count())
        .select_from(CitationSource)
        .join(BrandMention, BrandMention.id == CitationSource.mention_id)
        .join(DomainAuthority, DomainAuthority.domain == CitationSource.domain)
        .where(
            and_(
                BrandMention.brand_id.in_(matrix_brands),
                DomainAuthority.tier == 2,
                CitationSource.created_at >= f,
                CitationSource.created_at <= t,
            )
        )
        .group_by(CitationSource.domain)
        .order_by(desc(func.count()))
        .limit(8)
    )
    top_domains = [r[0] for r in (await session.execute(domain_stmt)).all() if r[0]]

    matrix: dict[tuple[int, str], int] = {}
    if top_domains and matrix_brands:
        cell_stmt = (
            select(BrandMention.brand_id, CitationSource.domain, func.count())
            .select_from(CitationSource)
            .join(BrandMention, BrandMention.id == CitationSource.mention_id)
            .where(
                and_(
                    BrandMention.brand_id.in_(matrix_brands),
                    CitationSource.domain.in_(top_domains),
                    CitationSource.created_at >= f,
                    CitationSource.created_at <= t,
                )
            )
            .group_by(BrandMention.brand_id, CitationSource.domain)
        )
        for bid, dom, cnt in (await session.execute(cell_stmt)).all():
            matrix[(int(bid), dom)] = int(cnt or 0)

    name_map = await resolve_brand_names(session, matrix_brands)
    matrix_brand_rows = [
        Tier2MatrixRow(
            brand_id=bid,
            label=name_map.get(bid) or f"#{bid}",
            counts=[matrix.get((bid, d), 0) for d in top_domains],
        )
        for bid in matrix_brands
    ]

    # PR targets = top-tier domains where competitors > we.
    target_stmt = (
        select(
            CitationSource.domain,
            DomainAuthority.tier,
            func.sum(case((BrandMention.brand_id == primary, 1), else_=0)).label("we"),
            func.sum(case((BrandMention.brand_id != primary, 1), else_=0)).label("comp"),
        )
        .select_from(CitationSource)
        .join(BrandMention, BrandMention.id == CitationSource.mention_id)
        .outerjoin(DomainAuthority, DomainAuthority.domain == CitationSource.domain)
        .where(
            and_(
                BrandMention.brand_id.in_(matrix_brands),
                CitationSource.created_at >= f,
                CitationSource.created_at <= t,
                CitationSource.domain.isnot(None),
            )
        )
        .group_by(CitationSource.domain, DomainAuthority.tier)
    )
    try:
        target_rows = (await session.execute(target_stmt)).all()
    except Exception:
        target_rows = []

    targets: list[PrTargetRow] = []
    for r in target_rows:
        we = int(r[2] or 0)
        comp = int(r[3] or 0)
        gap = comp - we
        if gap <= 0:
            continue
        targets.append(
            PrTargetRow(
                domain=r[0],
                tier=int(r[1]) if r[1] is not None else None,
                we_count=we,
                competitors_count=comp,
                gap=gap,
                suggestion=(
                    "竞品在该域引用更多 — 推 PR 目标"
                    if (r[1] or 5) <= 2
                    else "可作为长尾内容投放对象"
                ),
            )
        )
    targets.sort(key=lambda x: -x.gap)
    targets = targets[:12]

    # KOL scorecards — rough heuristic from citation_sources.source_type='kol'
    kol_stmt = (
        select(CitationSource.title, func.count())
        .select_from(CitationSource)
        .join(BrandMention, BrandMention.id == CitationSource.mention_id)
        .where(
            and_(
                BrandMention.brand_id == primary,
                CitationSource.source_type == "kol",
                CitationSource.created_at >= f,
                CitationSource.created_at <= t,
            )
        )
        .group_by(CitationSource.title)
        .order_by(desc(func.count()))
        .limit(6)
    )
    kols: list[KolScorecard] = []
    try:
        for title, cnt in (await session.execute(kol_stmt)).all():
            score = min(100.0, float(cnt) * 5.0)
            kols.append(
                KolScorecard(
                    name=title or "(未命名 KOL)",
                    audience_score=round(score, 1),
                    quality_score=round(score * 0.85, 1),
                    risk="low" if score > 60 else "med",
                )
            )
    except Exception:
        pass

    return PrTargetsOut(
        project_id=project.id,
        targets=targets,
        kol_scorecards=kols,
        tier2_matrix=Tier2MatrixOut(domains=top_domains, brands=matrix_brand_rows),
        state="ok" if (targets or kols or top_domains) else "empty",
    )


# ── /citations/simulator-baseline ───────────────────────────────────
async def get_simulator_baseline(
    session: AsyncSession,
    project: Project,
) -> SimulatorBaselineOut:
    primary = project.primary_brand_id
    if primary is None:
        return SimulatorBaselineOut(
            project_id=project.id,
            current_pano=0,
            industry_median=None,
            industry_top3_avg=None,
            tiers=[],
            presets=[],
            state="empty",
        )

    # Latest weekly citation tier counts.
    latest_stmt = (
        select(GeoScoreWeekly)
        .where(GeoScoreWeekly.brand_id == primary)
        .order_by(GeoScoreWeekly.week_start.desc())
        .limit(1)
    )
    weekly = (await session.execute(latest_stmt)).scalar_one_or_none()

    # Current PANO: latest avg_geo_score from geo_score_daily.
    pano_stmt = (
        select(func.avg(GeoScoreDaily.avg_geo_score))
        .where(GeoScoreDaily.brand_id == primary)
        .where(GeoScoreDaily.date >= datetime.now() - timedelta(days=14))
    )
    current_pano = float((await session.execute(pano_stmt)).scalar_one_or_none() or 0)

    # Industry median + top3 from industry_benchmark_daily.
    industry_name = await resolve_brand_industry(session, primary)
    industry_median = None
    top3 = None
    if industry_name:
        med_stmt = (
            select(
                func.avg(IndustryBenchmarkDaily.score_p50),
                func.avg(IndustryBenchmarkDaily.avg_geo_score),
            )
            .where(IndustryBenchmarkDaily.industry == industry_name)
            .where(IndustryBenchmarkDaily.date >= datetime.now() - timedelta(days=14))
        )
        rr = (await session.execute(med_stmt)).one_or_none()
        if rr:
            industry_median = float(rr[0]) if rr[0] is not None else None
            top3 = float(rr[1]) if rr[1] is not None else None

    tiers = [
        SimulatorTierWeight(
            tier=1,
            weight=0.40,
            confidence=0.95,
            current_count=int(weekly.tier1_citation_count) if weekly else 0,
        ),
        SimulatorTierWeight(
            tier=2,
            weight=0.30,
            confidence=0.85,
            current_count=int(weekly.tier2_citation_count) if weekly else 0,
        ),
        SimulatorTierWeight(
            tier=3,
            weight=0.20,
            confidence=0.65,
            current_count=int(weekly.tier3_citation_count) if weekly else 0,
        ),
        SimulatorTierWeight(
            tier=4,
            weight=0.10,
            confidence=0.50,
            current_count=int(weekly.tier4_citation_count) if weekly else 0,
        ),
    ]
    presets: list[dict[str, Any]] = [
        {
            "id": "official_push",
            "label": "官方域强化",
            "delta_by_tier": {1: 5, 2: 0, 3: 0, 4: 0},
        },
        {
            "id": "media_outreach",
            "label": "权威媒体投放",
            "delta_by_tier": {1: 0, 2: 5, 3: 1, 4: 0},
        },
        {
            "id": "kol_campaign",
            "label": "KOL 内容矩阵",
            "delta_by_tier": {1: 0, 2: 1, 3: 6, 4: 0},
        },
    ]
    return SimulatorBaselineOut(
        project_id=project.id,
        current_pano=round(current_pano, 1),
        industry_median=round(industry_median, 1) if industry_median is not None else None,
        industry_top3_avg=round(top3, 1) if top3 is not None else None,
        tiers=tiers,
        presets=presets,
        state="ok" if weekly is not None else "partial",
    )


# ── /competitors/authority-radar ────────────────────────────────────
async def get_authority_radar(
    session: AsyncSession,
    project: Project,
) -> AuthorityRadarOut:
    primary = project.primary_brand_id
    if primary is None:
        return AuthorityRadarOut(project_id=project.id, rows=[], state="empty")

    competitor_ids = [
        r[0]
        for r in (
            await session.execute(
                select(ProjectCompetitor.brand_id).where(ProjectCompetitor.project_id == project.id)
            )
        ).all()
    ]

    async def _tier_counts(brand_id: int) -> tuple[int, int, int, int, int]:
        stmt = (
            select(GeoScoreWeekly)
            .where(GeoScoreWeekly.brand_id == brand_id)
            .order_by(GeoScoreWeekly.week_start.desc())
            .limit(1)
        )
        w = (await session.execute(stmt)).scalar_one_or_none()
        if not w:
            return (0, 0, 0, 0, 0)
        total = (
            (w.tier1_citation_count or 0)
            + (w.tier2_citation_count or 0)
            + (w.tier3_citation_count or 0)
            + (w.tier4_citation_count or 0)
        )
        return (
            int(w.tier1_citation_count or 0),
            int(w.tier2_citation_count or 0),
            int(w.tier3_citation_count or 0),
            int(w.tier4_citation_count or 0),
            int(total),
        )

    me = await _tier_counts(primary)
    comps = [(bid, await _tier_counts(bid)) for bid in competitor_ids]

    # Top competitor: max total.
    top_comp_id: int | None = None
    top_comp_counts = (0, 0, 0, 0, 0)
    for bid, c in comps:
        if c[4] > top_comp_counts[4]:
            top_comp_id = bid
            top_comp_counts = c

    # Industry median: pick brands in same industry from geo_score_weekly.
    industry_name = await resolve_brand_industry(session, primary)
    industry_median_counts = [0.0, 0.0, 0.0, 0.0, 0.0]
    if industry_name:
        try:
            ind_brand_stmt = await session.execute(
                text("SELECT id FROM brands WHERE industry = :ind"),
                {"ind": industry_name},
            )
            ind_brand_ids = [int(r[0]) for r in ind_brand_stmt.all()]
            if ind_brand_ids:
                ind_stmt = (
                    select(
                        func.avg(GeoScoreWeekly.tier1_citation_count),
                        func.avg(GeoScoreWeekly.tier2_citation_count),
                        func.avg(GeoScoreWeekly.tier3_citation_count),
                        func.avg(GeoScoreWeekly.tier4_citation_count),
                    )
                    .where(GeoScoreWeekly.brand_id.in_(ind_brand_ids))
                    .where(GeoScoreWeekly.week_start >= datetime.now() - timedelta(days=30))
                )
                ir = (await session.execute(ind_stmt)).one_or_none()
                if ir:
                    industry_median_counts = [float(v or 0) for v in ir]
                    industry_median_counts.append(sum(industry_median_counts))
        except Exception:
            pass

    name_map = await resolve_brand_names(
        session, [primary] + ([top_comp_id] if top_comp_id else [])
    )
    tier_labels = ["Tier1", "Tier2", "Tier3", "Tier4", "总覆盖"]

    def _industry_median(i: int) -> float:
        if i < len(industry_median_counts):
            return round(float(industry_median_counts[i]), 1)
        return 0.0

    rows = [
        AuthorityRadarRow(
            tier=label,
            me=float(me[i]),
            industry_median=_industry_median(i),
            top_competitor=float(top_comp_counts[i]),
            top_competitor_id=top_comp_id,
            top_competitor_name=name_map.get(top_comp_id) if top_comp_id else None,
        )
        for i, label in enumerate(tier_labels)
    ]
    state = "ok" if me[4] or top_comp_counts[4] else "empty"
    return AuthorityRadarOut(project_id=project.id, rows=rows, state=state)


# ── /group-shared-domains ───────────────────────────────────────────
async def get_group_shared_domains(
    session: AsyncSession,
    project: Project,
) -> GroupSharedDomainsOut:
    primary = project.primary_brand_id
    if primary is None:
        return GroupSharedDomainsOut(
            project_id=project.id,
            group_id=None,
            group_name=None,
            shared_ratio=None,
            items=[],
            state="empty",
        )
    membership = (
        await session.execute(
            select(BrandGroupMember.group_id).where(BrandGroupMember.brand_id == primary)
        )
    ).scalar_one_or_none()
    if membership is None:
        return GroupSharedDomainsOut(
            project_id=project.id,
            group_id=None,
            group_name=None,
            shared_ratio=None,
            items=[],
            state="empty",
        )

    group = (
        await session.execute(select(BrandGroup).where(BrandGroup.id == membership))
    ).scalar_one_or_none()

    rows = (
        await session.execute(
            select(
                BrandGroupSharedDomain.domain,
                BrandGroupSharedDomain.brand_count,
                BrandGroupSharedDomain.total_mentions,
            )
            .where(BrandGroupSharedDomain.group_id == membership)
            .order_by(BrandGroupSharedDomain.total_mentions.desc())
            .limit(20)
        )
    ).all()

    # Sister brand IDs.
    sister_ids = [
        r[0]
        for r in (
            await session.execute(
                select(BrandGroupMember.brand_id).where(BrandGroupMember.group_id == membership)
            )
        ).all()
    ]
    sister_names = await resolve_brand_names(session, sister_ids)

    # Tier per domain (best-effort).
    domains = [r[0] for r in rows]
    tier_map: dict[str, int] = {}
    if domains:
        try:
            dr = await session.execute(
                select(DomainAuthority.domain, DomainAuthority.tier).where(
                    DomainAuthority.domain.in_(domains)
                )
            )
            tier_map = {r[0]: int(r[1]) for r in dr.all() if r[1] is not None}
        except Exception:
            pass

    items = [
        GroupSharedDomainEntry(
            domain=r[0],
            tier=tier_map.get(r[0]),
            brand_count=int(r[1] or 0),
            total_mentions=int(r[2] or 0),
            sister_brand_ids=sister_ids,
            sister_brand_names=[sister_names.get(b) or f"#{b}" for b in sister_ids],
        )
        for r in rows
    ]

    # shared_ratio: shared total / brand's own total citations (rough)
    total_shared = sum(int(r[2] or 0) for r in rows)
    own_total_stmt = (
        select(func.count())
        .select_from(CitationSource)
        .join(BrandMention, BrandMention.id == CitationSource.mention_id)
        .where(BrandMention.brand_id == primary)
    )
    own_total = int((await session.execute(own_total_stmt)).scalar_one_or_none() or 0)
    shared_ratio = round(total_shared / own_total, 3) if own_total else None

    return GroupSharedDomainsOut(
        project_id=project.id,
        group_id=membership,
        group_name=group.name if group else None,
        shared_ratio=shared_ratio,
        items=items,
        state="ok" if items else "empty",
    )


# ── /products/relations ─────────────────────────────────────────────
async def get_product_relations(
    session: AsyncSession,
    project: Project,
) -> ProductRelationsOut:
    primary = project.primary_brand_id
    if primary is None:
        return ProductRelationsOut(project_id=project.id, items=[], state="empty")

    # Find products owned by primary brand.
    own_stmt = select(KgProduct.product_id, KgProduct.primary_name).where(
        KgProduct.brand_id == primary
    )
    own_rows = (await session.execute(own_stmt)).all()
    own_ids = [int(r[0]) for r in own_rows]
    own_name = {int(r[0]): r[1] for r in own_rows}
    if not own_ids:
        return ProductRelationsOut(project_id=project.id, items=[], state="empty")

    # All relations involving these products.
    rel_stmt = select(KgProductRelation).where(
        or_(
            KgProductRelation.product_a_id.in_(own_ids),
            KgProductRelation.product_b_id.in_(own_ids),
        )
    )
    rels = list((await session.execute(rel_stmt)).scalars().all())

    # Resolve other-side names.
    other_ids = list(
        {r.product_b_id if r.product_a_id in own_ids else r.product_a_id for r in rels}
        - set(own_ids)
    )
    other_name_map: dict[int, str] = {}
    if other_ids:
        nm = await session.execute(
            select(KgProduct.product_id, KgProduct.primary_name).where(
                KgProduct.product_id.in_(other_ids)
            )
        )
        other_name_map = {int(r[0]): r[1] for r in nm.all() if r[1]}

    items = [
        ProductRelationRow(
            product_a_id=r.product_a_id,
            product_a_name=own_name.get(r.product_a_id) or other_name_map.get(r.product_a_id),
            product_b_id=r.product_b_id,
            product_b_name=own_name.get(r.product_b_id) or other_name_map.get(r.product_b_id),
            type=r.type,
            confidence=r.confidence,
        )
        for r in rels
    ]
    return ProductRelationsOut(
        project_id=project.id,
        items=items,
        state="ok" if items else "empty",
    )
