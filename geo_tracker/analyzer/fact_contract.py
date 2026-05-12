"""Analyzer fact packages for App chart metric readiness.

The structures here are intentionally JSON-shaped. The pipeline can persist
them in ``response_analyses.raw_analysis_json`` now, while #603 decides how to
surface the same formula proof through App API contracts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

STATUS_OK = "ok"
STATUS_PARTIAL = "partial"
STATUS_EMPTY = "empty"
STATUS_MISSING = "missing_required_inputs"


@dataclass(frozen=True)
class AnalyzerMentionInput:
    mention_id: int | None
    response_id: int
    brand_id: int | None
    brand_name: str
    raw_name: str | None = None
    is_target: bool = False
    mention_count: int | None = 1
    context_snippet: str | None = None
    sentiment: str | None = None
    sentiment_score: float | None = None
    sentiment_drivers: list[dict[str, Any]] = field(default_factory=list)
    product_name: str | None = None
    position_type: str | None = None
    position_rank: int | None = None
    provenance: str = "brand_mentions"
    confidence: float | None = None


@dataclass(frozen=True)
class AnalyzerCitationInput:
    citation_id: int | None
    response_id: int
    mention_id: int | None
    url: str
    domain: str | None = None
    source_type: str | None = None
    tier: int | None = None
    title: str | None = None
    brand_name: str | None = None


@dataclass(frozen=True)
class AnalyzerResponseInput:
    response_id: int
    query_id: int | None
    prompt_id: int | None
    topic_id: int | None
    project_brand_id: int | None
    engine: str | None
    profile_id: str | int | None
    collected_at: str | None
    analysis_status: str | None
    has_analysis: bool
    raw_text: str | None = None
    mentions: list[AnalyzerMentionInput] = field(default_factory=list)
    citations: list[AnalyzerCitationInput] = field(default_factory=list)


def build_response_fact_packages(
    responses: list[AnalyzerResponseInput],
    *,
    target_brand_id: int,
    target_brand_name: str,
    target_aliases: list[str] | None,
    configured_competitors: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Build #602 analyzer output packages from response-level evidence."""

    entity_facts = _entity_facts(
        responses=responses,
        target_brand_id=target_brand_id,
        target_brand_name=target_brand_name,
        target_aliases=target_aliases or [],
        configured_competitors=configured_competitors or [],
    )
    coverage = _coverage_package(responses)
    sov = _sov_package(entity_facts, coverage, target_brand_id)
    sentiment = _sentiment_package(responses, target_brand_id)
    citations = _citation_package(responses)
    topic_product = _topic_product_package(responses, entity_facts)
    pano_geo = _pano_geo_package(coverage, sov, sentiment, citations)

    return {
        "version": "issue_602_v1",
        "coverage": coverage,
        "entities": {
            "status": STATUS_OK if entity_facts else STATUS_EMPTY,
            "facts": entity_facts,
            "target_brand_id": target_brand_id,
            "target_brand_name": target_brand_name,
        },
        "sov": sov,
        "sentiment": sentiment,
        "citations": citations,
        "topic_product": topic_product,
        "pano_geo": pano_geo,
    }


def _coverage_package(responses: list[AnalyzerResponseInput]) -> dict[str, Any]:
    eligible_ids = sorted({r.response_id for r in responses})
    analyzed_ids = sorted({r.response_id for r in responses if r.has_analysis})
    failed_ids = sorted(
        {r.response_id for r in responses if (r.analysis_status or "").lower() == "failed"}
    )
    missing_ids = sorted(set(eligible_ids) - set(analyzed_ids) - set(failed_ids))
    reason_codes: list[str] = []
    if missing_ids:
        reason_codes.append("missing_analyzer_rows")
    if failed_ids:
        reason_codes.append("failed_analyzer_rows")
    status = STATUS_OK
    if not eligible_ids:
        status = STATUS_EMPTY
    elif missing_ids or failed_ids or len(analyzed_ids) < len(eligible_ids):
        status = STATUS_PARTIAL

    return {
        "status": status,
        "eligible_response_ids": eligible_ids,
        "analyzed_response_ids": analyzed_ids,
        "failed_response_ids": failed_ids,
        "missing_analyzer_response_ids": missing_ids,
        "eligible_count": len(eligible_ids),
        "analyzed_count": len(analyzed_ids),
        "failed_count": len(failed_ids),
        "missing_analyzer_count": len(missing_ids),
        "reason_codes": reason_codes,
        "chains": [
            {
                "response_id": r.response_id,
                "query_id": r.query_id,
                "prompt_id": r.prompt_id,
                "topic_id": r.topic_id,
                "project_brand_id": r.project_brand_id,
                "engine": r.engine,
                "profile_id": r.profile_id,
                "collected_at": r.collected_at,
                "analysis_status": r.analysis_status,
                "has_analysis": r.has_analysis,
            }
            for r in sorted(responses, key=lambda item: item.response_id)
        ],
    }


