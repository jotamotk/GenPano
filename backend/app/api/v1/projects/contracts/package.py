"""Analyzer-fact-package normalization helpers.

Phase 3 of splitting `_analytics_contract.py` (Epic #885, design #888).
Hosts the v3 and legacy issue_602_v1 package normalizers plus the status,
reason-code, response-id, brand-id, and date-window getters that consume
them.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.api.v1.projects.contracts.constants import (
    ANALYZER_FACT_PACKAGE_SOURCE,
    ANALYZER_FACT_PACKAGE_V3_SOURCE,
    FORMULA_MISSING_INPUTS_STATUS,
    FORMULA_NO_EVIDENCE_STATUS,
    FORMULA_OK_STATUS,
    FORMULA_PARTIAL_STATUS,
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


def _repair_entries(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    repairs = payload.get("canonical_alias_repairs")
    if not isinstance(repairs, list):
        return []
    return [entry for entry in repairs if isinstance(entry, dict)]


def _json_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_v3_package(payload: dict[str, Any]) -> dict[str, Any] | None:
    package = payload.get("analyzer_fact_package_v3")
    if not isinstance(package, dict) or package.get("analyzer_version") != "v3":
        return None
    coverage = package.get("coverage")
    if not isinstance(coverage, dict):
        return None
    response_id = _json_int(package.get("response_id"))
    normalized = dict(package)
    normalized["_package_source"] = ANALYZER_FACT_PACKAGE_V3_SOURCE
    normalized["_package_version"] = "v3"
    if response_id is not None:
        normalized["_response_ids"] = [response_id]

    reason_codes = [str(value) for value in coverage.get("validation_errors") or [] if value]
    parse_status = str(coverage.get("parse_status") or "ok")
    analyzed = bool(coverage.get("analyzed"))
    if parse_status != "ok":
        reason_codes.append(parse_status)
    if not analyzed:
        reason_codes.append("missing_analyzer_rows")
    coverage_status = FORMULA_OK_STATUS
    if reason_codes:
        coverage_status = FORMULA_PARTIAL_STATUS
    normalized_coverage = dict(coverage)
    normalized_coverage.setdefault("status", coverage_status)
    normalized_coverage.setdefault("formula_status", coverage_status)
    eligible_basis = _json_int(coverage.get("eligible_response_count_basis"))
    normalized_coverage.setdefault(
        "eligible_count",
        eligible_basis if eligible_basis is not None else (1 if response_id is not None else 0),
    )
    normalized_coverage.setdefault("analyzed_count", 1 if analyzed else 0)
    normalized_coverage.setdefault("failed_count", 1 if parse_status == "failed" else 0)
    normalized_coverage.setdefault("missing_analyzer_count", 0 if analyzed else 1)
    if response_id is not None:
        normalized_coverage.setdefault("eligible_response_ids", [response_id])
        normalized_coverage.setdefault("analyzed_response_ids", [response_id] if analyzed else [])
        normalized_coverage.setdefault(
            "missing_analyzer_response_ids", [] if analyzed else [response_id]
        )
        normalized_coverage.setdefault(
            "failed_response_ids", [response_id] if parse_status == "failed" else []
        )
        normalized_coverage.setdefault(
            "chains",
            [
                {
                    "response_id": response_id,
                    "query_id": package.get("query_id"),
                    "prompt_id": package.get("prompt_id"),
                    "topic_id": package.get("topic_id"),
                    "project_brand_id": package.get("target_brand_id"),
                    "engine": package.get("engine"),
                    "profile_id": package.get("profile_id"),
                    "collected_at": package.get("collected_at"),
                    "analysis_status": "done" if analyzed else None,
                    "has_analysis": analyzed,
                }
            ],
        )
    normalized_coverage.setdefault("reason_codes", _unique_str(reason_codes))
    normalized["coverage"] = normalized_coverage

    entities = normalized.get("entities")
    if isinstance(entities, dict) and "target_brand_id" not in entities:
        target = entities.get("target")
        if isinstance(target, dict):
            entities = dict(entities)
            entities["target_brand_id"] = target.get("brand_id")
            entities["target_brand_name"] = target.get("canonical_name")
            normalized["entities"] = entities

    sentiment = normalized.get("sentiment")
    if isinstance(sentiment, dict):
        sentiment = dict(sentiment)
        sentiment.setdefault("status", sentiment.get("formula_status"))
        sentiment.setdefault("score_count", 1 if sentiment.get("score") is not None else 0)
        sentiment.setdefault("label_count", 1 if sentiment.get("label") else 0)
        sentiment.setdefault("driver_count", len(sentiment.get("drivers") or []))
        sentiment.setdefault("quote_count", len(sentiment.get("source_quotes") or []))
        if response_id is not None:
            sentiment.setdefault("sample_response_ids", [response_id])
        normalized["sentiment"] = sentiment

    citations = normalized.get("citations")
    if isinstance(citations, dict):
        citations = dict(citations)
        attributed = citations.get("attributed_citations") or []
        unresolved = citations.get("unresolved_citations") or []
        citations.setdefault("status", citations.get("formula_status"))
        citations.setdefault("citation_count", citations.get("total_citations") or 0)
        citations.setdefault(
            "attributed_count", len(attributed) if isinstance(attributed, list) else 0
        )
        citations.setdefault(
            "unresolved_count", len(unresolved) if isinstance(unresolved, list) else 0
        )
        if response_id is not None:
            citations.setdefault("sample_response_ids", [response_id])
        normalized["citations"] = citations

    sov = normalized.get("sov")
    if isinstance(sov, dict):
        sov = dict(sov)
        sov.setdefault("status", sov.get("formula_status"))
        if response_id is not None:
            sov.setdefault("sample_response_ids", [response_id])
        normalized["sov"] = sov

    # Issue #1049: v3 packages pre-date the per-response `topic_product`
    # sub-block emitted by `geo_tracker/analyzer/fact_contract.py::_topic_product_package`
    # (fact_contract.py:803-820). The `_rollup_topic_product` aggregator
    # (rollups.py:302-366) skips packages without that key, so v3-only
    # projects (e.g. BestCoffer prod) end up with no `topic_product`
    # entry in `metric_formula_evidence` and the frontend
    # `canUseMetricEvidence(data, 'product')` gate returns false, leaving
    # the products page blank. Derive a `topic_product` sub-block here
    # from v3's existing `products` array (built by `_v3_products` at
    # fact_contract.py:460-472 — non-empty `product_name` only) and the
    # `topic`/`topic_id`/`prompt_id`/`query_id` chain, so the rollup
    # loop picks the package up unchanged.
    if "topic_product" not in normalized:
        products = normalized.get("products")
        product_fact_count = (
            sum(1 for entry in products if isinstance(entry, dict) and entry.get("product_name"))
            if isinstance(products, list)
            else 0
        )
        topic_chain = normalized.get("topic_chain")
        if isinstance(topic_chain, list):
            topic_chain_count = len(topic_chain)
        else:
            topic_info = normalized.get("topic")
            has_chain = (
                isinstance(topic_info, dict)
                and topic_info.get("topic_id") is not None
                and topic_info.get("prompt_id") is not None
                and topic_info.get("query_id") is not None
            )
            if not has_chain:
                has_chain = (
                    normalized.get("topic_id") is not None
                    and normalized.get("prompt_id") is not None
                    and normalized.get("query_id") is not None
                )
            topic_chain_count = 1 if has_chain else 0
        topic_product_status = FORMULA_OK_STATUS if product_fact_count > 0 else "empty"
        normalized["topic_product"] = {
            "status": topic_product_status,
            "topic_chain_count": topic_chain_count,
            "product_fact_count": product_fact_count,
            "topic_chain_missing_response_ids": [],
            "product_status": topic_product_status,
            "reason_codes": [],
        }

    return normalized


def _as_package(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    v3_package = _as_v3_package(payload)
    if v3_package is not None:
        return v3_package
    packages = payload.get("analyzer_fact_packages")
    if not isinstance(packages, dict):
        return None
    if packages.get("version") != "issue_602_v1":
        return None
    packages = dict(packages)
    packages["_package_source"] = ANALYZER_FACT_PACKAGE_SOURCE
    packages["_package_version"] = "issue_602_v1"
    return packages


def _status_from_package(package: dict[str, Any], key: str) -> str:
    value = package.get(key)
    if not isinstance(value, dict):
        return FORMULA_NO_EVIDENCE_STATUS
    return str(value.get("formula_status") or value.get("status") or FORMULA_NO_EVIDENCE_STATUS)


def _merge_status(current: str, candidate: str) -> str:
    order = {
        FORMULA_NO_EVIDENCE_STATUS: 0,
        FORMULA_OK_STATUS: 1,
        FORMULA_PARTIAL_STATUS: 2,
        FORMULA_MISSING_INPUTS_STATUS: 3,
    }
    if candidate == FORMULA_MISSING_INPUTS_STATUS:
        return candidate
    if current == FORMULA_MISSING_INPUTS_STATUS:
        return current
    if candidate == FORMULA_PARTIAL_STATUS or current == FORMULA_PARTIAL_STATUS:
        return FORMULA_PARTIAL_STATUS
    return candidate if order.get(candidate, 0) > order.get(current, 0) else current


def _package_reason_codes(package: dict[str, Any], key: str) -> list[str]:
    value = package.get(key)
    if not isinstance(value, dict):
        return []
    reasons = value.get("reason_codes")
    if not isinstance(reasons, list):
        return []
    return [str(reason) for reason in reasons if reason]


def _package_response_ids(package: dict[str, Any]) -> set[int]:
    ids: set[int] = set()
    if package.get("response_id") is not None:
        ids.add(int(package["response_id"]))
    response_ids = package.get("_response_ids")
    if isinstance(response_ids, list):
        ids.update(int(value) for value in response_ids if value is not None)
    coverage = package.get("coverage")
    if isinstance(coverage, dict):
        for field in (
            "eligible_response_ids",
            "analyzed_response_ids",
            "missing_analyzer_response_ids",
            "failed_response_ids",
        ):
            values = coverage.get(field)
            if isinstance(values, list):
                ids.update(int(value) for value in values if value is not None)
    for key in ("sov", "sentiment", "citations"):
        value = package.get(key)
        if isinstance(value, dict) and isinstance(value.get("sample_response_ids"), list):
            ids.update(int(value) for value in value["sample_response_ids"] if value is not None)
    return ids


def _package_target_brand_id(package: dict[str, Any]) -> int | None:
    if package.get("target_brand_id") is not None:
        return int(package["target_brand_id"])
    entities = package.get("entities")
    if isinstance(entities, dict) and entities.get("target_brand_id") is not None:
        return int(entities["target_brand_id"])
    return None


def _package_date_in_window(package: dict[str, Any], from_date: date, to_date: date) -> bool:
    raw_collected = package.get("collected_at")
    if raw_collected:
        try:
            collected = datetime.fromisoformat(str(raw_collected).replace("Z", "+00:00")).date()
        except ValueError:
            pass
        else:
            return from_date <= collected <= to_date
    coverage = package.get("coverage")
    if not isinstance(coverage, dict):
        return True
    chains = coverage.get("chains")
    if not isinstance(chains, list) or not chains:
        return True
    saw_date = False
    for chain in chains:
        if not isinstance(chain, dict):
            continue
        raw = chain.get("collected_at")
        if not raw:
            continue
        try:
            collected = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
        except ValueError:
            continue
        saw_date = True
        if from_date <= collected <= to_date:
            return True
    return not saw_date
