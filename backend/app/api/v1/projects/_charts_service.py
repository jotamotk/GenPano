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
from pydantic import BaseModel
from sqlalchemy import and_, case, desc, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._analytics_contract import (
    FORMULA_MISSING_INPUTS_STATUS,
    FORMULA_NO_EVIDENCE_STATUS,
    FORMULA_OK_STATUS,
    FORMULA_PARTIAL_STATUS,
    build_contract_context,
    formula_diagnostics_for,
    metric_formula_status,
    metric_missing_inputs,
)
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
from app.api.v1.projects._mention_rollups import (
    brand_mention_match_condition,
    brand_mention_names,
)
from app.api.v1.projects._topic_analysis_service import (
    AnalysisFilters,
    _as_float,
    _as_int,
    _date_key,
    _fact_all_mention_count,
    _fact_rows,
    _fact_target_mention_count,
    get_topic_monitoring,
    legacy_table_columns,
    legacy_table_exists,
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


def _state_reason(state: str, empty_reason: str) -> str:
    return "data_available" if state == "ok" else empty_reason


def _response_evidence_count(rows: list[dict[str, Any]]) -> int:
    response_ids = {_as_int(row.get("response_id")) for row in rows}
    return len({rid for rid in response_ids if rid is not None})


def _chart_counts(**counts: int) -> dict[str, int]:
    return {key: int(value or 0) for key, value in counts.items()}


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out


def _chart_has_data(out: Any) -> bool:
    if int(getattr(out, "evidence_count", 0) or 0) > 0:
        return True
    for attr in ("items", "points", "segments", "series"):
        value = getattr(out, attr, None)
        if value:
            return True
    if int(getattr(out, "total", 0) or 0) > 0:
        return True
    return False


def _metric_evidence_key(metric_key: str) -> str:
    if metric_key in {"mention_rate", "avg_mention_rate"}:
        return "coverage"
    if metric_key in {"citation_rate", "avg_citation_rate"}:
        return "citation"
    if metric_key in {"avg_sentiment"}:
        return "sentiment"
    if metric_key in {"avg_sov"}:
        return "sov"
    return metric_key


def _missing_analyzer_metric_evidence(metric_keys: list[str]) -> dict[str, dict[str, Any]]:
    return {
        evidence_key: {
            "metric_key": evidence_key,
            "formula_status": FORMULA_MISSING_INPUTS_STATUS,
            "reason_codes": ["missing_analyzer_fact_packages"],
            "source_tables": ["response_analyses.raw_analysis_json.analyzer_fact_packages"],
            "fact_classes": [evidence_key],
            "sample_response_ids": [],
        }
        for evidence_key in _unique([_metric_evidence_key(key) for key in metric_keys])
    }


async def _chart_contract_update(
    session: AsyncSession,
    project: Project,
    from_d: date,
    to_d: date,
    out: Any,
    *,
    metric_keys: list[str],
    source_provenance: list[str],
    brand_id: int | None = None,
) -> dict[str, Any]:
    scoped_brand_id = brand_id if brand_id is not None else project.primary_brand_id
    if scoped_brand_id is None:
        return {}
    has_data = _chart_has_data(out)
    context = await build_contract_context(
        session,
        project,
        brand_id=scoped_brand_id,
        from_date=from_d,
        to_date=to_d,
        has_data=has_data,
        base_state=getattr(out, "state", "ok"),
        source_provenance=source_provenance,
    )
    evidence = context.metric_formula_evidence
    missing_inputs: list[str] = list(context.missing_inputs)
    missing_reasons: list[str] = list(context.missing_reasons)
    coverage_status = metric_formula_status(context, "mention_rate")
    if coverage_status and coverage_status != FORMULA_OK_STATUS:
        missing_inputs.extend(metric_missing_inputs(context, "mention_rate"))
        coverage_evidence = context.metric_formula_evidence.get("coverage")
        if isinstance(coverage_evidence, dict):
            missing_reasons.extend(coverage_evidence.get("reason_codes") or [])
    for metric_key in metric_keys:
        status = metric_formula_status(context, metric_key)
        if status and status != FORMULA_OK_STATUS:
            missing_inputs.extend(metric_missing_inputs(context, metric_key))
            metric_evidence = context.metric_formula_evidence.get(_metric_evidence_key(metric_key))
            if isinstance(metric_evidence, dict):
                missing_reasons.extend(metric_evidence.get("reason_codes") or [])

    if not evidence and has_data:
        evidence = _missing_analyzer_metric_evidence(metric_keys)
        missing_inputs.append("response_analyses.raw_analysis_json.analyzer_fact_packages")
        missing_reasons.append("missing_analyzer_fact_packages")

    if not missing_inputs and not missing_reasons:
        return {
            "metric_formula_evidence": evidence,
            "evidence_counts": {
                **getattr(out, "evidence_counts", {}),
                **context.evidence_counts,
            },
            "selected_filters": context.selected_filters,
            "source_provenance": context.source_provenance,
        }

    missing_inputs = _unique(missing_inputs)
    missing_reasons = _unique(missing_reasons)
    evidence_counts = {
        **getattr(out, "evidence_counts", {}),
        **context.evidence_counts,
    }
    existing_status = getattr(out, "formula_status", FORMULA_OK_STATUS)
    chart_status = (
        existing_status
        if existing_status not in {None, FORMULA_NO_EVIDENCE_STATUS, FORMULA_OK_STATUS}
        else FORMULA_PARTIAL_STATUS
    )
    return {
        "state": "partial",
        "state_reason": "partial_analyzer_data",
        "formula_status": chart_status,
        "formula_diagnostics": formula_diagnostics_for(
            chart_status,
            missing_inputs=missing_inputs,
        ),
        "missing_inputs": _unique([*getattr(out, "missing_inputs", []), *missing_inputs]),
        "missing_sources": _unique(
            [
                *getattr(out, "missing_sources", []),
                "response_analyses.raw_analysis_json.analyzer_fact_packages",
            ]
        ),
        "missing_reasons": _unique([*getattr(out, "missing_reasons", []), *missing_reasons]),
        "evidence_counts": evidence_counts,
        "metric_formula_evidence": evidence,
        "selected_filters": context.selected_filters,
        "source_provenance": context.source_provenance,
    }


async def _with_chart_contract[ChartOutT: BaseModel](
    out: ChartOutT,
    session: AsyncSession,
    project: Project,
    from_d: date,
    to_d: date,
    *,
    metric_keys: list[str],
    source_provenance: list[str],
    brand_id: int | None = None,
) -> ChartOutT:
    update = await _chart_contract_update(
        session,
        project,
        from_d,
        to_d,
        out,
        metric_keys=metric_keys,
        source_provenance=source_provenance,
        brand_id=brand_id,
    )
    return out.model_copy(update=update) if update else out


def _contract_metric_status(update: dict[str, Any], metric_key: str) -> str | None:
    evidence = update.get("metric_formula_evidence") or {}
    metric_evidence = evidence.get(_metric_evidence_key(metric_key))
    if not isinstance(metric_evidence, dict):
        return None
    return str(metric_evidence.get("formula_status") or FORMULA_MISSING_INPUTS_STATUS)


def _contract_metric_non_ok(update: dict[str, Any], metric_key: str) -> bool:
    status = _contract_metric_status(update, metric_key)
    return status is not None and status != FORMULA_OK_STATUS


async def _with_sentiment_by_engine_contract(
    out: SentimentByEngineOut,
    session: AsyncSession,
    project: Project,
    from_d: date,
    to_d: date,
    *,
    source_provenance: list[str],
    brand_id: int | None = None,
) -> SentimentByEngineOut:
    update = await _chart_contract_update(
        session,
        project,
        from_d,
        to_d,
        out,
        metric_keys=["sentiment"],
        source_provenance=source_provenance,
        brand_id=brand_id,
    )
    if not update:
        return out
    if _contract_metric_non_ok(update, "sentiment"):
        update["items"] = []
    return out.model_copy(update=update)


async def _with_authority_trend_contract(
    out: AuthorityTrendOut,
    session: AsyncSession,
    project: Project,
    from_d: date,
    to_d: date,
    *,
    source_provenance: list[str],
    brand_id: int | None = None,
) -> AuthorityTrendOut:
    update = await _chart_contract_update(
        session,
        project,
        from_d,
        to_d,
        out,
        metric_keys=["citation"],
        source_provenance=source_provenance,
        brand_id=brand_id,
    )
    if not update:
        return out
    if _contract_metric_non_ok(update, "citation"):
        update["points"] = []
    return out.model_copy(update=update)


async def _with_citation_composition_contract(
    out: CitationCompositionOut,
    session: AsyncSession,
    project: Project,
    from_d: date,
    to_d: date,
    *,
    source_provenance: list[str],
    brand_id: int | None = None,
) -> CitationCompositionOut:
    update = await _chart_contract_update(
        session,
        project,
        from_d,
        to_d,
        out,
        metric_keys=["citation"],
        source_provenance=source_provenance,
        brand_id=brand_id,
    )
    if not update:
        return out
    if _contract_metric_non_ok(update, "citation"):
        update["segments"] = []
        update["total"] = 0
    return out.model_copy(update=update)


def _apply_engine_metric_contract(
    items: list[EngineMetricRow],
    update: dict[str, Any],
) -> list[EngineMetricRow]:
    evidence = update.get("metric_formula_evidence") or {}

    def _status(key: str) -> str | None:
        value = evidence.get(key)
        if not isinstance(value, dict):
            return FORMULA_MISSING_INPUTS_STATUS
        return str(value.get("formula_status") or FORMULA_MISSING_INPUTS_STATUS)

    return [
        item.model_copy(
            update={
                "mention_rate": None
                if _status("coverage") not in {None, FORMULA_OK_STATUS}
                else item.mention_rate,
                "sov": None if _status("sov") not in {None, FORMULA_OK_STATUS} else item.sov,
                "citation_rate": None
                if _status("citation") not in {None, FORMULA_OK_STATUS}
                else item.citation_rate,
                "sentiment": None
                if _status("sentiment") not in {None, FORMULA_OK_STATUS}
                else item.sentiment,
            }
        )
        for item in items
    ]


async def _with_engine_metric_contract(
    out: EngineMetricsOut,
    session: AsyncSession,
    project: Project,
    from_d: date,
    to_d: date,
    *,
    source_provenance: list[str],
    brand_id: int | None = None,
) -> EngineMetricsOut:
    update = await _chart_contract_update(
        session,
        project,
        from_d,
        to_d,
        out,
        metric_keys=["mention_rate", "sov", "citation", "sentiment"],
        source_provenance=source_provenance,
        brand_id=brand_id,
    )
    if not update:
        return out
    update["items"] = _apply_engine_metric_contract(out.items, update)
    return out.model_copy(update=update)


async def _with_sentiment_trend_contract(
    out: SentimentTrendByEngineOut,
    session: AsyncSession,
    project: Project,
    from_d: date,
    to_d: date,
    *,
    source_provenance: list[str],
    brand_id: int | None = None,
) -> SentimentTrendByEngineOut:
    update = await _chart_contract_update(
        session,
        project,
        from_d,
        to_d,
        out,
        metric_keys=["sentiment"],
        source_provenance=source_provenance,
        brand_id=brand_id,
    )
    if not update:
        return out
    if _contract_metric_non_ok(update, "sentiment"):
        update["items"] = []
    return out.model_copy(update=update)


def _sentiment_label_sql() -> str:
    return "LOWER(TRIM(COALESCE(bm.sentiment, '')))"


def _coalesce_sql(expressions: list[str]) -> str | None:
    if not expressions:
        return None
    if len(expressions) == 1:
        return expressions[0]
    return f"COALESCE({', '.join(expressions)})"


def _fact_response_ids(rows: list[dict[str, Any]]) -> list[int]:
    ids = {_as_int(row.get("response_id")) for row in rows}
    return sorted(rid for rid in ids if rid is not None)


def _fact_response_day_map(rows: list[dict[str, Any]]) -> dict[int, str]:
    response_days: dict[int, str] = {}
    for row in rows:
        rid = _as_int(row.get("response_id"))
        if rid is None or rid in response_days:
            continue
        day = _date_key(
            row.get("response_created_at")
            or row.get("query_finished_at")
            or row.get("query_created_at")
        )
        if day is not None:
            response_days[rid] = day
    return response_days


def _fact_sentiment_score_response_count(rows: list[dict[str, Any]]) -> int:
    ids = {
        _as_int(row.get("response_id"))
        for row in rows
        if _as_int(row.get("response_id")) is not None
        and (
            _as_float(row.get("target_sentiment_score")) is not None
            or _as_float(row.get("sentiment_score")) is not None
        )
    }
    return len({rid for rid in ids if rid is not None})


async def _target_citation_composition_rows(
    session: AsyncSession,
    *,
    brand_id: int,
    response_ids: list[int],
) -> tuple[list[CitationCompositionRow], int]:
    if not response_ids:
        return [], 0
    brand_filter = await brand_mention_match_condition(session, brand_id)
    rows = (
        await session.execute(
            select(DomainAuthority.tier, func.count())
            .select_from(CitationSource)
            .join(BrandMention, BrandMention.id == CitationSource.mention_id)
            .outerjoin(DomainAuthority, DomainAuthority.domain == CitationSource.domain)
            .where(
                and_(
                    CitationSource.response_id.in_(response_ids),
                    CitationSource.domain.isnot(None),
                    brand_filter,
                )
            )
            .group_by(DomainAuthority.tier)
        )
    ).all()
    total = sum(int(row[1] or 0) for row in rows)
    label_for = {
        1: "Tier 1",
        2: "Tier 2",
        3: "Tier 3",
        4: "Tier 4",
        None: "Untiered",
    }
    by_tier = {row[0]: int(row[1] or 0) for row in rows}
    return (
        [
            CitationCompositionRow(
                label=label_for[tier],
                tier=tier,
                count=count,
                pct=round(count / total * 100, 1) if total else 0.0,
            )
            for tier in (1, 2, 3, 4, None)
            if (count := by_tier.get(tier, 0)) or tier is not None
        ],
        total,
    )


async def _target_authority_points_from_facts(
    session: AsyncSession,
    *,
    brand_id: int,
    response_days: dict[int, str],
) -> tuple[list[AuthorityTrendPoint], int]:
    if not response_days:
        return [], 0
    brand_filter = await brand_mention_match_condition(session, brand_id)
    rows = (
        await session.execute(
            select(
                CitationSource.response_id,
                DomainAuthority.tier,
                func.count().label("cnt"),
            )
            .select_from(CitationSource)
            .join(BrandMention, BrandMention.id == CitationSource.mention_id)
            .outerjoin(DomainAuthority, DomainAuthority.domain == CitationSource.domain)
            .where(
                and_(
                    CitationSource.response_id.in_(sorted(response_days)),
                    CitationSource.domain.isnot(None),
                    brand_filter,
                )
            )
            .group_by(CitationSource.response_id, DomainAuthority.tier)
        )
    ).all()
    by_day: dict[str, dict[int | None, int]] = OrderedDict()
    total_count = 0
    for response_id, tier, count in rows:
        day = response_days.get(int(response_id))
        if day is None:
            continue
        value = int(count or 0)
        by_day.setdefault(day, defaultdict(int))[tier] += value
        total_count += value
    points: list[AuthorityTrendPoint] = []
    for day, tier_map in by_day.items():
        total = sum(tier_map.values())
        if total <= 0:
            continue
        points.append(
            AuthorityTrendPoint(
                date=day,
                tier1_pct=round(tier_map.get(1, 0) / total * 100, 1),
                tier2_pct=round(tier_map.get(2, 0) / total * 100, 1),
                tier3_pct=round(tier_map.get(3, 0) / total * 100, 1),
                tier4_pct=round(tier_map.get(4, 0) / total * 100, 1),
                untiered_pct=round(tier_map.get(None, 0) / total * 100, 1),
            )
        )
    return points, total_count


async def _sentiment_contract_evidence_count(
    session: AsyncSession,
    brand_id: int,
    from_d: date,
    to_d: date,
    *,
    response_ids: list[int] | None = None,
) -> int:
    brand_filter = await brand_mention_match_condition(session, brand_id)
    predicates = [
        brand_filter,
        BrandMention.sentiment_score.isnot(None),
        func.lower(BrandMention.sentiment).in_(["positive", "neutral", "negative"]),
    ]
    if response_ids is not None:
        if not response_ids:
            return 0
        predicates.append(BrandMention.response_id.in_(response_ids))
    else:
        f, t = _dt_range(from_d, to_d)
        predicates.extend([BrandMention.created_at >= f, BrandMention.created_at <= t])
    return int(
        (
            await session.execute(select(func.count(BrandMention.id)).where(and_(*predicates)))
        ).scalar_one()
        or 0
    )


async def _sentiment_window_evidence_count(
    session: AsyncSession,
    project: Project,
    from_d: date,
    to_d: date,
    *,
    fact_rows: list[dict[str, Any]] | None = None,
    brand_id: int | None = None,
) -> int:
    """Count target sentiment evidence using the response window before repair time."""
    scoped_brand_id = brand_id if brand_id is not None else project.primary_brand_id
    if scoped_brand_id is None:
        return 0
    direct_count = await _sentiment_contract_evidence_count(
        session,
        scoped_brand_id,
        from_d,
        to_d,
    )
    if direct_count:
        return direct_count
    rows = fact_rows
    if rows is None:
        rows = await _admin_fact_rows(session, project, from_d, to_d)
    return await _sentiment_contract_evidence_count(
        session,
        scoped_brand_id,
        from_d,
        to_d,
        response_ids=_fact_response_ids(rows),
    )


def _sentiment_by_engine_missing_out(
    *,
    project_id: str,
    period: dict[str, str],
    evidence_count: int,
    evidence_counts: dict[str, int],
    missing_inputs: list[str] | None = None,
) -> SentimentByEngineOut:
    missing_inputs = missing_inputs or [
        "brand_mentions.sentiment_score",
        "brand_mentions.sentiment",
    ]
    return SentimentByEngineOut(
        project_id=project_id,
        period=period,
        items=[],
        state="partial",
        state_reason="missing_formula_inputs",
        evidence_count=evidence_count,
        evidence_counts=evidence_counts,
        missing_inputs=missing_inputs,
        missing_sources=missing_inputs,
        formula_status=FORMULA_MISSING_INPUTS_STATUS,
        formula_diagnostics=formula_diagnostics_for(
            FORMULA_MISSING_INPUTS_STATUS,
            missing_inputs=missing_inputs,
        ),
        source_provenance=["brand_mentions", "llm_responses", "geo_score_daily"],
    )


def _sentiment_missing_out(
    *,
    project_id: str,
    period: dict[str, str],
    engines: list[str],
    evidence_count: int,
    evidence_counts: dict[str, int],
) -> SentimentTrendByEngineOut:
    missing_inputs = ["brand_mentions.sentiment_score", "brand_mentions.sentiment"]
    return SentimentTrendByEngineOut(
        project_id=project_id,
        period=period,
        engines=engines,
        items=[],
        state="partial",
        state_reason="missing_formula_inputs",
        evidence_count=evidence_count,
        evidence_counts=evidence_counts,
        missing_inputs=missing_inputs,
        missing_sources=missing_inputs,
        formula_status=FORMULA_MISSING_INPUTS_STATUS,
        formula_diagnostics=formula_diagnostics_for(
            FORMULA_MISSING_INPUTS_STATUS,
            missing_inputs=missing_inputs,
        ),
        source_provenance=["brand_mentions", "geo_score_daily"],
    )


async def _admin_fact_rows(
    session: AsyncSession,
    project: Project,
    from_d: date,
    to_d: date,
    *,
    engines: list[str] | None = None,
    segment_id: str | None = None,
    profile_id: str | None = None,
    brand_id_override: int | None = None,
) -> list[dict[str, Any]]:
    return await _fact_rows(
        session,
        project,
        filters=_admin_filters(
            from_d,
            to_d,
            engines=engines,
            segment_id=segment_id,
            profile_id=profile_id,
        ),
        brand_id_override=brand_id_override,
    )


async def _recover_after_swallowed_db_error(session: AsyncSession, project: Project) -> None:
    # PostgreSQL keeps a transaction aborted after a statement error; reset it
    # before fallback reads build the analyzer contract context.
    await session.rollback()
    await session.refresh(project)


def _polarity_from_score(score: object) -> str:
    value = _as_float(score)
    if value is None:
        return "neutral"
    if value > 0.05:
        return "positive"
    if value < -0.05:
        return "negative"
    return "neutral"


def _label_for_polarity(polarity: str) -> str:
    return {"positive": "Positive", "negative": "Negative", "neutral": "Neutral"}.get(
        polarity, "Neutral"
    )


def _engine_metric_rows_from_facts(
    fact_rows: list[dict[str, Any]],
) -> tuple[list[EngineMetricRow], int]:
    engine_bucket: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "responses": set(),
            "denominator_response_ids": set(),
            "target_response_ids": set(),
            "target_mentions": 0,
            "all_mentions": 0,
            "citations": 0,
            "sentiment": [],
        }
    )
    seen: set[int] = set()
    for row in fact_rows:
        rid = _as_int(row.get("response_id"))
        if rid is None or rid in seen:
            continue
        seen.add(rid)
        engine = str(row.get("target_llm") or row.get("response_target_llm") or "unknown")
        target_mentions = _fact_target_mention_count(row)
        all_mentions = _fact_all_mention_count(row, target_mentions)
        engine_bucket[engine]["responses"].add(rid)
        engine_bucket[engine]["denominator_response_ids"].add(rid)
        if target_mentions > 0:
            engine_bucket[engine]["target_response_ids"].add(rid)
        engine_bucket[engine]["target_mentions"] += target_mentions
        engine_bucket[engine]["all_mentions"] += all_mentions
        engine_bucket[engine]["citations"] += int(row.get("citation_count") or 0)
        target_mentions = _fact_target_mention_count(row)
        sentiment = (
            _as_float(row.get("target_sentiment_score"))
            if target_mentions > 0
            else _as_float(row.get("sentiment_score"))
        )
        if sentiment is not None:
            engine_bucket[engine]["sentiment"].append(sentiment)
    items = [
        EngineMetricRow(
            engine=engine,
            mention_rate=round(
                len(values["target_response_ids"]) / len(values["denominator_response_ids"]),
                4,
            )
            if values["denominator_response_ids"]
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
        for engine, values in sorted(engine_bucket.items())
        if values["responses"]
    ]
    return items, len(seen)


def _position_distribution_from_facts(
    fact_rows: list[dict[str, Any]],
) -> tuple[list[PositionBucketRow], int, int]:
    buckets: OrderedDict[str, int] = OrderedDict(
        [("Top1", 0), ("Top3", 0), ("Top5", 0), ("Top10", 0), ("11+", 0), ("Unmentioned", 0)]
    )
    seen: set[int] = set()
    for row in fact_rows:
        rid = _as_int(row.get("response_id"))
        if rid is None or rid in seen:
            continue
        seen.add(rid)
        if _fact_target_mention_count(row) <= 0:
            continue
        rank = _as_int(row.get("min_position_rank") or row.get("target_brand_rank"))
        if rank is None:
            buckets["Unmentioned"] += 1
        elif rank == 1:
            buckets["Top1"] += 1
        elif rank <= 3:
            buckets["Top3"] += 1
        elif rank <= 5:
            buckets["Top5"] += 1
        elif rank <= 10:
            buckets["Top10"] += 1
        else:
            buckets["11+"] += 1
    total = sum(buckets.values())
    return (
        [
            PositionBucketRow(
                bucket=k,
                count=v,
                pct=round((v / total * 100) if total else 0.0, 2),
            )
            for k, v in buckets.items()
        ],
        total,
        len(seen),
    )


async def _topic_heatmap_from_facts(
    session: AsyncSession,
    project: Project,
    fact_rows: list[dict[str, Any]],
    *,
    metric: str,
    compare_with: list[int],
    top_n: int,
) -> tuple[list[HeatmapRow], int]:
    primary = project.primary_brand_id
    if primary is None:
        return [], 0

    topic_buckets: dict[int, dict[str, Any]] = {}
    seen: set[int] = set()
    for row in fact_rows:
        tid = _as_int(row.get("topic_id"))
        rid = _as_int(row.get("response_id"))
        if tid is None or rid is None or rid in seen:
            continue
        seen.add(rid)
        bucket = topic_buckets.setdefault(
            tid,
            {
                "name": row.get("topic_name") or f"topic-{tid}",
                "responses": set(),
                "target_responses": set(),
                "sentiments": [],
            },
        )
        bucket["responses"].add(rid)
        if _fact_target_mention_count(row) > 0:
            bucket["target_responses"].add(rid)
        target_mentions = _fact_target_mention_count(row)
        sentiment = (
            _as_float(row.get("target_sentiment_score"))
            if target_mentions > 0
            else _as_float(row.get("sentiment_score"))
        )
        if sentiment is not None:
            bucket["sentiments"].append(sentiment)

    top_topics = sorted(
        topic_buckets,
        key=lambda tid: (
            -len(topic_buckets[tid]["target_responses"]),
            -len(topic_buckets[tid]["responses"]),
            tid,
        ),
    )[:top_n]
    if not top_topics:
        return [], len(seen)

    topic_names = await resolve_topic_names(session, top_topics)
    brand_ids = [primary, *compare_with]
    brand_names = await resolve_brand_names(session, brand_ids)
    cells: list[HeatmapCell] = []
    for tid in top_topics:
        bucket = topic_buckets[tid]
        sample = len(bucket["responses"])
        value = None
        if metric == "sentiment":
            sentiments = bucket["sentiments"]
            if sentiments:
                value = round(sum(sentiments) / len(sentiments), 4)
        elif sample:
            value = round(len(bucket["target_responses"]) / sample, 4)
        cells.append(
            HeatmapCell(
                topic_id=tid,
                topic_label=topic_names.get(tid) or bucket["name"],
                value=value,
                sample=sample,
            )
        )
    rows = [HeatmapRow(brand_id=primary, brand_name=brand_names.get(primary), values=cells)]
    for bid in compare_with:
        rows.append(
            HeatmapRow(
                brand_id=bid,
                brand_name=brand_names.get(bid),
                values=[
                    HeatmapCell(
                        topic_id=cell.topic_id,
                        topic_label=cell.topic_label,
                        value=None,
                        sample=0,
                    )
                    for cell in cells
                ],
            )
        )
    return rows, len(seen)


def _sentiment_by_engine_from_facts(
    fact_rows: list[dict[str, Any]],
) -> tuple[list[SentimentByEngineRow], int]:
    bucket: dict[str, dict[str, int]] = defaultdict(
        lambda: {"positive": 0, "neutral": 0, "negative": 0}
    )
    seen: set[int] = set()
    for row in fact_rows:
        rid = _as_int(row.get("response_id"))
        if rid is None or rid in seen:
            continue
        seen.add(rid)
        engine = str(row.get("target_llm") or row.get("response_target_llm") or "unknown")
        positive = int(row.get("positive_mentions") or 0)
        neutral = int(row.get("neutral_mentions") or 0)
        negative = int(row.get("negative_mentions") or 0)
        if positive or neutral or negative:
            bucket[engine]["positive"] += positive
            bucket[engine]["neutral"] += neutral
            bucket[engine]["negative"] += negative
    items = [
        SentimentByEngineRow(
            engine=engine,
            positive=v["positive"],
            neutral=v["neutral"],
            negative=v["negative"],
        )
        for engine, v in sorted(bucket.items())
        if v["positive"] or v["neutral"] or v["negative"]
    ]
    return items, len(seen)


async def _sentiment_by_engine_from_response_window(
    session: AsyncSession,
    project: Project,
    from_d: date,
    to_d: date,
    *,
    engines: list[str] | None = None,
) -> tuple[list[SentimentByEngineRow], int, dict[str, int], list[str]]:
    if project.primary_brand_id is None:
        return [], 0, {}, []
    if not await legacy_table_exists(session, "llm_responses"):
        return [], 0, {}, []

    response_cols = await legacy_table_columns(session, "llm_responses")
    if "id" not in response_cols:
        return [], 0, {}, []

    joins = ["JOIN llm_responses r ON r.id = bm.response_id"]
    timestamp_exprs: list[str] = []
    engine_exprs: list[str] = []
    if "created_at" in response_cols:
        timestamp_exprs.append("r.created_at")
    if "target_llm" in response_cols:
        engine_exprs.append("r.target_llm")

    query_cols: set[str] = set()
    if "query_id" in response_cols and await legacy_table_exists(session, "queries"):
        query_cols = await legacy_table_columns(session, "queries")
        if "id" in query_cols:
            joins.append("LEFT JOIN queries q ON q.id = r.query_id")
            for column in ("finished_at", "executed_at", "created_at"):
                if column in query_cols:
                    timestamp_exprs.append(f"q.{column}")
            if "target_llm" in query_cols:
                engine_exprs.insert(0, "q.target_llm")

    timestamp_expr = _coalesce_sql(timestamp_exprs)
    if timestamp_expr is None:
        return [], 0, {}, ["llm_responses.created_at"]

    params: dict[str, Any] = {
        "brand_id": project.primary_brand_id,
        "from_dt": datetime.combine(from_d, datetime.min.time()),
        "to_dt": datetime.combine(to_d, datetime.max.time()),
    }
    match_conditions = ["bm.brand_id = :brand_id"]
    names = await brand_mention_names(session, project.primary_brand_id)
    if names:
        placeholders: list[str] = []
        for idx, name in enumerate(sorted(names)):
            key = f"brand_name_{idx}"
            params[key] = name
            placeholders.append(f":{key}")
        match_conditions.append(
            f"LOWER(TRIM(COALESCE(bm.brand_name, ''))) IN ({', '.join(placeholders)})"
        )

    label_expr = _sentiment_label_sql()
    where_sql = f"""
        ({" OR ".join(match_conditions)})
        AND bm.sentiment_score IS NOT NULL
        AND {label_expr} IN ('positive', 'neutral', 'negative')
        AND {timestamp_expr} >= :from_dt
        AND {timestamp_expr} <= :to_dt
    """
    joins_sql = "\n".join(joins)
    evidence_count = int(
        (
            await session.execute(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM brand_mentions bm
                    {joins_sql}
                    WHERE {where_sql}
                    """
                ),
                params,
            )
        ).scalar_one()
        or 0
    )
    evidence_counts = _chart_counts(sentiment_label_count=evidence_count)
    if evidence_count <= 0:
        return [], 0, evidence_counts, []

    engine_expr = _coalesce_sql(engine_exprs)
    if engine_expr is None:
        return [], evidence_count, evidence_counts, ["llm_responses.target_llm"]

    rows = (
        await session.execute(
            text(
                f"""
                SELECT {engine_expr} AS engine, {label_expr} AS sentiment, COUNT(*) AS cnt
                FROM brand_mentions bm
                {joins_sql}
                WHERE {where_sql}
                GROUP BY {engine_expr}, {label_expr}
                """
            ),
            params,
        )
    ).all()

    allowed_engines = {engine.lower() for engine in engines or []}
    buckets: dict[str, dict[str, int]] = defaultdict(
        lambda: {"positive": 0, "neutral": 0, "negative": 0}
    )
    attributed_count = 0
    missing_engine_count = 0
    for engine_value, sentiment, count in rows:
        count_int = int(count or 0)
        engine = str(engine_value).strip() if engine_value is not None else ""
        if not engine:
            missing_engine_count += count_int
            continue
        if allowed_engines and engine.lower() not in allowed_engines:
            continue
        if sentiment not in buckets[engine]:
            continue
        buckets[engine][sentiment] += count_int
        attributed_count += count_int

    items = [
        SentimentByEngineRow(
            engine=engine,
            positive=values["positive"],
            neutral=values["neutral"],
            negative=values["negative"],
        )
        for engine, values in sorted(buckets.items())
        if values["positive"] or values["neutral"] or values["negative"]
    ]
    evidence_counts = _chart_counts(
        sentiment_label_count=evidence_count,
        engine_attributed_sentiment_label_count=attributed_count,
        engine_missing_sentiment_label_count=missing_engine_count,
    )
    if not items and evidence_count > 0:
        return [], evidence_count, evidence_counts, ["llm_responses.target_llm"]
    return items, attributed_count, evidence_counts, []


def _sentiment_trend_by_engine_from_facts(
    fact_rows: list[dict[str, Any]],
) -> tuple[list[str], list[SentimentTrendByEngineRow], int]:
    by_day_engine: dict[str, dict[str, list[float]]] = OrderedDict()
    engines_seen: set[str] = set()
    seen: set[int] = set()
    for row in fact_rows:
        rid = _as_int(row.get("response_id"))
        target_mentions = _fact_target_mention_count(row)
        sentiment = (
            _as_float(row.get("target_sentiment_score"))
            if target_mentions > 0
            else _as_float(row.get("sentiment_score"))
        )
        if rid is None or rid in seen or sentiment is None:
            continue
        seen.add(rid)
        day = _date_key(
            row.get("query_created_at")
            or row.get("response_created_at")
            or row.get("query_finished_at")
        )
        if day is None:
            continue
        engine = str(row.get("target_llm") or row.get("response_target_llm") or "unknown")
        engines_seen.add(engine)
        by_day_engine.setdefault(day, defaultdict(list))[engine].append(sentiment)
    engines = sorted(engines_seen)
    items = [
        SentimentTrendByEngineRow(
            date=day,
            by_engine={
                engine: round(sum(values.get(engine, [])) / len(values.get(engine, [])), 4)
                if values.get(engine)
                else None
                for engine in engines
            },
        )
        for day, values in by_day_engine.items()
    ]
    return engines, items, len(seen)


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
    brand_id_override: int | None = None,
) -> EngineMetricsOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    brand_id = brand_id_override if brand_id_override is not None else project.primary_brand_id
    if brand_id is None:
        return EngineMetricsOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            items=[],
            state="empty",
            state_reason="no_primary_brand",
        )
    f, t = _dt_range(from_d, to_d)
    if _needs_admin_filter(engines=engines, segment_id=segment_id, profile_id=profile_id):
        fact_rows = await _admin_fact_rows(
            session,
            project,
            from_d,
            to_d,
            engines=engines,
            segment_id=segment_id,
            profile_id=profile_id,
            brand_id_override=brand_id,
        )
        items, evidence_count = _engine_metric_rows_from_facts(fact_rows)
        state = "ok" if items else "empty"
        out = EngineMetricsOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            items=items,
            state=state,
            state_reason=_state_reason(state, "no_admin_fact_data"),
            evidence_count=evidence_count,
            evidence_counts=_chart_counts(admin_fact_response_count=evidence_count),
        )
        return await _with_engine_metric_contract(
            out,
            session,
            project,
            from_d,
            to_d,
            source_provenance=["admin_facts", "brand_mentions", "citation_sources"],
            brand_id=brand_id,
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
                GeoScoreDaily.brand_id == brand_id,
                GeoScoreDaily.date >= f,
                GeoScoreDaily.date <= t,
                GeoScoreDaily.target_llm.isnot(None),
            )
        )
        .group_by(GeoScoreDaily.target_llm)
        .order_by(GeoScoreDaily.target_llm)
    )
    score_rows = (await session.execute(stmt)).all()
    items = [
        EngineMetricRow(
            engine=r[0] or "(unknown)",
            mention_rate=round(float(r[1]), 4) if r[1] is not None else None,
            sov=round(float(r[2]), 4) if r[2] is not None else None,
            citation_rate=round(float(r[3]), 4) if r[3] is not None else None,
            sentiment=round(float(r[4]), 3) if r[4] is not None else None,
        )
        for r in score_rows
    ]
    if not items:
        fact_rows = await _admin_fact_rows(
            session,
            project,
            from_d,
            to_d,
            brand_id_override=brand_id,
        )
        items, evidence_count = _engine_metric_rows_from_facts(fact_rows)
        state = "ok" if items else "empty"
        out = EngineMetricsOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            items=items,
            state=state,
            state_reason=_state_reason(state, "no_metric_data"),
            evidence_count=evidence_count,
            evidence_counts=_chart_counts(admin_fact_response_count=evidence_count),
        )
        return await _with_engine_metric_contract(
            out,
            session,
            project,
            from_d,
            to_d,
            source_provenance=["admin_facts", "brand_mentions", "citation_sources"],
            brand_id=brand_id,
        )
    evidence_count = len(score_rows)
    out = EngineMetricsOut(
        project_id=project.id,
        period=_period(from_d, to_d),
        items=items,
        state="ok",
        state_reason="data_available",
        evidence_count=evidence_count,
        evidence_counts=_chart_counts(geo_score_daily_rows=evidence_count),
    )
    return await _with_engine_metric_contract(
        out,
        session,
        project,
        from_d,
        to_d,
        source_provenance=["geo_score_daily"],
        brand_id=brand_id,
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
    brand_id_override: int | None = None,
) -> PositionDistributionOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    brand_id = brand_id_override if brand_id_override is not None else project.primary_brand_id
    if brand_id is None:
        return PositionDistributionOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            items=[],
            total_mentions=0,
            state="empty",
            state_reason="no_primary_brand",
        )
    f, t = _dt_range(from_d, to_d)
    if _needs_admin_filter(engines=engines, segment_id=segment_id, profile_id=profile_id):
        fact_rows = await _admin_fact_rows(
            session,
            project,
            from_d,
            to_d,
            engines=engines,
            segment_id=segment_id,
            profile_id=profile_id,
            brand_id_override=brand_id,
        )
        items, total, evidence_count = _position_distribution_from_facts(fact_rows)
        state = "ok" if total else "empty"
        out = PositionDistributionOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            items=items,
            total_mentions=total,
            state=state,
            state_reason=_state_reason(state, "no_admin_fact_mentions"),
            evidence_count=evidence_count,
            evidence_counts=_chart_counts(admin_fact_response_count=evidence_count),
        )
        return await _with_chart_contract(
            out,
            session,
            project,
            from_d,
            to_d,
            metric_keys=["mention_rate"],
            source_provenance=["admin_facts"],
            brand_id=brand_id,
        )
    stmt = (
        select(BrandMention.position_rank, func.count())
        .where(
            and_(
                BrandMention.brand_id == brand_id,
                BrandMention.created_at >= f,
                BrandMention.created_at <= t,
            )
        )
        .group_by(BrandMention.position_rank)
    )
    position_rows = (await session.execute(stmt)).all()
    position_buckets: OrderedDict[str, int] = OrderedDict(
        [("Top1", 0), ("Top3", 0), ("Top5", 0), ("Top10", 0), ("11+", 0), ("Unmentioned", 0)]
    )
    total = 0
    for r in position_rows:
        rank = r[0]
        cnt = int(r[1] or 0)
        total += cnt
        if rank is None:
            position_buckets["Unmentioned"] += cnt
        elif rank == 1:
            position_buckets["Top1"] += cnt
        elif rank <= 3:
            position_buckets["Top3"] += cnt
        elif rank <= 5:
            position_buckets["Top5"] += cnt
        elif rank <= 10:
            position_buckets["Top10"] += cnt
        else:
            position_buckets["11+"] += cnt
    items = [
        PositionBucketRow(bucket=k, count=v, pct=round((v / total * 100) if total else 0.0, 2))
        for k, v in position_buckets.items()
    ]
    if total == 0:
        fact_rows = await _admin_fact_rows(
            session,
            project,
            from_d,
            to_d,
            brand_id_override=brand_id,
        )
        items, total, evidence_count = _position_distribution_from_facts(fact_rows)
        state = "ok" if total else "empty"
        out = PositionDistributionOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            items=items,
            total_mentions=total,
            state=state,
            state_reason=_state_reason(state, "no_position_data"),
            evidence_count=evidence_count,
            evidence_counts=_chart_counts(admin_fact_response_count=evidence_count),
        )
        return await _with_chart_contract(
            out,
            session,
            project,
            from_d,
            to_d,
            metric_keys=["mention_rate"],
            source_provenance=["admin_facts"],
            brand_id=brand_id,
        )
    out = PositionDistributionOut(
        project_id=project.id,
        period=_period(from_d, to_d),
        items=items,
        total_mentions=total,
        state="ok",
        state_reason="data_available",
        evidence_count=total,
        evidence_counts=_chart_counts(brand_mention_count=total),
    )
    return await _with_chart_contract(
        out,
        session,
        project,
        from_d,
        to_d,
        metric_keys=["mention_rate"],
        source_provenance=["brand_mentions"],
        brand_id=brand_id,
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
    brand_id_override: int | None = None,
) -> TopicHeatmapOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    primary = brand_id_override if brand_id_override is not None else project.primary_brand_id
    if primary is None:
        return TopicHeatmapOut(
            project_id=project.id,
            metric=metric,
            rows=[],
            state="empty",
            state_reason="no_primary_brand",
        )

    # If no explicit comparison list supplied, use pinned competitors (top 4).
    if compare_with is None:
        comp_stmt = select(ProjectCompetitor.brand_id).where(
            ProjectCompetitor.project_id == project.id
        )
        compare_with = [r[0] for r in (await session.execute(comp_stmt)).all()][:4]

    brand_ids = _unique([str(primary), *[str(value) for value in compare_with]])
    brand_ids = [int(value) for value in brand_ids]
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
        fact_rows = await _admin_fact_rows(
            session,
            project,
            from_d,
            to_d,
            brand_id_override=primary,
        )
        fact_rows_out, evidence_count = await _topic_heatmap_from_facts(
            session,
            project,
            fact_rows,
            metric=metric,
            compare_with=compare_with,
            top_n=top_n,
        )
        state = (
            "ok"
            if any(any(cell.value is not None for cell in row.values) for row in fact_rows_out)
            else "empty"
        )
        out = TopicHeatmapOut(
            project_id=project.id,
            metric=metric,
            rows=fact_rows_out,
            state=state,
            state_reason=_state_reason(state, "no_topic_metric_data"),
            evidence_count=evidence_count,
            evidence_counts=_chart_counts(admin_fact_response_count=evidence_count),
        )
        return await _with_chart_contract(
            out,
            session,
            project,
            from_d,
            to_d,
            metric_keys=["sentiment" if metric == "sentiment" else "mention_rate"],
            source_provenance=["admin_facts"],
            brand_id=primary,
        )

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

    heatmap_rows: list[HeatmapRow] = []
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
        heatmap_rows.append(HeatmapRow(brand_id=bid, brand_name=brand_names.get(bid), values=cells))

    state = (
        "ok"
        if any(any(c.value is not None for c in row.values) for row in heatmap_rows)
        else "empty"
    )
    evidence_count = sum(cell.sample for row in heatmap_rows for cell in row.values)
    out = TopicHeatmapOut(
        project_id=project.id,
        metric=metric,
        rows=heatmap_rows,
        state=state,
        state_reason=_state_reason(state, "no_topic_metric_data"),
        evidence_count=evidence_count,
        evidence_counts=_chart_counts(topic_score_daily_sample_count=evidence_count),
    )
    update = await _chart_contract_update(
        session,
        project,
        from_d,
        to_d,
        out,
        metric_keys=["sentiment" if metric == "sentiment" else "mention_rate"],
        source_provenance=["topic_score_daily"],
        brand_id=primary,
    )
    contract_metric = "sentiment" if metric == "sentiment" else "mention_rate"
    if update and _contract_metric_non_ok(update, contract_metric):
        update["rows"] = [
            row.model_copy(
                update={"values": [cell.model_copy(update={"value": None}) for cell in row.values]}
            )
            for row in out.rows
        ]
    return out.model_copy(update=update) if update else out


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
    brand_id_override: int | None = None,
) -> SentimentByEngineOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    brand_id = brand_id_override if brand_id_override is not None else project.primary_brand_id
    if brand_id is None:
        return SentimentByEngineOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            items=[],
            state="empty",
            state_reason="no_primary_brand",
        )
    f, t = _dt_range(from_d, to_d)
    if _needs_admin_filter(engines=engines, segment_id=segment_id, profile_id=profile_id):
        fact_rows = await _admin_fact_rows(
            session,
            project,
            from_d,
            to_d,
            engines=engines,
            segment_id=segment_id,
            profile_id=profile_id,
            brand_id_override=brand_id,
        )
        items, evidence_count = _sentiment_by_engine_from_facts(fact_rows)
        score_evidence_count = _fact_sentiment_score_response_count(fact_rows)
        if not items and score_evidence_count:
            out = _sentiment_by_engine_missing_out(
                project_id=project.id,
                period=_period(from_d, to_d),
                evidence_count=score_evidence_count,
                evidence_counts=_chart_counts(admin_fact_response_count=score_evidence_count),
            )
            return await _with_sentiment_by_engine_contract(
                out,
                session,
                project,
                from_d,
                to_d,
                source_provenance=["admin_facts", "brand_mentions", "response_analyses"],
                brand_id=brand_id,
            )
        state = "ok" if items else "empty"
        out = SentimentByEngineOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            items=items,
            state=state,
            state_reason=_state_reason(state, "no_sentiment_data"),
            evidence_count=evidence_count,
            evidence_counts=_chart_counts(admin_fact_response_count=evidence_count),
        )
        return await _with_sentiment_by_engine_contract(
            out,
            session,
            project,
            from_d,
            to_d,
            source_provenance=["admin_facts", "brand_mentions", "response_analyses"],
            brand_id=brand_id,
        )
    # JOIN brand_mentions → llm_responses to get target_llm. SQLite tests fall
    # back to "all" engine bucket if join unavailable.
    (
        response_items,
        response_evidence,
        response_counts,
        response_missing,
    ) = await _sentiment_by_engine_from_response_window(
        session,
        project,
        from_d,
        to_d,
        engines=engines,
    )
    if response_items:
        out = SentimentByEngineOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            items=response_items,
            state="ok",
            state_reason="data_available",
            evidence_count=response_evidence,
            evidence_counts=response_counts,
            source_provenance=["brand_mentions", "llm_responses"],
        )
        return await _with_sentiment_by_engine_contract(
            out,
            session,
            project,
            from_d,
            to_d,
            source_provenance=["brand_mentions", "llm_responses"],
            brand_id=brand_id,
        )
    if response_missing and response_evidence:
        out = _sentiment_by_engine_missing_out(
            project_id=project.id,
            period=_period(from_d, to_d),
            evidence_count=response_evidence,
            evidence_counts=response_counts,
            missing_inputs=response_missing,
        )
        return await _with_sentiment_by_engine_contract(
            out,
            session,
            project,
            from_d,
            to_d,
            source_provenance=["brand_mentions", "llm_responses"],
            brand_id=brand_id,
        )
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
            {"bid": brand_id, "f": f, "t": t},
        )
        sentiment_rows = result.all()
    except Exception:
        await _recover_after_swallowed_db_error(session, project)
        sentiment_rows = []

    sentiment_bucket: dict[str, dict[str, int]] = defaultdict(
        lambda: {"positive": 0, "neutral": 0, "negative": 0}
    )
    for r in sentiment_rows:
        engine = r[0] or "unknown"
        sent = r[1] or "neutral"
        cnt = int(r[2] or 0)
        if sent in sentiment_bucket[engine]:
            sentiment_bucket[engine][sent] += cnt

    items = [
        SentimentByEngineRow(
            engine=engine,
            positive=v["positive"],
            neutral=v["neutral"],
            negative=v["negative"],
        )
        for engine, v in sorted(sentiment_bucket.items())
    ]
    if not items:
        fact_rows = await _admin_fact_rows(
            session,
            project,
            from_d,
            to_d,
            brand_id_override=brand_id,
        )
        items, evidence_count = _sentiment_by_engine_from_facts(fact_rows)
        score_evidence_count = _fact_sentiment_score_response_count(fact_rows)
        if not items and score_evidence_count:
            out = _sentiment_by_engine_missing_out(
                project_id=project.id,
                period=_period(from_d, to_d),
                evidence_count=score_evidence_count,
                evidence_counts=_chart_counts(admin_fact_response_count=score_evidence_count),
            )
            return await _with_sentiment_by_engine_contract(
                out,
                session,
                project,
                from_d,
                to_d,
                source_provenance=["admin_facts", "brand_mentions", "response_analyses"],
                brand_id=brand_id,
            )
        state = "ok" if items else "empty"
        out = SentimentByEngineOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            items=items,
            state=state,
            state_reason=_state_reason(state, "no_sentiment_data"),
            evidence_count=evidence_count,
            evidence_counts=_chart_counts(admin_fact_response_count=evidence_count),
        )
        return await _with_sentiment_by_engine_contract(
            out,
            session,
            project,
            from_d,
            to_d,
            source_provenance=["admin_facts", "brand_mentions", "response_analyses"],
            brand_id=brand_id,
        )
    evidence_count = sum(
        v["positive"] + v["neutral"] + v["negative"] for v in sentiment_bucket.values()
    )
    out = SentimentByEngineOut(
        project_id=project.id,
        period=_period(from_d, to_d),
        items=items,
        state="ok",
        state_reason="data_available",
        evidence_count=evidence_count,
        evidence_counts=_chart_counts(brand_mention_count=evidence_count),
    )
    return await _with_sentiment_by_engine_contract(
        out,
        session,
        project,
        from_d,
        to_d,
        source_provenance=["brand_mentions", "llm_responses"],
        brand_id=brand_id,
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
    brand_id_override: int | None = None,
) -> SentimentTrendByEngineOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    brand_id = brand_id_override if brand_id_override is not None else project.primary_brand_id
    if brand_id is None:
        return SentimentTrendByEngineOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            engines=[],
            items=[],
            state="empty",
            state_reason="no_primary_brand",
        )
    f, t = _dt_range(from_d, to_d)
    if _needs_admin_filter(engines=engines, segment_id=segment_id, profile_id=profile_id):
        fact_rows = await _admin_fact_rows(
            session,
            project,
            from_d,
            to_d,
            engines=engines,
            segment_id=segment_id,
            profile_id=profile_id,
            brand_id_override=brand_id,
        )
        engine_list, items, evidence_count = _sentiment_trend_by_engine_from_facts(fact_rows)
        state = "ok" if items else "empty"
        evidence_counts = _chart_counts(admin_fact_response_count=evidence_count)
        if items and not await _sentiment_contract_evidence_count(
            session,
            brand_id,
            from_d,
            to_d,
            response_ids=_fact_response_ids(fact_rows),
        ):
            return await _with_sentiment_trend_contract(
                _sentiment_missing_out(
                    project_id=project.id,
                    period=_period(from_d, to_d),
                    engines=engine_list,
                    evidence_count=evidence_count,
                    evidence_counts=evidence_counts,
                ),
                session,
                project,
                from_d,
                to_d,
                source_provenance=["admin_facts", "brand_mentions", "response_analyses"],
                brand_id=brand_id,
            )
        out = SentimentTrendByEngineOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            engines=engine_list,
            items=items,
            state=state,
            state_reason=_state_reason(state, "no_sentiment_data"),
            evidence_count=evidence_count,
            evidence_counts=evidence_counts,
        )
        return await _with_sentiment_trend_contract(
            out,
            session,
            project,
            from_d,
            to_d,
            source_provenance=["admin_facts", "brand_mentions", "response_analyses"],
            brand_id=brand_id,
        )
    stmt = (
        select(
            GeoScoreDaily.date,
            GeoScoreDaily.target_llm,
            func.avg(GeoScoreDaily.avg_sentiment),
        )
        .where(
            and_(
                GeoScoreDaily.brand_id == brand_id,
                GeoScoreDaily.date >= f,
                GeoScoreDaily.date <= t,
                GeoScoreDaily.target_llm.isnot(None),
            )
        )
        .group_by(GeoScoreDaily.date, GeoScoreDaily.target_llm)
        .order_by(GeoScoreDaily.date)
    )
    sentiment_rows = (await session.execute(stmt)).all()

    by_date: dict[str, dict[str, float | None]] = OrderedDict()
    sentiment_engines_seen: set[str] = set()
    for d, eng, v in sentiment_rows:
        d_iso = str(d)[:10]
        sentiment_engines_seen.add(eng or "unknown")
        by_date.setdefault(d_iso, {})[eng or "unknown"] = float(v) if v is not None else None

    engines = sorted(sentiment_engines_seen)
    items = [
        SentimentTrendByEngineRow(date=d_iso, by_engine={e: by_date[d_iso].get(e) for e in engines})
        for d_iso in by_date
    ]
    if not items:
        fact_rows = await _admin_fact_rows(
            session,
            project,
            from_d,
            to_d,
            brand_id_override=brand_id,
        )
        engines, items, evidence_count = _sentiment_trend_by_engine_from_facts(fact_rows)
        state = "ok" if items else "empty"
        evidence_counts = _chart_counts(admin_fact_response_count=evidence_count)
        if items and not await _sentiment_contract_evidence_count(
            session,
            brand_id,
            from_d,
            to_d,
            response_ids=_fact_response_ids(fact_rows),
        ):
            return await _with_sentiment_trend_contract(
                _sentiment_missing_out(
                    project_id=project.id,
                    period=_period(from_d, to_d),
                    engines=engines,
                    evidence_count=evidence_count,
                    evidence_counts=evidence_counts,
                ),
                session,
                project,
                from_d,
                to_d,
                source_provenance=["admin_facts", "brand_mentions", "response_analyses"],
                brand_id=brand_id,
            )
        out = SentimentTrendByEngineOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            engines=engines,
            items=items,
            state=state,
            state_reason=_state_reason(state, "no_sentiment_data"),
            evidence_count=evidence_count,
            evidence_counts=evidence_counts,
        )
        return await _with_sentiment_trend_contract(
            out,
            session,
            project,
            from_d,
            to_d,
            source_provenance=["admin_facts", "brand_mentions", "response_analyses"],
            brand_id=brand_id,
        )
    evidence_count = len(sentiment_rows)
    evidence_counts = _chart_counts(geo_score_daily_rows=evidence_count)
    if not await _sentiment_window_evidence_count(
        session,
        project,
        from_d,
        to_d,
        brand_id=brand_id,
    ):
        return await _with_sentiment_trend_contract(
            _sentiment_missing_out(
                project_id=project.id,
                period=_period(from_d, to_d),
                engines=engines,
                evidence_count=evidence_count,
                evidence_counts=evidence_counts,
            ),
            session,
            project,
            from_d,
            to_d,
            source_provenance=["geo_score_daily", "brand_mentions"],
            brand_id=brand_id,
        )
    out = SentimentTrendByEngineOut(
        project_id=project.id,
        period=_period(from_d, to_d),
        engines=engines,
        items=items,
        state="ok",
        state_reason="data_available",
        evidence_count=evidence_count,
        evidence_counts=evidence_counts,
    )
    return await _with_sentiment_trend_contract(
        out,
        session,
        project,
        from_d,
        to_d,
        source_provenance=["geo_score_daily", "brand_mentions"],
        brand_id=brand_id,
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
    brand_id_override: int | None = None,
) -> TopicAttributionOut:
    from_d, to_d = _resolve_window(from_date, to_date)
    primary = brand_id_override if brand_id_override is not None else project.primary_brand_id
    if primary is None:
        return TopicAttributionOut(
            project_id=project.id,
            items=[],
            state="empty",
            state_reason="no_primary_brand",
        )
    f, t = _dt_range(from_d, to_d)

    admin_filters = AnalysisFilters(
        from_date=from_d,
        to_date=to_d,
        engines=tuple(engines) if engines else None,
        segment_id=segment_id,
        profile_id=profile_id,
    )
    admin_rows = await _fact_rows(
        session,
        project,
        filters=admin_filters,
        brand_id_override=primary,
    )
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
                "responses": 0,
                "sample": None,
            }
        rid = row.get("response_id")
        if rid is None or int(rid) in seen_responses:
            continue
        seen_responses.add(int(rid))
        bucket = by_topic[tid]
        bucket["responses"] += 1
        bucket["positive"] += int(row.get("positive_mentions") or 0)
        bucket["neutral"] += int(row.get("neutral_mentions") or 0)
        bucket["negative"] += int(row.get("negative_mentions") or 0)
        if bucket["sample"] is None and row.get("negative_sample_snippet"):
            bucket["sample"] = row.get("negative_sample_snippet")

    admin_items: list[TopicAttributionRow] = []
    for tid, bucket in by_topic.items():
        total = int(bucket["responses"])
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
        state = "ok" if admin_items else "empty"
        evidence_count = _response_evidence_count(admin_rows)
        out = TopicAttributionOut(
            project_id=project.id,
            items=admin_items[:limit],
            state=state,
            state_reason=_state_reason(state, "no_negative_topic_data"),
            evidence_count=evidence_count,
            evidence_counts=_chart_counts(admin_fact_response_count=evidence_count),
        )
        update = await _chart_contract_update(
            session,
            project,
            from_d,
            to_d,
            out,
            metric_keys=["sentiment"],
            source_provenance=["admin_facts"],
            brand_id=primary,
        )
        if update and _contract_metric_non_ok(update, "sentiment"):
            update["items"] = []
        return out.model_copy(update=update) if update else out

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
    state = "ok" if items else "empty"
    out = TopicAttributionOut(
        project_id=project.id,
        items=items,
        state=state,
        state_reason=_state_reason(state, "no_negative_topic_data"),
        evidence_count=sum(item.negative_count for item in items),
    )
    update = await _chart_contract_update(
        session,
        project,
        from_d,
        to_d,
        out,
        metric_keys=["sentiment"],
        source_provenance=["topic_score_daily"],
        brand_id=primary,
    )
    if update and _contract_metric_non_ok(update, "sentiment"):
        update["items"] = []
    return out.model_copy(update=update) if update else out


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
        return MentionSamplesOut(
            project_id=project.id,
            items=[],
            state="empty",
            state_reason="no_primary_brand",
        )
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
    if not items:
        fact_rows = await _admin_fact_rows(session, project, from_d, to_d)
        seen: set[int] = set()
        fact_items: list[MentionSampleRow] = []
        for row in fact_rows:
            rid = _as_int(row.get("response_id"))
            if rid is None or rid in seen or _fact_target_mention_count(row) <= 0:
                continue
            seen.add(rid)
            polarity_value = _polarity_from_score(
                row.get("target_sentiment_score")
                if row.get("target_sentiment_score") is not None
                else row.get("sentiment_score")
            )
            fact_items.append(
                MentionSampleRow(
                    mention_id=rid,
                    response_id=rid,
                    label=_label_for_polarity(polarity_value),
                    polarity=polarity_value,
                    summary=str(row.get("response_raw_text") or "")[:280] or None,
                    snippet=row.get("response_raw_text"),
                    engine=row.get("target_llm") or row.get("response_target_llm"),
                    topic=row.get("topic_name"),
                    occurred_at=str(
                        row.get("response_created_at")
                        or row.get("query_finished_at")
                        or row.get("query_created_at")
                        or ""
                    )
                    or None,
                )
            )
            if len(fact_items) >= limit:
                break
        state = "ok" if fact_items else "empty"
        return MentionSamplesOut(
            project_id=project.id,
            items=fact_items,
            state=state,
            state_reason=_state_reason(state, "no_mention_sample_data"),
            evidence_count=len(seen),
            evidence_counts=_chart_counts(admin_fact_response_count=len(seen)),
        )
    return MentionSamplesOut(
        project_id=project.id,
        items=items,
        state="ok",
        state_reason="data_available",
        evidence_count=len(items),
        evidence_counts=_chart_counts(brand_mention_count=len(items)),
    )


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
            project_id=project.id,
            period=_period(from_d, to_d),
            points=[],
            state="empty",
            state_reason="no_primary_brand",
        )
    f, t = _dt_range(from_d, to_d)
    if _needs_admin_filter(engines=engines, segment_id=segment_id, profile_id=profile_id):
        fact_rows = await _admin_fact_rows(
            session,
            project,
            from_d,
            to_d,
            engines=engines,
            segment_id=segment_id,
            profile_id=profile_id,
        )
        evidence_count = _response_evidence_count(fact_rows)
        response_ids = sorted(
            {int(r["response_id"]) for r in fact_rows if r.get("response_id") is not None}
        )
        if not response_ids:
            return AuthorityTrendOut(
                project_id=project.id,
                period=_period(from_d, to_d),
                points=[],
                state="empty",
                state_reason="no_admin_fact_data",
            )
        fact_points, citation_count = await _target_authority_points_from_facts(
            session,
            brand_id=primary,
            response_days=_fact_response_day_map(fact_rows),
        )
        state = "ok" if fact_points else "empty"
        out = AuthorityTrendOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            points=fact_points,
            state=state,
            state_reason=_state_reason(state, "no_citation_data"),
            evidence_count=citation_count if citation_count else evidence_count,
            evidence_counts=_chart_counts(
                admin_fact_response_count=evidence_count,
                citation_source_count=citation_count,
            ),
        )
        return await _with_authority_trend_contract(
            out,
            session,
            project,
            from_d,
            to_d,
            source_provenance=["admin_facts", "citation_sources", "brand_mentions"],
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
    authority_rows = (await session.execute(stmt)).all()

    authority_by_day: dict[str, dict[int | None, int]] = OrderedDict()
    for d, tier, cnt in authority_rows:
        d_iso = d.isoformat() if hasattr(d, "isoformat") else str(d)[:10]
        authority_by_day.setdefault(d_iso, defaultdict(int))[tier] += int(cnt or 0)

    authority_points: list[AuthorityTrendPoint] = []
    for d_iso, tier_map in authority_by_day.items():
        total = sum(tier_map.values())
        if total <= 0:
            continue
        authority_points.append(
            AuthorityTrendPoint(
                date=d_iso,
                tier1_pct=round(tier_map.get(1, 0) / total * 100, 1),
                tier2_pct=round(tier_map.get(2, 0) / total * 100, 1),
                tier3_pct=round(tier_map.get(3, 0) / total * 100, 1),
                tier4_pct=round(tier_map.get(4, 0) / total * 100, 1),
                untiered_pct=round(tier_map.get(None, 0) / total * 100, 1),
            )
        )
    if not authority_points:
        fact_rows = await _admin_fact_rows(session, project, from_d, to_d)
        evidence_count = _response_evidence_count(fact_rows)
        fact_points, citation_count = await _target_authority_points_from_facts(
            session,
            brand_id=primary,
            response_days=_fact_response_day_map(fact_rows),
        )
        if fact_points:
            out = AuthorityTrendOut(
                project_id=project.id,
                period=_period(from_d, to_d),
                points=fact_points,
                state="ok",
                state_reason="data_available",
                evidence_count=citation_count,
                evidence_counts=_chart_counts(
                    admin_fact_response_count=evidence_count,
                    citation_source_count=citation_count,
                ),
            )
            return await _with_authority_trend_contract(
                out,
                session,
                project,
                from_d,
                to_d,
                source_provenance=["admin_facts", "citation_sources", "brand_mentions"],
            )
        out = AuthorityTrendOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            points=[],
            state="empty",
            state_reason="no_citation_data",
            evidence_count=evidence_count,
            evidence_counts=_chart_counts(admin_fact_response_count=evidence_count),
        )
        return await _with_authority_trend_contract(
            out,
            session,
            project,
            from_d,
            to_d,
            source_provenance=["admin_facts", "citation_sources", "brand_mentions"],
        )
    out = AuthorityTrendOut(
        project_id=project.id,
        period=_period(from_d, to_d),
        points=authority_points,
        state="ok",
        state_reason="data_available",
        evidence_count=sum(
            1
            for point in authority_points
            if point.tier1_pct
            or point.tier2_pct
            or point.tier3_pct
            or point.tier4_pct
            or point.untiered_pct
        ),
    )
    return await _with_authority_trend_contract(
        out,
        session,
        project,
        from_d,
        to_d,
        source_provenance=["citation_sources", "brand_mentions"],
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
            project_id=project.id,
            period=_period(from_d, to_d),
            segments=[],
            total=0,
            state="empty",
            state_reason="no_primary_brand",
        )
    f, t = _dt_range(from_d, to_d)
    if _needs_admin_filter(engines=engines, segment_id=segment_id, profile_id=profile_id):
        fact_rows = await _admin_fact_rows(
            session,
            project,
            from_d,
            to_d,
            engines=engines,
            segment_id=segment_id,
            profile_id=profile_id,
        )
        evidence_count = _response_evidence_count(fact_rows)
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
                state_reason="no_admin_fact_data",
                evidence_count=0,
            )
        segments, total = await _target_citation_composition_rows(
            session,
            brand_id=primary,
            response_ids=response_ids,
        )
        state = "ok" if total else "empty"
        out = CitationCompositionOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            segments=segments,
            total=total,
            state=state,
            state_reason=_state_reason(state, "no_citation_data"),
            evidence_count=evidence_count,
            evidence_counts=_chart_counts(
                admin_fact_response_count=evidence_count,
                citation_source_count=total,
            ),
        )
        return await _with_citation_composition_contract(
            out,
            session,
            project,
            from_d,
            to_d,
            source_provenance=["admin_facts", "citation_sources", "brand_mentions"],
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
    if total == 0:
        fact_rows = await _admin_fact_rows(session, project, from_d, to_d)
        evidence_count = _response_evidence_count(fact_rows)
        fact_segments, fact_total = await _target_citation_composition_rows(
            session,
            brand_id=primary,
            response_ids=_fact_response_ids(fact_rows),
        )
        if fact_total:
            out = CitationCompositionOut(
                project_id=project.id,
                period=_period(from_d, to_d),
                segments=fact_segments,
                total=fact_total,
                state="ok",
                state_reason="data_available",
                evidence_count=fact_total,
                evidence_counts=_chart_counts(
                    admin_fact_response_count=evidence_count,
                    citation_source_count=fact_total,
                ),
            )
            return await _with_citation_composition_contract(
                out,
                session,
                project,
                from_d,
                to_d,
                source_provenance=["admin_facts", "citation_sources", "brand_mentions"],
            )
        out = CitationCompositionOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            segments=segments,
            total=0,
            state="empty",
            state_reason="no_citation_data",
            evidence_count=evidence_count,
            evidence_counts=_chart_counts(admin_fact_response_count=evidence_count),
        )
        return await _with_citation_composition_contract(
            out,
            session,
            project,
            from_d,
            to_d,
            source_provenance=["admin_facts", "citation_sources", "brand_mentions"],
        )
    out = CitationCompositionOut(
        project_id=project.id,
        period=_period(from_d, to_d),
        segments=segments,
        total=total,
        state="ok",
        state_reason="data_available",
        evidence_count=total,
        evidence_counts=_chart_counts(citation_source_count=total),
    )
    return await _with_citation_composition_contract(
        out,
        session,
        project,
        from_d,
        to_d,
        source_provenance=["citation_sources", "brand_mentions"],
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
            state_reason="no_primary_brand",
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
        monitoring_topics: list[ContentGapTopicRow] = []
        for row in monitoring.topics:
            mention_rate = float(row.mention_rate or 0)
            citation_rate = float(row.citation_rate or 0)
            gap = round(mention_rate - citation_rate, 4)
            if gap <= 0:
                continue
            monitoring_topics.append(
                ContentGapTopicRow(
                    topic_id=row.topic_id,
                    topic_name=row.topic_name,
                    mention_rate=round(mention_rate, 4),
                    citation_rate=round(citation_rate, 4),
                    gap_score=gap,
                    suggestion="Increase authoritative/owned citations for this topic.",
                )
            )
            if len(monitoring_topics) >= limit:
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
            pt_total = sum(int(r[1] or 0) for r in pt_rows)
            if pt_total > 0:
                page_types = [
                    ContentGapPageTypeRow(
                        page_type=r[0] or "other",
                        count=int(r[1] or 0),
                        pct=round(int(r[1] or 0) / pt_total * 100, 1),
                    )
                    for r in pt_rows
                ]
        state = "ok" if monitoring_topics else "empty"
        evidence_count = _response_evidence_count(admin_rows)
        return ContentGapOut(
            project_id=project.id,
            topics=monitoring_topics,
            page_type_distribution=page_types,
            state=state,
            state_reason=_state_reason(state, "no_content_gap_data"),
            evidence_count=evidence_count,
            evidence_counts=_chart_counts(admin_fact_response_count=evidence_count),
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
            project_id=project.id,
            topics=[],
            page_type_distribution=[],
            state="empty",
            state_reason="no_topic_metric_data",
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

    gap_topics: list[ContentGapTopicRow] = []
    for r in topic_rows:
        tid = int(r[0])
        mr = float(r[1] or 0)
        approx_citation = round(brand_citation_rate * (1.0 - min(mr, 1.0)), 4)
        gap = round(mr - approx_citation, 4)
        if gap <= 0:
            continue
        gap_topics.append(
            ContentGapTopicRow(
                topic_id=tid,
                topic_name=name_map.get(tid) or f"topic-{tid}",
                mention_rate=round(mr, 4),
                citation_rate=approx_citation,
                gap_score=gap,
                suggestion="增加权威媒体/官方域引用, 弥补 citation gap",
            )
        )
        if len(gap_topics) >= limit:
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
    pt_total = sum(int(r[1] or 0) for r in pt_rows)
    page_types = (
        [
            ContentGapPageTypeRow(
                page_type=r[0] or "other",
                count=int(r[1] or 0),
                pct=round(int(r[1] or 0) / pt_total * 100, 1),
            )
            for r in pt_rows
        ]
        if pt_total > 0
        else []
    )

    state = "ok" if gap_topics else "empty"
    return ContentGapOut(
        project_id=project.id,
        topics=gap_topics,
        page_type_distribution=page_types,
        state=state,
        state_reason=_state_reason(state, "no_content_gap_data"),
        evidence_count=len(topic_rows),
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
            state_reason="no_primary_brand",
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

    state = "ok" if (targets or kols or top_domains) else "empty"
    return PrTargetsOut(
        project_id=project.id,
        targets=targets,
        kol_scorecards=kols,
        tier2_matrix=Tier2MatrixOut(domains=top_domains, brands=matrix_brand_rows),
        state=state,
        state_reason=_state_reason(state, "no_pr_target_data"),
        evidence_count=sum(row.gap for row in targets) + len(kols) + len(top_domains),
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
            state_reason="no_primary_brand",
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
    state = "ok" if weekly is not None else "partial"
    return SimulatorBaselineOut(
        project_id=project.id,
        current_pano=round(current_pano, 1),
        industry_median=round(industry_median, 1) if industry_median is not None else None,
        industry_top3_avg=round(top3, 1) if top3 is not None else None,
        tiers=tiers,
        presets=presets,
        state=state,
        state_reason="data_available" if state == "ok" else "geo_product_daily_pending",
        evidence_count=1 if weekly is not None else 0,
    )


# ── /competitors/authority-radar ────────────────────────────────────
async def get_authority_radar(
    session: AsyncSession,
    project: Project,
) -> AuthorityRadarOut:
    primary = project.primary_brand_id
    if primary is None:
        return AuthorityRadarOut(
            project_id=project.id,
            rows=[],
            state="empty",
            state_reason="no_primary_brand",
        )

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
    return AuthorityRadarOut(
        project_id=project.id,
        rows=rows,
        state=state,
        state_reason=_state_reason(state, "geo_product_daily_pending"),
        evidence_count=me[4] + top_comp_counts[4],
    )


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
            state_reason="no_primary_brand",
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
            state_reason="no_brand_group_data",
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

    state = "ok" if items else "empty"
    return GroupSharedDomainsOut(
        project_id=project.id,
        group_id=membership,
        group_name=group.name if group else None,
        shared_ratio=shared_ratio,
        items=items,
        state=state,
        state_reason=_state_reason(state, "no_shared_domain_data"),
        evidence_count=len(items),
    )


# ── /products/relations ─────────────────────────────────────────────
async def get_product_relations(
    session: AsyncSession,
    project: Project,
) -> ProductRelationsOut:
    primary = project.primary_brand_id
    if primary is None:
        return ProductRelationsOut(
            project_id=project.id,
            items=[],
            state="empty",
            state_reason="no_primary_brand",
        )

    # Find products owned by primary brand.
    own_stmt = select(KgProduct.product_id, KgProduct.primary_name).where(
        KgProduct.brand_id == primary
    )
    own_rows = (await session.execute(own_stmt)).all()
    own_ids = [int(r[0]) for r in own_rows]
    own_name = {int(r[0]): r[1] for r in own_rows}
    if not own_ids:
        return ProductRelationsOut(
            project_id=project.id,
            items=[],
            state="empty",
            state_reason="no_product_kg_data",
        )

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
    state = "ok" if items else "empty"
    return ProductRelationsOut(
        project_id=project.id,
        items=items,
        state=state,
        state_reason=_state_reason(state, "no_product_relation_data"),
        evidence_count=len(items),
    )
