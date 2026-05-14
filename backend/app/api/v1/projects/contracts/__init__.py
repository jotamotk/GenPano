"""Contracts sub-package — split from the legacy `_analytics_contract.py`
god-module.

This package is being filled incrementally; see Epic #885 and tracking issue
#888. Public surface re-exported here for backwards-compatible imports.
"""

from __future__ import annotations

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
from app.api.v1.projects.contracts.format import (
    percent_display,
    ratio_decimal,
    score_0_100,
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
    "formula_diagnostics_for",
    "metric_definition",
    "metric_definitions",
    "percent_display",
    "ratio_decimal",
    "score_0_100",
]
