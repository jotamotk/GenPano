"""Metric-definition registry + formula diagnostics builder.

Phase 2 of splitting `_analytics_contract.py` (Epic #885, design #888).
"""

from __future__ import annotations

from app.api.v1.projects.contracts.constants import (
    FORMULA_MISSING_INPUTS_STATUS,
    FORMULA_NO_EVIDENCE_STATUS,
    FORMULA_OK_STATUS,
    FORMULA_PARTIAL_STATUS,
    FORMULA_PENDING_SOURCE,
    FORMULA_PENDING_STATUS,
)
from app.api.v1.projects.contracts.models import (
    FormulaDiagnostics,
    MetricDefinition,
    ValueRange,
)


def metric_definition(metric_key: str, *, display_percent: bool = False) -> MetricDefinition:
    source = "geo_score_daily"
    formula_status = FORMULA_OK_STATUS
    if metric_key in {"mention_rate", "avg_mention_rate"}:
        unit = "percent" if display_percent else "ratio"
        value_scale = "percent" if display_percent else "decimal"
        value_range = ValueRange(min=0.0, max=100.0 if display_percent else 1.0)
        return MetricDefinition(
            metric_key=metric_key,
            unit=unit,
            value_scale=value_scale,
            value_range=value_range,
            numerator_label="target brand mentioned eligible responses",
            denominator_label="eligible non-brand/category responses",
            source=source,
            formula_status=formula_status,
        )
    if metric_key in {"sov", "avg_sov"}:
        unit = "percent" if display_percent else "ratio"
        value_scale = "percent" if display_percent else "decimal"
        value_range = ValueRange(min=0.0, max=100.0 if display_percent else 1.0)
        return MetricDefinition(
            metric_key=metric_key,
            unit=unit,
            value_scale=value_scale,
            value_range=value_range,
            numerator_label="target brand mentioned competitive-set responses",
            denominator_label="competitive-set brand-mentioned responses",
            source=source,
            formula_status=formula_status,
        )
    if metric_key in {"citation", "citation_rate", "avg_citation_rate"}:
        return MetricDefinition(
            metric_key=metric_key,
            unit="ratio",
            value_scale="decimal",
            value_range=ValueRange(min=0.0, max=1.0),
            numerator_label="citation-backed brand mentions/responses",
            denominator_label="eligible brand mentions/responses",
            source=source,
            formula_status=formula_status,
        )
    if metric_key in {"geo_score", "avg_geo_score", "pano_score"}:
        return MetricDefinition(
            metric_key=metric_key,
            unit="score",
            value_scale="score_0_100",
            value_range=ValueRange(min=0.0, max=100.0),
            source=source,
            formula_status=formula_status,
        )
    if metric_key in {"rank", "avg_position_rank"}:
        return MetricDefinition(
            metric_key=metric_key,
            unit="rank",
            value_scale="ordinal",
            value_range=ValueRange(min=1.0, max=1000.0),
            numerator_label="mentioned responses only",
            denominator_label="mentioned responses only",
            source=source,
            formula_status=formula_status,
        )
    if metric_key == "avg_sentiment":
        return MetricDefinition(
            metric_key=metric_key,
            unit="score",
            value_scale="score_0_100",
            value_range=ValueRange(min=0.0, max=100.0),
            source="geo_score_daily.avg_sentiment",
            formula_status=formula_status,
        )
    if metric_key == "sentiment":
        return MetricDefinition(
            metric_key=metric_key,
            unit="score",
            value_scale="raw_-1_1",
            value_range=ValueRange(min=-1.0, max=1.0),
            source="response_analyses.sentiment_score",
            formula_status=formula_status,
        )
    return MetricDefinition(
        metric_key=metric_key,
        unit="value",
        value_scale="raw",
        value_range=ValueRange(min=0.0, max=1.0),
        source=source,
        formula_status=formula_status,
    )


def metric_definitions(
    metric_keys: list[str],
    *,
    display_percent: bool = False,
) -> dict[str, MetricDefinition]:
    return {key: metric_definition(key, display_percent=display_percent) for key in metric_keys}


def formula_diagnostics_for(
    status: str,
    *,
    missing_inputs: list[str] | None = None,
) -> FormulaDiagnostics:
    if status == FORMULA_OK_STATUS:
        return FormulaDiagnostics(status=FORMULA_OK_STATUS)
    if status == FORMULA_NO_EVIDENCE_STATUS:
        return FormulaDiagnostics(
            status=FORMULA_NO_EVIDENCE_STATUS,
            details=["No eligible evidence exists for the selected analytics filters."],
        )
    if status == FORMULA_MISSING_INPUTS_STATUS:
        return FormulaDiagnostics(
            status=FORMULA_MISSING_INPUTS_STATUS,
            pending_sources=list(missing_inputs or []),
            details=["Required formula inputs are missing; metric values are withheld."],
        )
    if status == FORMULA_PARTIAL_STATUS:
        return FormulaDiagnostics(
            status=FORMULA_PARTIAL_STATUS,
            pending_sources=list(missing_inputs or []),
            details=[
                "Analyzer fact packages are present, but at least one metric has "
                "partial or missing formula proof."
            ],
        )
    return FormulaDiagnostics(
        status=FORMULA_PENDING_STATUS,
        pending_sources=[FORMULA_PENDING_SOURCE],
        details=[
            "Upstream aggregate provenance is pending review for PRD mention-rate "
            "and SoV denominators.",
            "Treat geo_score_daily ratio values as formula-pending until analyzer/data "
            "PRs are patched.",
        ],
    )
