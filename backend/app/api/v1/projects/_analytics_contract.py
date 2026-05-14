"""Shared App analytics contract metadata for project-scoped endpoints."""

from __future__ import annotations

from app.api.v1.projects.contracts.builder import (
    _analyzer_fact_rollup as _analyzer_fact_rollup,
)
from app.api.v1.projects.contracts.builder import (
    _competitor_ids as _competitor_ids,
)
from app.api.v1.projects.contracts.builder import (
    _empty_evidence as _empty_evidence,
)
from app.api.v1.projects.contracts.builder import (
    _first_class_analyzer_fact_rollup as _first_class_analyzer_fact_rollup,
)
from app.api.v1.projects.contracts.builder import (
    _latest_runs_by_response as _latest_runs_by_response,
)
from app.api.v1.projects.contracts.builder import (
    _quality_flag_reasons_by_metric as _quality_flag_reasons_by_metric,
)
from app.api.v1.projects.contracts.builder import (
    build_contract_context as build_contract_context,
)
from app.api.v1.projects.contracts.builder import (
    context_dump as context_dump,
)
from app.api.v1.projects.contracts.builder import (
    context_update as context_update,
)
from app.api.v1.projects.contracts.constants import (
    _BLOCKING_REASON_CODES as _BLOCKING_REASON_CODES,
)
from app.api.v1.projects.contracts.constants import (
    _COMMON_METRIC_BLOCKING_REASONS as _COMMON_METRIC_BLOCKING_REASONS,
)
from app.api.v1.projects.contracts.constants import (
    _METRIC_BLOCKING_REASONS as _METRIC_BLOCKING_REASONS,
)
from app.api.v1.projects.contracts.constants import (
    ANALYSIS_MISSING_REASON as ANALYSIS_MISSING_REASON,
)
from app.api.v1.projects.contracts.constants import (
    ANALYZER_FACT_PACKAGE_SOURCE as ANALYZER_FACT_PACKAGE_SOURCE,
)
from app.api.v1.projects.contracts.constants import (
    ANALYZER_FACT_PACKAGE_V3_SOURCE as ANALYZER_FACT_PACKAGE_V3_SOURCE,
)
from app.api.v1.projects.contracts.constants import (
    FORMULA_MISSING_INPUTS_STATUS as FORMULA_MISSING_INPUTS_STATUS,
)
from app.api.v1.projects.contracts.constants import (
    FORMULA_NO_EVIDENCE_STATUS as FORMULA_NO_EVIDENCE_STATUS,
)
from app.api.v1.projects.contracts.constants import (
    FORMULA_OK_STATUS as FORMULA_OK_STATUS,
)
from app.api.v1.projects.contracts.constants import (
    FORMULA_PARTIAL_STATUS as FORMULA_PARTIAL_STATUS,
)
from app.api.v1.projects.contracts.constants import (
    FORMULA_PENDING_SOURCE as FORMULA_PENDING_SOURCE,
)
from app.api.v1.projects.contracts.constants import (
    FORMULA_PENDING_STATUS as FORMULA_PENDING_STATUS,
)
from app.api.v1.projects.contracts.constants import (
    MISSING_PROJECT_BRAND_BINDING_REASON as MISSING_PROJECT_BRAND_BINDING_REASON,
)
from app.api.v1.projects.contracts.constants import (
    NO_AGGREGATE_ROWS_REASON as NO_AGGREGATE_ROWS_REASON,
)
from app.api.v1.projects.contracts.constants import (
    PROJECT_UNBOUND_REASON as PROJECT_UNBOUND_REASON,
)
from app.api.v1.projects.contracts.definitions import (
    formula_diagnostics_for as formula_diagnostics_for,
)
from app.api.v1.projects.contracts.definitions import (
    metric_definition as metric_definition,
)
from app.api.v1.projects.contracts.definitions import (
    metric_definitions as metric_definitions,
)
from app.api.v1.projects.contracts.evidence import (
    _blocking_metric_evidence as _blocking_metric_evidence,
)
from app.api.v1.projects.contracts.evidence import (
    _evidence_source_tables as _evidence_source_tables,
)
from app.api.v1.projects.contracts.evidence import (
    _metric_evidence_template as _metric_evidence_template,
)
from app.api.v1.projects.contracts.evidence import (
    _package_source_tables as _package_source_tables,
)
from app.api.v1.projects.contracts.format import (
    percent_display as percent_display,
)
from app.api.v1.projects.contracts.format import (
    ratio_decimal as ratio_decimal,
)
from app.api.v1.projects.contracts.format import (
    score_0_100 as score_0_100,
)
from app.api.v1.projects.contracts.metrics import (
    metric_blocking_inputs_from_evidence as metric_blocking_inputs_from_evidence,
)
from app.api.v1.projects.contracts.metrics import (
    metric_evidence_for as metric_evidence_for,
)
from app.api.v1.projects.contracts.metrics import (
    metric_formula_status as metric_formula_status,
)
from app.api.v1.projects.contracts.metrics import (
    metric_missing_inputs as metric_missing_inputs,
)
from app.api.v1.projects.contracts.models import (
    AnalyticsContractContext as AnalyticsContractContext,
)
from app.api.v1.projects.contracts.models import (
    DataFreshness as DataFreshness,
)
from app.api.v1.projects.contracts.models import (
    FormulaDiagnostics as FormulaDiagnostics,
)
from app.api.v1.projects.contracts.models import (
    IdentityDiagnostics as IdentityDiagnostics,
)
from app.api.v1.projects.contracts.models import (
    MetricDefinition as MetricDefinition,
)
from app.api.v1.projects.contracts.models import (
    MetricValue as MetricValue,
)
from app.api.v1.projects.contracts.models import (
    ProjectScope as ProjectScope,
)
from app.api.v1.projects.contracts.models import (
    ValueRange as ValueRange,
)
from app.api.v1.projects.contracts.package import (
    _as_package as _as_package,
)
from app.api.v1.projects.contracts.package import (
    _as_v3_package as _as_v3_package,
)
from app.api.v1.projects.contracts.package import (
    _json_int as _json_int,
)
from app.api.v1.projects.contracts.package import (
    _merge_status as _merge_status,
)
from app.api.v1.projects.contracts.package import (
    _package_date_in_window as _package_date_in_window,
)
from app.api.v1.projects.contracts.package import (
    _package_reason_codes as _package_reason_codes,
)
from app.api.v1.projects.contracts.package import (
    _package_response_ids as _package_response_ids,
)
from app.api.v1.projects.contracts.package import (
    _package_target_brand_id as _package_target_brand_id,
)
from app.api.v1.projects.contracts.package import (
    _repair_entries as _repair_entries,
)
from app.api.v1.projects.contracts.package import (
    _status_from_package as _status_from_package,
)
from app.api.v1.projects.contracts.queries import (
    _pinned_topic_response_ids as _pinned_topic_response_ids,
)
from app.api.v1.projects.contracts.queries import (
    _project_eligible_response_ids as _project_eligible_response_ids,
)
from app.api.v1.projects.contracts.queries import (
    _target_response_ids as _target_response_ids,
)
from app.api.v1.projects.contracts.rollups import (
    _rollup_citations as _rollup_citations,
)
from app.api.v1.projects.contracts.rollups import (
    _rollup_coverage as _rollup_coverage,
)
from app.api.v1.projects.contracts.rollups import (
    _rollup_pano_geo as _rollup_pano_geo,
)
from app.api.v1.projects.contracts.rollups import (
    _rollup_sentiment as _rollup_sentiment,
)
from app.api.v1.projects.contracts.rollups import (
    _rollup_sov as _rollup_sov,
)
