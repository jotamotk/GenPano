from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


ANALYZER_V4_SCHEMA_VERSION = "analyzer_v4"

TOP_LEVEL_KEYS = (
    "analysis_meta",
    "entities",
    "mentions",
    "sentiment_drivers",
    "product_features",
    "relations",
    "citations",
    "quality_flags",
)
REQUIRED_TOP_LEVEL_KEYS = ("analysis_meta", "entities", "mentions")
OPTIONAL_TOP_LEVEL_COLLECTIONS = (
    "sentiment_drivers",
    "product_features",
    "relations",
    "citations",
)


def _utcnow_iso() -> str:
    return datetime.now(UTC).replace(tzinfo=None).isoformat()

ENTITY_TYPES = {
    "brand",
    "product",
    "attribute",
    "need",
    "scenario",
    "category",
    "ingredient",
    "channel",
    "price_tier",
    "other",
}
MENTION_TYPES = {
    "brand",
    "product",
    "attribute",
    "need",
    "scenario",
    "category",
    "citation",
    "other",
}
POSITIONS = {"top", "middle", "tail", "unknown"}
SENTIMENT_LABELS = {"positive", "negative", "neutral", "mixed", "unknown"}
DRIVER_TYPES = {
    "benefit",
    "drawback",
    "comparison",
    "recommendation",
    "warning",
    "uncertainty",
    "price",
    "availability",
    "quality",
    "other",
}
FEATURE_TYPES = {
    "ingredient",
    "function",
    "attribute",
    "benefit",
    "drawback",
    "texture",
    "price",
    "scenario",
    "audience",
    "packaging",
    "availability",
    "quality",
    "other",
}
CATEGORY_PRODUCT_FEATURE_TYPES = {"category"}
RELATION_TYPES = {
    "recommended_for",
    "compared_with",
    "has_attribute",
    "addresses_need",
    "avoid_for",
    "belongs_to_brand",
    "substitute_for",
    "complements",
    "other",
}
RELATION_TYPE_ALIASES = {"belongs_to", "belongs_to_category"}
DIRECTIONS = {"directed", "undirected", "unknown"}
CITATION_SOURCE_TYPES = {
    "official",
    "commerce",
    "media",
    "ugc",
    "social",
    "knowledge_base",
    "research",
    "unknown",
    "other",
}
ATTRIBUTION_METHODS = {
    "official_domain",
    "co_occurrence",
    "text_match",
    "llm_inferred",
    "unattributed",
    "not_applicable",
}
CANONICALIZATION_STATUSES = {"matched", "suggested", "unresolved", "not_applicable"}


@dataclass
class AnalyzerV4ValidationResult:
    package: dict[str, Any]
    is_valid: bool
    validator_status: str
    errors: list[str] = field(default_factory=list)
    quality_flags: list[dict[str, Any]] = field(default_factory=list)
    failure_code: str | None = None
    failure_message: str | None = None
    raw_output_sha256: str | None = None

    @property
    def run_status(self) -> str:
        if not self.is_valid:
            return "failed"
        if self.validator_status == "passed_with_flags":
            return "partial"
        return "done"

    @property
    def validator_summary(self) -> dict[str, Any]:
        return {
            "schema_version": ANALYZER_V4_SCHEMA_VERSION,
            "validator_status": self.validator_status,
            "errors": list(self.errors),
            "quality_flag_count": len(self.quality_flags),
            "failure_code": self.failure_code,
            "failure_message": self.failure_message,
        }


