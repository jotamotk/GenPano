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

import logging
from datetime import date, datetime, timedelta
from typing import Any, cast

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
from app.api.v1.projects._mention_rollups import (
    brand_mention_daily_rollups,
    brand_mention_match_condition,
    brand_mention_window_rollup,
    geo_score,
    mention_rate,
    metric_value,
    share_of_voice,
)
from app.api.v1.projects._topic_analysis_service import (
    AnalysisFilters,
    _as_float,
    _as_int,
    _date_key,
    _fact_rows,
    _has_admin_chain,
    _is_non_branded_row,
)
from app.api.v1.projects._overview_dto import (
    BrandOverviewOut,
    GroupSharedDomainRow,
    KpiCard,
    TopPromptRow,
    TrendPoint,
)

DEFAULT_WINDOW_DAYS = 30
logger = logging.getLogger(__name__)


def _row_has_values(row: object | None, names: tuple[str, ...]) -> bool:
    return row is not None and any(getattr(row, name, None) is not None for name in names)


def _optional_float(value: Any) -> float | None:
    return float(value) if value is not None else None


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


def _fact_geo_display(value: Any) -> float | None:
    score = _as_float(value)
    if score is None:
        return None
    return round(score * 100, 2) if 0 <= score <= 1 else round(score, 2)


def _fact_target_mentions(row: dict[str, Any]) -> tuple[int, int]:
    mentions = int(row.get("target_mention_count") or 0)
    if mentions <= 0 and row.get("target_brand_mentioned"):
        mentions = 1
    total = int(row.get("all_mention_count") or 0)
    if total <= 0 and mentions > 0:
        total = 1
    return mentions, total


