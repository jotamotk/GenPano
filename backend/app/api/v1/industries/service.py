"""Service for /v1/industries (Phase 3)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from genpano_models import (
    BrandMention,
    GeoScoreDaily,
    IndustryBenchmarkDaily,
)
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.industries._dto import (
    IndustriesListOut,
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
    today = date.today()
    stmt = select(GeoScoreDaily.brand_id, func.avg(GeoScoreDaily.avg_geo_score).label("g")).where(
        GeoScoreDaily.date >= datetime.combine(today - timedelta(days=29), datetime.min.time())
    )
    if industry_name:
        stmt = stmt.where(GeoScoreDaily.industry == industry_name)
    stmt = stmt.group_by(GeoScoreDaily.brand_id).order_by(desc("g")).limit(20)
    brand_rows = (await session.execute(stmt)).all()

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

    for r in brand_rows:
        bid = r[0]
        node_id = f"brand-{bid}"
        nodes.append(
            KGNode(
                id=node_id,
                type="brand",
                name=f"brand-{bid}",
                metadata={"avg_geo_score": round(r[1], 2) if r[1] else None},
            )
        )
        edges.append(KGEdge(source=industry_node_id, target=node_id, type="BELONGS_TO", weight=1.0))

    return IndustryKgOut(
        industry_id=industry_id,
        focus=focus or industry_node_id,
        depth=depth,
        nodes=nodes,
        edges=edges,
        state="ok" if brand_rows else "empty",
    )