def _entity_facts(
    *,
    responses: list[AnalyzerResponseInput],
    target_brand_id: int,
    target_brand_name: str,
    target_aliases: list[str],
    configured_competitors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    seen_structured: set[tuple[int, str]] = set()
    configured_specs = [_competitor_spec(item) for item in configured_competitors]
    target_terms = [target_brand_name, *target_aliases]
    for response in responses:
        for mention in response.mentions:
            role = _entity_role(mention, target_brand_id, target_terms, configured_specs)
            raw_name = mention.raw_name or mention.brand_name
            key = (response.response_id, _norm(raw_name))
            seen_structured.add(key)
            facts.append(
                {
                    "response_id": response.response_id,
                    "query_id": response.query_id,
                    "prompt_id": response.prompt_id,
                    "topic_id": response.topic_id,
                    "engine": response.engine,
                    "mention_id": mention.mention_id,
                    "entity_role": role,
                    "raw_name": raw_name,
                    "brand_name": mention.brand_name,
                    "canonical_brand_id": mention.brand_id,
                    "alias_provenance": mention.provenance,
                    "mention_count": _mention_count(mention.mention_count),
                    "context_snippet": mention.context_snippet,
                    "confidence": mention.confidence,
                    "source": "brand_mentions",
                    "product_name": mention.product_name,
                    "position_type": mention.position_type,
                    "position_rank": mention.position_rank,
                    "missing_inputs": [],
                }
            )
        for spec in configured_specs:
            if spec["brand_id"] == target_brand_id:
                continue
            if any(
                (response.response_id, _norm(term)) in seen_structured for term in spec["terms"]
            ):
                continue
            hit = _first_text_hit(response.raw_text, spec["terms"])
            if not hit:
                continue
            facts.append(
                {
                    "response_id": response.response_id,
                    "query_id": response.query_id,
                    "prompt_id": response.prompt_id,
                    "topic_id": response.topic_id,
                    "engine": response.engine,
                    "mention_id": None,
                    "entity_role": "configured_competitor",
                    "raw_name": hit["term"],
                    "brand_name": spec["brand_name"],
                    "canonical_brand_id": spec["brand_id"],
                    "alias_provenance": spec["source"],
                    "mention_count": hit["count"],
                    "context_snippet": hit["snippet"],
                    "confidence": 0.55,
                    "source": "text_configured_competitor",
                    "product_name": None,
                    "position_type": None,
                    "position_rank": None,
                    "missing_inputs": ["brand_mentions"],
                }
            )
    return sorted(
        facts,
        key=lambda item: (
            item["response_id"],
            item["entity_role"],
            str(item["canonical_brand_id"] or ""),
            item["raw_name"],
        ),
    )


def _sov_package(
    entity_facts: list[dict[str, Any]],
    coverage: dict[str, Any],
    target_brand_id: int,
) -> dict[str, Any]:
    competitive_facts = [
        f
        for f in entity_facts
        if f["entity_role"] in {"target", "configured_competitor", "response_named_competitor"}
    ]
    numerator = sum(
        int(f["mention_count"] or 0)
        for f in competitive_facts
        if f["entity_role"] == "target" or f["canonical_brand_id"] == target_brand_id
    )
    denominator = sum(int(f["mention_count"] or 0) for f in competitive_facts)
    competitor_facts = [
        f
        for f in competitive_facts
        if not (f["entity_role"] == "target" or f["canonical_brand_id"] == target_brand_id)
    ]
    reason_codes: list[str] = []
    if not competitive_facts:
        reason_codes.append("missing_competitive_extraction")
    if denominator and not competitor_facts:
        reason_codes.append("target_only_sov")
    if any("brand_mentions" in f["missing_inputs"] for f in competitor_facts):
        reason_codes.append("competitor_text_without_structured_brand_mentions")
    if coverage["status"] != STATUS_OK:
        reason_codes.append("partial_analyzer_coverage")

    if not competitive_facts:
        status = STATUS_EMPTY
    elif "target_only_sov" in reason_codes or not competitor_facts:
        status = STATUS_MISSING
    elif (
        "competitor_text_without_structured_brand_mentions" in reason_codes
        or coverage["status"] != STATUS_OK
    ):
        status = STATUS_PARTIAL
    else:
        status = STATUS_OK

    return {
        "status": status,
        "formula_status": status,
        "reason_codes": _unique(reason_codes),
        "numerator_target_mentions": numerator,
        "denominator_competitive_mentions": denominator,
        "sov": round(numerator / denominator, 4) if denominator and status == STATUS_OK else None,
        "competitors": _competitor_list(competitor_facts),
        "sample_response_ids": sorted({f["response_id"] for f in competitive_facts})[:20],
    }


def _sentiment_package(
    responses: list[AnalyzerResponseInput],
    target_brand_id: int,
) -> dict[str, Any]:
    if any(not r.has_analysis for r in responses):
        coverage_partial = True
    else:
        coverage_partial = False
    target_mentions = [
        mention
        for response in responses
        if response.has_analysis
        for mention in response.mentions
        if mention.is_target or mention.brand_id == target_brand_id
    ]
    scored = [
        mention
        for mention in target_mentions
        if mention.sentiment_score is not None and _valid_polarity(mention.sentiment)
    ]
    drivers = [
        driver
        for mention in scored
        for driver in mention.sentiment_drivers
        if _clean(driver.get("driver_text"))
    ]
    quoted = [driver for driver in drivers if _clean(driver.get("source_quote"))]
    reason_codes: list[str] = []
    if coverage_partial:
        reason_codes.append("partial_analyzer_coverage")
    if not target_mentions:
        status = STATUS_EMPTY
    elif not scored:
        status = STATUS_MISSING
        reason_codes.append("missing_sentiment_score_or_label")
    elif not drivers or not quoted:
        status = STATUS_PARTIAL
        reason_codes.append("missing_sentiment_driver_quote")
    else:
        status = STATUS_OK
    avg_score = None
    if scored:
        avg_score = round(sum(float(m.sentiment_score or 0) for m in scored) / len(scored), 4)
    return {
        "status": status,
        "formula_status": status,
        "reason_codes": _unique(reason_codes),
        "score_count": len(scored) if scored else None,
        "label_count": len(scored) if scored else 0,
        "driver_count": len(drivers),
        "quote_count": len(quoted),
        "avg_sentiment_score": avg_score,
        "sample_response_ids": sorted({m.response_id for m in target_mentions})[:20],
    }


def _citation_package(responses: list[AnalyzerResponseInput]) -> dict[str, Any]:
    citations = [citation for response in responses for citation in response.citations]
    attributed = [citation for citation in citations if citation.mention_id is not None]
    unresolved = [citation for citation in citations if citation.mention_id is None]
    domains = sorted(
        {_normalize_domain(c.domain or c.url) for c in attributed if c.domain or c.url}
    )
    if not citations:
        status = STATUS_EMPTY
    elif unresolved:
        status = STATUS_PARTIAL
    else:
        status = STATUS_OK
    return {
        "status": status,
        "formula_status": status,
        "citation_count": len(citations),
        "attributed_count": len(attributed),
        "unresolved_count": len(unresolved),
        "normalized_domains": domains,
        "source_type_counts": _count_by(attributed, "source_type"),
        "tier_counts": _count_by(attributed, "tier"),
        "unresolved_source_type_counts": _count_by(unresolved, "source_type"),
        "unresolved_tier_counts": _count_by(unresolved, "tier"),
        "sample_response_ids": sorted({c.response_id for c in citations})[:20],
        "reason_codes": ["unresolved_citation_attribution"] if unresolved else [],
    }


def _topic_product_package(
    responses: list[AnalyzerResponseInput],
    entity_facts: list[dict[str, Any]],
) -> dict[str, Any]:
    missing_chain = [
        r.response_id
        for r in responses
        if r.topic_id is None or r.prompt_id is None or r.query_id is None
    ]
    product_facts = [f for f in entity_facts if _clean(f.get("product_name"))]
    return {
        "status": STATUS_PARTIAL if missing_chain else STATUS_OK if responses else STATUS_EMPTY,
        "topic_chain_missing_response_ids": sorted(missing_chain),
        "topic_chain_count": len(responses) - len(missing_chain),
        "product_fact_count": len(product_facts),
        "product_status": STATUS_OK if product_facts else STATUS_EMPTY,
        "reason_codes": ["missing_topic_prompt_query_chain"] if missing_chain else [],
    }


def _pano_geo_package(
    coverage: dict[str, Any],
    sov: dict[str, Any],
    sentiment: dict[str, Any],
    citations: dict[str, Any],
) -> dict[str, Any]:
    readiness = {
        "coverage": coverage["status"],
        "sov": sov["status"],
        "sentiment": sentiment["status"],
        "citation": citations["status"],
    }
    ok = all(value == STATUS_OK for value in readiness.values())
    empty = all(value == STATUS_EMPTY for value in readiness.values())
    status = STATUS_OK if ok else STATUS_EMPTY if empty else STATUS_MISSING
    reason_codes: list[str] = []
    for component, component_status in readiness.items():
        if component_status != STATUS_OK:
            reason_codes.append(f"{component}_{component_status}")
    return {
        "status": status,
        "formula_status": status,
        "component_readiness": readiness,
        "reason_codes": reason_codes,
    }


def _competitor_spec(item: dict[str, Any]) -> dict[str, Any]:
    terms = [item.get("brand_name") or item.get("name")]
    terms.extend(item.get("aliases") or [])
    clean_terms = [str(term).strip() for term in terms if str(term or "").strip()]
    return {
        "brand_id": item.get("brand_id"),
        "brand_name": item.get("brand_name") or item.get("name"),
        "terms": clean_terms,
        "source": item.get("source") or "configured_competitor",
    }


def _entity_role(
    mention: AnalyzerMentionInput,
    target_brand_id: int,
    target_terms: list[str],
    configured_specs: list[dict[str, Any]],
) -> str:
    mention_terms = {_norm(mention.brand_name), _norm(mention.raw_name)}
    mention_terms.discard("")
    target_names = {_norm(term) for term in target_terms}
    target_names.discard("")
    if mention.is_target or mention.brand_id == target_brand_id or mention_terms & target_names:
        return "target"
    configured_ids = {spec["brand_id"] for spec in configured_specs if spec["brand_id"] is not None}
    configured_names = {_norm(term) for spec in configured_specs for term in spec["terms"]}
    if mention.brand_id in configured_ids or _norm(mention.brand_name) in configured_names:
        return "configured_competitor"
    return "response_named_competitor" if mention.brand_name else "other_entity"


def _first_text_hit(raw_text: str | None, terms: list[str]) -> dict[str, Any] | None:
    if not raw_text:
        return None
    lowered = raw_text.lower()
    for term in terms:
        normalized = str(term or "").strip()
        if not normalized:
            continue
        positions = _find_all(lowered, normalized.lower())
        if not positions:
            continue
        start, end = positions[0]
        radius = 120
        return {
            "term": normalized,
            "count": len(positions),
            "snippet": raw_text[max(0, start - radius) : min(len(raw_text), end + radius)],
        }
    return None


def _find_all(text_lower: str, term_lower: str) -> list[tuple[int, int]]:
    if not term_lower:
        return []
    is_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in term_lower)
    if is_cjk:
        positions: list[tuple[int, int]] = []
        start = 0
        while True:
            idx = text_lower.find(term_lower, start)
            if idx < 0:
                return positions
            positions.append((idx, idx + len(term_lower)))
            start = idx + 1
    pattern = re.compile(r"\b" + re.escape(term_lower) + r"\b", re.IGNORECASE)
    return [(match.start(), match.end()) for match in pattern.finditer(text_lower)]


