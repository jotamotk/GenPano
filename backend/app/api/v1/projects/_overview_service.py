"""Service for Brand Overview (Phase 2.1).

Query strategy:
- KPI cards: read latest day from `geo_score_daily` joined with previous-30d
  for delta calc.
- 30d trends: pull `geo_score_daily` rows (geo_score / sov / mention_rate),
  bucketed by `date`. Sentiment trend reads `response_analyses.sentiment_score`
  averaged per day.
- Top prompts: aggregate `brand_mentions` JOIN `llm_responses`
  → `prompts.text` over the time window.
- Same-group shared domains: `brand_group_shared_domains` (Phase A.6 will
  populate; Phase 2.1 returns [] if table empty).

When project has no primary_brand_id → return `state='empty'` with all
collections []  + KPI cards with 0 / null deltas.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import cast

from genpano_models import (
    BrandGroupMember,
    BrandGroupSharedDomain,
    BrandMention,
    GeoScoreDaily,
    Project,
    ResponseAnalysis,
)
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._legacy_lookups import resolve_brand_name
from app.api.v1.projects._overview_dto import (
    BrandOverviewOut,
    GroupSharedDomainRow,
    KpiCard,
    TopPromptRow,
    TrendPoint,
)

DEFAULT_WINDOW_DAYS = 30


def _empty_overview(project: Project) -> BrandOverviewOut:
    today = date.today()
    return BrandOverviewOut(
        project_id=project.id,
        brand_id=project.primary_brand_id,
        brand_name=None,
        industry_id=project.industry_id,
        period={
            "from": (today - timedelta(days=DEFAULT_WINDOW_DAYS - 1)).isoformat(),
            "to": today.isoformat(),
        },
        kpi_cards=[
            KpiCard(label_zh="GEO 评分", label_en="GeoScore", value=0, delta_30d_pct=None),
            KpiCard(
                label_zh="提及率", label_en="Mention Rate", value=0, unit="%", delta_30d_pct=None
            ),
            KpiCard(
                label_zh="声量份额",
                label_en="Share of Voice",
                value=0,
                unit="%",
                delta_30d_pct=None,
            ),
            KpiCard(label_zh="情感分", label_en="Sentiment", value=0, delta_30d_pct=None),
        ],
        geo_score_30d=[],
        sov_30d=[],
        sentiment_30d=[],
        top_prompts=[],
        same_group_shared_domains=[],
        state="empty",
    )


async def _kpi_cards(
    session: AsyncSession,
    brand_id: int,
    from_date: date,
    to_date: date,
) -> list[KpiCard]:
    """Read latest geo_score_daily row + 30d-prior comparison."""
    # Window aggregates: avg geo_score, avg mention_rate, avg sov, avg sentiment
    stmt = select(
        func.avg(GeoScoreDaily.avg_geo_score).label("avg_geo"),
        func.avg(GeoScoreDaily.mention_rate).label("avg_mention"),
        func.avg(GeoScoreDaily.avg_sov).label("avg_sov"),
        func.avg(GeoScoreDaily.avg_sentiment).label("avg_sentiment"),
    ).where(
        and_(
            GeoScoreDaily.brand_id == brand_id,
            GeoScoreDaily.date >= datetime.combine(from_date, datetime.min.time()),
            GeoScoreDaily.date <= datetime.combine(to_date, datetime.max.time()),
        )
    )
    cur = (await session.execute(stmt)).one_or_none()

    # Prior 30-day window
    prior_from = from_date - timedelta(days=DEFAULT_WINDOW_DAYS)
    prior_to = from_date - timedelta(days=1)
    stmt_prior = select(
        func.avg(GeoScoreDaily.avg_geo_score).label("avg_geo"),
        func.avg(GeoScoreDaily.mention_rate).label("avg_mention"),
        func.avg(GeoScoreDaily.avg_sov).label("avg_sov"),
        func.avg(GeoScoreDaily.avg_sentiment).label("avg_sentiment"),
    ).where(
        and_(
            GeoScoreDaily.brand_id == brand_id,
            GeoScoreDaily.date >= datetime.combine(prior_from, datetime.min.time()),
            GeoScoreDaily.date <= datetime.combine(prior_to, datetime.max.time()),
        )
    )
    prior = (await session.execute(stmt_prior)).one_or_none()

    def _pct_delta(now: float | None, before: float | None) -> float | None:
        if now is None or before is None or before == 0:
            return None
        return round((now - before) / before * 100, 1)

    def _direction(delta: float | None) -> str | None:
        if delta is None:
            return None
        if delta > 0.5:
            return "up"
        if delta < -0.5:
            return "down"
        return "flat"

    geo = cur.avg_geo if cur else None
    mention = cur.avg_mention if cur else None
    sov = cur.avg_sov if cur else None
    sentiment = cur.avg_sentiment if cur else None

    geo_delta = _pct_delta(geo, prior.avg_geo if prior else None)
    mention_delta = _pct_delta(mention, prior.avg_mention if prior else None)
    sov_delta = _pct_delta(sov, prior.avg_sov if prior else None)
    sentiment_delta = _pct_delta(sentiment, prior.avg_sentiment if prior else None)

    return [
        KpiCard(
            label_zh="GEO 评分",
            label_en="GeoScore",
            value=round(geo or 0, 1),
            delta_30d_pct=geo_delta,
            direction=_direction(geo_delta),
        ),
        KpiCard(
            label_zh="提及率",
            label_en="Mention Rate",
            value=round((mention or 0) * 100, 1),
            unit="%",
            delta_30d_pct=mention_delta,
            direction=_direction(mention_delta),
        ),
        KpiCard(
            label_zh="声量份额",
            label_en="Share of Voice",
            value=round((sov or 0) * 100, 1),
            unit="%",
            delta_30d_pct=sov_delta,
            direction=_direction(sov_delta),
        ),
        KpiCard(
            label_zh="情感分",
            label_en="Sentiment",
            value=round(sentiment or 0, 2),
            delta_30d_pct=sentiment_delta,
            direction=_direction(sentiment_delta),
        ),
    ]


async def _trend(
    session: AsyncSession,
    brand_id: int,
    from_date: date,
    to_date: date,
    column: str,
) -> list[TrendPoint]:
    """Pull daily trend points for a given metric column."""
    col = getattr(GeoScoreDaily, column)
    stmt = (
        select(GeoScoreDaily.date, func.avg(col))
        .where(
            and_(
                GeoScoreDaily.brand_id == brand_id,
                GeoScoreDaily.date >= datetime.combine(from_date, datetime.min.time()),
                GeoScoreDaily.date <= datetime.combine(to_date, datetime.max.time()),
            )
        )
        .group_by(GeoScoreDaily.date)
        .order_by(GeoScoreDaily.date)
    )
    rows = (await session.execute(stmt)).all()
    return [TrendPoint(date=cast(datetime, r[0]).date(), value=round(r[1] or 0, 4)) for r in rows]


async def _sentiment_trend(
    session: AsyncSession,
    brand_id: int,
    from_date: date,
    to_date: date,
) -> list[TrendPoint]:
    """Sentiment trend pulls from `response_analyses.sentiment_score`.

    Uses date_trunc('day', analyzed_at) to bucket; works for both
    Postgres and SQLite (via func.date()).
    """
    bucket = func.date(ResponseAnalysis.analyzed_at)
    stmt = (
        select(bucket, func.avg(ResponseAnalysis.sentiment_score))
        .where(
            and_(
                ResponseAnalysis.target_brand_mentioned.is_(True),
                ResponseAnalysis.analyzed_at >= datetime.combine(from_date, datetime.min.time()),
                ResponseAnalysis.analyzed_at <= datetime.combine(to_date, datetime.max.time()),
            )
        )
        .group_by(bucket)
        .order_by(bucket)
    )
    rows = (await session.execute(stmt)).all()

    points = []
    for r in rows:
        d = r[0]
        if isinstance(d, str):
            d = date.fromisoformat(d)
        elif isinstance(d, datetime):
            d = d.date()
        points.append(TrendPoint(date=d, value=round(r[1] or 0, 4)))
    return points


async def _top_prompts(
    session: AsyncSession,
    brand_id: int,
    from_date: date,
    to_date: date,
    *,
    limit: int = 5,
) -> list[TopPromptRow]:
    """Top N prompts by mention_count over the window.

    Joins `brand_mentions` → `llm_responses` → `prompts` (legacy upstream
    tables). Falls back to a brand-level aggregate if the join path is
    unavailable (e.g. SQLite test fixtures without those tables).
    """
    from sqlalchemy import text as _text

    try:
        result = await session.execute(
            _text(
                """
                SELECT p.id,
                       p.text,
                       COUNT(bm.id)::int AS cnt,
                       AVG(bm.position_rank) AS avg_rank,
                       AVG(bm.sentiment_score) AS avg_sent
                FROM brand_mentions bm
                JOIN llm_responses r ON r.id = bm.response_id
                JOIN prompts p ON p.id = r.prompt_id
                WHERE bm.brand_id = :bid
                  AND bm.created_at >= :from_d
                  AND bm.created_at <= :to_d
                GROUP BY p.id, p.text
                ORDER BY cnt DESC
                LIMIT :lim
                """
            ),
            {
                "bid": brand_id,
                "from_d": datetime.combine(from_date, datetime.min.time()),
                "to_d": datetime.combine(to_date, datetime.max.time()),
                "lim": limit,
            },
        )
        rows = result.all()
        if rows:
            return [
                TopPromptRow(
                    prompt_id=int(r[0]) if r[0] is not None else None,
                    prompt_text=r[1] or "",
                    mention_count=int(r[2] or 0),
                    avg_position_rank=round(r[3], 2) if r[3] is not None else None,
                    avg_sentiment_score=round(r[4], 2) if r[4] is not None else None,
                )
                for r in rows
            ]
    except Exception:
        pass

    # Fallback: brand-level aggregation when llm_responses/prompts unavailable.
    stmt = (
        select(
            BrandMention.brand_id,
            func.count(BrandMention.id).label("cnt"),
            func.avg(BrandMention.position_rank).label("avg_rank"),
            func.avg(BrandMention.sentiment_score).label("avg_sent"),
        )
        .where(
            and_(
                BrandMention.brand_id == brand_id,
                BrandMention.created_at >= datetime.combine(from_date, datetime.min.time()),
                BrandMention.created_at <= datetime.combine(to_date, datetime.max.time()),
            )
        )
        .group_by(BrandMention.brand_id)
        .order_by(func.count(BrandMention.id).desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [
        TopPromptRow(
            prompt_id=None,
            prompt_text=f"(aggregated prompts for brand #{r[0]})",
            mention_count=int(r[1] or 0),
            avg_position_rank=round(r[2] or 0, 2) if r[2] is not None else None,
            avg_sentiment_score=round(r[3] or 0, 2) if r[3] is not None else None,
        )
        for r in rows
    ]


async def _same_group_shared_domains(
    session: AsyncSession, brand_id: int, *, limit: int = 8
) -> list[GroupSharedDomainRow]:
    """Resolve shared domains for the brand's corporate group (Phase A.6)."""
    membership = (
        await session.execute(
            select(BrandGroupMember.group_id).where(BrandGroupMember.brand_id == brand_id)
        )
    ).scalar_one_or_none()
    if membership is None:
        return []
    rows = (
        await session.execute(
            select(
                BrandGroupSharedDomain.domain,
                BrandGroupSharedDomain.brand_count,
                BrandGroupSharedDomain.total_mentions,
            )
            .where(BrandGroupSharedDomain.group_id == membership)
            .order_by(BrandGroupSharedDomain.total_mentions.desc())
            .limit(limit)
        )
    ).all()
    return [
        GroupSharedDomainRow(
            domain=r[0],
            brand_count=int(r[1] or 0),
            total_mentions=int(r[2] or 0),
        )
        for r in rows
    ]


