"""Service for /v1/industries (Phase 3)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from genpano_models import (
    BrandMention,
    GeoScoreDaily,
    IndustryBenchmarkDaily,
    KgBrand,
    KgBrandRelation,
    KgCategory,
    KgProduct,
    KgProductRelation,
)
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.industries._dto import (
    IndustriesListOut,
    IndustryAvgGeoOut,
    IndustryAvgGeoPoint,
    IndustryEvent,
    IndustryKgOut,
    IndustryKpiCard,
    IndustryOverviewOut,
    IndustryRankingOut,
    IndustryRankingRow,
    IndustryRow,
    IndustryTopicRow,
    IndustryTopicsOut,
    KGEdge,
    KGNode,
    TopBrandRow,
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
) -> IndustryRankingOut:
    from_d, to_d = _resolve_window(from_date, to_date)

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
        )
        .where(base_filter)
        .group_by(GeoScoreDaily.brand_id)
        .order_by(desc("geo"))
        .offset(offset)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    items = [
        IndustryRankingRow(
            rank=offset + i + 1,
            brand_id=r[0],
            brand_name=None,
            avg_geo_score=round(r[1], 2) if r[1] else None,
            avg_mention_rate=round(r[2], 4) if r[2] else None,
            avg_sov=round(r[3], 4) if r[3] else None,
            avg_sentiment=round(r[4], 3) if r[4] else None,
        )
        for i, r in enumerate(rows)
    ]

    count_stmt = select(func.count(func.distinct(GeoScoreDaily.brand_id))).where(base_filter)
    total = int((await session.execute(count_stmt)).scalar_one() or 0)

    return IndustryRankingOut(
        industry_id=industry_id,
        period=_period(from_d, to_d),
        items=items,
        total=total,
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

    stmt = (
        select(
            BrandMention.brand_name,
            func.count(func.distinct(BrandMention.response_id)).label("cnt"),
            func.count(func.distinct(BrandMention.brand_id)).label("brands"),
        )
        .where(
            and_(
                BrandMention.created_at >= datetime.combine(from_d, datetime.min.time()),
                BrandMention.created_at <= datetime.combine(to_d, datetime.max.time()),
            )
        )
        .group_by(BrandMention.brand_name)
        .order_by(desc("cnt"))
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    items = [
        IndustryTopicRow(
            topic_id=None,
            topic_name=str(r[0] or "(unknown)"),
            mention_count=int(r[1] or 0),
            unique_brand_count=int(r[2] or 0),
            hot_score=None,
        )
        for r in rows
        if r[0]
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


async def _resolve_industry_name(session: AsyncSession, industry_id: int) -> str | None:
    """Map numeric industry_id → industry_name (the table key).

    Currently leverages the same lookup used by industry_overview/ranking:
    pick the most-represented industry name in industry_benchmark_daily
    matching industry_id. (industry table has 1:1 id↔name; this is a
    deliberate fallback in case the upstream `industries` mirror is empty.)
    """
    stmt = (
        select(IndustryBenchmarkDaily.industry, func.count())
        .where(IndustryBenchmarkDaily.industry.isnot(None))
        .group_by(IndustryBenchmarkDaily.industry)
        .order_by(func.count().desc())
    )
    rows = list((await session.execute(stmt)).all())
    if not rows:
        return None
    # Pick the row whose industry slug ends in the numeric id, or the
    # most-frequent if no match.
    for name, _ in rows:
        if name and (str(industry_id) in name or name == str(industry_id)):
            return str(name)
    return str(rows[0][0]) if rows[0][0] is not None else None
