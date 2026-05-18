"""Services for Brand metrics / topics / sentiment / citations (Phase 2.2).

Each service function is callable independently from MCP tools + Reports
(reusable per ADR-009 design).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any, TypedDict

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

from app.api.v1.projects._analytics_contract import (
    ANALYZER_FACT_PACKAGE_SOURCE,
    ANALYZER_FACT_PACKAGE_V3_SOURCE,
    FORMULA_MISSING_INPUTS_STATUS,
    FORMULA_OK_STATUS,
    FORMULA_PARTIAL_STATUS,
    FORMULA_PENDING_STATUS,
    AnalyticsContractContext,
    build_contract_context,
    context_update,
    context_with_sov_competitive_gap,
    formula_diagnostics_for,
    metric_definition,
    metric_evidence_for,
    metric_formula_status,
    metric_missing_inputs,
    ratio_decimal,
    score_0_100,
)
from app.api.v1.projects._legacy_lookups import resolve_topic_names
from app.api.v1.projects._mention_rollups import brand_mention_match_condition
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
ALLOWED_METRICS = {"mention_rate", "sov", "rank", "sentiment", "citation"}
METRIC_TO_COLUMN = {
    "mention_rate": GeoScoreDaily.mention_rate,
    "sov": GeoScoreDaily.avg_sov,
    "rank": GeoScoreDaily.avg_position_rank,
    "sentiment": GeoScoreDaily.avg_sentiment,
    "citation": GeoScoreDaily.citation_rate,
}


class _FactMetricBucket(TypedDict):
    response_ids: set[int]
    mention_denominator_response_ids: set[int]
    target_mention_response_ids: set[int]
    citation_target_response_ids: set[int]
    has_citation_input: bool
    has_target_mention_input: bool
    has_all_mention_input: bool
    target_mentions: int
    all_mentions: int
    ranks: list[float]
    sentiment_scores: list[float]
    sentiment_label_count: int
    cited_target_response_ids: set[int]
    # Issue #948 follow-up: per-day sums of attributed-citation count
    # (numerator) and total-citation count (denominator) for the proper
    # citation_share = target_attributed / eligible_project semantic.
    target_citation_count_sum: int
    citation_count_sum: int


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


def _normalize_metric_value(metric: str, value: float | int | None) -> float:
    if metric in {"mention_rate", "sov", "citation"}:
        return ratio_decimal(value) or 0.0
    if metric == "geo_score":
        return score_0_100(value) or 0.0
    return round(float(value or 0), 4)


def _decorate_metric_series(
    series: list[MetricSeries],
    *,
    score_component_metrics: set[str] | None = None,
) -> list[MetricSeries]:
    score_component_metrics = score_component_metrics or set()
    decorated: list[MetricSeries] = []
    for item in series:
        definition_key = (
            "avg_sentiment"
            if item.metric == "sentiment" and item.metric in score_component_metrics
            else item.metric
        )
        spec = metric_definition(definition_key)
        formula_status = FORMULA_OK_STATUS if item.points else FORMULA_MISSING_INPUTS_STATUS
        missing_inputs: list[str] = []
        if not item.points:
            if item.metric == "mention_rate":
                missing_inputs.append("eligible_response_denominator")
            elif item.metric == "sov":
                missing_inputs.append("brand_mentions.competitive_set")
            elif item.metric == "rank":
                missing_inputs.append("brand_mentions.position_rank")
            elif item.metric == "sentiment":
                missing_inputs.append("brand_mentions.sentiment_score")
            elif item.metric == "citation":
                missing_inputs.append("citation_sources")
        decorated.append(
            item.model_copy(
                update={
                    "unit": spec.unit,
                    "value_scale": spec.value_scale,
                    "value_range": spec.value_range,
                    "denominator_label": spec.denominator_label,
                    "numerator_label": spec.numerator_label,
                    "source": spec.source,
                    "formula_status": formula_status,
                    "missing_inputs": missing_inputs,
                    "state": "ok" if item.points else "partial",
                    "state_reason": ("data_available" if item.points else "missing_formula_inputs"),
                    "evidence_count": len(item.points),
                }
            )
        )
    return decorated


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            out.append(value)
            seen.add(value)
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
            "source_tables": [ANALYZER_FACT_PACKAGE_V3_SOURCE, ANALYZER_FACT_PACKAGE_SOURCE],
            "fact_classes": [evidence_key],
            "sample_response_ids": [],
        }
        for evidence_key in _unique(
            [evidence_key_by_metric.get(metric_key, metric_key) for metric_key in metric_keys]
        )
    }


def _series_missing_inputs(
    metric: str,
    context: AnalyticsContractContext,
    *,
    evidence_source: str = "geo_score_daily",
) -> list[str]:
    package_missing = metric_missing_inputs(context, metric)
    if package_missing:
        return package_missing
    # Issue #1225: citation_share collapses to target-only attribution when
    # competitors are configured but ZERO citation_sources rows are
    # attributable to a competitive brand_mention. The analyzer-evidence
    # rollup for citations (`contracts/builder.py:372-406`) checks
    # citation_total / attributed_citations / fact_link_count but does NOT
    # check for the target-only-denominator case, so `metric_missing_inputs`
    # above can return `[]` while the denominator is still degenerate.
    # This must run regardless of `evidence_source` because admin_facts
    # short-circuits the metric-specific branches below; the captured
    # bestCoffer surface (#1225, project 7380c0e0-…, brand_id=24) uses
    # `evidence_source="admin_facts"`. Symmetric to the SoV / mention_rate
    # path which the analyzer rollup already covers via `target_only_sov`.
    # See PRD-APP-ANALYTICS-002/003/008.
    if (
        metric == "citation"
        and context.evidence_counts.get("citation_source_count", 0) > 0
        and context.evidence_counts.get("competitor_brand_count", 0) > 0
        and context.evidence_counts.get("competitive_citation_count", 0) <= 0
    ):
        return ["brand_mentions.competitive_set"]
    if evidence_source == "admin_facts":
        return []
    inputs = {*context.missing_inputs, *context.missing_sources}
    missing: list[str] = []
    if evidence_source == "geo_score_daily":
        if "eligible_response_denominator" in inputs:
            missing.append("eligible_response_denominator")
        if "geo_score_daily.total_queries" in inputs:
            missing.append("geo_score_daily.total_queries")
    if metric == "sov" and (
        "brand_mentions.competitive_set" in inputs
        or context.evidence_counts.get("competitive_mention_count", 0) <= 0
    ):
        missing.append("brand_mentions.competitive_set")
    elif metric == "rank" and "llm_brand_position" in inputs:
        missing.append("brand_mentions.position_rank")
    elif metric == "sentiment" and (
        "brand_mentions.sentiment_score" in inputs or "llm_brand_sentiment" in inputs
    ):
        missing.append("brand_mentions.sentiment_score")
    elif metric == "citation" and context.evidence_counts.get("citation_source_count", 0) <= 0:
        missing.append("citation_sources")
    return _unique(missing)


# Issue #948: peripheral missing inputs — analyzer-rollup pointers that do
# NOT invalidate the value because the value was computed directly from
# GeoScoreDaily / admin-fact rows (a separate, real source).
_PERIPHERAL_PACKAGE_INPUTS: frozenset[str] = frozenset(
    {
        "missing_analyzer_fact_packages",
        ANALYZER_FACT_PACKAGE_SOURCE,
        ANALYZER_FACT_PACKAGE_V3_SOURCE,
    }
)


def _series_has_real_evidence(
    item: MetricSeries,
    context: AnalyticsContractContext,
    missing_inputs: list[str],
    *,
    evidence_source: str,
) -> bool:
    """Return True when the series points were derived from real aggregate
    evidence AND the only missing inputs are peripheral.

    Issue #948 fix. When this returns True, peripheral missing inputs
    (e.g. ``missing_analyzer_fact_packages`` when the rollup is absent
    but the value was computed from `GeoScoreDaily` / admin facts; or a
    metric whose analyzer evidence is `formula_partial` rather than
    `missing_required_inputs`) should not clear ``item.points``. The
    value itself is real and computable. The contract surfaces
    ``formula_partial`` instead so the frontend gate keeps rendering the
    number rather than the ``—`` placeholder.

    Returns False when any missing input is critical (denominator
    missing, primary source missing, target-only SoV, analyzer reported
    the metric is unprovable, etc.) so the no-fallback contract still
    surfaces ``—`` for unprovable values.
    """
    if not item.points:
        return False
    # Treat the analyzer-rollup pointer paths as peripheral.
    non_peripheral = [r for r in missing_inputs if r not in _PERIPHERAL_PACKAGE_INPUTS]
    if non_peripheral:
        # If the remaining reasons all came from an analyzer-evidence
        # entry whose own formula_status is `partial` (not blocking),
        # treat them as peripheral too — the analyzer itself considers
        # the metric value computable. This preserves PR #899's intent
        # for metrics that report partial coverage but real numbers.
        evidence = metric_evidence_for(context, item.metric)
        evidence_status = str(evidence.get("formula_status") or "") if evidence else ""
        if evidence_status != FORMULA_PARTIAL_STATUS:
            return False
    if evidence_source == "admin_facts":
        return context.evidence_counts.get("admin_fact_response_count", 0) > 0
    return context.evidence_counts.get("geo_score_daily_rows", 0) > 0


def _only_peripheral_package_inputs(missing_inputs: list[str]) -> bool:
    return bool(missing_inputs) and all(
        item in _PERIPHERAL_PACKAGE_INPUTS for item in missing_inputs
    )


def _apply_metric_series_contract(
    series: list[MetricSeries],
    context: AnalyticsContractContext,
    *,
    evidence_source: str = "geo_score_daily",
) -> list[MetricSeries]:
    out: list[MetricSeries] = []
    for item in series:
        missing_inputs = _series_missing_inputs(
            item.metric,
            context,
            evidence_source=evidence_source,
        )
        if not missing_inputs:
            formula_status = metric_formula_status(
                context,
                item.metric,
                item.formula_status,
            )
            if item.metric == "sov" and item.points and item.formula_status == FORMULA_OK_STATUS:
                formula_status = FORMULA_OK_STATUS
            out.append(item.model_copy(update={"formula_status": formula_status}))
            continue
        # Peripheral analyzer inputs are missing, but the series already
        # carries points that were computed from real aggregate evidence
        # (Issue #948: KPI cards rendered "—" because this branch cleared
        # `points` and downgraded `formula_status` to `missing_required_inputs`
        # even when `geo_score_daily` / admin facts contained the rows that
        # produced the values). Preserve the values, record the peripheral
        # missing inputs, and emit `formula_partial` so the frontend gate
        # keeps surfacing the number. Critical missing inputs (no
        # denominator, no source rows, project unbound) still clear points
        # per the no-fallback contract — see `_series_has_real_evidence`.
        if _series_has_real_evidence(
            item, context, missing_inputs, evidence_source=evidence_source
        ):
            formula_status = (
                FORMULA_OK_STATUS
                if _only_peripheral_package_inputs(missing_inputs)
                else FORMULA_PARTIAL_STATUS
            )
            state = "ok" if formula_status == FORMULA_OK_STATUS else "partial"
            state_reason = (
                "data_available" if formula_status == FORMULA_OK_STATUS else "partial_analyzer_data"
            )
            item_missing_inputs = (
                item.missing_inputs
                if formula_status == FORMULA_OK_STATUS
                else _unique([*item.missing_inputs, *missing_inputs])
            )
            out.append(
                item.model_copy(
                    update={
                        "formula_status": formula_status,
                        "missing_inputs": item_missing_inputs,
                        "state": state,
                        "state_reason": state_reason,
                    }
                )
            )
            continue
        formula_status = metric_formula_status(
            context,
            item.metric,
            FORMULA_MISSING_INPUTS_STATUS,
        )
        out.append(
            item.model_copy(
                update={
                    "points": [],
                    "formula_status": formula_status,
                    "missing_inputs": _unique([*item.missing_inputs, *missing_inputs]),
                    "state": "partial",
                    "state_reason": "missing_formula_inputs",
                    "evidence_count": 0,
                }
            )
        )
    return out


def _series_contract_missing_inputs(
    series: list[MetricSeries],
    context: AnalyticsContractContext,
    *,
    evidence_source: str = "geo_score_daily",
) -> list[str]:
    missing: list[str] = []
    for item in series:
        missing.extend(
            _series_missing_inputs(
                item.metric,
                context,
                evidence_source=evidence_source,
            )
        )
    return _unique(missing)


def _fact_metric_value(metric: str, bucket: _FactMetricBucket) -> float | None:
    if metric == "mention_rate":
        denominator = len(bucket["mention_denominator_response_ids"])
        if denominator <= 0 or not bucket["has_target_mention_input"]:
            return None
        return round(
            len(bucket["target_mention_response_ids"]) / denominator,
            4,
        )
    if metric == "sov":
        all_mentions = bucket["all_mentions"]
        if (
            all_mentions <= 0
            or all_mentions <= bucket["target_mentions"]
            or not bucket["has_target_mention_input"]
            or not bucket["has_all_mention_input"]
        ):
            return None
        return round(float(bucket["target_mentions"]) / all_mentions, 4)
    if metric == "rank":
        ranks = bucket["ranks"]
        if not ranks:
            return None
        return round(sum(ranks) / len(ranks), 4)
    if metric == "sentiment":
        scores = bucket["sentiment_scores"]
        if not scores:
            return None
        if (
            bucket["has_target_mention_input"]
            and bucket["target_mentions"] > 0
            and bucket["sentiment_label_count"] <= 0
        ):
            return None
        return round(sum(scores) / len(scores), 4)
    if metric == "citation":
        # Issue #948 follow-up: citation_share = target_attributed /
        # eligible_project citations. Previous implementation used
        # `(any target-mentioning response has any citation) /
        # (target-mentioning responses)`, which collapsed to 100% the moment
        # the LLM emitted any citations because the COUNT(*) denominator
        # subquery in admin_facts (queries.py:407-410) was unfiltered by
        # `mention_id`. Switch to the proper attributed/total ratio that
        # matches `metric_formula_evidence.citation.numerator_name /
        # denominator_name` (target_attributed_citations /
        # eligible_project_citations).
        if not bucket["has_citation_input"]:
            return None
        total_citations = int(bucket["citation_count_sum"])
        if total_citations <= 0:
            # Nothing to divide by — guard the no-fallback contract.
            return None
        target_citations = int(bucket["target_citation_count_sum"])
        return round(target_citations / total_citations, 4)
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
    buckets: dict[str, _FactMetricBucket] = {}
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
                "response_ids": set[int](),
                "mention_denominator_response_ids": set[int](),
                "target_mention_response_ids": set[int](),
                "citation_target_response_ids": set[int](),
                "has_citation_input": False,
                "has_target_mention_input": False,
                "has_all_mention_input": False,
                "target_mentions": 0,
                "all_mentions": 0,
                "ranks": [],
                "sentiment_scores": [],
                "sentiment_label_count": 0,
                "cited_target_response_ids": set[int](),
                "target_citation_count_sum": 0,
                "citation_count_sum": 0,
            },
        )
        bucket["response_ids"].add(response_id)
        target_mentions = _fact_target_mention_count(row)
        all_mentions = _fact_all_mention_count(row, target_mentions)
        if row.get("target_mention_count") is not None:
            bucket["has_target_mention_input"] = True
        if row.get("all_mention_count") is not None:
            bucket["has_all_mention_input"] = True
        if row.get("citation_count") is not None:
            bucket["has_citation_input"] = True
        bucket["target_mentions"] += target_mentions
        bucket["all_mentions"] += all_mentions
        if target_mentions > 0:
            bucket["citation_target_response_ids"].add(response_id)
        if _is_non_branded_row(row):
            bucket["mention_denominator_response_ids"].add(response_id)
            if target_mentions > 0:
                bucket["target_mention_response_ids"].add(response_id)
        rank = _as_int(row.get("min_position_rank") or row.get("target_brand_rank"))
        if rank is not None:
            bucket["ranks"].append(float(rank))
        sentiment = (
            _as_float(row.get("target_sentiment_score"))
            if target_mentions > 0
            else _as_float(row.get("sentiment_score"))
        )
        if sentiment is not None:
            bucket["sentiment_scores"].append(sentiment)
        bucket["sentiment_label_count"] += (
            int(row.get("positive_mentions") or 0)
            + int(row.get("neutral_mentions") or 0)
            + int(row.get("negative_mentions") or 0)
        )
        if target_mentions > 0 and int(row.get("citation_count") or 0) > 0:
            bucket["cited_target_response_ids"].add(response_id)
        # Issue #948 follow-up: track per-day attributed and total citation
        # sums so citation_share = target_attributed / eligible_project,
        # not the previous "any target-mentioning response has any citation"
        # ratio which was 100% whenever the LLM emitted citations on a
        # target-mentioning response. Total per response is bounded by
        # COUNT(*) from citation_sources; target is the subset whose
        # `mention_id` links to a brand_mention for the target brand.
        bucket["citation_count_sum"] += int(row.get("citation_count") or 0)
        bucket["target_citation_count_sum"] += int(row.get("target_citation_count") or 0)

    out_series: list[MetricSeries] = []
    for metric in requested:
        points: list[MetricSeriesPoint] = []
        for day in sorted(buckets):
            value = _fact_metric_value(metric, buckets[day])
            if value is None:
                continue
            points.append(MetricSeriesPoint(date=date.fromisoformat(day), value=value))
        out_series.append(MetricSeries(metric=metric, points=points))

    out_series = _decorate_metric_series(out_series)
    has_data = any(series.points for series in out_series)
    context = await build_contract_context(
        session,
        project,
        brand_id=brand_id,
        from_date=from_d,
        to_date=to_d,
        has_data=has_data,
        base_state="ok" if has_data else "empty",
        source_provenance=["admin_facts"],
    )
    explicit_primary_brand = (
        brand_id_override is not None and brand_id_override == project.primary_brand_id
    )
    if (
        explicit_primary_brand
        and context.evidence_counts.get("geo_score_daily_rows", 0) <= 0
        and not context.metric_formula_evidence
    ):
        context = context.model_copy(
            update={
                "state": "partial",
                "state_reason": "partial_analyzer_data",
                "formula_status": FORMULA_PARTIAL_STATUS,
                "formula_diagnostics": formula_diagnostics_for(
                    FORMULA_PARTIAL_STATUS,
                    missing_inputs=[
                        ANALYZER_FACT_PACKAGE_V3_SOURCE,
                        ANALYZER_FACT_PACKAGE_SOURCE,
                    ],
                ),
                "missing_inputs": _unique(
                    [
                        *context.missing_inputs,
                        ANALYZER_FACT_PACKAGE_V3_SOURCE,
                        ANALYZER_FACT_PACKAGE_SOURCE,
                    ]
                ),
                "missing_sources": _unique(
                    [
                        *context.missing_sources,
                        ANALYZER_FACT_PACKAGE_V3_SOURCE,
                        ANALYZER_FACT_PACKAGE_SOURCE,
                    ]
                ),
                "missing_reasons": _unique(
                    [*context.missing_reasons, "missing_analyzer_fact_packages"]
                ),
                "metric_formula_evidence": _missing_analyzer_evidence(requested),
            }
        )
    series_missing_inputs = _series_contract_missing_inputs(
        out_series,
        context_with_sov_competitive_gap(context),
        evidence_source="admin_facts",
    )
    if series_missing_inputs:
        context = context_with_sov_competitive_gap(context)
    if series_missing_inputs and context.formula_status == FORMULA_OK_STATUS:
        context = await build_contract_context(
            session,
            project,
            brand_id=brand_id,
            from_date=from_d,
            to_date=to_d,
            has_data=has_data,
            base_state="partial",
            base_state_reason="missing_formula_inputs",
            base_missing_inputs=series_missing_inputs,
            base_missing_sources=series_missing_inputs,
            formula_status=FORMULA_MISSING_INPUTS_STATUS,
        )
        context = context_with_sov_competitive_gap(context)
    elif (
        context.formula_status == FORMULA_OK_STATUS
        and context.evidence_counts.get("geo_score_daily_rows", 0) <= 0
    ):
        context = await build_contract_context(
            session,
            project,
            brand_id=brand_id,
            from_date=from_d,
            to_date=to_d,
            has_data=has_data,
            base_state="partial",
            base_state_reason="formula_pending_upstream",
            formula_status=FORMULA_PENDING_STATUS,
            source_provenance=["admin_facts"],
        )
        context = context_with_sov_competitive_gap(context)
    else:
        context = context_with_sov_competitive_gap(context)
    out_series = _apply_metric_series_contract(
        out_series,
        context,
        evidence_source="admin_facts",
    )
    out = MetricsOut(
        project_id=project.id,
        brand_id=brand_id,
        period=_period(from_d, to_d),
        engines=list(filters.engines) if filters.engines else None,
        series=out_series,
        state="ok" if has_data else "empty",
    )
    return out.model_copy(update=context_update(context))


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
        out = MetricsOut(
            project_id=project.id,
            brand_id=None,
            period=_period(from_d, to_d),
            engines=engines,
            series=_decorate_metric_series([MetricSeries(metric=m, points=[]) for m in requested]),
            state="empty",
        )
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
        return out.model_copy(update=context_update(context))

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
        return fact_metrics

    out_series: list[MetricSeries] = []
    score_component_metrics: set[str] = set()
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
        if metric == "sentiment" and rows:
            score_component_metrics.add(metric)
        points = []
        for r in rows:
            if r[1] is None:
                continue
            d = r[0]
            if isinstance(d, datetime):
                d = d.date()
            elif isinstance(d, str):
                d = date.fromisoformat(d)
            points.append(MetricSeriesPoint(date=d, value=_normalize_metric_value(metric, r[1])))
        out_series.append(MetricSeries(metric=metric, points=points))

    out_series = _decorate_metric_series(
        out_series,
        score_component_metrics=score_component_metrics,
    )
    has_data = any(s.points for s in out_series)
    out = MetricsOut(
        project_id=project.id,
        brand_id=primary_brand_id,
        period=_period(from_d, to_d),
        engines=engines,
        series=out_series,
        state="ok" if has_data else "empty",
    )
    context = await build_contract_context(
        session,
        project,
        brand_id=primary_brand_id,
        from_date=from_d,
        to_date=to_d,
        has_data=has_data,
        base_state=out.state,
    )
    context = context_with_sov_competitive_gap(context)
    series_missing_inputs = _series_contract_missing_inputs(out_series, context)
    if series_missing_inputs and context.formula_status == FORMULA_OK_STATUS:
        context = await build_contract_context(
            session,
            project,
            brand_id=primary_brand_id,
            from_date=from_d,
            to_date=to_d,
            has_data=has_data,
            base_state="partial",
            base_state_reason="missing_formula_inputs",
            base_missing_inputs=series_missing_inputs,
            base_missing_sources=series_missing_inputs,
            formula_status=FORMULA_MISSING_INPUTS_STATUS,
        )
        context = context_with_sov_competitive_gap(context)
    out = out.model_copy(update={"series": _apply_metric_series_contract(out_series, context)})
    return out.model_copy(update=context_update(context))


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
    state = "ok" if items and sum(item.mention_count for item in items) else "empty"
    out = TopicsOut(
        project_id=project.id,
        items=items,
        total=len(items),
        state=state,
        state_reason="data_available" if state == "ok" else "no_topic_data",
        evidence_count=sum(item.mention_count for item in items),
    )
    today = date.today()
    context = await build_contract_context(
        session,
        project,
        brand_id=project.primary_brand_id,
        from_date=today - timedelta(days=DEFAULT_WINDOW_DAYS - 1),
        to_date=today,
        has_data=state == "ok",
        base_state=state,
        base_missing_inputs=["topic_score_daily"] if state != "ok" else None,
        source_provenance=["project_topic_pins", "topic_score_daily"],
    )
    return out.model_copy(update=context_update(context))


# ─── /sentiment ────────────────────────────────────────────────────
def _empty_sentiment_distribution() -> SentimentDistribution:
    return SentimentDistribution(
        positive_count=0,
        neutral_count=0,
        negative_count=0,
        positive_pct=0.0,
        neutral_pct=0.0,
        negative_pct=0.0,
        avg_sentiment_score=0.0,
    )


def _fact_response_day_map(rows: list[dict[str, Any]]) -> dict[int, date]:
    response_days: dict[int, date] = {}
    for row in rows:
        rid = _as_int(row.get("response_id"))
        if rid is None or rid in response_days:
            continue
        day_key = _date_key(
            row.get("response_created_at")
            or row.get("query_finished_at")
            or row.get("query_created_at")
        )
        if day_key is not None:
            response_days[rid] = date.fromisoformat(day_key)
    return response_days


async def _sentiment_driver_rows_for_responses(
    session: AsyncSession,
    response_ids: list[int],
) -> tuple[list[SentimentKeywordRow], list[SentimentDriverRow], int]:
    if not response_ids:
        return [], [], 0
    driver_rows = (
        await session.execute(
            select(
                SentimentDriver.driver_text,
                SentimentDriver.polarity,
                SentimentDriver.category,
                func.count().label("cnt"),
                func.avg(SentimentDriver.strength).label("avg_strength"),
            )
            .where(
                and_(
                    SentimentDriver.response_id.in_(response_ids),
                    SentimentDriver.driver_text.isnot(None),
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
    ).all()
    top_keywords = [
        SentimentKeywordRow(
            keyword=row[0],
            polarity=row[1] or "neutral",
            count=int(row[3] or 0),
            avg_strength=round(row[4], 2) if row[4] is not None else None,
        )
        for row in driver_rows
    ]
    top_drivers = [
        SentimentDriverRow(
            driver_text=row[0],
            polarity=row[1] or "neutral",
            category=row[2],
            count=int(row[3] or 0),
            avg_strength=round(row[4], 2) if row[4] is not None else None,
        )
        for row in driver_rows
    ]
    driver_count = sum(item.count for item in top_drivers)
    return top_keywords, top_drivers, driver_count


async def _sentiment_from_admin_facts(
    session: AsyncSession,
    project: Project,
    *,
    brand_id: int,
    from_d: date,
    to_d: date,
) -> SentimentOut | None:
    rows = await _fact_rows(
        session,
        project,
        filters=AnalysisFilters(from_date=from_d, to_date=to_d),
        brand_id_override=brand_id,
    )
    response_days = _fact_response_day_map(rows)
    if not response_days:
        return None

    score_response_ids = {
        _as_int(row.get("response_id"))
        for row in rows
        if _as_int(row.get("response_id")) is not None
        and (
            _as_float(row.get("target_sentiment_score")) is not None
            or _as_float(row.get("sentiment_score")) is not None
        )
    }
    score_response_ids = {rid for rid in score_response_ids if rid is not None}
    if not score_response_ids:
        return None

    brand_filter = await brand_mention_match_condition(session, brand_id)
    sentiment_rows = (
        await session.execute(
            select(
                BrandMention.response_id,
                func.lower(BrandMention.sentiment).label("sentiment"),
                BrandMention.sentiment_score,
            ).where(
                and_(
                    BrandMention.response_id.in_(sorted(response_days)),
                    brand_filter,
                    BrandMention.sentiment_score.isnot(None),
                    func.lower(BrandMention.sentiment).in_(["positive", "neutral", "negative"]),
                )
            )
        )
    ).all()

    if not sentiment_rows:
        missing_inputs = ["brand_mentions.sentiment_score", "brand_mentions.sentiment"]
        return SentimentOut(
            project_id=project.id,
            brand_id=brand_id,
            period=_period(from_d, to_d),
            distribution=_empty_sentiment_distribution(),
            trend_30d=[],
            top_keywords=[],
            top_drivers=[],
            state="partial",
            state_reason="missing_formula_inputs",
            evidence_count=len(score_response_ids),
            missing_inputs=missing_inputs,
            missing_sources=missing_inputs,
            evidence_counts={
                "admin_fact_response_count": len(score_response_ids),
                "sentiment_label_count": 0,
            },
            formula_status=FORMULA_MISSING_INPUTS_STATUS,
            formula_diagnostics=formula_diagnostics_for(
                FORMULA_MISSING_INPUTS_STATUS,
                missing_inputs=missing_inputs,
            ),
            source_provenance=["brand_mentions", "response_analyses", "admin_facts"],
        )

    top_keywords, top_drivers, driver_count = await _sentiment_driver_rows_for_responses(
        session,
        sorted(response_days),
    )
    pos = neu = neg = 0
    total_score = 0.0
    score_count = 0
    by_day: dict[date, dict[str, Any]] = {}
    for response_id, sentiment, score in sentiment_rows:
        cnt_score = _as_float(score)
        if sentiment == "positive":
            pos += 1
        elif sentiment == "negative":
            neg += 1
        elif sentiment == "neutral":
            neu += 1
        if cnt_score is not None:
            total_score += cnt_score
            score_count += 1
        day = response_days.get(int(response_id))
        if day is None:
            continue
        bucket = by_day.setdefault(day, {"pos": 0, "neg": 0, "total": 0, "scores": []})
        bucket["total"] += 1
        if sentiment == "positive":
            bucket["pos"] += 1
        elif sentiment == "negative":
            bucket["neg"] += 1
        if cnt_score is not None:
            bucket["scores"].append(cnt_score)

    total = pos + neu + neg
    trend = [
        SentimentTrendPoint(
            date=day,
            positive_pct=round(bucket["pos"] / bucket["total"] * 100, 1),
            negative_pct=round(bucket["neg"] / bucket["total"] * 100, 1),
            avg_score=round(sum(bucket["scores"]) / len(bucket["scores"]), 3)
            if bucket["scores"]
            else 0.0,
        )
        for day, bucket in sorted(by_day.items())
        if bucket["total"]
    ]
    missing_inputs = [] if driver_count else ["sentiment_drivers.source_quote"]
    formula_status = FORMULA_OK_STATUS if driver_count else FORMULA_MISSING_INPUTS_STATUS
    return SentimentOut(
        project_id=project.id,
        brand_id=brand_id,
        period=_period(from_d, to_d),
        distribution=SentimentDistribution(
            positive_count=pos,
            neutral_count=neu,
            negative_count=neg,
            positive_pct=round(pos / total * 100, 1) if total else 0.0,
            neutral_pct=round(neu / total * 100, 1) if total else 0.0,
            negative_pct=round(neg / total * 100, 1) if total else 0.0,
            avg_sentiment_score=round(total_score / score_count, 3) if score_count else 0.0,
        ),
        trend_30d=trend,
        top_keywords=top_keywords,
        top_drivers=top_drivers,
        state="ok" if not missing_inputs else "partial",
        state_reason="data_available" if not missing_inputs else "missing_formula_inputs",
        evidence_count=total,
        missing_inputs=missing_inputs,
        missing_sources=missing_inputs,
        evidence_counts={
            "admin_fact_response_count": len(response_days),
            "sentiment_label_count": total,
            "sentiment_driver_count": driver_count,
        },
        formula_status=formula_status,
        formula_diagnostics=formula_diagnostics_for(
            formula_status,
            missing_inputs=missing_inputs,
        ),
        source_provenance=[
            "brand_mentions",
            "response_analyses",
            "sentiment_drivers",
            "admin_facts",
        ],
    )


async def get_sentiment(
    session: AsyncSession,
    project: Project,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    brand_id_override: int | None = None,
) -> SentimentOut:
    from_d, to_d = _resolve_window(from_date, to_date)

    brand_id = brand_id_override if brand_id_override is not None else project.primary_brand_id
    if brand_id is None:
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
            state_reason="no_primary_brand",
            evidence_count=0,
        )

    if await _has_admin_chain(session):
        admin_sentiment = await _sentiment_from_admin_facts(
            session,
            project,
            brand_id=brand_id,
            from_d=from_d,
            to_d=to_d,
        )
        if admin_sentiment is not None:
            context = await build_contract_context(
                session,
                project,
                brand_id=brand_id,
                from_date=from_d,
                to_date=to_d,
                has_data=admin_sentiment.evidence_count > 0,
                base_state=admin_sentiment.state,
                base_missing_inputs=admin_sentiment.missing_inputs,
                source_provenance=admin_sentiment.source_provenance
                or ["brand_mentions", "response_analyses", "admin_facts"],
            )
            update = context_update(context)
            if not context.metric_formula_evidence:
                missing_inputs = list(admin_sentiment.missing_inputs)
                missing_sources = list(admin_sentiment.missing_sources)
                missing_reasons = list(admin_sentiment.missing_reasons)
                formula_status = admin_sentiment.formula_status
                formula_diagnostics = admin_sentiment.formula_diagnostics
                if (
                    context.evidence_counts.get("geo_score_daily_rows", 0) <= 0
                    and context.evidence_counts.get("response_analysis_count", 0) > 0
                ):
                    missing_inputs.extend(
                        [
                            ANALYZER_FACT_PACKAGE_V3_SOURCE,
                            ANALYZER_FACT_PACKAGE_SOURCE,
                        ]
                    )
                    missing_sources.extend(
                        [
                            ANALYZER_FACT_PACKAGE_V3_SOURCE,
                            ANALYZER_FACT_PACKAGE_SOURCE,
                        ]
                    )
                    missing_reasons.append("missing_analyzer_fact_packages")
                    formula_status = FORMULA_PARTIAL_STATUS
                    formula_diagnostics = formula_diagnostics_for(
                        FORMULA_PARTIAL_STATUS,
                        missing_inputs=missing_inputs,
                    )
                update.update(
                    {
                        "state": admin_sentiment.state,
                        "state_reason": admin_sentiment.state_reason,
                        "missing_inputs": _unique(missing_inputs),
                        "missing_sources": _unique(missing_sources),
                        "missing_reasons": _unique(missing_reasons),
                        "formula_status": formula_status,
                        "formula_diagnostics": formula_diagnostics,
                    }
                )
            return admin_sentiment.model_copy(update=update)

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
        total_for_day = int(r[3] or 0)
        if total_for_day <= 0:
            continue
        trend.append(
            SentimentTrendPoint(
                date=d,
                positive_pct=round((r[1] or 0) / total_for_day * 100, 1),
                negative_pct=round((r[2] or 0) / total_for_day * 100, 1),
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
    state = "ok" if has_data else "empty"
    out = SentimentOut(
        project_id=project.id,
        brand_id=brand_id,
        period=_period(from_d, to_d),
        distribution=dist,
        trend_30d=trend,
        top_keywords=top_keywords,
        top_drivers=top_drivers,
        state=state,
        state_reason="data_available" if has_data else "no_sentiment_data",
        evidence_count=total,
    )
    context = await build_contract_context(
        session,
        project,
        brand_id=brand_id,
        from_date=from_d,
        to_date=to_d,
        has_data=has_data,
        base_state=state,
        base_missing_inputs=["brand_mentions.sentiment_score"] if not has_data else None,
        source_provenance=["brand_mentions", "sentiment_drivers"],
    )
    return out.model_copy(update=context_update(context))


# ─── /citations ────────────────────────────────────────────────────
async def get_citations(
    session: AsyncSession,
    project: Project,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    brand_id_override: int | None = None,
    page_size: int = 50,
) -> CitationsOut:
    from_d, to_d = _resolve_window(from_date, to_date)

    brand_id = brand_id_override if brand_id_override is not None else project.primary_brand_id
    if brand_id is None:
        return CitationsOut(
            project_id=project.id,
            brand_id=None,
            period=_period(from_d, to_d),
            items=[],
            next_cursor=None,
            total=0,
            by_domain_top=[],
            state="empty",
            state_reason="no_primary_brand",
            evidence_count=0,
        )

    if await _has_admin_chain(session):
        fact_rows = await _fact_rows(
            session,
            project,
            filters=AnalysisFilters(from_date=from_d, to_date=to_d),
            brand_id_override=brand_id,
        )
        response_days = _fact_response_day_map(fact_rows)
        if response_days:
            brand_filter = await brand_mention_match_condition(session, brand_id)
            target_mentions = (
                select(BrandMention.id)
                .where(
                    and_(
                        BrandMention.response_id.in_(sorted(response_days)),
                        brand_filter,
                    )
                )
                .scalar_subquery()
            )
            stmt = (
                select(CitationSource)
                .where(CitationSource.mention_id.in_(target_mentions))
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
            stmt_dom = (
                select(
                    CitationSource.domain,
                    func.count().label("cnt"),
                    func.max(DomainAuthority.tier).label("tier"),
                )
                .outerjoin(DomainAuthority, DomainAuthority.domain == CitationSource.domain)
                .where(
                    and_(
                        CitationSource.mention_id.in_(target_mentions),
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
            total = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(CitationSource)
                        .where(CitationSource.mention_id.in_(target_mentions))
                    )
                ).scalar_one()
                or 0
            )
            state = "ok" if total else "empty"
            missing_inputs = [] if total else ["citation_sources"]
            formula_status = FORMULA_OK_STATUS if total else FORMULA_MISSING_INPUTS_STATUS
            out = CitationsOut(
                project_id=project.id,
                brand_id=brand_id,
                period=_period(from_d, to_d),
                items=items,
                next_cursor=str(items[-1].citation_id) if has_more and items else None,
                total=total,
                by_domain_top=by_domain,
                state=state if total else "partial",
                state_reason="data_available" if total else "missing_formula_inputs",
                evidence_count=total if total else len(response_days),
                missing_inputs=missing_inputs,
                missing_sources=missing_inputs,
                evidence_counts={
                    "admin_fact_response_count": len(response_days),
                    "citation_source_count": total,
                },
                formula_status=formula_status,
                formula_diagnostics=formula_diagnostics_for(
                    formula_status,
                    missing_inputs=missing_inputs,
                ),
                metric_definitions={
                    "citation_rate": metric_definition("citation_rate"),
                    "citation_share": metric_definition("citation"),
                },
                selected_filters={
                    "project_id": project.id,
                    "brand_id": brand_id,
                    "date_range": _period(from_d, to_d),
                },
                source_provenance=["citation_sources", "brand_mentions", "admin_facts"],
            )
            context = await build_contract_context(
                session,
                project,
                brand_id=brand_id,
                from_date=from_d,
                to_date=to_d,
                has_data=total > 0,
                base_state=out.state,
                base_missing_inputs=out.missing_inputs,
                source_provenance=out.source_provenance,
            )
            if (
                context.formula_status == FORMULA_OK_STATUS
                and context.evidence_counts.get("geo_score_daily_rows", 0) <= 0
                and not context.metric_formula_evidence
                and context.evidence_counts.get("response_analysis_count", 0) > 0
            ):
                context = context.model_copy(
                    update={
                        "state": "partial",
                        "state_reason": "partial_analyzer_data",
                        "formula_status": FORMULA_PARTIAL_STATUS,
                        "formula_diagnostics": formula_diagnostics_for(
                            FORMULA_PARTIAL_STATUS,
                            missing_inputs=[
                                ANALYZER_FACT_PACKAGE_V3_SOURCE,
                                ANALYZER_FACT_PACKAGE_SOURCE,
                            ],
                        ),
                        "missing_inputs": _unique(
                            [
                                *context.missing_inputs,
                                ANALYZER_FACT_PACKAGE_V3_SOURCE,
                                ANALYZER_FACT_PACKAGE_SOURCE,
                            ]
                        ),
                        "missing_sources": _unique(
                            [
                                *context.missing_sources,
                                ANALYZER_FACT_PACKAGE_V3_SOURCE,
                                ANALYZER_FACT_PACKAGE_SOURCE,
                            ]
                        ),
                        "missing_reasons": _unique(
                            [*context.missing_reasons, "missing_analyzer_fact_packages"]
                        ),
                        "metric_formula_evidence": _missing_analyzer_evidence(["citation"]),
                    }
                )
            return out.model_copy(update=context_update(context))

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

    state = "ok" if total else "empty"
    out = CitationsOut(
        project_id=project.id,
        brand_id=brand_id,
        period=_period(from_d, to_d),
        items=items,
        next_cursor=str(items[-1].citation_id) if has_more and items else None,
        total=total,
        by_domain_top=by_domain,
        state=state,
        state_reason="data_available" if total else "no_citation_data",
        evidence_count=total,
        metric_definitions={
            "citation_rate": metric_definition("citation_rate"),
            "citation_share": metric_definition("citation"),
        },
    )
    context = await build_contract_context(
        session,
        project,
        brand_id=brand_id,
        from_date=from_d,
        to_date=to_d,
        has_data=bool(total),
        base_state=state,
        base_missing_inputs=["citation_sources"] if not total else None,
        source_provenance=["citation_sources", "brand_mentions"],
    )
    return out.model_copy(update=context_update(context))


# Minor service: ResponseAnalysis-based mention rate for /sentiment trend
# (kept here for interest; not exposed in DTO above)
__all__ = [
    "ResponseAnalysis",  # re-export for downstream MCP tools
    "get_citations",
    "get_metrics",
    "get_sentiment",
    "get_topics",
]