def validate_analyzer_v4_package(
    package: dict[str, Any] | None,
    *,
    response_text: str | None,
    response_id: int,
    query_id: int | None,
) -> AnalyzerV4ValidationResult:
    raw_package = deepcopy(package) if isinstance(package, dict) else {}
    errors: list[str] = []
    flags: list[dict[str, Any]] = []

    if not isinstance(package, dict):
        errors.append("schema_validation_failed: package must be a JSON object")
        raw_package = _failed_package(
            response_id=response_id,
            query_id=query_id,
            code="schema_validation_failed",
            message="Analyzer output was not a JSON object.",
        )
    else:
        missing_required = [key for key in REQUIRED_TOP_LEVEL_KEYS if key not in raw_package]
        if missing_required:
            errors.append(
                f"schema_validation_failed: missing top-level keys {missing_required}"
            )
        for key in OPTIONAL_TOP_LEVEL_COLLECTIONS:
            if key not in raw_package:
                _append_flag(
                    flags,
                    code="missing_optional_collection",
                    severity="warning",
                    message=f"Optional analyzer collection {key} was absent and normalized to [].",
                    target_type="collection",
                    target_key=key,
                    blocks_metric_readiness=True,
                )

    _ensure_v4_shape(raw_package, response_id=response_id, query_id=query_id)
    meta = raw_package["analysis_meta"]
    if meta.get("schema_version") != ANALYZER_V4_SCHEMA_VERSION:
        errors.append("schema_validation_failed: analysis_meta.schema_version must be analyzer_v4")
    if meta.get("input_response_id") not in (None, response_id):
        errors.append("schema_validation_failed: analysis_meta.input_response_id mismatch")
    if query_id is not None and meta.get("input_query_id") not in (None, query_id):
        errors.append("schema_validation_failed: analysis_meta.input_query_id mismatch")

    for key in TOP_LEVEL_KEYS[1:]:
        if not isinstance(raw_package.get(key), list):
            errors.append(f"schema_validation_failed: {key} must be a list")
            raw_package[key] = []
    _drop_malformed_mentions(raw_package, flags)
    _drop_malformed_sentiment_drivers(raw_package, flags)
    _drop_unsupported_sentiment_driver_types(raw_package, flags)
    _drop_malformed_product_features(raw_package, flags)
    _drop_category_product_features(raw_package, flags)
    _drop_malformed_citations(raw_package, flags)
    _drop_malformed_relations(raw_package, flags)
    _normalize_or_drop_relation_types(raw_package, flags)

    entity_keys: set[str] = set()
    for index, entity in enumerate(_objects(raw_package["entities"])):
        key = str(entity.get("entity_key") or f"entity_{index}")
        entity["entity_key"] = key
        entity_keys.add(key)
        _require_string(entity, "raw_name", errors, f"entities[{index}]")
        _validate_enum(entity, "entity_type", ENTITY_TYPES, errors, f"entities[{index}]")
        _validate_enum(
            entity,
            "canonicalization_status",
            CANONICALIZATION_STATUSES,
            errors,
            f"entities[{index}]",
        )
        _validate_confidence(entity, errors, f"entities[{index}]")
        _flag_missing_evidence(flags, entity, "entity", key, response_text=response_text)
        if entity.get("canonicalization_status") == "unresolved":
            code = _unresolved_entity_code(entity.get("entity_type"))
            _append_flag(
                flags,
                code=code,
                severity="warning",
                message=f"{entity.get('entity_type') or 'entity'} was not canonicalized.",
                target_type="entity",
                target_key=key,
                blocks_metric_readiness=True,
            )

    fact_keys: dict[str, str] = {}
    for index, mention in enumerate(_objects(raw_package["mentions"])):
        key = str(mention.get("mention_key") or f"mention_{index}")
        mention["mention_key"] = key
        fact_keys[key] = "mention"
        if mention.get("entity_key") not in entity_keys:
            _append_flag(
                flags,
                code="entity_unresolved",
                severity="warning",
                message="Mention entity_key does not resolve to a response entity.",
                target_type="mention",
                target_key=key,
                blocks_metric_readiness=True,
            )
        if mention.get("mention_type") not in MENTION_TYPES:
            _append_flag(
                flags,
                code="invalid_mention_type",
                severity="error",
                message=f"Mention type {mention.get('mention_type')!r} is not supported.",
                target_type="mention",
                target_key=key,
                blocks_metric_readiness=True,
            )
        _validate_enum(mention, "mention_type", MENTION_TYPES, errors, f"mentions[{index}]")
        _validate_enum(mention, "position", POSITIONS, errors, f"mentions[{index}]")
        _validate_enum(
            mention, "sentiment_label", SENTIMENT_LABELS, errors, f"mentions[{index}]"
        )
        _validate_confidence(mention, errors, f"mentions[{index}]")
        _flag_missing_evidence(flags, mention, "mention", key, response_text=response_text)
        if mention.get("sentiment_label") == "unknown":
            _append_flag(
                flags,
                code="sentiment_unknown",
                severity="warning",
                message="Mention sentiment is unknown.",
                target_type="mention",
                target_key=key,
                blocks_metric_readiness=True,
            )

    for index, driver in enumerate(_objects(raw_package["sentiment_drivers"])):
        key = str(driver.get("driver_key") or f"driver_{index}")
        driver["driver_key"] = key
        fact_keys[key] = "driver"
        if driver.get("mention_key") not in fact_keys:
            _append_flag(
                flags,
                code="mention_unresolved",
                severity="warning",
                message="Driver mention_key does not resolve to a mention.",
                target_type="driver",
                target_key=key,
                blocks_metric_readiness=True,
            )
        if driver.get("target_entity_key") not in entity_keys:
            _append_flag(
                flags,
                code="entity_unresolved",
                severity="warning",
                message="Driver target_entity_key does not resolve to a response entity.",
                target_type="driver",
                target_key=key,
                blocks_metric_readiness=True,
            )
        _validate_enum(
            driver, "sentiment_label", SENTIMENT_LABELS, errors, f"sentiment_drivers[{index}]"
        )
        _validate_enum(driver, "driver_type", DRIVER_TYPES, errors, f"sentiment_drivers[{index}]")
        _validate_confidence(driver, errors, f"sentiment_drivers[{index}]")
        _flag_missing_evidence(flags, driver, "driver", key, response_text=response_text)
        if driver.get("sentiment_label") == "mixed":
            _append_flag(
                flags,
                code="mixed_sentiment",
                severity="info",
                message="Driver carries mixed sentiment.",
                target_type="driver",
                target_key=key,
                blocks_metric_readiness=False,
            )

    for index, feature in enumerate(_objects(raw_package["product_features"])):
        key = str(feature.get("feature_key") or f"feature_{index}")
        feature["feature_key"] = key
        fact_keys[key] = "feature"
        if feature.get("product_entity_key") not in entity_keys:
            _append_flag(
                flags,
                code="product_unresolved",
                severity="warning",
                message="Feature product_entity_key does not resolve to a response entity.",
                target_type="feature",
                target_key=key,
                blocks_metric_readiness=True,
            )
        if feature.get("brand_entity_key") in ("", None):
            _append_flag(
                flags,
                code="brand_unresolved",
                severity="warning",
                message="Feature has no resolved brand entity.",
                target_type="feature",
                target_key=key,
                blocks_metric_readiness=True,
            )
        _validate_enum(feature, "feature_type", FEATURE_TYPES, errors, f"product_features[{index}]")
        _validate_confidence(feature, errors, f"product_features[{index}]")
        _flag_missing_evidence(flags, feature, "feature", key, response_text=response_text)

    for index, relation in enumerate(_objects(raw_package["relations"])):
        key = str(relation.get("relation_key") or f"relation_{index}")
        relation["relation_key"] = key
        fact_keys[key] = "relation"
        unresolved = False
        if relation.get("subject_entity_key") not in entity_keys:
            unresolved = True
        if relation.get("object_entity_key") not in entity_keys:
            unresolved = True
        if "relation_unresolved" in _quality_codes(relation):
            unresolved = True
        if unresolved:
            _append_flag(
                flags,
                code="relation_unresolved",
                severity="warning",
                message="Relation endpoint could not be fully resolved.",
                target_type="relation",
                target_key=key,
                blocks_metric_readiness=True,
            )
        _validate_enum(relation, "relation_type", RELATION_TYPES, errors, f"relations[{index}]")
        _validate_enum(relation, "direction", DIRECTIONS, errors, f"relations[{index}]")
        _validate_confidence(relation, errors, f"relations[{index}]")
        _flag_missing_evidence(flags, relation, "relation", key, response_text=response_text)

    for index, citation in enumerate(_objects(raw_package["citations"])):
        key = str(citation.get("citation_key") or f"citation_{index}")
        citation["citation_key"] = key
        fact_keys[key] = "citation"
        _validate_enum(citation, "source_type", CITATION_SOURCE_TYPES, errors, f"citations[{index}]")
        _validate_enum(
            citation, "attribution_method", ATTRIBUTION_METHODS, errors, f"citations[{index}]"
        )
        _validate_confidence(citation, errors, f"citations[{index}]")
        _flag_missing_evidence(flags, citation, "citation", key, response_text=response_text)
        linked = [str(value) for value in citation.get("linked_fact_keys") or [] if value]
        valid_linked: list[str] = []
        for linked_key in linked:
            if linked_key not in fact_keys:
                _append_flag(
                    flags,
                    code="citation_unlinked",
                    severity="warning",
                    message=f"Citation linked_fact_key {linked_key} does not resolve.",
                    target_type="citation",
                    target_key=key,
                    blocks_metric_readiness=True,
                )
                continue
            valid_linked.append(linked_key)
        citation["linked_fact_keys"] = valid_linked
        if not valid_linked:
            _append_flag(
                flags,
                code="citation_unlinked",
                severity="warning",
                message="Citation is not linked to a concrete analyzer fact.",
                target_type="citation",
                target_key=key,
                blocks_metric_readiness=True,
            )

    for item in _objects(raw_package.get("quality_flags") or []):
        _append_flag(
            flags,
            code=str(item.get("code") or "partial_output"),
            severity=str(item.get("severity") or "warning"),
            message=str(item.get("message") or item.get("code") or "Analyzer quality flag."),
            target_type=str(item.get("target_type") or "analysis"),
            target_key=item.get("target_key"),
            blocks_metric_readiness=bool(item.get("blocks_metric_readiness", False)),
            flag_key=item.get("flag_key"),
        )

    if errors:
        status = "failed"
        raw_package["analysis_meta"]["response_quality"] = "invalid"
    elif flags:
        status = "passed_with_flags"
        if raw_package["analysis_meta"].get("response_quality") == "ok":
            raw_package["analysis_meta"]["response_quality"] = "partial"
    else:
        status = "passed"

    raw_package["analysis_meta"]["validator_status"] = status
    raw_package["analysis_meta"]["validator_errors"] = errors
    raw_package["quality_flags"] = _dedupe_flags(flags)

    return AnalyzerV4ValidationResult(
        package=raw_package,
        is_valid=not errors,
        validator_status=status,
        errors=errors,
        quality_flags=raw_package["quality_flags"],
        failure_code="schema_validation_failed" if errors else None,
        failure_message="; ".join(errors) if errors else None,
    )


