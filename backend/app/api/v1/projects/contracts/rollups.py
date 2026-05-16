"""Rollup builders for the analytics contract layer.

Phase 4 of splitting `_analytics_contract.py` (Epic #885, design #888).
Each rollup function aggregates per-package data into a single
`metric_evidence` record. Five rollups: sov, sentiment, citations,
coverage, pano_geo.
"""

from __future__ import annotations

from typing import Any

from app.api.v1.projects.contracts.constants import (
    _COMMON_METRIC_BLOCKING_REASONS,
    _METRIC_BLOCKING_REASONS,
    ANALYZER_FACT_PACKAGE_SOURCE,
    ANALYZER_FACT_PACKAGE_V3_SOURCE,
    FORMULA_MISSING_INPUTS_STATUS,
    FORMULA_NO_EVIDENCE_STATUS,
    FORMULA_OK_STATUS,
    FORMULA_PARTIAL_STATUS,
)
from app.api.v1.projects.contracts.evidence import (
    _metric_evidence_template,
    _package_source_tables,
    _unique_str,
)
from app.api.v1.projects.contracts.package import (
    _merge_status,
    _package_reason_codes,
    _package_response_ids,
)


def _rollup_sov(packages: list[dict[str, Any]]) -> dict[str, Any]:
    evidence = _metric_evidence_template("sov", FORMULA_NO_EVIDENCE_STATUS)
    numerator = 0
    denominator = 0
    competitors: list[dict[str, Any]] = []
    reason_codes: list[str] = []
    for package in packages:
        sov = package.get("sov")
        if not isinstance(sov, dict):
            continue
        evidence["formula_status"] = _merge_status(
            evidence["formula_status"],
            str(sov.get("formula_status") or sov.get("status") or FORMULA_NO_EVIDENCE_STATUS),
        )
        numerator += int(sov.get("numerator_target_mentions") or 0)
        denominator += int(sov.get("denominator_competitive_mentions") or 0)
        if isinstance(sov.get("competitors"), list):
            competitors.extend(item for item in sov["competitors"] if isinstance(item, dict))
        reason_codes.extend(_package_reason_codes(package, "sov"))
        evidence["sample_response_ids"].extend(sov.get("sample_response_ids") or [])
    if packages and evidence["formula_status"] == FORMULA_NO_EVIDENCE_STATUS:
        evidence["formula_status"] = FORMULA_MISSING_INPUTS_STATUS
    competitor_count = len(
        {
            (
                item.get("brand_id"),
                str(item.get("brand_name") or item.get("raw_name") or ""),
            )
            for item in competitors
        }
    )
    has_competitive_denominator = denominator > 0 and denominator > numerator
    if has_competitive_denominator:
        reason_codes = [
            reason
            for reason in reason_codes
            if reason
            not in {
                "missing_competitive_extraction",
                "target_only_sov",
                "sov_empty",
                "sov_missing_required_inputs",
            }
        ]
        blocking_reasons = [
            reason
            for reason in reason_codes
            if reason in _METRIC_BLOCKING_REASONS["sov"]
            or reason in _COMMON_METRIC_BLOCKING_REASONS
        ]
        if not blocking_reasons:
            evidence["formula_status"] = (
                FORMULA_PARTIAL_STATUS
                if "partial_analyzer_coverage" in reason_codes
                or "missing_analyzer_rows" in reason_codes
                else FORMULA_OK_STATUS
            )
    evidence.update(
        {
            "numerator_name": "target_competitive_mentions",
            "denominator_name": "all_competitive_mentions",
            "numerator_count": numerator,
            "denominator_count": denominator,
            "competitor_count": competitor_count,
            "source_tables": _package_source_tables(packages),
            "fact_classes": ["sov", "entities"],
        }
    )
    evidence["reason_codes"] = _unique_str(reason_codes)
    evidence["sample_response_ids"] = sorted(
        {int(value) for value in evidence["sample_response_ids"]}
    )
    return evidence


