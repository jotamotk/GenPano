"""Service for /v1/industries (Phase 3)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from genpano_models import (
    BrandGroup,
    BrandGroupMember,
    BrandMention,
    CitationSource,
    DomainAuthority,
    GeoScoreDaily,
    IndustryBenchmarkDaily,
    IndustryTopicDaily,
    KgBrand,
    KgBrandRelation,
    KgCategory,
    KgProduct,
    KgProductRelation,
    ResponseAnalysis,
    TopicScoreDaily,
)
from sqlalchemy import and_, desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.industries._dto import (
    IndustriesListOut,
    IndustryAvgGeoOut,
    IndustryAvgGeoPoint,
    IndustryDistributionOut,
    IndustryDistributionStats,
    IndustryEvent,
    IndustryGroupRow,
    IndustryGroupsOut,
    IndustryHeroCounts,
    IndustryKgOut,
    IndustryKpiCard,
    IndustryMoverRow,
    IndustryMoversOut,
    IndustryOverviewOut,
    IndustryRankingByEngineCell,
    IndustryRankingByEngineOut,
    IndustryRankingByEngineRow,
    IndustryRankingOut,
    IndustryRankingRow,
    IndustryRow,
    IndustrySegmentRow,
    IndustrySegmentsOut,
    IndustryTopDomainRow,
    IndustryTopDomainsOut,
    IndustryTopicDetailOut,
    IndustryTopicRow,
    IndustryTopicsOut,
    KGEdge,
    KGNode,
    TopBrandRow,
    TopicIntentCell,
    TopicIntentMatrixOut,
    TopicIntentRow,
)
from app.api.v1.projects._legacy_lookups import (
    resolve_brand_names,
    resolve_topic_names,
)

DEFAULT_WINDOW_DAYS = 30


def _resolve_window(from_date: date | None, to_date: date | None) -> tuple[date, date]:
    today = date.today()
    to_d = to_date or today
    from_d = from_date or (to_d - timedelta(days=DEFAULT_WINDOW_DAYS - 1))
    return from_d, to_d


def _period(from_d: date, to_d: date) -> dict[str, str]:
    return {"from": from_d.isoformat(), "to": to_d.isoformat()}


async def list_industries(session: AsyncSession) -> IndustriesListOut:
    stmt = (
        select(
            IndustryBenchmarkDaily.industry,
            func.count().label("cnt"),
        )
        .where(IndustryBenchmarkDaily.industry.isnot(None))
        .group_by(IndustryBenchmarkDaily.industry)
        .order_by(desc("cnt"))
    )
    rows = (await session.execute(stmt)).all()
    items = []
    for i, r in enumerate(rows):
        if not r[0]:
            continue
        items.append(
            IndustryRow(
                industry_id=i + 1,
                name=r[0],
                brand_count=int(r[1] or 0),
            )
        )
    return IndustriesListOut(items=items, total=len(items))


async def get_top_brands(
    session: AsyncSession,
    industry_id: int,
    *,
    n: int = 3,
) -> list[TopBrandRow]:
    today = date.today()
    stmt = (
        select(
            GeoScoreDaily.brand_id,
            func.avg(GeoScoreDaily.avg_geo_score).label("score"),
        )
        .where(
            GeoScoreDaily.date >= datetime.combine(today - timedelta(days=29), datetime.min.time())
        )
        .group_by(GeoScoreDaily.brand_id)
        .order_by(desc("score"))
        .limit(n)
    )
    rows = (await session.execute(stmt)).all()
    return [
        TopBrandRow(
            brand_id=r[0],
            brand_name=None,
            avg_geo_score=round(r[1], 2) if r[1] else None,
            rank=i + 1,
        )
        for i, r in enumerate(rows)
    ]


async def get_industry_overview(
    session: AsyncSession,
    industry_id: int,
    *,
    industry_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> IndustryOverviewOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    industry_name = industry_name or await _resolve_industry_name(session, industry_id)

    if industry_name:
        bench_filter = and_(
            IndustryBenchmarkDaily.industry == industry_name,
            IndustryBenchmarkDaily.date >= datetime.combine(from_d, datetime.min.time()),
            IndustryBenchmarkDaily.date <= datetime.combine(to_d, datetime.max.time()),
        )
    else:
        # No name → match nothing (aggregate is None)
        bench_filter = IndustryBenchmarkDaily.id == -1
    stmt = select(
        func.avg(IndustryBenchmarkDaily.avg_geo_score),
        func.avg(IndustryBenchmarkDaily.avg_mention_rate),
        func.avg(IndustryBenchmarkDaily.avg_sentiment),
        func.max(IndustryBenchmarkDaily.total_brands),
    ).where(bench_filter)
    r = (await session.execute(stmt)).one_or_none()
    avg_geo = r[0] if r else None
    avg_mention = r[1] if r else None
    avg_sent = r[2] if r else None
    total_brands = int(r[3]) if r and r[3] else 0

    kpi_cards = [
        IndustryKpiCard(
            label_zh="industry GEO",
            label_en="Industry GEO",
            value=round(avg_geo, 2) if avg_geo else 0,
        ),
        IndustryKpiCard(
            label_zh="avg mention rate",
            label_en="Avg Mention Rate",
            value=round((avg_mention or 0) * 100, 2),
            unit="%",
        ),
        IndustryKpiCard(
            label_zh="avg sentiment",
            label_en="Avg Sentiment",
            value=round(avg_sent or 0, 3),
        ),
        IndustryKpiCard(
            label_zh="active brands",
            label_en="Active Brands",
            value=total_brands,
        ),
    ]

    top_brands = await get_top_brands(session, industry_id, n=10)
    # Bulk-resolve brand names for top_brands.
    if top_brands:
        nm = await resolve_brand_names(session, [b.brand_id for b in top_brands])
        for b in top_brands:
            b.brand_name = nm.get(b.brand_id)

    # Hero counts (brand / topic / category / response).
    brand_count = total_brands
    topic_count = 0
    category_count = 0
    response_count = 0
    try:
        topic_count = int(
            (
                await session.execute(
                    select(func.count(func.distinct(IndustryTopicDaily.topic_id))).where(
                        and_(
                            IndustryTopicDaily.industry_id == industry_id,
                            IndustryTopicDaily.date
                            >= datetime.combine(from_d, datetime.min.time()),
                            IndustryTopicDaily.date <= datetime.combine(to_d, datetime.max.time()),
                        )
                    )
                )
            ).scalar_one()
            or 0
        )
    except Exception:
        topic_count = 0
    try:
        category_count = int(
            (
                await session.execute(
                    select(func.count(KgCategory.id)).where(
                        and_(
                            KgCategory.industry_id == industry_id,
                            KgCategory.status == "approved",
                        )
                    )
                )
            ).scalar_one()
            or 0
        )
    except Exception:
        category_count = 0
    if industry_name:
        try:
            response_count = int(
                (
                    await session.execute(
                        select(func.count(ResponseAnalysis.id)).where(
                            and_(
                                ResponseAnalysis.dimension_industry == industry_name,
                                ResponseAnalysis.analyzed_at
                                >= datetime.combine(from_d, datetime.min.time()),
                                ResponseAnalysis.analyzed_at
                                <= datetime.combine(to_d, datetime.max.time()),
                            )
                        )
                    )
                ).scalar_one()
                or 0
            )
        except Exception:
            response_count = 0

    hero = IndustryHeroCounts(
        brand_count=brand_count,
        topic_count=topic_count,
        category_count=category_count,
        response_count=response_count,
    )

    events: list[IndustryEvent] = []
    mover_stmt = (
        select(
            BrandMention.brand_id,
            func.count().label("cnt"),
            func.max(BrandMention.created_at).label("recent"),
        )
        .where(
            and_(
                BrandMention.created_at
                >= datetime.combine(to_d - timedelta(days=7), datetime.min.time()),
                BrandMention.created_at <= datetime.combine(to_d, datetime.max.time()),
            )
        )
        .group_by(BrandMention.brand_id)
        .order_by(desc("cnt"))
        .limit(3)
    )
    mover_rows = (await session.execute(mover_stmt)).all()
    for mr in mover_rows:
        recent = mr[2]
        if isinstance(recent, datetime):
            recent_d = recent.date()
        elif isinstance(recent, str):
            recent_d = date.fromisoformat(recent[:10])
        else:
            recent_d = to_d
        events.append(
            IndustryEvent(
                date=recent_d,
                event_type="trending_brand",
                description=f"brand {mr[0]} surged ({int(mr[1])} mentions in 7d)",
                brand_id=mr[0],
            )
        )

    has_data = bool(top_brands) or bool(avg_geo)
    return IndustryOverviewOut(
        industry_id=industry_id,
        industry_name=industry_name,
        period=_period(from_d, to_d),
        kpi_cards=kpi_cards,
        top_brands=top_brands,
        events_30d=events,
        hero_counts=hero,
        state="ok" if has_data else "empty",
    )


async def get_industry_ranking(
    session: AsyncSession,
    industry_id: int,
    *,
    industry_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    offset: int = 0,
    limit: int = 50,
    primary_brand_id: int | None = None,
) -> IndustryRankingOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    industry_name = industry_name or await _resolve_industry_name(session, industry_id)

    base_filter = and_(
        GeoScoreDaily.date >= datetime.combine(from_d, datetime.min.time()),
        GeoScoreDaily.date <= datetime.combine(to_d, datetime.max.time()),
    )
    if industry_name:
        base_filter = and_(base_filter, GeoScoreDaily.industry == industry_name)

    stmt = (
        select(
            GeoScoreDaily.brand_id,
            func.avg(GeoScoreDaily.avg_geo_score).label("geo"),
            func.avg(GeoScoreDaily.mention_rate).label("mention"),
            func.avg(GeoScoreDaily.avg_sov).label("sov"),
            func.avg(GeoScoreDaily.avg_sentiment).label("sentiment"),
            func.avg(GeoScoreDaily.citation_rate).label("citation"),
        )
        .where(base_filter)
        .group_by(GeoScoreDaily.brand_id)
        .order_by(desc("geo"))
        .offset(offset)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    brand_ids = [r[0] for r in rows]

    # Bulk-fetch sparklines (per-day avg_geo_score) for these brands.
    sparklines: dict[int, list[float]] = {bid: [] for bid in brand_ids}
    if brand_ids:
        spark_stmt = (
            select(
                GeoScoreDaily.brand_id,
                GeoScoreDaily.date,
                func.avg(GeoScoreDaily.avg_geo_score),
            )
            .where(
                and_(
                    GeoScoreDaily.brand_id.in_(brand_ids),
                    GeoScoreDaily.date >= datetime.combine(from_d, datetime.min.time()),
                    GeoScoreDaily.date <= datetime.combine(to_d, datetime.max.time()),
                )
            )
            .group_by(GeoScoreDaily.brand_id, GeoScoreDaily.date)
            .order_by(GeoScoreDaily.brand_id, GeoScoreDaily.date)
        )
        for bid, _d, val in (await session.execute(spark_stmt)).all():
            sparklines.setdefault(bid, []).append(round(float(val or 0), 2))

    name_map = await resolve_brand_names(session, brand_ids)

    items = [
        IndustryRankingRow(
            rank=offset + i + 1,
            brand_id=r[0],
            brand_name=name_map.get(r[0]),
            avg_geo_score=round(r[1], 2) if r[1] else None,
            avg_mention_rate=round(r[2], 4) if r[2] else None,
            avg_sov=round(r[3], 4) if r[3] else None,
            avg_sentiment=round(r[4], 3) if r[4] else None,
            avg_citation_rate=round(r[5], 4) if r[5] else None,
            sparkline=sparklines.get(r[0], []),
        )
        for i, r in enumerate(rows)
    ]

    count_stmt = select(func.count(func.distinct(GeoScoreDaily.brand_id))).where(base_filter)
    total = int((await session.execute(count_stmt)).scalar_one() or 0)

    # Compute my_rank if primary_brand_id given (across full population, not just page)
    my_rank: int | None = None
    if primary_brand_id is not None:
        full_stmt = (
            select(
                GeoScoreDaily.brand_id,
                func.avg(GeoScoreDaily.avg_geo_score).label("geo"),
            )
            .where(base_filter)
            .group_by(GeoScoreDaily.brand_id)
            .order_by(desc("geo"))
        )
        all_rows = (await session.execute(full_stmt)).all()
        for i, ar in enumerate(all_rows):
            if ar[0] == primary_brand_id:
                my_rank = i + 1
                break

    return IndustryRankingOut(
        industry_id=industry_id,
        period=_period(from_d, to_d),
        items=items,
        total=total,
        my_rank=my_rank,
        state="ok" if items else "empty",
    )


async def get_industry_topics(
    session: AsyncSession,
    industry_id: int,
    *,
    industry_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    limit: int = 50,
) -> IndustryTopicsOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    industry_name = industry_name or await _resolve_industry_name(session, industry_id)
    f = datetime.combine(from_d, datetime.min.time())
    t = datetime.combine(to_d, datetime.max.time())

    topic_stmt = (
        select(
            IndustryTopicDaily.topic_id,
            func.sum(IndustryTopicDaily.mention_count).label("mentions"),
            func.max(IndustryTopicDaily.unique_brand_count).label("brands"),
            func.avg(IndustryTopicDaily.hot_score).label("hot"),
        )
        .where(
            and_(
                IndustryTopicDaily.industry_id == industry_id,
                IndustryTopicDaily.date >= f,
                IndustryTopicDaily.date <= t,
            )
        )
        .group_by(IndustryTopicDaily.topic_id)
        .order_by(desc("mentions"))
        .limit(limit)
    )
    rows = (await session.execute(topic_stmt)).all()

    if not rows and industry_name:
        brand_rows = await session.execute(
            select(GeoScoreDaily.brand_id)
            .where(
                and_(
                    GeoScoreDaily.industry == industry_name,
                    GeoScoreDaily.date >= f,
                    GeoScoreDaily.date <= t,
                )
            )
            .group_by(GeoScoreDaily.brand_id)
        )
        brand_ids = [int(r[0]) for r in brand_rows.all()]
        if brand_ids:
            fallback_stmt = (
                select(
                    TopicScoreDaily.topic_id,
                    func.sum(TopicScoreDaily.mention_count).label("mentions"),
                    func.count(func.distinct(TopicScoreDaily.brand_id)).label("brands"),
                    func.avg(TopicScoreDaily.avg_geo_score).label("hot"),
                )
                .where(
                    and_(
                        TopicScoreDaily.brand_id.in_(brand_ids),
                        TopicScoreDaily.date >= f,
                        TopicScoreDaily.date <= t,
                    )
                )
                .group_by(TopicScoreDaily.topic_id)
                .order_by(desc("mentions"))
                .limit(limit)
            )
            rows = (await session.execute(fallback_stmt)).all()

    topic_ids = [int(r[0]) for r in rows if r[0] is not None]
    name_map = await resolve_topic_names(session, topic_ids)
    items = [
        IndustryTopicRow(
            topic_id=int(r[0]),
            topic_name=name_map.get(int(r[0])) or f"topic-{int(r[0])}",
            mention_count=int(r[1] or 0),
            unique_brand_count=int(r[2] or 0),
            hot_score=round(float(r[3]), 4) if r[3] is not None else None,
        )
        for r in rows
        if r[0] is not None
    ]

    return IndustryTopicsOut(
        industry_id=industry_id,
        period=_period(from_d, to_d),
        items=items,
        total=len(items),
        state="ok" if items else "empty",
    )


async def get_industry_kg(
    session: AsyncSession,
    industry_id: int,
    *,
    industry_name: str | None = None,
    focus: str | None = None,
    depth: int = 2,
) -> IndustryKgOut:
    """Industry knowledge graph (Phase K.6).

    Layers, in order of containment:
        depth 0: industry root
        depth 1: kg_categories under industry_id (level=1 only)
        depth 1: kg_brands joined with the brands surfaced by 30d
                 geo_score_daily — name comes from kg_brands.primary_name
                 when present, fallback to f"brand-{id}".
        depth 2: kg_products belonging to the discovered brands
                 (only when depth >= 2)

    Edges:
        BELONGS_TO    industry → category, industry → brand
        IN_CATEGORY   product  → category
        OF_BRAND      product  → brand
        COMPETES_WITH brand    ↔ brand   (kg_brand_relations)
        SAME_GROUP    brand    ↔ brand
        SUBSTITUTES / UPGRADES_TO / BUDGET_ALT_OF / PAIRS_WITH / COMPETES_WITH
                       product ↔ product (kg_product_relations) — depth >= 2
    """
    today = date.today()
    industry_name = industry_name or await _resolve_industry_name(session, industry_id)

    # Discover brands via 30d geo_score_daily (existing behavior — keeps
    # the graph populated even when kg_brands has no rows yet).
    stmt = select(GeoScoreDaily.brand_id, func.avg(GeoScoreDaily.avg_geo_score).label("g")).where(
        GeoScoreDaily.date >= datetime.combine(today - timedelta(days=29), datetime.min.time())
    )
    if industry_name:
        stmt = stmt.where(GeoScoreDaily.industry == industry_name)
    stmt = stmt.group_by(GeoScoreDaily.brand_id).order_by(desc("g")).limit(50)
    brand_rows = (await session.execute(stmt)).all()
    brand_ids: list[int] = [r[0] for r in brand_rows]
    brand_score: dict[int, float | None] = {
        r[0]: (round(r[1], 2) if r[1] else None) for r in brand_rows
    }

    # kg_brands metadata for richer naming + group membership
    kg_brand_rows: list[KgBrand] = []
    if brand_ids:
        kg_brand_rows = list(
            (await session.execute(select(KgBrand).where(KgBrand.brand_id.in_(brand_ids))))
            .scalars()
            .all()
        )
    kg_brand_by_id: dict[int, KgBrand] = {kb.brand_id: kb for kb in kg_brand_rows}

    # kg_categories (level=1 under this industry)
    cat_rows: list[KgCategory] = list(
        (
            await session.execute(
                select(KgCategory).where(
                    and_(
                        KgCategory.industry_id == industry_id,
                        KgCategory.status == "approved",
                    )
                )
            )
        )
        .scalars()
        .all()
    )

    industry_node_id = f"industry-{industry_id}"
    nodes: list[KGNode] = [
        KGNode(
            id=industry_node_id,
            type="industry",
            name=industry_name or f"industry-{industry_id}",
            metadata={"depth": 0},
        )
    ]
    edges: list[KGEdge] = []

    # Category nodes
    for cat in cat_rows:
        cat_node_id = f"category-{cat.id}"
        nodes.append(
            KGNode(
                id=cat_node_id,
                type="category",
                name=cat.name_zh,
                metadata={
                    "level": cat.level,
                    "parent_id": (
                        f"category-{cat.parent_id}" if cat.parent_id is not None else None
                    ),
                },
            )
        )
        # Top-level categories belong to the industry; children to parent.
        parent = f"category-{cat.parent_id}" if cat.parent_id is not None else industry_node_id
        edges.append(KGEdge(source=parent, target=cat_node_id, type="BELONGS_TO", weight=1.0))

    # Brand nodes
    for bid in brand_ids:
        node_id = f"brand-{bid}"
        kb = kg_brand_by_id.get(bid)
        nodes.append(
            KGNode(
                id=node_id,
                type="brand",
                name=kb.primary_name if kb else f"brand-{bid}",
                metadata={
                    "avg_geo_score": brand_score.get(bid),
                    "group_id": kb.group_id if kb else None,
                    "official_domains": kb.official_domains if kb else None,
                },
            )
        )
        edges.append(KGEdge(source=industry_node_id, target=node_id, type="BELONGS_TO", weight=1.0))

    # Brand-to-brand relations (COMPETES_WITH / SAME_GROUP)
    if len(brand_ids) >= 2:
        rel_stmt = select(KgBrandRelation).where(
            and_(
                KgBrandRelation.brand_a_id.in_(brand_ids),
                KgBrandRelation.brand_b_id.in_(brand_ids),
            )
        )
        for rel in (await session.execute(rel_stmt)).scalars().all():
            edges.append(
                KGEdge(
                    source=f"brand-{rel.brand_a_id}",
                    target=f"brand-{rel.brand_b_id}",
                    type=rel.type,
                    weight=rel.confidence,
                )
            )

    # Products (depth >= 2)
    if depth >= 2 and brand_ids:
        prod_rows: list[KgProduct] = list(
            (
                await session.execute(
                    select(KgProduct).where(
                        and_(
                            KgProduct.brand_id.in_(brand_ids),
                            KgProduct.status == "approved",
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        product_ids: list[int] = []
        for p in prod_rows:
            pn_id = f"product-{p.product_id}"
            product_ids.append(p.product_id)
            nodes.append(
                KGNode(
                    id=pn_id,
                    type="product",
                    name=p.primary_name,
                    metadata={
                        "brand_id": p.brand_id,
                        "category_id": p.category_id,
                    },
                )
            )
            edges.append(
                KGEdge(source=f"brand-{p.brand_id}", target=pn_id, type="OF_BRAND", weight=1.0)
            )
            if p.category_id is not None:
                edges.append(
                    KGEdge(
                        source=f"category-{p.category_id}",
                        target=pn_id,
                        type="IN_CATEGORY",
                        weight=1.0,
                    )
                )

        # Product-to-product relations
        if len(product_ids) >= 2:
            prel_stmt = select(KgProductRelation).where(
                and_(
                    KgProductRelation.product_a_id.in_(product_ids),
                    KgProductRelation.product_b_id.in_(product_ids),
                )
            )
            for prel in (await session.execute(prel_stmt)).scalars().all():
                edges.append(
                    KGEdge(
                        source=f"product-{prel.product_a_id}",
                        target=f"product-{prel.product_b_id}",
                        type=prel.type,
                        weight=prel.confidence or 1.0,
                    )
                )

    return IndustryKgOut(
        industry_id=industry_id,
        focus=focus or industry_node_id,
        depth=depth,
        nodes=nodes,
        edges=edges,
        state="ok" if (brand_rows or cat_rows) else "empty",
    )


# ─── /industries/:id/avg-geo-score ─────────────────────────────────
async def get_industry_avg_geo_score(
    session: AsyncSession,
    industry_id: int,
    *,
    industry_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> IndustryAvgGeoOut:
    """Daily industry-level GEO benchmark from `industry_benchmark_daily`.

    Replaces the FE-side mock fallback in BrandPanoramaPanel's hero
    industry-average comparison bar. Pipeline writes this table via
    aggregator.aggregate_industry_benchmark() each day.
    """
    today = date.today()
    to_d = to_date or today
    from_d = from_date or (to_d - timedelta(days=29))

    name = industry_name or await _resolve_industry_name(session, industry_id)
    if not name:
        return IndustryAvgGeoOut(
            industry_id=industry_id,
            industry_name=None,
            period={"from": from_d.isoformat(), "to": to_d.isoformat()},
            points=[],
            summary={},
            state="empty",
        )

    # Pipeline writes score_p25/p50/p75 (percentiles) — use p50 as median.
    # top10_avg derivation from top_brands_json is deferred (Phase A
    # follow-up); return None for now.
    stmt = (
        select(
            IndustryBenchmarkDaily.date,
            func.avg(IndustryBenchmarkDaily.avg_geo_score).label("avg_geo"),
            func.avg(IndustryBenchmarkDaily.score_p50).label("median"),
            func.max(IndustryBenchmarkDaily.total_brands).label("total"),
        )
        .where(
            and_(
                IndustryBenchmarkDaily.industry == name,
                IndustryBenchmarkDaily.date >= datetime.combine(from_d, datetime.min.time()),
                IndustryBenchmarkDaily.date <= datetime.combine(to_d, datetime.max.time()),
            )
        )
        .group_by(IndustryBenchmarkDaily.date)
        .order_by(IndustryBenchmarkDaily.date)
    )
    rows = list((await session.execute(stmt)).all())

    points = [
        IndustryAvgGeoPoint(
            date=(d.date().isoformat() if hasattr(d, "date") else str(d)),
            avg_geo_score=float(g) if g is not None else None,
            industry_median=float(m) if m is not None else None,
            top10_avg=None,
            total_brands=int(n) if n is not None else None,
        )
        for d, g, m, n in rows
    ]

    summary: dict[str, float | None] = {}
    if points:
        latest = points[-1]
        summary = {
            "avg_geo_score": latest.avg_geo_score,
            "industry_median": latest.industry_median,
            "top10_avg": None,
        }

    return IndustryAvgGeoOut(
        industry_id=industry_id,
        industry_name=name,
        period={"from": from_d.isoformat(), "to": to_d.isoformat()},
        points=points,
        summary=summary,
        state="ok" if points else "empty",
    )


# ─── Phase 5: Chart endpoints ──────────────────────────────────────


def _percentiles(values: list[float]) -> tuple[float | None, float | None, float | None]:
    if not values:
        return (None, None, None)
    s = sorted(values)
    n = len(s)

    def q(p: float) -> float:
        if n == 1:
            return s[0]
        idx = (n - 1) * p
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        frac = idx - lo
        return s[lo] * (1 - frac) + s[hi] * frac

    return (q(0.25), q(0.5), q(0.75))


async def get_industry_distribution(
    session: AsyncSession,
    industry_id: int,
    *,
    industry_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> IndustryDistributionOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    industry_name = industry_name or await _resolve_industry_name(session, industry_id)
    f = datetime.combine(from_d, datetime.min.time())
    t = datetime.combine(to_d, datetime.max.time())

    base_filter = and_(GeoScoreDaily.date >= f, GeoScoreDaily.date <= t)
    if industry_name:
        base_filter = and_(base_filter, GeoScoreDaily.industry == industry_name)

    stmt = (
        select(
            GeoScoreDaily.brand_id,
            func.avg(GeoScoreDaily.mention_rate),
            func.avg(GeoScoreDaily.avg_sov),
            func.avg(GeoScoreDaily.avg_sentiment),
            func.avg(GeoScoreDaily.citation_rate),
            func.avg(GeoScoreDaily.industry_rank),
        )
        .where(base_filter)
        .group_by(GeoScoreDaily.brand_id)
    )
    rows = (await session.execute(stmt)).all()

    metric_to_idx = {
        "mention_rate": 1,
        "sov": 2,
        "sentiment": 3,
        "citation": 4,
        "rank": 5,
    }
    stats: list[IndustryDistributionStats] = []
    for metric, idx in metric_to_idx.items():
        values = [float(r[idx]) for r in rows if r[idx] is not None]
        # mention_rate / sov / citation are 0..1; multiply for UI display percent
        if metric in ("mention_rate", "sov", "citation"):
            values = [v * 100 for v in values]
        elif metric == "sentiment":
            values = [v * 100 for v in values]
        p25, p50, p75 = _percentiles(values)
        stats.append(
            IndustryDistributionStats(
                metric=metric,
                values=[round(v, 2) for v in values],
                p25=round(p25, 2) if p25 is not None else None,
                p50=round(p50, 2) if p50 is not None else None,
                p75=round(p75, 2) if p75 is not None else None,
                min=round(min(values), 2) if values else None,
                max=round(max(values), 2) if values else None,
                n=len(values),
            )
        )

    return IndustryDistributionOut(
        industry_id=industry_id,
        industry_name=industry_name,
        period=_period(from_d, to_d),
        stats=stats,
        state="ok" if rows else "empty",
    )


async def get_industry_movers(
    session: AsyncSession,
    industry_id: int,
    *,
    industry_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    limit: int = 5,
) -> IndustryMoversOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    industry_name = industry_name or await _resolve_industry_name(session, industry_id)
    half = max(7, (to_d - from_d).days // 2)
    mid = to_d - timedelta(days=half)

    f_recent = datetime.combine(mid, datetime.min.time())
    t_recent = datetime.combine(to_d, datetime.max.time())
    f_prev = datetime.combine(from_d, datetime.min.time())
    t_prev = datetime.combine(mid - timedelta(days=1), datetime.max.time())

    industry_filter = GeoScoreDaily.industry == industry_name if industry_name else None

    async def _avg(brand_filter: Any, frm: datetime, to: datetime) -> dict[int, float]:
        stmt = select(GeoScoreDaily.brand_id, func.avg(GeoScoreDaily.avg_geo_score)).where(
            GeoScoreDaily.date >= frm, GeoScoreDaily.date <= to
        )
        if brand_filter is not None:
            stmt = stmt.where(brand_filter)
        stmt = stmt.group_by(GeoScoreDaily.brand_id)
        rs = (await session.execute(stmt)).all()
        return {int(r[0]): float(r[1]) for r in rs if r[1] is not None}

    recent = await _avg(industry_filter, f_recent, t_recent)
    prev = await _avg(industry_filter, f_prev, t_prev)

    deltas: list[tuple[int, float, float]] = []
    for bid, cur in recent.items():
        before = prev.get(bid)
        if before and before > 0:
            d = (cur - before) / before * 100
            deltas.append((bid, round(d, 2), cur))
    deltas.sort(key=lambda x: x[1])
    losers_raw = deltas[:limit]
    gainers_raw = sorted(deltas[-limit:], key=lambda x: -x[1])

    all_ids = [d[0] for d in losers_raw + gainers_raw]
    name_map = await resolve_brand_names(session, all_ids)

    # Sparklines
    sparkline_map: dict[int, list[float]] = {bid: [] for bid in all_ids}
    if all_ids:
        spark_stmt = (
            select(
                GeoScoreDaily.brand_id,
                GeoScoreDaily.date,
                func.avg(GeoScoreDaily.avg_geo_score),
            )
            .where(
                and_(
                    GeoScoreDaily.brand_id.in_(all_ids),
                    GeoScoreDaily.date >= f_prev,
                    GeoScoreDaily.date <= t_recent,
                )
            )
            .group_by(GeoScoreDaily.brand_id, GeoScoreDaily.date)
            .order_by(GeoScoreDaily.brand_id, GeoScoreDaily.date)
        )
        for bid, _d, v in (await session.execute(spark_stmt)).all():
            sparkline_map.setdefault(int(bid), []).append(round(float(v or 0), 2))

    def _row(triple: tuple[int, float, float]) -> IndustryMoverRow:
        bid, delta, cur = triple
        return IndustryMoverRow(
            brand_id=bid,
            brand_name=name_map.get(bid),
            delta_pct=delta,
            current_pano=round(cur, 2),
            sparkline=sparkline_map.get(bid, []),
            driver=None,
        )

    return IndustryMoversOut(
        industry_id=industry_id,
        period=_period(from_d, to_d),
        gainers=[_row(x) for x in gainers_raw],
        losers=[_row(x) for x in losers_raw],
        state="ok" if deltas else "empty",
    )


async def get_industry_groups(
    session: AsyncSession,
    industry_id: int,
    *,
    industry_name: str | None = None,
    limit: int = 8,
) -> IndustryGroupsOut:
    today = date.today()
    industry_name = industry_name or await _resolve_industry_name(session, industry_id)
    f = datetime.combine(today - timedelta(days=29), datetime.min.time())
    base_filter = GeoScoreDaily.date >= f
    if industry_name:
        base_filter = and_(base_filter, GeoScoreDaily.industry == industry_name)

    brand_stmt = (
        select(
            GeoScoreDaily.brand_id,
            func.avg(GeoScoreDaily.avg_geo_score),
            func.avg(GeoScoreDaily.avg_sov),
        )
        .where(base_filter)
        .group_by(GeoScoreDaily.brand_id)
    )
    brand_rows = (await session.execute(brand_stmt)).all()
    brand_metrics = {
        int(r[0]): (
            float(r[1]) if r[1] is not None else 0,
            float(r[2]) if r[2] is not None else 0,
        )
        for r in brand_rows
    }
    if not brand_metrics:
        return IndustryGroupsOut(industry_id=industry_id, items=[], state="empty")

    member_stmt = select(BrandGroupMember).where(
        BrandGroupMember.brand_id.in_(list(brand_metrics.keys()))
    )
    members = list((await session.execute(member_stmt)).scalars().all())
    by_group: dict[int, list[int]] = defaultdict(list)
    for m in members:
        by_group[m.group_id].append(m.brand_id)

    if not by_group:
        return IndustryGroupsOut(industry_id=industry_id, items=[], state="empty")

    groups = list(
        (await session.execute(select(BrandGroup).where(BrandGroup.id.in_(list(by_group.keys())))))
        .scalars()
        .all()
    )
    group_meta = {g.id: g for g in groups}

    all_member_ids = [bid for ids in by_group.values() for bid in ids]
    name_map = await resolve_brand_names(session, all_member_ids)

    items: list[IndustryGroupRow] = []
    for gid, member_ids in by_group.items():
        g = group_meta.get(gid)
        if not g:
            continue
        agg_geo = sum(brand_metrics[bid][0] for bid in member_ids if bid in brand_metrics) / max(
            1, len(member_ids)
        )
        agg_sov = sum(brand_metrics[bid][1] for bid in member_ids if bid in brand_metrics) / max(
            1, len(member_ids)
        )
        items.append(
            IndustryGroupRow(
                group_id=gid,
                group_name=g.name,
                parent_company=g.parent_company,
                member_brand_ids=member_ids,
                member_brand_names=[name_map.get(b) or f"#{b}" for b in member_ids],
                aggregate_geo_score=round(agg_geo, 2),
                aggregate_sov=round(agg_sov, 4),
            )
        )
    items.sort(key=lambda r: -(r.aggregate_geo_score or 0))
    items = items[:limit]
    return IndustryGroupsOut(
        industry_id=industry_id,
        items=items,
        state="ok" if items else "empty",
    )


async def get_industry_top_domains(
    session: AsyncSession,
    industry_id: int,
    *,
    industry_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    limit: int = 10,
) -> IndustryTopDomainsOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    industry_name = industry_name or await _resolve_industry_name(session, industry_id)
    f = datetime.combine(from_d, datetime.min.time())
    t = datetime.combine(to_d, datetime.max.time())

    # Restrict to brands in industry.
    brand_filter = None
    if industry_name:
        try:
            br = await session.execute(
                text("SELECT id FROM brands WHERE industry = :ind"),
                {"ind": industry_name},
            )
            brand_filter = [int(r[0]) for r in br.all()]
        except Exception:
            brand_filter = None

    stmt = (
        select(
            CitationSource.domain,
            func.count().label("cnt"),
            func.max(DomainAuthority.tier),
        )
        .select_from(CitationSource)
        .join(BrandMention, BrandMention.id == CitationSource.mention_id)
        .outerjoin(DomainAuthority, DomainAuthority.domain == CitationSource.domain)
        .where(
            and_(
                CitationSource.created_at >= f,
                CitationSource.created_at <= t,
                CitationSource.domain.isnot(None),
            )
        )
    )
    if brand_filter:
        stmt = stmt.where(BrandMention.brand_id.in_(brand_filter))
    stmt = stmt.group_by(CitationSource.domain).order_by(desc("cnt")).limit(limit)
    rows = (await session.execute(stmt)).all()

    items: list[IndustryTopDomainRow] = []
    for r in rows:
        domain = r[0]
        total = int(r[1] or 0)
        tier = int(r[2]) if r[2] is not None else None

        # Top brand citing this domain.
        top_stmt = (
            select(BrandMention.brand_id, func.count().label("c"))
            .select_from(CitationSource)
            .join(BrandMention, BrandMention.id == CitationSource.mention_id)
            .where(
                and_(
                    CitationSource.domain == domain,
                    CitationSource.created_at >= f,
                    CitationSource.created_at <= t,
                )
            )
            .group_by(BrandMention.brand_id)
            .order_by(desc("c"))
            .limit(1)
        )
        if brand_filter:
            top_stmt = top_stmt.where(BrandMention.brand_id.in_(brand_filter))
        top = (await session.execute(top_stmt)).one_or_none()
        top_bid: int | None = int(top[0]) if top else None
        top_count = int(top[1]) if top else 0
        nm = await resolve_brand_names(session, [top_bid]) if top_bid else {}
        items.append(
            IndustryTopDomainRow(
                domain=domain,
                tier=tier,
                total_citations=total,
                top_brand_id=top_bid,
                top_brand_name=nm.get(top_bid) if top_bid else None,
                top_brand_share=round(top_count / total, 3) if total else None,
            )
        )
    return IndustryTopDomainsOut(
        industry_id=industry_id,
        period=_period(from_d, to_d),
        items=items,
        state="ok" if items else "empty",
    )


async def get_industry_segments(
    session: AsyncSession,
    industry_id: int,
    *,
    industry_name: str | None = None,
    limit: int = 5,
) -> IndustrySegmentsOut:
    today = date.today()
    industry_name = industry_name or await _resolve_industry_name(session, industry_id)
    f = datetime.combine(today - timedelta(days=29), datetime.min.time())
    base_filter = GeoScoreDaily.date >= f
    if industry_name:
        base_filter = and_(base_filter, GeoScoreDaily.industry == industry_name)

    brand_stmt = (
        select(
            GeoScoreDaily.brand_id,
            func.avg(GeoScoreDaily.avg_geo_score),
            func.avg(GeoScoreDaily.mention_rate),
            func.avg(GeoScoreDaily.avg_sov),
            func.avg(GeoScoreDaily.avg_sentiment),
        )
        .where(base_filter)
        .group_by(GeoScoreDaily.brand_id)
    )
    brand_rows = (await session.execute(brand_stmt)).all()
    if not brand_rows:
        return IndustrySegmentsOut(industry_id=industry_id, items=[], state="empty")

    bids = [int(r[0]) for r in brand_rows]
    pos_stmt = select(KgBrand.brand_id, KgBrand.positioning).where(KgBrand.brand_id.in_(bids))
    try:
        pos_map = {int(r[0]): r[1] for r in (await session.execute(pos_stmt)).all()}
    except Exception:
        pos_map = {}

    name_map = await resolve_brand_names(session, bids)

    by_segment: dict[str, list[IndustryRankingRow]] = defaultdict(list)
    rank_counter: dict[str, int] = defaultdict(int)
    for r in sorted(brand_rows, key=lambda x: -(float(x[1] or 0))):
        bid = int(r[0])
        seg = pos_map.get(bid) or "niche_emerging"
        rank_counter[seg] += 1
        if rank_counter[seg] > limit:
            continue
        by_segment[seg].append(
            IndustryRankingRow(
                rank=rank_counter[seg],
                brand_id=bid,
                brand_name=name_map.get(bid),
                avg_geo_score=round(float(r[1]), 2) if r[1] is not None else None,
                avg_mention_rate=round(float(r[2]), 4) if r[2] is not None else None,
                avg_sov=round(float(r[3]), 4) if r[3] is not None else None,
                avg_sentiment=round(float(r[4]), 3) if r[4] is not None else None,
            )
        )

    label_map = {
        "luxury_intl": "国际高端",
        "mass_premium": "大众高端",
        "niche_emerging": "小众-新锐",
    }
    items = [
        IndustrySegmentRow(
            segment=seg,
            label_zh=label_map.get(seg, seg),
            items=by_segment.get(seg, []),
        )
        for seg in ("luxury_intl", "mass_premium", "niche_emerging")
    ]
    return IndustrySegmentsOut(
        industry_id=industry_id,
        items=items,
        state="ok" if any(seg.items for seg in items) else "empty",
    )


async def get_industry_ranking_by_engine(
    session: AsyncSession,
    industry_id: int,
    *,
    industry_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    limit: int = 10,
) -> IndustryRankingByEngineOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    industry_name = industry_name or await _resolve_industry_name(session, industry_id)
    f = datetime.combine(from_d, datetime.min.time())
    t = datetime.combine(to_d, datetime.max.time())
    base_filter = and_(GeoScoreDaily.date >= f, GeoScoreDaily.date <= t)
    if industry_name:
        base_filter = and_(base_filter, GeoScoreDaily.industry == industry_name)

    overall_stmt = (
        select(
            GeoScoreDaily.brand_id,
            func.avg(GeoScoreDaily.avg_geo_score).label("g"),
        )
        .where(base_filter)
        .group_by(GeoScoreDaily.brand_id)
        .order_by(desc("g"))
        .limit(limit)
    )
    overall = (await session.execute(overall_stmt)).all()
    bids = [int(r[0]) for r in overall]
    if not bids:
        return IndustryRankingByEngineOut(
            industry_id=industry_id,
            period=_period(from_d, to_d),
            engines=[],
            items=[],
            state="empty",
        )

    cell_stmt = (
        select(
            GeoScoreDaily.brand_id,
            GeoScoreDaily.target_llm,
            func.avg(GeoScoreDaily.avg_geo_score),
        )
        .where(
            and_(
                GeoScoreDaily.brand_id.in_(bids),
                GeoScoreDaily.date >= f,
                GeoScoreDaily.date <= t,
                GeoScoreDaily.target_llm.isnot(None),
            )
        )
        .group_by(GeoScoreDaily.brand_id, GeoScoreDaily.target_llm)
    )
    cells: dict[tuple[int, str], float] = {}
    engines: set[str] = set()
    for bid, eng, val in (await session.execute(cell_stmt)).all():
        engines.add(eng or "unknown")
        cells[(int(bid), eng or "unknown")] = float(val or 0)

    engine_list = sorted(engines)
    name_map = await resolve_brand_names(session, bids)
    items: list[IndustryRankingByEngineRow] = []
    # Compute per-engine ranks
    rank_per_engine: dict[str, dict[int, int]] = {}
    for eng in engine_list:
        ranked = sorted(bids, key=lambda b: -cells.get((b, eng), -1))
        rank_per_engine[eng] = {b: i + 1 for i, b in enumerate(ranked)}

    for i, bid in enumerate(bids):
        rcells = []
        scores = []
        for eng in engine_list:
            val = cells.get((bid, eng))
            scores.append(val if val is not None else 0)
            rcells.append(
                IndustryRankingByEngineCell(
                    engine=eng,
                    rank=rank_per_engine.get(eng, {}).get(bid),
                    avg_geo_score=round(val, 2) if val is not None else None,
                )
            )
        delta_max = round(max(scores) - min(scores), 2) if scores else None
        items.append(
            IndustryRankingByEngineRow(
                brand_id=bid,
                brand_name=name_map.get(bid),
                overall_rank=i + 1,
                cells=rcells,
                delta_max=delta_max,
            )
        )
    return IndustryRankingByEngineOut(
        industry_id=industry_id,
        period=_period(from_d, to_d),
        engines=engine_list,
        items=items,
        state="ok",
    )


async def get_industry_topic_intent_matrix(
    session: AsyncSession,
    industry_id: int,
    *,
    industry_name: str | None = None,
    limit: int = 8,
    from_date: date | None = None,
    to_date: date | None = None,
) -> TopicIntentMatrixOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    industry_name = industry_name or await _resolve_industry_name(session, industry_id)
    f = datetime.combine(from_d, datetime.min.time())
    t = datetime.combine(to_d, datetime.max.time())

    industry_brands: list[int] = []
    if industry_name:
        try:
            br = await session.execute(
                text("SELECT id FROM brands WHERE industry = :ind"),
                {"ind": industry_name},
            )
            industry_brands = [int(r[0]) for r in br.all()]
        except Exception:
            industry_brands = []

    # Top topics by mention_count (industry-scoped if possible).
    topic_stmt = select(
        TopicScoreDaily.topic_id,
        func.sum(TopicScoreDaily.mention_count).label("c"),
    ).where(and_(TopicScoreDaily.date >= f, TopicScoreDaily.date <= t))
    if industry_brands:
        topic_stmt = topic_stmt.where(TopicScoreDaily.brand_id.in_(industry_brands))
    topic_stmt = topic_stmt.group_by(TopicScoreDaily.topic_id).order_by(desc("c")).limit(limit)
    topic_rows = (await session.execute(topic_stmt)).all()
    topic_ids = [int(r[0]) for r in topic_rows]
    if not topic_ids:
        return TopicIntentMatrixOut(industry_id=industry_id, intents=[], rows=[], state="empty")
    name_map = await resolve_topic_names(session, topic_ids)

    # Get intent distribution per topic from llm_responses.
    try:
        result = await session.execute(
            text(
                """
                SELECT t.id AS topic_id, r.intent AS intent, COUNT(*)::int AS c
                FROM llm_responses r
                JOIN prompts p ON p.id = r.prompt_id
                JOIN topics t ON t.id = p.topic_id
                WHERE t.id = ANY(:ids)
                  AND r.created_at >= :f
                  AND r.created_at <= :t
                GROUP BY t.id, r.intent
                """
            ),
            {"ids": topic_ids, "f": f, "t": t},
        )
        rows = result.all()
    except Exception:
        rows = []

    by_topic: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    intents: set[str] = set()
    for tid, intent, c in rows:
        intent_label = intent or "unknown"
        intents.add(intent_label)
        by_topic[int(tid)][intent_label] += int(c or 0)

    intent_list = sorted(intents) or ["unknown"]
    out_rows: list[TopicIntentRow] = []
    for tid in topic_ids:
        bucket = by_topic.get(tid, {})
        total = sum(bucket.values()) or 1
        cells = [
            TopicIntentCell(
                intent=intent,
                count=bucket.get(intent, 0),
                pct=round(bucket.get(intent, 0) / total * 100, 1),
            )
            for intent in intent_list
        ]
        out_rows.append(
            TopicIntentRow(
                topic_id=tid,
                topic_name=name_map.get(tid) or f"topic-{tid}",
                total_count=total,
                cells=cells,
            )
        )
    return TopicIntentMatrixOut(
        industry_id=industry_id,
        intents=intent_list,
        rows=out_rows,
        state="ok" if any(r.total_count > 0 for r in out_rows) else "empty",
    )


async def get_industry_topic_detail(
    session: AsyncSession,
    industry_id: int,
    topic_id: int,
    *,
    industry_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> IndustryTopicDetailOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    industry_name = industry_name or await _resolve_industry_name(session, industry_id)
    f = datetime.combine(from_d, datetime.min.time())
    t = datetime.combine(to_d, datetime.max.time())

    name = (await resolve_topic_names(session, [topic_id])).get(topic_id) or f"topic-{topic_id}"

    agg_stmt = select(
        func.sum(TopicScoreDaily.mention_count),
        func.count(func.distinct(TopicScoreDaily.brand_id)),
        func.avg(TopicScoreDaily.avg_sentiment_score),
    ).where(
        and_(
            TopicScoreDaily.topic_id == topic_id,
            TopicScoreDaily.date >= f,
            TopicScoreDaily.date <= t,
        )
    )
    agg = (await session.execute(agg_stmt)).one_or_none()
    mention_count = int(agg[0] or 0) if agg else 0
    unique_brands = int(agg[1] or 0) if agg else 0
    avg_sent = float(agg[2]) if agg and agg[2] is not None else None

    # Top brands for this topic.
    top_stmt = (
        select(
            TopicScoreDaily.brand_id,
            func.sum(TopicScoreDaily.mention_count).label("c"),
            func.avg(TopicScoreDaily.avg_geo_score).label("g"),
        )
        .where(
            and_(
                TopicScoreDaily.topic_id == topic_id,
                TopicScoreDaily.date >= f,
                TopicScoreDaily.date <= t,
            )
        )
        .group_by(TopicScoreDaily.brand_id)
        .order_by(desc("c"))
        .limit(5)
    )
    top_rows = (await session.execute(top_stmt)).all()
    top_ids = [int(r[0]) for r in top_rows]
    name_map = await resolve_brand_names(session, top_ids)
    top_brands = [
        TopBrandRow(
            brand_id=int(r[0]),
            brand_name=name_map.get(int(r[0])),
            avg_geo_score=round(float(r[2]), 2) if r[2] is not None else None,
            rank=i + 1,
        )
        for i, r in enumerate(top_rows)
    ]

    # Sparkline: per-day mention_count for topic.
    spark_stmt = (
        select(
            TopicScoreDaily.date,
            func.sum(TopicScoreDaily.mention_count),
        )
        .where(
            and_(
                TopicScoreDaily.topic_id == topic_id,
                TopicScoreDaily.date >= f,
                TopicScoreDaily.date <= t,
            )
        )
        .group_by(TopicScoreDaily.date)
        .order_by(TopicScoreDaily.date)
    )
    sparkline = [float(v or 0) for _, v in (await session.execute(spark_stmt)).all()]

    return IndustryTopicDetailOut(
        industry_id=industry_id,
        topic_id=topic_id,
        topic_name=name,
        mention_count=mention_count,
        unique_brand_count=unique_brands,
        avg_sentiment=round(avg_sent, 3) if avg_sent is not None else None,
        top_brands=top_brands,
        sparkline=sparkline,
        intents=[],
        state="ok" if mention_count else "empty",
    )


async def _resolve_industry_name(session: AsyncSession, industry_id: int) -> str | None:
    """Map numeric industry_id → industry_name (the table key).

    `industry_id` is a synthetic position-based ID assigned by
    `list_industries`: rows are sorted by mention count desc, and the
    1-indexed position is exposed as `industry_id`. Resolution here must
    mirror that exact ordering, otherwise downstream endpoints
    (avg-geo-score, overview, ranking, …) load the wrong industry and
    return empty results — see issue #975.

    Falls back to `brands.industry` distinct values when the benchmark
    table is empty (live deployments may have industries with brands but
    no aggregated benchmarks yet).
    """
    bench_stmt = (
        select(IndustryBenchmarkDaily.industry, func.count().label("cnt"))
        .where(IndustryBenchmarkDaily.industry.isnot(None))
        .group_by(IndustryBenchmarkDaily.industry)
        .order_by(desc("cnt"))
    )
    rows = list((await session.execute(bench_stmt)).all())
    names: list[str] = []
    for r in rows:
        if r[0]:
            names.append(str(r[0]))

    if not names:
        try:
            brand_rows = await session.execute(
                text(
                    "SELECT industry, COUNT(*) AS cnt FROM brands "
                    "WHERE industry IS NOT NULL AND industry <> '' "
                    "GROUP BY industry ORDER BY cnt DESC"
                )
            )
            for r in brand_rows.all():
                if r[0]:
                    names.append(str(r[0]))
        except Exception:
            return None

    idx = industry_id - 1
    if 0 <= idx < len(names):
        return names[idx]
    return None