def _competitor_list(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[Any, str], dict[str, Any]] = {}
    for fact in facts:
        key = (fact["canonical_brand_id"], _norm(fact["brand_name"] or fact["raw_name"]))
        row = by_key.setdefault(
            key,
            {
                "brand_id": fact["canonical_brand_id"],
                "brand_name": fact["brand_name"],
                "raw_names": [],
                "mention_count": 0,
                "source": fact["source"],
                "missing_inputs": [],
            },
        )
        row["mention_count"] += int(fact["mention_count"] or 0)
        row["raw_names"].append(fact["raw_name"])
        row["missing_inputs"].extend(fact["missing_inputs"])
    return [
        {
            **row,
            "raw_names": sorted(set(row["raw_names"])),
            "missing_inputs": sorted(set(row["missing_inputs"])),
        }
        for row in sorted(
            by_key.values(), key=lambda item: (str(item["brand_id"]), item["brand_name"] or "")
        )
    ]


def _count_by(items: list[Any], attr: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = getattr(item, attr)
        key = str(value if value is not None else "unknown")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _normalize_domain(value: str) -> str:
    cleaned = re.sub(r"^https?://", "", value.strip().lower())
    return cleaned.split("/", 1)[0].removeprefix("www.")


def _mention_count(value: int | None) -> int:
    return int(value or 1)


def _valid_polarity(value: str | None) -> bool:
    return _norm(value) in {"positive", "neutral", "negative"}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
