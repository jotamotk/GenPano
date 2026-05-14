"""Analytics contract constants — status codes, source paths, blocking reasons.

Phase 2 of splitting `_analytics_contract.py` (Epic #885, design #888).
Extracted as a separate module so the model and definition layers can
reference these without a circular import back to the original file.
"""

from __future__ import annotations

FORMULA_OK_STATUS = "ok"
FORMULA_PARTIAL_STATUS = "partial"
FORMULA_PENDING_STATUS = "formula_pending_upstream"
FORMULA_MISSING_INPUTS_STATUS = "missing_required_inputs"
FORMULA_NO_EVIDENCE_STATUS = "no_evidence"
FORMULA_PENDING_SOURCE = "upstream_formula_provenance"
ANALYZER_FACT_PACKAGE_SOURCE = "response_analyses.raw_analysis_json.analyzer_fact_packages"
ANALYZER_FACT_PACKAGE_V3_SOURCE = "response_analyses.raw_analysis_json.analyzer_fact_package_v3"
PROJECT_UNBOUND_REASON = "project_unbound"
MISSING_PROJECT_BRAND_BINDING_REASON = "missing_project_brand_binding"
ANALYSIS_MISSING_REASON = "analysis_missing"
NO_AGGREGATE_ROWS_REASON = "no_aggregate_rows"
_BLOCKING_REASON_CODES = {
    PROJECT_UNBOUND_REASON,
    MISSING_PROJECT_BRAND_BINDING_REASON,
    ANALYSIS_MISSING_REASON,
    NO_AGGREGATE_ROWS_REASON,
}
_COMMON_METRIC_BLOCKING_REASONS = {
    PROJECT_UNBOUND_REASON,
    MISSING_PROJECT_BRAND_BINDING_REASON,
    ANALYSIS_MISSING_REASON,
    NO_AGGREGATE_ROWS_REASON,
    "missing_analyzer_fact_packages",
}
_METRIC_BLOCKING_REASONS = {
    "coverage": {
        "missing_analyzer_rows",
        "partial_analyzer_coverage",
        "eligible_response_denominator",
    },
    "sov": {
        "missing_competitive_extraction",
        "target_only_sov",
        "sov_empty",
        "sov_missing_required_inputs",
        "brand_mentions.competitive_set",
    },
    "sentiment": {
        "missing_sentiment_score_or_label",
        "missing_sentiment_label",
        "missing_sentiment_driver_quote",
        "missing_competitor_sentiment_evidence",
        "sentiment_empty",
        "sentiment_component_empty",
        "brand_mentions.sentiment_score",
    },
    "citation": {
        "unresolved_citation_attribution",
        "citation_empty",
        "citation_partial",
        "citation_sources",
        "citation_sources.mention_id",
        "citation_component_partial",
        "citation_component_empty",
    },
    "pano_geo": {
        "missing_analyzer_rows",
        "pano_component_empty",
        "visibility_component_empty",
        "sentiment_component_empty",
        "sov_component_empty",
        "citation_component_empty",
        "sov_missing_required_inputs",
        "citation_component_partial",
        "sentiment_component_partial",
    },
}