async def get_brand_overview(
    session: AsyncSession,
    project: Project,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    brand_id_override: int | None = None,
) -> BrandOverviewOut:
    """Compose the full Brand Overview response.

    `brand_id_override` lets callers (typically the dashboard's brand
    picker via ?brand_id=X) view this project's panorama as if a
    different brand were the primary. Project ownership is still
    enforced upstream by `get_project_for_user`; the override only
    changes which brand's metrics are pulled from `geo_score_daily`,
    `brand_mentions`, and friends.
    """
    today = date.today()
    to_d = to_date or today
    from_d = from_date or (to_d - timedelta(days=DEFAULT_WINDOW_DAYS - 1))

    brand_id = brand_id_override if brand_id_override is not None else project.primary_brand_id
    if brand_id is None:
        return _empty_overview(project)

    kpi_cards = await _kpi_cards(session, brand_id, from_d, to_d)
    geo_30d = await _trend(session, brand_id, from_d, to_d, "avg_geo_score")
    sov_30d = await _trend(session, brand_id, from_d, to_d, "avg_sov")
    sentiment_30d = await _sentiment_trend(session, brand_id, from_d, to_d)
    top_prompts = await _top_prompts(session, brand_id, from_d, to_d)
    brand_name = await resolve_brand_name(session, brand_id)
    shared_domains = await _same_group_shared_domains(session, brand_id)

    state = "ok" if any(c.value for c in kpi_cards) else "empty"

    return BrandOverviewOut(
        project_id=project.id,
        brand_id=brand_id,
        brand_name=brand_name,
        industry_id=project.industry_id,
        period={"from": from_d.isoformat(), "to": to_d.isoformat()},
        kpi_cards=kpi_cards,
        geo_score_30d=geo_30d,
        sov_30d=sov_30d,
        sentiment_30d=sentiment_30d,
        top_prompts=top_prompts,
        same_group_shared_domains=shared_domains,
        state=state,
    )