def _rollup_sentiment(packages: list[dict[str, Any]]) -> dict[str, Any]:
    evidence = _metric_evidence_template("sentiment", FORMULA_NO_EVIDENCE_STATUS)
    score_count = label_count = driver_count = quote_count = 0
    for package in packages:
        sentiment = package.get("sentiment")
        if not isinstance(sentiment, dict):
            continue
        evidence["formula_status"] = _merge_status(
            evidence["formula_status"],
            str(
                sentiment.get("formula_status")
                or sentiment.get("status")
                or FORMULA_NO_EVIDENCE_STATUS
            ),
        )
        score_count += int(sentiment.get("score_count") or 0)
        label_count += int(sentiment.get("label_count") or 0)
        driver_count += int(sentiment.get("driver_count") or 0)
        quote_count += int(sentiment.get("quote_count") or 0)
        evidence["reason_codes"].extend(_package_reason_codes(package, "sentiment"))
        evidence["sample_response_ids"].extend(sentiment.get("sample_response_ids") or [])
    if packages and evidence["formula_status"] == FORMULA_NO_EVIDENCE_STATUS:
        evidence["formula_status"] = FORMULA_MISSING_INPUTS_STATUS
    evidence.update(
        {
            "numerator_name": "brand_scoped_sentiment_score_sum",
            "denominator_name": "target_mentions_with_sentiment_score_and_label",
            "score_count": score_count,
            "label_count": label_count,
            "driver_count": driver_count,
            "quote_count": quote_count,
            "source_tables": [
                ANALYZER_FACT_PACKAGE_V3_SOURCE,
                ANALYZER_FACT_PACKAGE_SOURCE,
                "brand_mentions",
                "sentiment_drivers",
            ],
            "fact_classes": ["sentiment"],
        }
    )
    evidence["reason_codes"] = _unique_str(evidence["reason_codes"])
    evidence["sample_response_ids"] = sorted(
        {int(value) for value in evidence["sample_response_ids"]}
    )
    return evidence


def _rollup_citations(packages: list[dict[str, Any]]) -> dict[str, Any]:
    evidence = _metric_evidence_template("citation", FORMULA_NO_EVIDENCE_STATUS)
    counts = {
        "citation_count": 0,
        "attributed_count": 0,
        "unresolved_count": 0,
    }
    source_type_counts: dict[str, int] = {}
    tier_counts: dict[str, int] = {}
    unresolved_source_type_counts: dict[str, int] = {}
    unresolved_tier_counts: dict[str, int] = {}
    for package in packages:
        citations = package.get("citations")
        if not isinstance(citations, dict):
            continue
        evidence["formula_status"] = _merge_status(
            evidence["formula_status"],
            str(
                citations.get("formula_status")
                or citations.get("status")
                or FORMULA_NO_EVIDENCE_STATUS
            ),
        )
        for key in counts:
            counts[key] += int(citations.get(key) or 0)
        for source, target in (
            ("source_type_counts", source_type_counts),
            ("tier_counts", tier_counts),
            ("unresolved_source_type_counts", unresolved_source_type_counts),
            ("unresolved_tier_counts", unresolved_tier_counts),
        ):
            source_counts = citations.get(source)
            if isinstance(source_counts, dict):
                for name, count in source_counts.items():
                    target[str(name)] = target.get(str(name), 0) + int(count or 0)
        evidence["reason_codes"].extend(_package_reason_codes(package, "citations"))
        evidence["sample_response_ids"].extend(citations.get("sample_response_ids") or [])
    if packages and evidence["formula_status"] == FORMULA_NO_EVIDENCE_STATUS:
        evidence["formula_status"] = FORMULA_MISSING_INPUTS_STATUS
    evidence.update(
        {
            "numerator_name": "target_attributed_citations",
            "denominator_name": "eligible_project_citations",
            **counts,
            "source_type_counts": source_type_counts,
            "tier_counts": tier_counts,
            "unresolved_source_type_counts": unresolved_source_type_counts,
            "unresolved_tier_counts": unresolved_tier_counts,
            "source_tables": [
                ANALYZER_FACT_PACKAGE_V3_SOURCE,
                ANALYZER_FACT_PACKAGE_SOURCE,
                "citation_sources",
            ],
            "fact_classes": ["citations"],
        }
    )
    evidence["reason_codes"] = _unique_str(evidence["reason_codes"])
    evidence["sample_response_ids"] = sorted(
        {int(value) for value in evidence["sample_response_ids"]}
    )
    return evidence


def _rollup_coverage(
    packages: list[dict[str, Any]],
    *,
    target_response_ids: set[int],
) -> dict[str, Any]:
    evidence = _metric_evidence_template("coverage", FORMULA_NO_EVIDENCE_STATUS)
    package_response_ids: set[int] = set()
    eligible = analyzed = failed = missing = 0
    for package in packages:
        coverage = package.get("coverage")
        if not isinstance(coverage, dict):
            continue
        package_response_ids.update(_package_response_ids(package))
        evidence["formula_status"] = _merge_status(
            evidence["formula_status"],
            str(
                coverage.get("formula_status")
                or coverage.get("status")
                or FORMULA_NO_EVIDENCE_STATUS
            ),
        )
        eligible += int(coverage.get("eligible_count") or 0)
        analyzed += int(coverage.get("analyzed_count") or 0)
        failed += int(coverage.get("failed_count") or 0)
        missing += int(coverage.get("missing_analyzer_count") or 0)
        evidence["reason_codes"].extend(_package_reason_codes(package, "coverage"))
    missing_ids = sorted(target_response_ids - package_response_ids)
    if missing_ids:
        evidence["formula_status"] = FORMULA_PARTIAL_STATUS
        evidence["reason_codes"].append("missing_analyzer_rows")
        missing += len(missing_ids)
    if packages and evidence["formula_status"] == FORMULA_NO_EVIDENCE_STATUS:
        evidence["formula_status"] = FORMULA_OK_STATUS
    evidence.update(
        {
            "eligible_response_count": max(eligible, len(target_response_ids)),
            "analyzed_response_count": analyzed,
            "failed_response_count": failed,
            "missing_response_count": missing,
            "missing_response_ids": missing_ids[:20],
            "source_tables": _package_source_tables(packages),
            "fact_classes": ["coverage"],
        }
    )
    evidence["reason_codes"] = _unique_str(evidence["reason_codes"])
    evidence["sample_response_ids"] = sorted(package_response_ids)[:20]
    return evidence