def stage_analyzer_v4_result(
    *,
    llm_result: Any,
    response_text: str,
    response_id: int,
    query_id: int | None,
    model: str | None,
    prompt_version: str | None,
    citation_mappings: list[Any] | None = None,
    created_at: str | None = None,
) -> AnalyzerV4ValidationResult:
    parse_status = str(getattr(llm_result, "parse_status", "ok") or "ok")
    parse_error = getattr(llm_result, "parse_error", None)
    raw_output = getattr(llm_result, "raw_output", None)
    raw_json = getattr(llm_result, "raw_json", None)
    raw_hash = _hash_output(raw_output if raw_output is not None else raw_json)

    if parse_status not in {"ok", "json_repaired"}:
        code = "invalid_json" if parse_status == "invalid_json" else parse_status
        result = validate_analyzer_v4_package(
            _failed_package(
                response_id=response_id,
                query_id=query_id,
                code=code,
                message=str(parse_error or "Analyzer output could not be parsed."),
                model=model,
                prompt_version=prompt_version,
                created_at=created_at,
            ),
            response_text=response_text,
            response_id=response_id,
            query_id=query_id,
        )
        result.is_valid = False
        result.validator_status = "failed"
        result.failure_code = code
        result.failure_message = str(parse_error or "Analyzer output could not be parsed.")
        result.package["analysis_meta"]["validator_status"] = "failed"
        result.package["analysis_meta"]["validator_errors"] = [result.failure_message]
        result.raw_output_sha256 = raw_hash
        return result

    package = (
        deepcopy(raw_json)
        if isinstance(raw_json, dict) and _looks_like_v4(raw_json)
        else _legacy_to_v4_package(
            llm_result=llm_result,
            response_text=response_text,
            response_id=response_id,
            query_id=query_id,
            model=model,
            prompt_version=prompt_version,
            citation_mappings=citation_mappings or [],
            created_at=created_at,
        )
    )
    if parse_status == "json_repaired" or bool(getattr(llm_result, "json_repaired", False)):
        package.setdefault("quality_flags", []).append(
            {
                "flag_key": "flag_json_repaired",
                "severity": "warning",
                "code": "json_repaired",
                "message": "Analyzer output required JSON repair before validation.",
                "target_type": "analysis",
                "target_key": None,
                "blocks_metric_readiness": False,
            }
        )
    result = validate_analyzer_v4_package(
        package,
        response_text=response_text,
        response_id=response_id,
        query_id=query_id,
    )
    result.raw_output_sha256 = raw_hash
    return result


