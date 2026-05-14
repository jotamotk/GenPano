"""Contracts sub-package — split from the legacy `_analytics_contract.py`
god-module.

This package is being filled incrementally; see Epic #885 and tracking issue
#888. Public surface re-exported here for backwards-compatible imports.
"""

from __future__ import annotations

from app.api.v1.projects.contracts.builder import (
    _analyzer_fact_rollup,
    _competitor_ids,
    _empty_evidence,
    _first_class_analyzer_fact_rollup,
    _latest_runs_by_response,
    _quality_flag_reasons_by_metric,
    build_contract_context,
    context_dump,
    context_update,
)
from app.api.v1.projects.contracts.constants import (
    _BLOCKING_REASON_CODES,
    _COMMON_METRIC_BLOCKING_REASONS,
    _METRIC_BLOCKING_REASONS,
    ANALYSIS_MISSING_REASON,
    ANALYZER_FACT_PACKAGE_SOURCE,
    ANALYZER_FACT_PACKAGE_V3_SOURCE,
    FORMULA_MISSING_INPUTS_STATUS,
    FORMULA_NO_EVIDENCE_STATUS,
    FORMULA_OK_STATUS,
    FORMULA_PARTIAL_STATUS,
    FORMULA_PENDING_SOURCE,
    FORMULA_PENDING_STATUS,
    MISSING_PROJECT_BRAND_BINDING_REASON,
    NO_AGGREGATE_ROWS_REASON,
    PROJECT_UNBOUND_REASON,
)
from app.api.v1.projects.contracts.definitions import (
    formula_diagnostics_for,
    metric_definition,
    metric_definitions,
)
from app.api.v1.projects.contracts.evidence import (
    _blocking_metric_evidence,
    _evidence_source_tables,
    _metric_evidence_template,
    _package_source_tables,
)
from app.api.v1.projects.contracts.format import (
    percent_display,
    ratio_decimal,
    score_0_100,
)
from app.api.v1.projects.contracts.metrics import (
    metric_blocking_inputs_from_evidence,
    metric_evidence_for,
    metric_formula_status,
    metric_missing_inputs,
)
from app.api.v1.projects.contracts.models import (
    AnalyticsContractContext,
    DataFreshness,
    FormulaDiagnostics,
    IdentityDiagnostics,
    MetricDefinition,
    MetricValue,
    ProjectScope,
    ValueRange,
)
from app.api.v1.projects.contracts.package import (
    _as_package,
    _as_v3_package,
    _json_int,
    _merge_status,
    _package_date_in_window,
    _package_reason_codes,
    _package_response_ids,
    _package_target_brand_id,
    _repair_entries,
    _status_from_package,
)
from app.api.v1.projects.contracts.queries import (
    _pinned_topic_response_ids,
    _project_eligible_response_ids,
    _target_response_ids,
)
from app.api.v1.projects.contracts.rollups import (
    _rollup_citations,
    _rollup_coverage,
    _rollup_pano_geo,
    _rollup_sentiment,
    _rollup_sov,
)

__all__ = [
    "ANALYSIS_MISSING_REASON",
    "ANALYZER_FACT_PACKAGE_SOURCE",
    "ANALYZER_FACT_PACKAGE_V3_SOURCE",
    "FORMULA_MISSING_INPUTS_STATUS",
    "FORMULA_NO_EVIDENCE_STATUS",
    "FORMULA_OK_STATUS",
    "FORMULA_PARTIAL_STATUS",
    "FORMULA_PENDING_SOURCE",
    "FORMULA_PENDING_STATUS",
    "MISSING_PROJECT_BRAND_BINDING_REASON",
    "NO_AGGREGATE_ROWS_REASON",
    "PROJECT_UNBOUND_REASON",
    "_BLOCKING_REASON_CODES",
    "_COMMON_METRIC_BLOCKING_REASONS",
    "_METRIC_BLOCKING_REASONS",
    "AnalyticsContractContext",
    "DataFreshness",
    "FormulaDiagnostics",
    "IdentityDiagnostics",
    "MetricDefinition",
    "MetricValue",
    "ProjectScope",
    "ValueRange",
    "_analyzer_fact_rollup",
    "_as_package",
    "_as_v3_package",
    "_blocking_metric_evidence",
    "_competitor_ids",
    "_empty_evidence",
    "_evidence_source_tables",
    "_first_class_analyzer_fact_rollup",
    "_json_int",
    "_latest_runs_by_response",
    "_merge_status",
    "_metric_evidence_template",
    "_package_date_in_window",
    "_package_reason_codes",
    "_package_response_ids",
    "_package_source_tables",
    "_package_target_brand_id",
    "_pinned_topic_response_ids",
    "_project_eligible_response_ids",
    "_quality_flag_reasons_by_metric",
    "_repair_entries",
    "_rollup_citations",
    "_rollup_coverage",
    "_rollup_pano_geo",
    "_rollup_sentiment",
    "_rollup_sov",
    "_status_from_package",
    "_target_response_ids",
    "build_contract_context",
    "context_dump",
    "context_update",
    "formula_diagnostics_for",
    "metric_blocking_inputs_from_evidence",
    "metric_definition",
    "metric_definitions",
    "metric_evidence_for",
    "metric_formula_status",
    "metric_missing_inputs",
    "percent_display",
    "ratio_decimal",
    "score_0_100",
]