def _rollup_pano_geo(packages: list[dict[str, Any]]) -> dict[str, Any]:
    evidence = _metric_evidence_template("pano_geo", FORMULA_NO_EVIDENCE_STATUS)
    readiness: dict[str, str] = {}
    for package in packages:
        pano = package.get("geo_pano") or package.get("pano_geo")
        if not isinstance(pano, dict):
            continue
        evidence["formula_status"] = _merge_status(
            evidence["formula_status"],
            str(pano.get("formula_status") or pano.get("status") or FORMULA_NO_EVIDENCE_STATUS),
        )
        component_readiness = pano.get("component_readiness")
        if isinstance(component_readiness, dict):
            for key, status in component_readiness.items():
                readiness[str(key)] = _merge_status(
                    readiness.get(str(key), FORMULA_OK_STATUS), str(status)
                )
        evidence["reason_codes"].extend(
            _package_reason_codes(package, "geo_pano") or _package_reason_codes(package, "pano_geo")
        )
    if packages and evidence["formula_status"] == FORMULA_NO_EVIDENCE_STATUS:
        evidence["formula_status"] = FORMULA_MISSING_INPUTS_STATUS
    evidence.update(
        {
            "component_readiness": readiness,
            "source_tables": _package_source_tables(packages),
            "fact_classes": ["pano_geo"],
        }
    )
    evidence["reason_codes"] = _unique_str(evidence["reason_codes"])
    return evidence


def _rollup_topic_product(packages: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Aggregate per-response `topic_product` packages into a page-level rollup.

    Issue #1039: `/api/v1/projects/<id>/products` must surface a
    `metric_formula_evidence.topic_product` record so the frontend
    `canUseMetricEvidence(data, 'product')` gate (BrandProductsPage.tsx:92)
    can render the products list. The per-response shape produced by
    `geo_tracker/analyzer/fact_contract.py::_topic_product_package` is:
        {status, topic_chain_missing_response_ids, topic_chain_count,
         product_fact_count, product_status, reason_codes}

    Returns `None` when no in-scope package carried a `topic_product`
    key (e.g. legacy v3 packages, or older `issue_602_v1` fixtures) so
    the caller can omit the entry from `metric_formula_evidence` and
    preserve backwards compatibility for callers that never consumed
    product evidence.
    """
    evidence = _metric_evidence_template("topic_product", FORMULA_NO_EVIDENCE_STATUS)
    topic_chain_count = 0
    product_fact_count = 0
    missing_chain_ids: list[int] = []
    contributing_response_ids: list[int] = []
    saw_topic_product = False
    for package in packages:
        topic_product = package.get("topic_product")
        if not isinstance(topic_product, dict):
            continue
        saw_topic_product = True
        topic_chain_count += int(topic_product.get("topic_chain_count") or 0)
        product_fact_count += int(topic_product.get("product_fact_count") or 0)
        missing_raw = topic_product.get("topic_chain_missing_response_ids")
        if isinstance(missing_raw, list):
            for value in missing_raw:
                try:
                    missing_chain_ids.append(int(value))
                except (TypeError, ValueError):
                    continue
        evidence["reason_codes"].extend(_package_reason_codes(package, "topic_product"))
        for rid in _package_response_ids(package):
            contributing_response_ids.append(int(rid))

    if not saw_topic_product:
        return None
    if topic_chain_count == 0 and product_fact_count == 0:
        # Responses carried the key but no product facts and no chain rows —
        # the page is genuinely empty (not blocked).
        evidence["formula_status"] = "empty"
        status = "empty"
    else:
        evidence["formula_status"] = FORMULA_OK_STATUS
        status = FORMULA_OK_STATUS

    evidence.update(
        {
            "status": status,
            "topic_chain_count": topic_chain_count,
            "product_fact_count": product_fact_count,
            "topic_chain_missing_response_ids": sorted(set(missing_chain_ids))[:20],
            "source_tables": _package_source_tables(packages),
            "fact_classes": ["topic_product"],
        }
    )
    evidence["reason_codes"] = _unique_str(evidence["reason_codes"])
    evidence["sample_response_ids"] = sorted(set(contributing_response_ids))[:5]
    return evidence
