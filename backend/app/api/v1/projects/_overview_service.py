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
collections []  + KPI cards with null values/deltas.
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
)
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._analytics_contract import (
    ANALYZER_FACT_PACKAGE_SOURCE,
    ANALYZER_FACT_PACKAGE_V3_SOURCE,
    FORMULA_MISSING_INPUTS_STATUS,
    FORMULA_NO_EVIDENCE_STATUS,
    FORMULA_OK_STATUS,
    FORMULA_PARTIAL_STATUS,
    FORMULA_PENDING_STATUS,
    AnalyticsContractContext,
    MetricValue,
    ValueRange,
    build_contract_context,
    context_update,
    metric_definition,
    metric_evidence_for,
    metric_formula_status,
    metric_missing_inputs,
    percent_display,
    score_0_100,
)
from app.api.v1.projects._legacy_lookups import resolve_brand_name
from app.api.v1.projects._mention_rollups import (
    brand_mention_match_condition,
)
from app.api.v1.projects._overview_dto import (
    BrandOverviewOut,
    GroupSharedDomainRow,
    KpiCard,
    TopPromptRow,
    TrendPoint,
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

DEFAULT_WINDOW_DAYS = 30
logger = logging.getLogger(__name__)
AdminOverviewFacts = tuple[
    list[KpiCard],
    list[TrendPoint],
    list[TrendPoint],
    list[TrendPoint],
    list[TopPromptRow],
]


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
    mentions = _fact_target_mention_count(row)
    total = _fact_all_mention_count(row, mentions)
    return mentions, total


def _decorate_kpi_cards(cards: list[KpiCard]) -> list[KpiCard]:
    key_by_label = {
        "GeoScore": "geo_score",
        "Mention Rate": "mention_rate",
        "Share of Voice": "sov",
        "Sentiment": "sentiment",
    }
    decorated: list[KpiCard] = []
    for card in cards:
        metric_key = card.metric_key or key_by_label.get(card.label_en)
        if metric_key is None:
            decorated.append(card)
            continue
        if metric_key == "sentiment" and abs(float(card.value or 0)) > 1:
            metric_key = "avg_sentiment"
        spec = metric_definition(
            metric_key,
            display_percent=metric_key in {"mention_rate", "sov"},
        )
        value = card.value
        if value is not None and metric_key in {"mention_rate", "sov"}:
            value = percent_display(float(value))
        elif value is not None and metric_key in {"geo_score", "avg_sentiment"}:
            value = score_0_100(float(value))
        formula_status = card.formula_status
        if formula_status is None:
            formula_status = (
                FORMULA_OK_STATUS if value is not None else FORMULA_MISSING_INPUTS_STATUS
            )
        decorated.append(
            card.model_copy(
                update={
                    "metric_key": metric_key,
                    "value": value,
                    "unit": spec.unit,
                    "value_scale": spec.value_scale,
                    "value_range": spec.value_range,
                    "denominator_label": spec.denominator_label,
                    "numerator_label": spec.numerator_label,
                    "source": spec.source,
                    "formula_status": formula_status,
                }
            )
        )
    return decorated


def _kpi_missing_inputs(
    metric_key: str | None,
    context: AnalyticsContractContext,
    *,
    evidence_source: str = "geo_score_daily",
) -> list[str]:
    package_missing = metric_missing_inputs(context, metric_key)
    if package_missing:
        return package_missing
    if context.formula_status == FORMULA_OK_STATUS:
        return []
    inputs = {*context.missing_inputs, *context.missing_sources}
    missing: list[str] = []
    if evidence_source == "geo_score_daily":
        if (
            context.evidence_counts.get("geo_score_daily_rows", 0) <= 0
            or "geo_score_daily.total_queries" in inputs
            or "eligible_response_denominator" in inputs
        ):
            missing.append("geo_score_daily")
            if "eligible_response_denominator" in inputs:
                missing.append("eligible_response_denominator")
            if "geo_score_daily.total_queries" in inputs:
                missing.append("geo_score_daily.total_queries")
    if metric_key == "sov" and (
        "brand_mentions.competitive_set" in inputs
        or context.evidence_counts.get("competitive_mention_count", 0) <= 0
    ):
        missing.append("brand_mentions.competitive_set")
    if metric_key in {"avg_sentiment", "sentiment"} and "brand_mentions.sentiment_score" in inputs:
        missing.append("brand_mentions.sentiment_score")
    if (
        evidence_source != "admin_facts"
        and metric_key in {"avg_sentiment", "sentiment"}
        and "llm_brand_sentiment" in inputs
    ):
        missing.append("brand_mentions.sentiment_score")
    if metric_key == "geo_score" and "llm_brand_position" in inputs:
        missing.append("llm_brand_position")
    return _unique(missing)


# Issue #948: peripheral missing inputs — analyzer-rollup pointers that do
# NOT invalidate the value (mirror of `_metrics_service` equivalent).
_PERIPHERAL_PACKAGE_INPUTS: frozenset[str] = frozenset(
    {
        "missing_analyzer_fact_packages",
        ANALYZER_FACT_PACKAGE_SOURCE,
        ANALYZER_FACT_PACKAGE_V3_SOURCE,
    }
)


def _kpi_has_real_evidence(
    card: KpiCard,
    context: AnalyticsContractContext,
    missing_inputs: list[str],
    *,
    evidence_source: str,
) -> bool:
    """Mirror of ``_series_has_real_evidence`` for KPI cards.

    Returns True when ``card.value`` was computed from real aggregate
    evidence AND the only missing inputs are peripheral.

    Returns False when missing inputs include any critical input
    (denominator missing, source data missing, project unbound, primary
    source missing for the specific metric) so the no-fallback contract
    still nulls out unprovable values. See issue #948.
    """
    if card.value is None:
        return False
    non_peripheral = [r for r in missing_inputs if r not in _PERIPHERAL_PACKAGE_INPUTS]
    if non_peripheral:
        evidence = metric_evidence_for(context, card.metric_key)
        evidence_status = str(evidence.get("formula_status") or "") if evidence else ""
        if evidence_status != FORMULA_PARTIAL_STATUS:
            return False
    if evidence_source == "admin_facts":
        return context.evidence_counts.get("admin_fact_response_count", 0) > 0
    return context.evidence_counts.get("geo_score_daily_rows", 0) > 0


def _apply_kpi_contract(
    cards: list[KpiCard],
    context: AnalyticsContractContext,
    *,
    evidence_source: str = "geo_score_daily",
) -> list[KpiCard]:
    out: list[KpiCard] = []
    for card in cards:
        missing_inputs = _kpi_missing_inputs(
            card.metric_key,
            context,
            evidence_source=evidence_source,
        )
        if not missing_inputs:
            formula_status = metric_formula_status(
                context,
                card.metric_key,
                card.formula_status,
            )
            if (
                card.metric_key == "sov"
                and card.value is not None
                and card.formula_status == FORMULA_OK_STATUS
            ):
                formula_status = FORMULA_OK_STATUS
            out.append(card.model_copy(update={"formula_status": formula_status}))
            continue
        # Peripheral analyzer inputs are missing, but the KPI card already
        # carries a value that was computed from real aggregate evidence
        # (Issue #948: 提及率 / 引用份额 / 行业排名 / Sentiment rendered "—"
        # on /brand/overview and /brand/visibility because this branch
        # nulled out `card.value` even when `geo_score_daily` / admin
        # facts contained the rows that produced the value). Preserve
        # the value and emit `formula_partial` so the frontend gate
        # (`canUseContractMetricValue`) keeps surfacing the number.
        # Critical missing inputs (no denominator, no source rows, project
        # unbound) still null the value per the no-fallback contract — see
        # `_kpi_has_real_evidence`.
        if _kpi_has_real_evidence(card, context, missing_inputs, evidence_source=evidence_source):
            out.append(
                card.model_copy(
                    update={
                        "formula_status": FORMULA_PARTIAL_STATUS,
                    }
                )
            )
            continue
        formula_status = metric_formula_status(
            context,
            card.metric_key,
            FORMULA_MISSING_INPUTS_STATUS,
        )
        out.append(
            card.model_copy(
                update={
                    "value": None,
                    "delta_30d_pct": None,
                    "direction": None,
                    "formula_status": formula_status,
                }
            )
        )
    return out


def _missing_analyzer_evidence(metric_keys: list[str]) -> dict[str, dict[str, Any]]:
    evidence_key_by_metric = {
        "mention_rate": "coverage",
        "avg_mention_rate": "coverage",
        "citation_rate": "citation",
        "avg_citation_rate": "citation",
        "avg_sentiment": "sentiment",
        "avg_sov": "sov",
    }
    return {
        evidence_key: {
            "metric_key": evidence_key,
            "formula_status": FORMULA_MISSING_INPUTS_STATUS,
            "reason_codes": ["missing_analyzer_fact_packages"],
            "source_tables": ["response_analyses.raw_analysis_json.analyzer_fact_packages"],
            "fact_classes": [evidence_key],
            "sample_response_ids": [],
        }
        for evidence_key in _unique(
            [evidence_key_by_metric.get(metric_key, metric_key) for metric_key in metric_keys]
        )
    }


async def _score_components(
    session: AsyncSession,
    brand_id: int,
    from_date: date,
    to_date: date,
) -> dict[str, MetricValue]:
    stmt = select(
        func.avg(GeoScoreDaily.avg_geo_score).label("final_geo_score"),
        func.avg(GeoScoreDaily.avg_visibility).label("visibility"),
        func.avg(GeoScoreDaily.avg_position_rank).label("ranking"),
        func.avg(GeoScoreDaily.avg_sentiment).label("sentiment"),
        func.avg(GeoScoreDaily.avg_sov_score).label("context"),
        func.avg(GeoScoreDaily.avg_citation_score).label("authority"),
    ).where(
        and_(
            GeoScoreDaily.brand_id == brand_id,
            GeoScoreDaily.date >= datetime.combine(from_date, datetime.min.time()),
            GeoScoreDaily.date <= datetime.combine(to_date, datetime.max.time()),
        )
    )
    row = (await session.execute(stmt)).one_or_none()
    value_range = ValueRange(min=0.0, max=100.0)
    values = {
        "final_geo_score": row.final_geo_score if row else None,
        "visibility": row.visibility if row else None,
        "ranking": row.ranking if row else None,
        "sentiment": row.sentiment if row else None,
        "context": row.context if row else None,
        "authority": row.authority if row else None,
    }
    return {
        key: MetricValue(
            value=score_0_100(value),
            unit="score",
            value_scale="score_0_100",
            value_range=value_range,
            source="geo_score_daily",
            formula_status=FORMULA_OK_STATUS if value is not None else None,
        )
        for key, value in values.items()
    }


def _apply_score_component_contract(
    values: dict[str, MetricValue],
    context: AnalyticsContractContext,
) -> dict[str, MetricValue]:
    pano_status = metric_formula_status(context, "pano_score")
    if pano_status and pano_status != FORMULA_OK_STATUS:
        return {
            key: value.model_copy(
                update={
                    "value": None,
                    "formula_status": pano_status,
                }
            )
            for key, value in values.items()
        }
    inputs = {*context.missing_inputs, *context.missing_sources}
    if context.formula_status == FORMULA_OK_STATUS:
        return values
    if (
        context.evidence_counts.get("geo_score_daily_rows", 0) > 0
        and "geo_score_daily.total_queries" not in inputs
        and "eligible_response_denominator" not in inputs
    ):
        return values
    return {
        key: value.model_copy(
            update={
                "value": None,
                "formula_status": FORMULA_MISSING_INPUTS_STATUS,
            }
        )
        for key, value in values.items()
    }


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out


async def _overview_from_admin_facts(
    session: AsyncSession,
    project: Project,
    *,
    brand_id: int,
    from_date: date,
    to_date: date,
    brand_id_override: int | None,
) -> AdminOverviewFacts | None:
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
        bucket["all_mentions"] += total
        if mentions > 0:
            bucket["target_response_ids"].add(rid)
            bucket["target_mentions"] += mentions
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
        sentiment = (
            _as_float(row.get("target_sentiment_score"))
            if mentions > 0
            else _as_float(row.get("sentiment_score"))
        )
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
                TrendPoint(
                    date=date.fromisoformat(day),
                    value=round(target_mentions / all_mentions, 4),
                )
            )
        sentiment = _avg(bucket["sentiments"])
        if sentiment is not None:
            sentiment_points.append(TrendPoint(date=date.fromisoformat(day), value=sentiment))
            all_sentiments.extend(bucket["sentiments"])
        total_target_mentions += target_mentions
        total_all_mentions += all_mentions
        total_target_responses += len(bucket["target_response_ids"])
        total_denominator += len(bucket["denominator_ids"])

    avg_geo = _avg(all_geo_scores)
    mention = total_target_responses / total_denominator if total_denominator > 0 else None
    sov = total_target_mentions / total_all_mentions if total_all_mentions else None
    avg_sentiment = _avg(all_sentiments)
    kpi_cards = [
        KpiCard(
            label_zh="GEO 评分",
            label_en="GeoScore",
            value=round(avg_geo, 1) if avg_geo is not None else None,
            delta_30d_pct=None,
        ),
        KpiCard(
            label_zh="提及率",
            label_en="Mention Rate",
            value=round(mention * 100, 1) if mention is not None else None,
            unit="%",
            delta_30d_pct=None,
        ),
        KpiCard(
            label_zh="声量份额",
            label_en="Share of Voice",
            value=round(sov * 100, 1) if sov is not None else None,
            unit="%",
            delta_30d_pct=None,
        ),
        KpiCard(
            label_zh="情感分",
            label_en="Sentiment",
            metric_key="sentiment",
            value=round(avg_sentiment, 2) if avg_sentiment is not None else None,
            delta_30d_pct=None,
        ),
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
            KpiCard(
                label_zh="GEO 评分",
                label_en="GeoScore",
                value=None,
                formula_status=FORMULA_NO_EVIDENCE_STATUS,
                delta_30d_pct=None,
            ),
            KpiCard(
                label_zh="提及率",
                label_en="Mention Rate",
                value=None,
                unit="%",
                formula_status=FORMULA_NO_EVIDENCE_STATUS,
                delta_30d_pct=None,
            ),
            KpiCard(
                label_zh="声量份额",
                label_en="Share of Voice",
                value=None,
                unit="%",
                formula_status=FORMULA_NO_EVIDENCE_STATUS,
                delta_30d_pct=None,
            ),
            KpiCard(
                label_zh="情感分",
                label_en="Sentiment",
                metric_key="sentiment",
                value=None,
                formula_status=FORMULA_NO_EVIDENCE_STATUS,
                delta_30d_pct=None,
            ),
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
        func.coalesce(func.sum(GeoScoreDaily.total_queries), 0).label("total_queries"),
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

    geo = _optional_float(cur.avg_geo if cur else None)
    mention = _optional_float(cur.avg_mention if cur else None)
    sov = _optional_float(cur.avg_sov if cur else None)
    sentiment = _optional_float(cur.avg_sentiment if cur else None)
    total_queries = int(getattr(cur, "total_queries", 0) or 0) if cur else 0
    if total_queries <= 0:
        mention = None
        sov = None

    geo_delta = _pct_delta(geo, _optional_float(prior.avg_geo if prior else None))
    mention_delta = _pct_delta(mention, _optional_float(prior.avg_mention if prior else None))
    sov_delta = _pct_delta(sov, _optional_float(prior.avg_sov if prior else None))
    sentiment_delta = _pct_delta(sentiment, _optional_float(prior.avg_sentiment if prior else None))

    return [
        KpiCard(
            label_zh="GEO 评分",
            label_en="GeoScore",
            value=round(geo, 1) if geo is not None else None,
            delta_30d_pct=geo_delta,
            direction=_direction(geo_delta),
        ),
        KpiCard(
            label_zh="提及率",
            label_en="Mention Rate",
            value=round(mention * 100, 1) if mention is not None else None,
            unit="%",
            delta_30d_pct=mention_delta,
            direction=_direction(mention_delta),
        ),
        KpiCard(
            label_zh="声量份额",
            label_en="Share of Voice",
            value=round(sov * 100, 1) if sov is not None else None,
            unit="%",
            delta_30d_pct=sov_delta,
            direction=_direction(sov_delta),
        ),
        KpiCard(
            label_zh="情感分",
            label_en="Sentiment",
            metric_key="avg_sentiment",
            value=round(sentiment, 2) if sentiment is not None else None,
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
            TrendPoint(date=cast(datetime, r[0]).date(), value=round(r[1], 4))
            for r in rows
            if r[1] is not None
        ]
    return []


async def _sentiment_trend(
    session: AsyncSession,
    brand_id: int,
    from_date: date,
    to_date: date,
) -> list[TrendPoint]:
    """Sentiment trend pulls from target-brand mention sentiment evidence."""
    brand_filter = await brand_mention_match_condition(session, brand_id)
    bucket = func.date(BrandMention.created_at)
    stmt = (
        select(bucket, func.avg(BrandMention.sentiment_score))
        .where(
            and_(
                brand_filter,
                BrandMention.sentiment_score.isnot(None),
                BrandMention.created_at >= datetime.combine(from_date, datetime.min.time()),
                BrandMention.created_at <= datetime.combine(to_date, datetime.max.time()),
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
        if r[1] is not None:
            points.append(TrendPoint(date=d, value=round(r[1], 4)))
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
    tables). If the join path is unavailable, the endpoint returns an empty
    list and surfaces the missing evidence through the shared contract.
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
            "Brand overview top prompts join failed; returning empty top_prompts "
            "without substituting aggregate values (brand_id=%s, error=%s)",
            brand_id,
            exc.__class__.__name__,
        )
    return []


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
        empty = _empty_overview(project)
        context = await build_contract_context(
            session,
            project,
            brand_id=None,
            from_date=from_d,
            to_date=to_d,
            has_data=False,
            base_state="empty",
            base_state_reason="no_primary_brand",
        )
        return empty.model_copy(update=context_update(context))

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
    kpi_cards = _decorate_kpi_cards(kpi_cards)
    brand_name = await resolve_brand_name(session, brand_id)
    shared_domains = await _same_group_shared_domains(session, brand_id)

    state = "ok" if any(c.value is not None for c in kpi_cards) else "empty"
    has_data = state == "ok" or bool(geo_30d or sov_30d or sentiment_30d or top_prompts)
    context = await build_contract_context(
        session,
        project,
        brand_id=brand_id,
        from_date=from_d,
        to_date=to_d,
        has_data=has_data,
        base_state=state,
        source_provenance=["admin_facts"] if admin_fact_overview is not None else None,
    )
    if (
        admin_fact_overview is not None
        and context.formula_status == FORMULA_OK_STATUS
        and context.evidence_counts.get("geo_score_daily_rows", 0) <= 0
    ):
        pending_status = (
            FORMULA_PARTIAL_STATUS
            if brand_id_override is not None and brand_id_override == project.primary_brand_id
            else FORMULA_PENDING_STATUS
        )
        context = await build_contract_context(
            session,
            project,
            brand_id=brand_id,
            from_date=from_d,
            to_date=to_d,
            has_data=has_data,
            base_state="partial",
            base_state_reason=(
                "partial_analyzer_data"
                if pending_status == FORMULA_PARTIAL_STATUS
                else "formula_pending_upstream"
            ),
            formula_status=pending_status,
            source_provenance=["admin_facts"],
        )
        if pending_status == FORMULA_PARTIAL_STATUS and not context.metric_formula_evidence:
            context = context.model_copy(
                update={
                    "missing_inputs": _unique(
                        [
                            *context.missing_inputs,
                            "response_analyses.raw_analysis_json.analyzer_fact_packages",
                        ]
                    ),
                    "missing_sources": _unique(
                        [
                            *context.missing_sources,
                            "response_analyses.raw_analysis_json.analyzer_fact_packages",
                        ]
                    ),
                    "missing_reasons": _unique(
                        [*context.missing_reasons, "missing_analyzer_fact_packages"]
                    ),
                    "metric_formula_evidence": _missing_analyzer_evidence(
                        ["geo_score", "sov", "sentiment", "citation"]
                    ),
                }
            )
    kpi_cards = _apply_kpi_contract(
        kpi_cards,
        context,
        evidence_source="admin_facts" if admin_fact_overview is not None else "geo_score_daily",
    )
    score_components = _apply_score_component_contract(
        await _score_components(session, brand_id, from_d, to_d),
        context,
    )
    if metric_missing_inputs(context, "pano_score"):
        geo_30d = []
    if metric_missing_inputs(context, "sov"):
        sov_30d = []
    if metric_missing_inputs(context, "sentiment"):
        sentiment_30d = []

    out = BrandOverviewOut(
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
        score_components=score_components,
    )
    return out.model_copy(update=context_update(context))
