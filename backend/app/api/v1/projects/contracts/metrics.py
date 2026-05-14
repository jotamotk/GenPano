"""Metric evidence + blocking-reason lookups.

Phase 6 of splitting `_analytics_contract.py` (Epic #885, design #888).
Public API consumed by chart contract wrappers and other call sites:
- `metric_evidence_for`: lookup `metric_formula_evidence` slice by metric key
- `metric_formula_status`: extract status from that slice
- `metric_blocking_inputs_from_evidence`: list of blocking reason codes
- `metric_missing_inputs`: convenience composition of the above
"""

from __future__ import annotations

from typing import Any

from app.api.v1.projects.contracts.constants import (
    _COMMON_METRIC_BLOCKING_REASONS,
    _METRIC_BLOCKING_REASONS,
    FORMULA_NO_EVIDENCE_STATUS,
    FORMULA_OK_STATUS,
)
from app.api.v1.projects.contracts.evidence import _unique_str
from app.api.v1.projects.contracts.models import AnalyticsContractContext


def metric_evidence_for(
    context: AnalyticsContractContext, metric_key: str | None
) -> dict[str, Any] | None:
    if not metric_key:
        return None
    if metric_key in {"sov", "avg_sov"}:
        return context.metric_formula_evidence.get("sov")
    if metric_key in {"sentiment", "avg_sentiment"}:
        return context.metric_formula_evidence.get("sentiment")
    if metric_key in {"citation", "citation_rate", "avg_citation_rate"}:
        return context.metric_formula_evidence.get("citation")
    if metric_key in {"geo_score", "avg_geo_score", "pano_score", "final_geo_score"}:
        return context.metric_formula_evidence.get("pano_geo")
    if metric_key in {"mention_rate", "avg_mention_rate"}:
        return context.metric_formula_evidence.get("coverage")
    return None


def metric_formula_status(
    context: AnalyticsContractContext,
    metric_key: str | None,
    default: str | None = None,
) -> str | None:
    evidence = metric_evidence_for(context, metric_key)
    if not evidence:
        return default
    return str(evidence.get("formula_status") or default or FORMULA_NO_EVIDENCE_STATUS)


def metric_blocking_inputs_from_evidence(
    metric_key: str | None,
    evidence: dict[str, Any] | None,
) -> list[str]:
    if not metric_key or not evidence:
        return []
    status = str(evidence.get("formula_status") or FORMULA_NO_EVIDENCE_STATUS)
    if status == FORMULA_OK_STATUS:
        return []
    evidence_key = (
        "sov"
        if metric_key in {"sov", "avg_sov"}
        else "sentiment"
        if metric_key in {"sentiment", "avg_sentiment"}
        else "citation"
        if metric_key in {"citation", "citation_rate", "avg_citation_rate"}
        else "pano_geo"
        if metric_key in {"geo_score", "avg_geo_score", "pano_score", "final_geo_score"}
        else "coverage"
        if metric_key in {"mention_rate", "avg_mention_rate"}
        else metric_key
    )
    blocking_reasons = {
        *_COMMON_METRIC_BLOCKING_REASONS,
        *_METRIC_BLOCKING_REASONS.get(evidence_key, set()),
    }
    reasons = [str(reason) for reason in evidence.get("reason_codes", []) if reason]
    if evidence_key == "sov":
        denominator = int(evidence.get("denominator_count") or 0)
        numerator = int(evidence.get("numerator_count") or 0)
        if denominator > numerator:
            blocking_reasons = {
                reason
                for reason in blocking_reasons
                if reason
                not in {
                    "missing_competitive_extraction",
                    "target_only_sov",
                    "sov_empty",
                    "sov_missing_required_inputs",
                }
            }
    return _unique_str([reason for reason in reasons if reason in blocking_reasons])


def metric_missing_inputs(
    context: AnalyticsContractContext,
    metric_key: str | None,
) -> list[str]:
    evidence = metric_evidence_for(context, metric_key)
    return metric_blocking_inputs_from_evidence(metric_key, evidence)