def _failed_package(
    *,
    response_id: int,
    query_id: int | None,
    code: str,
    message: str,
    model: str | None = None,
    prompt_version: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    return {
        "analysis_meta": {
            "schema_version": ANALYZER_V4_SCHEMA_VERSION,
            "language": "mixed",
            "response_quality": "invalid",
            "model": model,
            "prompt_version": prompt_version,
            "input_response_id": response_id,
            "input_query_id": query_id,
            "created_at": created_at or _utcnow_iso(),
            "validator_status": "failed",
            "validator_errors": [message],
        },
        "entities": [],
        "mentions": [],
        "sentiment_drivers": [],
        "product_features": [],
        "relations": [],
        "citations": [],
        "quality_flags": [
            {
                "flag_key": f"flag_{_slug(code)}_analysis",
                "severity": "error",
                "code": code,
                "message": message,
                "target_type": "analysis",
                "target_key": None,
                "blocks_metric_readiness": True,
            }
        ],
    }


def _legacy_to_v4_package(
    *,
    llm_result: Any,
    response_text: str,
    response_id: int,
    query_id: int | None,
    model: str | None,
    prompt_version: str | None,
    citation_mappings: list[Any],
    created_at: str | None,
) -> dict[str, Any]:
    raw_json = getattr(llm_result, "raw_json", None)
    brands = list(getattr(llm_result, "brands", []) or [])
    entities: list[dict[str, Any]] = []
    mentions: list[dict[str, Any]] = []
    drivers: list[dict[str, Any]] = []
    features: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    quality_flags: list[dict[str, Any]] = []
    brand_keys: dict[str, str] = {}
    product_keys: dict[tuple[str, str], str] = {}

    for index, brand in enumerate(brands):
        brand_name = getattr(brand, "brand_name", "") or "unknown"
        product_name = getattr(brand, "product_name", None)
        brand_key = brand_keys.setdefault(
            _identity(brand_name), f"ent_brand_{_slug(brand_name)}"
        )
        if not any(entity.get("entity_key") == brand_key for entity in entities):
            entities.append(
                {
                    "entity_key": brand_key,
                    "entity_type": "brand",
                    "raw_name": brand_name,
                    "canonical_id": None,
                    "canonical_name": brand_name,
                    "canonicalization_status": "suggested",
                    "evidence_quote": _snippet(response_text, brand_name),
                    "confidence": 0.8,
                    "quality_flags": [],
                }
            )
        target_entity_key = brand_key
        mention_type = "brand"
        if product_name:
            product_key = product_keys.setdefault(
                (_identity(brand_name), _identity(product_name)),
                f"ent_product_{_slug(brand_name)}_{_slug(product_name)}",
            )
            if not any(entity.get("entity_key") == product_key for entity in entities):
                entities.append(
                    {
                        "entity_key": product_key,
                        "entity_type": "product",
                        "raw_name": product_name,
                        "canonical_id": None,
                        "canonical_name": None,
                        "canonicalization_status": "unresolved",
                        "evidence_quote": _snippet(response_text, product_name) or _snippet(response_text, brand_name),
                        "confidence": 0.75,
                        "quality_flags": ["product_unresolved"],
                    }
                )
            target_entity_key = product_key
            mention_type = "product"

        mention_key = f"mention_{index}_{_slug(brand_name)}"
        mentions.append(
            {
                "mention_key": mention_key,
                "entity_key": target_entity_key,
                "response_id": response_id,
                "raw_text": product_name or brand_name,
                "normalized_text": product_name or brand_name,
                "mention_type": mention_type,
                "position": _legacy_position(getattr(brand, "position_type", None)),
                "sentiment_label": _legacy_sentiment(getattr(brand, "sentiment", None)),
                "sentiment_score": getattr(brand, "sentiment_score", None),
                "evidence_quote": _snippet(response_text, product_name or brand_name),
                "confidence": 0.8,
                "quality_flags": [],
            }
        )
        for driver_index, driver in enumerate(getattr(brand, "sentiment_drivers", []) or []):
            drivers.append(
                {
                    "driver_key": f"driver_{index}_{driver_index}_{_slug(getattr(driver, 'category', None))}",
                    "mention_key": mention_key,
                    "target_entity_key": target_entity_key,
                    "sentiment_label": _legacy_sentiment(getattr(driver, "polarity", None)),
                    "driver_type": _legacy_driver_type(getattr(driver, "category", None)),
                    "driver_summary": getattr(driver, "driver_text", "") or "",
                    "evidence_quote": getattr(driver, "source_quote", "") or "",
                    "confidence": float(getattr(driver, "strength", 0.5) or 0.5),
                    "quality_flags": [],
                }
            )
        for feature_index, feature in enumerate(getattr(brand, "product_features", []) or []):
            features.append(
                {
                    "feature_key": f"feature_{index}_{feature_index}_{_slug(getattr(feature, 'feature_name', None))}",
                    "product_entity_key": target_entity_key,
                    "brand_entity_key": brand_key,
                    "feature_type": "other",
                    "feature_name": getattr(feature, "feature_name", "") or "feature",
                    "feature_value": None,
                    "evidence_quote": getattr(feature, "context_snippet", "") or "",
                    "confidence": 0.7,
                    "quality_flags": [],
                }
            )

    for index, item in enumerate(_legacy_relations(raw_json)):
        relation_type = str(item.get("relation_type") or item.get("type") or "other")
        subject_name = str(item.get("subject_name") or item.get("a_name") or "")
        object_name = str(item.get("object_name") or item.get("b_name") or "")
        subject_key = _find_entity_key(entities, subject_name)
        object_key = _find_entity_key(entities, object_name)
        relation_flags = []
        if not subject_key or not object_key:
            relation_flags.append("relation_unresolved")
        relations.append(
            {
                "relation_key": str(item.get("relation_key") or f"relation_{index}_{_slug(relation_type)}"),
                "subject_entity_key": subject_key or f"unresolved_subject_{index}",
                "relation_type": relation_type if relation_type in RELATION_TYPES else "other",
                "object_entity_key": object_key or f"unresolved_object_{index}",
                "direction": str(item.get("direction") or "directed"),
                "evidence_quote": str(item.get("evidence_quote") or item.get("evidence") or ""),
                "confidence": float(item.get("confidence") or 0.5),
                "quality_flags": relation_flags,
            }
        )

    citations = []
    for index, mapping in enumerate(citation_mappings):
        citation_key = f"citation_{index + 1}"
        citations.append(
            {
                "citation_key": citation_key,
                "url": getattr(mapping, "url", None),
                "domain": getattr(mapping, "domain", None),
                "title": getattr(mapping, "title", None),
                "source_type": _legacy_source_type(getattr(mapping, "source_type", None)),
                "attribution_method": "official_domain"
                if getattr(mapping, "source_type", None) == "official_site"
                else "co_occurrence",
                "mentioned_entity_keys": [
                    key
                    for name, key in brand_keys.items()
                    if _identity(getattr(mapping, "brand_name", None)) == name
                ],
                "linked_fact_keys": [],
                "evidence_quote": getattr(mapping, "title", None) or getattr(mapping, "domain", None) or "",
                "confidence": 0.7,
                "quality_flags": ["citation_unlinked"],
            }
        )

    return {
        "analysis_meta": {
            "schema_version": ANALYZER_V4_SCHEMA_VERSION,
            "language": "mixed",
            "response_quality": "ok" if brands else "partial",
            "model": model,
            "prompt_version": prompt_version,
            "input_response_id": response_id,
            "input_query_id": query_id,
            "created_at": created_at or _utcnow_iso(),
            "validator_status": "passed",
            "validator_errors": [],
        },
        "entities": entities,
        "mentions": mentions,
        "sentiment_drivers": drivers,
        "product_features": features,
        "relations": relations,
        "citations": citations,
        "quality_flags": quality_flags,
    }


def _ensure_v4_shape(package: dict[str, Any], *, response_id: int, query_id: int | None) -> None:
    package.setdefault("analysis_meta", {})
    meta = package["analysis_meta"] if isinstance(package["analysis_meta"], dict) else {}
    meta.setdefault("schema_version", ANALYZER_V4_SCHEMA_VERSION)
    meta.setdefault("language", "mixed")
    meta.setdefault("response_quality", "ok")
    meta.setdefault("model", None)
    meta.setdefault("prompt_version", None)
    meta.setdefault("input_response_id", response_id)
    meta.setdefault("input_query_id", query_id)
    meta.setdefault("created_at", _utcnow_iso())
    meta.setdefault("validator_status", "passed")
    meta.setdefault("validator_errors", [])
    package["analysis_meta"] = meta
    for key in TOP_LEVEL_KEYS[1:]:
        package.setdefault(key, [])


def _looks_like_v4(raw_json: dict[str, Any]) -> bool:
    return any(key in raw_json for key in TOP_LEVEL_KEYS) and "analysis_meta" in raw_json


def _objects(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _drop_malformed_mentions(package: dict[str, Any], flags: list[dict[str, Any]]) -> None:
    _drop_malformed_required_fact_rows(
        package,
        flags,
        collection_key="mentions",
        key_field="mention_key",
        fallback_prefix="mention",
        target_type="mention",
        flag_code="malformed_mention_dropped",
        label="Mention",
        required_fields=("mention_type", "position", "sentiment_label", "confidence"),
        numeric_fields=("confidence",),
    )


def _drop_malformed_sentiment_drivers(
    package: dict[str, Any],
    flags: list[dict[str, Any]],
) -> None:
    _drop_malformed_required_fact_rows(
        package,
        flags,
        collection_key="sentiment_drivers",
        key_field="driver_key",
        fallback_prefix="driver",
        target_type="driver",
        flag_code="malformed_sentiment_driver_dropped",
        label="Sentiment driver",
        required_fields=("sentiment_label", "driver_type", "confidence"),
        numeric_fields=("confidence",),
    )


def _drop_malformed_citations(
    package: dict[str, Any],
    flags: list[dict[str, Any]],
) -> None:
    _drop_malformed_required_fact_rows(
        package,
        flags,
        collection_key="citations",
        key_field="citation_key",
        fallback_prefix="citation",
        target_type="citation",
        flag_code="malformed_citation_dropped",
        label="Citation",
        required_fields=("source_type", "attribution_method", "confidence"),
        numeric_fields=("confidence",),
    )


def _drop_malformed_relations(
    package: dict[str, Any],
    flags: list[dict[str, Any]],
) -> None:
    _drop_malformed_required_fact_rows(
        package,
        flags,
        collection_key="relations",
        key_field="relation_key",
        fallback_prefix="relation",
        target_type="relation",
        flag_code="malformed_relation_dropped",
        label="Relation",
        required_fields=("confidence",),
        numeric_fields=("confidence",),
    )


def _drop_malformed_product_features(
    package: dict[str, Any],
    flags: list[dict[str, Any]],
) -> None:
    _drop_malformed_required_fact_rows(
        package,
        flags,
        collection_key="product_features",
        key_field="feature_key",
        fallback_prefix="feature",
        target_type="feature",
        flag_code="malformed_product_feature_dropped",
        label="Product feature",
        required_fields=("confidence",),
        numeric_fields=("confidence",),
    )


def _drop_malformed_required_fact_rows(
    package: dict[str, Any],
    flags: list[dict[str, Any]],
    *,
    collection_key: str,
    key_field: str,
    fallback_prefix: str,
    target_type: str,
    flag_code: str,
    label: str,
    required_fields: tuple[str, ...],
    numeric_fields: tuple[str, ...] = (),
) -> None:
    rows = package.get(collection_key)
    if not isinstance(rows, list):
        return

    kept: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        invalid_fields = [
            field for field in required_fields if row.get(field) is None
        ]
        invalid_fields.extend(
            field
            for field in numeric_fields
            if row.get(field) is not None and not _is_numeric(row.get(field))
        )
        if not invalid_fields:
            for field in numeric_fields:
                row[field] = float(row[field])
            kept.append(row)
            continue

        key = str(row.get(key_field) or f"{fallback_prefix}_{index}")
        row[key_field] = key
        _append_flag(
            flags,
            code=flag_code,
            severity="error",
            message=(
                f"{label} was dropped because required fields were null "
                f"or invalid: {', '.join(dict.fromkeys(invalid_fields))}."
            ),
            target_type=target_type,
            target_key=key,
            blocks_metric_readiness=True,
        )
    package[collection_key] = kept


def _drop_unsupported_sentiment_driver_types(
    package: dict[str, Any],
    flags: list[dict[str, Any]],
) -> None:
    drivers = package.get("sentiment_drivers")
    if not isinstance(drivers, list):
        return

    kept: list[dict[str, Any]] = []
    for index, driver in enumerate(drivers):
        if not isinstance(driver, dict):
            continue
        if driver.get("driver_type") in DRIVER_TYPES:
            kept.append(driver)
            continue

        key = str(driver.get("driver_key") or f"driver_{index}")
        driver["driver_key"] = key
        _append_flag(
            flags,
            code="unsupported_sentiment_driver_type_dropped",
            severity="error",
            message=(
                "Sentiment driver was dropped because driver_type="
                f"{driver.get('driver_type')!r} is not supported by analyzer_v4."
            ),
            target_type="driver",
            target_key=key,
            blocks_metric_readiness=True,
        )
    package["sentiment_drivers"] = kept


def _drop_category_product_features(
    package: dict[str, Any],
    flags: list[dict[str, Any]],
) -> None:
    features = package.get("product_features")
    if not isinstance(features, list):
        return

    kept: list[dict[str, Any]] = []
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            continue
        if feature.get("feature_type") not in CATEGORY_PRODUCT_FEATURE_TYPES:
            kept.append(feature)
            continue

        key = str(feature.get("feature_key") or f"feature_{index}")
        feature["feature_key"] = key
        _append_flag(
            flags,
            code="unsupported_product_feature_type_dropped",
            severity="error",
            message=(
                "Product feature was dropped because feature_type='category' "
                "belongs in category entities, mentions, or relations."
            ),
            target_type="feature",
            target_key=key,
            blocks_metric_readiness=True,
        )
    package["product_features"] = kept


def _normalize_or_drop_relation_types(
    package: dict[str, Any],
    flags: list[dict[str, Any]],
) -> None:
    relations = package.get("relations")
    if not isinstance(relations, list):
        return

    entity_types = {
        str(entity.get("entity_key") or ""): str(entity.get("entity_type") or "")
        for entity in _objects(package.get("entities") or [])
    }

    kept: list[dict[str, Any]] = []
    for index, relation in enumerate(relations):
        if not isinstance(relation, dict):
            continue
        key = str(relation.get("relation_key") or f"relation_{index}")
        relation["relation_key"] = key
        relation_type = relation.get("relation_type")
        if relation_type in RELATION_TYPES:
            kept.append(relation)
            continue
        if relation_type in RELATION_TYPE_ALIASES:
            object_type = entity_types.get(str(relation.get("object_entity_key") or ""))
            normalized = (
                "belongs_to_brand"
                if relation_type == "belongs_to" and object_type == "brand"
                else "has_attribute"
            )
            relation["relation_type"] = normalized
            _append_flag(
                flags,
                code="relation_type_normalized",
                severity="warning",
                message=(
                    f"Relation type {relation_type!r} was normalized to "
                    f"{normalized!r} to match analyzer_v4 relation schema."
                ),
                target_type="relation",
                target_key=key,
                blocks_metric_readiness=True,
                flag_key=f"flag_relation_type_normalized_relation_{_slug(key)}",
            )
            kept.append(relation)
            continue

        _append_flag(
            flags,
            code="unsupported_relation_type_dropped",
            severity="error",
            message=(
                "Relation was dropped because relation_type="
                f"{relation_type!r} is not supported by analyzer_v4."
            ),
            target_type="relation",
            target_key=key,
            blocks_metric_readiness=True,
        )
    package["relations"] = kept


def _quality_codes(item: dict[str, Any]) -> set[str]:
    codes = set()
    for flag in item.get("quality_flags") or []:
        if isinstance(flag, dict):
            codes.add(str(flag.get("code") or ""))
        else:
            codes.add(str(flag))
    return codes


def _unresolved_entity_code(entity_type: Any) -> str:
    value = str(entity_type or "entity")
    if value == "brand":
        return "brand_unresolved"
    if value == "product":
        return "product_unresolved"
    if value == "category":
        return "category_unresolved"
    return "entity_unresolved"


def _append_flag(
    flags: list[dict[str, Any]],
    *,
    code: str,
    severity: str,
    message: str,
    target_type: str,
    target_key: Any,
    blocks_metric_readiness: bool,
    flag_key: Any = None,
) -> None:
    target = None if target_key in ("", None) else str(target_key)
    flags.append(
        {
            "flag_key": str(flag_key or f"flag_{_slug(code)}_{target_type}_{_slug(target)}"),
            "severity": severity,
            "code": code,
            "message": message,
            "target_type": target_type,
            "target_key": target,
            "blocks_metric_readiness": bool(blocks_metric_readiness),
        }
    )


def _dedupe_flags(flags: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str | None]] = set()
    deduped: list[dict[str, Any]] = []
    for flag in flags:
        key = (
            str(flag.get("code") or ""),
            str(flag.get("target_type") or ""),
            None if flag.get("target_key") is None else str(flag.get("target_key")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(flag)
    return deduped


def _flag_missing_evidence(
    flags: list[dict[str, Any]],
    item: dict[str, Any],
    target_type: str,
    target_key: str,
    *,
    response_text: str | None,
) -> None:
    evidence_quote = str(item.get("evidence_quote") or "").strip()
    if evidence_quote:
        if _evidence_quote_matches_response(evidence_quote, response_text):
            return
        _append_flag(
            flags,
            code="evidence_quote_mismatch",
            severity="warning",
            message=f"{target_type} evidence_quote is not present in response_text.",
            target_type=target_type,
            target_key=target_key,
            blocks_metric_readiness=True,
        )
        return
    _append_flag(
        flags,
        code="missing_evidence_quote",
        severity="warning",
        message=f"{target_type} is missing evidence_quote.",
        target_type=target_type,
        target_key=target_key,
        blocks_metric_readiness=True,
    )


def _evidence_quote_matches_response(evidence_quote: str, response_text: str | None) -> bool:
    quote = _normalize_evidence_text(evidence_quote)
    text = _normalize_evidence_text(response_text)
    return bool(quote and text and quote in text)


def _normalize_evidence_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def _validate_enum(
    item: dict[str, Any],
    field_name: str,
    allowed: set[str],
    errors: list[str],
    path: str,
) -> None:
    value = item.get(field_name)
    if value not in allowed:
        errors.append(f"schema_validation_failed: {path}.{field_name}={value!r} is invalid")


def _validate_confidence(item: dict[str, Any], errors: list[str], path: str) -> None:
    try:
        value = float(item.get("confidence"))
    except (TypeError, ValueError):
        errors.append(f"schema_validation_failed: {path}.confidence must be numeric")
        return
    if not 0 <= value <= 1:
        errors.append(f"schema_validation_failed: {path}.confidence must be between 0 and 1")


def _is_numeric(value: Any) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def _require_string(item: dict[str, Any], field_name: str, errors: list[str], path: str) -> None:
    if not str(item.get(field_name) or "").strip():
        errors.append(f"schema_validation_failed: {path}.{field_name} is required")


def _hash_output(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        raw = value
    else:
        raw = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _legacy_relations(raw_json: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_json, dict):
        return []
    for key in ("relations", "response_relations", "relation_facts"):
        value = raw_json.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _find_entity_key(entities: list[dict[str, Any]], raw_name: str | None) -> str | None:
    wanted = _identity(raw_name)
    if not wanted:
        return None
    for entity in entities:
        if _identity(entity.get("raw_name")) == wanted or _identity(entity.get("canonical_name")) == wanted:
            return str(entity.get("entity_key"))
    return None


def _snippet(response_text: str | None, term: str | None) -> str:
    text = response_text or ""
    term = (term or "").strip()
    if not text or not term:
        return ""
    index = text.lower().find(term.lower())
    if index < 0:
        return ""
    start = max(index - 40, 0)
    end = min(index + len(term) + 80, len(text))
    return text[start:end].strip()


def _legacy_position(value: str | None) -> str:
    value = (value or "").lower()
    if value in {"first_recommendation", "comparison_winner", "listed"}:
        return "top"
    if value == "mentioned_only":
        return "middle"
    if value == "comparison_loser":
        return "tail"
    return "unknown"


def _legacy_sentiment(value: str | None) -> str:
    value = (value or "").lower()
    if value in SENTIMENT_LABELS:
        return value
    if value in {"pos", "plus"}:
        return "positive"
    if value in {"neg", "minus"}:
        return "negative"
    return "unknown" if not value else "neutral"


def _legacy_driver_type(value: str | None) -> str:
    value = (value or "").lower()
    if value in DRIVER_TYPES:
        return value
    if value in {"product_feature", "ux", "brand_image", "innovation"}:
        return "benefit"
    return "other"


def _legacy_source_type(value: str | None) -> str:
    value = (value or "").lower()
    if value == "official_site":
        return "official"
    if value == "review_site":
        return "media"
    if value == "wiki":
        return "knowledge_base"
    if value in {"news", "media"}:
        return "media"
    if value in {"social", "ugc"}:
        return value
    return "other"


def _identity(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _slug(value: Any) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", str(value or "none").strip().lower()).strip("_")
    return slug or "none"