async def _overview_from_admin_facts(
    session: AsyncSession,
    project: Project,
    *,
    brand_id: int,
    from_date: date,
    to_date: date,
    brand_id_override: int | None,
) -> tuple[list[KpiCard], list[TrendPoint], list[TrendPoint], list[TrendPoint], list[TopPromptRow]] | None:
    rows = await _fact_rows(
        session,
        project,
        filters=AnalysisFilters(from_date=from_date, to_date=to_date),
        brand_id_override=brand_id_override,
    )
    if not rows:
        return None

    buckets: dict[str, dict[str, Any]] = {}
    prompt_buckets: dict[int | str, dict[str, Any]] = {}
    seen_response_ids: set[int] = set()
    for row in rows:
        rid = _as_int(row.get("response_id"))
        if rid is None or rid in seen_response_ids:
            continue
        seen_response_ids.add(rid)
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
                "denominator_ids": set(),
                "target_response_ids": set(),
                "target_mentions": 0,
                "all_mentions": 0,
                "geo_scores": [],
                "sentiments": [],
                "ranks": [],
            },
        )
        bucket["response_ids"].add(rid)
        if _is_non_branded_row(row):
            bucket["denominator_ids"].add(rid)
        mentions, total = _fact_target_mentions(row)
        if mentions > 0:
            bucket["target_response_ids"].add(rid)
            bucket["target_mentions"] += mentions
            bucket["all_mentions"] += total
            prompt_id = _as_int(row.get("prompt_id"))
            prompt_key = prompt_id if prompt_id is not None else row.get("prompt_text") or rid
            prompt_bucket = prompt_buckets.setdefault(
                prompt_key,
                {
                    "prompt_id": prompt_id,
                    "prompt_text": row.get("prompt_text") or "",
                    "mention_count": 0,
                    "ranks": [],
                    "sentiments": [],
                },
            )
            prompt_bucket["mention_count"] += mentions
        rank = _as_int(row.get("min_position_rank") or row.get("target_brand_rank"))
        if rank is not None:
            bucket["ranks"].append(float(rank))
            if mentions > 0:
                prompt_buckets[prompt_key]["ranks"].append(float(rank))
        sentiment = _as_float(row.get("sentiment_score"))
        if sentiment is not None:
            bucket["sentiments"].append(sentiment)
            if mentions > 0:
                prompt_buckets[prompt_key]["sentiments"].append(sentiment)
        geo = _fact_geo_display(row.get("geo_score"))
        if geo is not None:
            bucket["geo_scores"].append(geo)

    if not buckets:
        return None

    def _avg(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    geo_points: list[TrendPoint] = []
    sov_points: list[TrendPoint] = []
    sentiment_points: list[TrendPoint] = []
    total_target_mentions = 0
    total_all_mentions = 0
    total_target_responses = 0
    total_denominator = 0
    all_geo_scores: list[float] = []
    all_sentiments: list[float] = []

    for day, bucket in sorted(buckets.items()):
        geo = _avg(bucket["geo_scores"])
        if geo is not None:
            geo_points.append(TrendPoint(date=date.fromisoformat(day), value=geo))
            all_geo_scores.extend(bucket["geo_scores"])
        target_mentions = int(bucket["target_mentions"] or 0)
        all_mentions = int(bucket["all_mentions"] or 0)
        if all_mentions:
            sov_points.append(
                TrendPoint(date=date.fromisoformat(day), value=round(target_mentions / all_mentions, 4))
            )
        sentiment = _avg(bucket["sentiments"])
        if sentiment is not None:
            sentiment_points.append(TrendPoint(date=date.fromisoformat(day), value=sentiment))
            all_sentiments.extend(bucket["sentiments"])
        total_target_mentions += target_mentions
        total_all_mentions += all_mentions
        total_target_responses += len(bucket["target_response_ids"])
        total_denominator += len(bucket["denominator_ids"]) or len(bucket["response_ids"])

    if total_denominator <= 0:
        return None
    avg_geo = _avg(all_geo_scores) or 0
    mention = total_target_responses / total_denominator
    sov = total_target_mentions / total_all_mentions if total_all_mentions else 0
    avg_sentiment = _avg(all_sentiments) or 0
    kpi_cards = [
        KpiCard(label_zh="GEO 评分", label_en="GeoScore", value=round(avg_geo, 1), delta_30d_pct=None),
        KpiCard(label_zh="提及率", label_en="Mention Rate", value=round(mention * 100, 1), unit="%", delta_30d_pct=None),
        KpiCard(label_zh="声量份额", label_en="Share of Voice", value=round(sov * 100, 1), unit="%", delta_30d_pct=None),
        KpiCard(label_zh="情感分", label_en="Sentiment", value=round(avg_sentiment, 2), delta_30d_pct=None),
    ]
    top_prompts = [
        TopPromptRow(
            prompt_id=bucket["prompt_id"],
            prompt_text=bucket["prompt_text"],
            mention_count=int(bucket["mention_count"] or 0),
            avg_position_rank=_avg(bucket["ranks"]),
            avg_sentiment_score=_avg(bucket["sentiments"]),
        )
        for bucket in sorted(
            prompt_buckets.values(),
            key=lambda item: int(item["mention_count"] or 0),
            reverse=True,
        )[:10]
    ]
    return kpi_cards, geo_points, sov_points, sentiment_points, top_prompts


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

    if not _row_has_values(cur, ("avg_geo", "avg_mention", "avg_sov", "avg_sentiment")):
        cur_rollup = await brand_mention_window_rollup(session, brand_id, from_date, to_date)
        prior_rollup = await brand_mention_window_rollup(session, brand_id, prior_from, prior_to)
        if cur_rollup.has_data:
            rollup_geo = geo_score(cur_rollup)
            rollup_mention = mention_rate(cur_rollup)
            rollup_sov = share_of_voice(cur_rollup)
            rollup_sentiment = cur_rollup.avg_sentiment_score
            prior_geo = geo_score(prior_rollup) if prior_rollup.has_data else None
            prior_mention = mention_rate(prior_rollup) if prior_rollup.has_data else None
            prior_sov = share_of_voice(prior_rollup) if prior_rollup.has_data else None
            prior_sentiment = prior_rollup.avg_sentiment_score if prior_rollup.has_data else None

            geo_delta = _pct_delta(rollup_geo, prior_geo)
            mention_delta = _pct_delta(rollup_mention, prior_mention)
            sov_delta = _pct_delta(rollup_sov, prior_sov)
            sentiment_delta = _pct_delta(rollup_sentiment, prior_sentiment)

            return [
                KpiCard(
                    label_zh="GEO 评分",
                    label_en="GeoScore",
                    value=round(rollup_geo or 0, 1),
                    delta_30d_pct=geo_delta,
                    direction=_direction(geo_delta),
                ),
                KpiCard(
                    label_zh="提及率",
                    label_en="Mention Rate",
                    value=round((rollup_mention or 0) * 100, 1),
                    unit="%",
                    delta_30d_pct=mention_delta,
                    direction=_direction(mention_delta),
                ),
                KpiCard(
                    label_zh="声量份额",
                    label_en="Share of Voice",
                    value=round((rollup_sov or 0) * 100, 1),
                    unit="%",
                    delta_30d_pct=sov_delta,
                    direction=_direction(sov_delta),
                ),
                KpiCard(
                    label_zh="情感分",
                    label_en="Sentiment",
                    value=round(rollup_sentiment or 0, 2),
                    delta_30d_pct=sentiment_delta,
                    direction=_direction(sentiment_delta),
                ),
            ]

    geo = _optional_float(cur.avg_geo if cur else None)
    mention = _optional_float(cur.avg_mention if cur else None)
    sov = _optional_float(cur.avg_sov if cur else None)
    sentiment = _optional_float(cur.avg_sentiment if cur else None)

    geo_delta = _pct_delta(geo, _optional_float(prior.avg_geo if prior else None))
    mention_delta = _pct_delta(mention, _optional_float(prior.avg_mention if prior else None))
    sov_delta = _pct_delta(sov, _optional_float(prior.avg_sov if prior else None))
    sentiment_delta = _pct_delta(sentiment, _optional_float(prior.avg_sentiment if prior else None))

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
    if rows:
        return [
            TrendPoint(date=cast(datetime, r[0]).date(), value=round(r[1] or 0, 4)) for r in rows
        ]

    fallback_metric = {
        "avg_geo_score": "geo_score",
        "avg_sov": "sov",
        "mention_rate": "mention_rate",
        "avg_sentiment": "sentiment",
        "avg_position_rank": "rank",
        "citation_rate": "citation",
    }.get(column)
    if fallback_metric is None:
        return []
    rollups = await brand_mention_daily_rollups(session, brand_id, from_date, to_date)
    return [
        TrendPoint(date=date.fromisoformat(day), value=metric_value(rollup, fallback_metric))
        for day, rollup in sorted(rollups.items())
        if rollup.has_data
    ]


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
    rollups = await brand_mention_daily_rollups(session, brand_id, from_date, to_date)
    if rollups:
        return [
            TrendPoint(date=date.fromisoformat(day), value=metric_value(rollup, "sentiment"))
            for day, rollup in sorted(rollups.items())
            if rollup.has_data
        ]

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
        async with session.begin_nested():
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
    except Exception as exc:
        logger.warning(
            "Brand overview top prompts join failed; falling back to brand aggregate "
            "(brand_id=%s, error=%s)",
            brand_id,
            exc.__class__.__name__,
        )

    # Fallback: brand-level aggregation when llm_responses/prompts unavailable.
    brand_filter = await brand_mention_match_condition(session, brand_id)
    stmt = (
        select(
            func.count(BrandMention.id).label("cnt"),
            func.avg(BrandMention.position_rank).label("avg_rank"),
            func.avg(BrandMention.sentiment_score).label("avg_sent"),
        )
        .where(
            and_(
                brand_filter,
                BrandMention.created_at >= datetime.combine(from_date, datetime.min.time()),
                BrandMention.created_at <= datetime.combine(to_date, datetime.max.time()),
            )
        )
        .order_by(func.count(BrandMention.id).desc())
        .limit(limit)
    )
    try:
        async with session.begin_nested():
            rows = (await session.execute(stmt)).all()
    except Exception:
        logger.exception(
            "Brand overview top prompts fallback failed; returning empty top_prompts",
            extra={"brand_id": brand_id},
        )
        return []
    return [
        TopPromptRow(
            prompt_id=None,
            prompt_text=f"(aggregated prompts for brand #{brand_id})",
            mention_count=int(r[0] or 0),
            avg_position_rank=round(r[1] or 0, 2) if r[1] is not None else None,
            avg_sentiment_score=round(r[2] or 0, 2) if r[2] is not None else None,
        )
        for r in rows
        if int(r[0] or 0) > 0
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

    admin_fact_overview = None
    if await _has_admin_chain(session):
        admin_fact_overview = await _overview_from_admin_facts(
            session,
            project,
            brand_id=brand_id,
            from_date=from_d,
            to_date=to_d,
            brand_id_override=brand_id_override,
        )
    if admin_fact_overview is not None:
        kpi_cards, geo_30d, sov_30d, sentiment_30d, top_prompts = admin_fact_overview
    else:
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
