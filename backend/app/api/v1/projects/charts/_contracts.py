"""Contract wrapper layer for chart endpoints.

Translates `AnalyticsContractContext` into per-chart `state` / `formula_status` /
`metric_formula_evidence` / `missing_*` fields. Extracted from
`_charts_service.py` as phase 2 of the split (Epic #885, design #886).

Public surface (re-exported by `charts/__init__.py`):
- `_chart_contract_update` — build the contract-fields dict for a chart output
- `_with_chart_contract` — generic wrapper applying `_chart_contract_update`
  to a Pydantic chart model
- `_contract_metric_blocked` — given a contract update, check if a specific
  metric is blocked
- `_chart_has_data` / `_metric_evidence_key` / `_metric_evidence_dict` /
  `_missing_analyzer_metric_evidence` — supporting helpers used by the
  contract layer and by per-domain `_with_*_contract` wrappers in sibling
  modules
"""

from __future__ import annotations

from datetime import date
from typing import Any

from genpano_models import Project
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._analytics_contract import (
    ANALYZER_FACT_PACKAGE_SOURCE,
    ANALYZER_FACT_PACKAGE_V3_SOURCE,
    FORMULA_MISSING_INPUTS_STATUS,
    FORMULA_NO_EVIDENCE_STATUS,
    FORMULA_OK_STATUS,
    FORMULA_PARTIAL_STATUS,
    build_contract_context,
    formula_diagnostics_for,
    metric_blocking_inputs_from_evidence,
    metric_formula_status,
    metric_missing_inputs,
)
from app.api.v1.projects.charts._common import _unique


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
            "source_tables": [ANALYZER_FACT_PACKAGE_V3_SOURCE, ANALYZER_FACT_PACKAGE_SOURCE],
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
    require_analyzer_package: bool = False,
    allow_geo_score_daily_without_analyzer: bool = False,
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
    has_aggregate_metric_rows = context.evidence_counts.get("geo_score_daily_rows", 0) > 0
    use_aggregate_contract = (
        allow_geo_score_daily_without_analyzer and has_aggregate_metric_rows and not evidence
    )
    missing_inputs: list[str] = [] if use_aggregate_contract else list(context.missing_inputs)
    missing_reasons: list[str] = [] if use_aggregate_contract else list(context.missing_reasons)
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

    if (
        require_analyzer_package
        and not evidence
        and has_data
        and not (allow_geo_score_daily_without_analyzer and has_aggregate_metric_rows)
    ):
        evidence = _missing_analyzer_metric_evidence(metric_keys)
        missing_inputs.extend([ANALYZER_FACT_PACKAGE_V3_SOURCE, ANALYZER_FACT_PACKAGE_SOURCE])
        missing_reasons.append("missing_analyzer_fact_packages")

    if not evidence and not require_analyzer_package:
        return {
            "metric_formula_evidence": evidence,
            "evidence_counts": {
                **getattr(out, "evidence_counts", {}),
                **context.evidence_counts,
            },
            "selected_filters": context.selected_filters,
            "source_provenance": context.source_provenance,
        }

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
                ANALYZER_FACT_PACKAGE_V3_SOURCE,
                ANALYZER_FACT_PACKAGE_SOURCE,
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
    require_analyzer_package: bool = False,
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
        require_analyzer_package=require_analyzer_package,
    )
    return out.model_copy(update=update) if update else out


def _contract_metric_blocked(update: dict[str, Any], metric_key: str) -> bool:
    evidence = update.get("metric_formula_evidence") or {}
    evidence_key = _metric_evidence_key(metric_key)
    value = evidence.get(evidence_key)
    return bool(
        metric_blocking_inputs_from_evidence(
            metric_key,
            value if isinstance(value, dict) else None,
        )
    )


def _metric_evidence_allows_partial_data(
    update: dict[str, Any], metric_key: str
) -> bool:
    """Return True when the contract update has `formula_status: partial`
    backed by real analyzer evidence so chart points/segments/items should
    survive even though `_contract_metric_blocked` flagged the metric.

    Issue #1002: chart wrappers (`_with_authority_trend_contract`,
    `_with_citation_composition_contract`, sentiment wrappers) cleared
    their data the moment `_contract_metric_blocked` returned True.
    That contradicts the contract-loosening already applied at the
    KPI / series / frontend layers (`_kpi_has_real_evidence` from #948,
    `hasUsableMetricEvidence` from #960), where `formula_status: partial`
    is treated as trustworthy because the value was computed from real
    analyzer evidence and only auxiliary quality flags remain (e.g.
    `unresolved_citation_attribution` while `attributed_count > 0`,
    `missing_sentiment_driver_quote` while `score_count > 0`).

    Excludes the synthetic-partial case that `build_contract_context`
    emits when admin chain rows exist but no analyzer fact packages do.
    There the only `reason_code` is `missing_analyzer_fact_packages`
    and issue #603 specifically requires the chart to clear (no analyzer
    rollup = no trustworthy data).
    """
    evidence = update.get("metric_formula_evidence") or {}
    evidence_key = _metric_evidence_key(metric_key)
    value = evidence.get(evidence_key)
    if not isinstance(value, dict):
        return False
    status = str(value.get("formula_status") or "")
    if status != FORMULA_PARTIAL_STATUS:
        return False
    reasons = {str(r) for r in (value.get("reason_codes") or [])}
    return "missing_analyzer_fact_packages" not in reasons


def _metric_evidence_dict(evidence: dict[str, Any], key: str) -> dict[str, Any] | None:
    value = evidence.get(key)
    return value if isinstance(value, dict) else None
