"""Metric-evidence builders shared by the rollup layer.

Phase 4 of splitting `_analytics_contract.py` (Epic #885, design #888).
Hosts the small helpers that both the rollup functions and the
`build_contract_context` orchestrator use to assemble metric-evidence
records and source-table lists.
"""

from __future__ import annotations

from typing import Any

from app.api.v1.projects.contracts.constants import (
    ANALYZER_FACT_PACKAGE_SOURCE,
    ANALYZER_FACT_PACKAGE_V3_SOURCE,
    FORMULA_MISSING_INPUTS_STATUS,
)


def _unique_str(values: list[str]) -> list[str]:
    """Local dedup; cannot reuse `_analytics_contract._unique` without
    creating a circular import."""
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out


def _metric_evidence_template(metric_key: str, status: str) -> dict[str, Any]:
    return {
        "metric_key": metric_key,
        "formula_status": status,
        "reason_codes": [],
        "sample_response_ids": [],
    }


def _package_source_tables(packages: list[dict[str, Any]] | None = None) -> list[str]:
    sources = [
        str(package.get("_package_source"))
        for package in packages or []
        if package.get("_package_source")
    ]
    return _unique_str(sources) or [ANALYZER_FACT_PACKAGE_V3_SOURCE, ANALYZER_FACT_PACKAGE_SOURCE]


def _evidence_source_tables(metric_evidence: dict[str, Any]) -> list[str]:
    sources: list[str] = []
    for evidence in metric_evidence.values():
        if not isinstance(evidence, dict):
            continue
        tables = evidence.get("source_tables")
        if isinstance(tables, list):
            sources.extend(str(table) for table in tables if table)
    return _unique_str(sources) or _package_source_tables()


def _blocking_metric_evidence(
    reason_codes: list[str],
    *,
    source_tables: list[str],
    sample_response_ids: list[int] | None = None,
) -> dict[str, Any]:
    sample_ids = sorted({int(value) for value in sample_response_ids or []})[:20]
    reasons = _unique_str(reason_codes)
    return {
        key: {
            "metric_key": key,
            "formula_status": FORMULA_MISSING_INPUTS_STATUS,
            "reason_codes": reasons,
            "source_tables": source_tables,
            "fact_classes": [key],
            "sample_response_ids": sample_ids,
        }
        for key in ("coverage", "sov", "sentiment", "citation", "pano_geo")
    }
