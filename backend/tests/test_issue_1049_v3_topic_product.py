"""Issue #1049: `_as_v3_package` must derive a `topic_product` sub-block.

`/api/v1/projects/<id>/products` aggregates the `topic_product` block from
each in-scope analyzer package (rollups.py::_rollup_topic_product). PR #1043
emits that block from `geo_tracker/analyzer/fact_contract.py::_topic_product_package`
for v1 (`issue_602_v1`) packages, but the durable v3 schema produced by
`build_response_fact_package_v3` (fact_contract.py:114-189) never carried it.
Because BestCoffer prod stores v3 payloads, the rollup returned `None`,
the frontend `canUseMetricEvidence(data, 'product')` gate failed, and the
products page rendered blank (issue #1031).

The fix derives the sub-block from v3's existing fields:

  * `product_fact_count` — count of v3 `products[]` entries with a
    non-empty `product_name`, mirroring `_topic_product_package`'s
    `entity_facts` filter at fact_contract.py:812.
  * `topic_chain_count` — 1 when the v3 `topic` (or top-level
    `topic_id`/`prompt_id`/`query_id`) chain is complete, else 0
    (v3 = one response per package).
  * `status` / `product_status` — `"ok"` if `product_fact_count > 0`,
    else `"empty"`.
  * `topic_chain_missing_response_ids` — `[]` (v3 has no notion of this).
  * `reason_codes` — `[]` (v3 carries no per-fact reasons).
"""

from __future__ import annotations

from typing import Any

from app.api.v1.projects.contracts.package import _as_v3_package


def _v3_package_skeleton(*, response_id: int = 71001, analyzed: bool = True) -> dict[str, Any]:
    """Minimal v3 payload accepted by `_as_v3_package` — coverage block is
    the only structural requirement. Mirrors the fixture shape used by
    `tests/test_issue_687_bestcoffer_app_api_contract.py::_bestcoffer_package_v3`
    so this stays in lock-step with the canonical v3 contract."""
    status = "ok" if analyzed else "missing"
    return {
        "analyzer_version": "v3",
        "response_id": response_id,
        "query_id": response_id + 1,
        "prompt_id": response_id + 2,
        "topic_id": response_id + 3,
        "project_ids": [],
        "source_brand_id": 24,
        "target_brand_id": 24,
        "engine": "deepseek",
        "collected_at": "2026-05-12T08:00:00",
        "analysis_started_at": "2026-05-12T08:00:00",
        "analysis_completed_at": "2026-05-12T08:00:00",
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "prompt_version": "issue-1049-test",
        "raw_output_sha256": "abc123",
        "idempotency_key": f"{response_id}:v3:abc123",
        "eligibility": {
            "eligible": True,
            "success_response": analyzed,
            "invalid_reason": None,
            "missing_reason_codes": [],
        },
        "coverage": {
            "eligible_response_count_basis": 1,
            "analyzed": analyzed,
            "parse_status": "ok",
            "validation_errors": [],
        },
        "entities": {
            "target": {
                "brand_id": 24,
                "canonical_name": "BestCoffer",
                "mentioned": True,
                "mention_count": 1,
            },
            "configured_competitors": [],
            "response_named_brands": [],
        },
        "visibility": {
            "is_visible": True,
            "rank": 1,
            "position_type": "ranked_list",
            "visibility_score": 1.0,
            "formula_status": status,
            "reason_codes": [],
        },
        "sov": {
            "numerator_target_mentions": 1,
            "denominator_competitive_mentions": 1,
            "denominator_brand_ids": [],
            "denominator_raw_names": [],
            "formula_status": status,
            "reason_codes": [],
            "sample_response_ids": [response_id],
        },
        "sentiment": {
            "label": "positive",
            "score": 0.8,
            "drivers": [],
            "source_quotes": [],
            "formula_status": status,
            "reason_codes": [],
        },
        "citations": {
            "total_citations": 0,
            "attributed_citations": [],
            "unresolved_citations": [],
            "domains": [],
            "source_types": [],
            "formula_status": status,
            "reason_codes": [],
        },
        "rank": {
            "best_rank": 1,
            "rank_bucket": "top_3",
            "rank_basis": "position_rank",
            "formula_status": status,
            "reason_codes": [],
        },
        "topic": {
            "topic_id": response_id + 3,
            "topic_name": "BestCoffer espresso workflow",
            "dimension": "product",
            "associated_brand_id": 24,
            "prompt_id": response_id + 2,
            "query_id": response_id + 1,
        },
        "products": [],
        "topic_metrics": {
            "visible": True,
            "visibility_rate_basis": 1,
            "sentiment_basis": 1,
            "citation_basis": 0,
            "rank_basis": 1,
            "formula_status": status,
            "reason_codes": [],
        },
        "geo_pano": {
            "visibility_component": status,
            "sentiment_component": status,
            "sov_component": status,
            "citation_component": status,
            "geo_score": None,
            "pano_score": None,
            "formula_status": status,
            "reason_codes": [],
        },
    }


def test_v3_normalizer_derives_topic_product_when_products_present() -> None:
    """Case (i): v3 payload with >=1 product mention -> topic_product.status='ok',
    product_fact_count matches the number of entries with non-empty product_name.

    Mirrors `_topic_product_package` (fact_contract.py:812) which filters
    `entity_facts` on `_clean(f.get("product_name"))`. In v3 the equivalent
    list is the top-level `products[]` populated by `_v3_products`
    (fact_contract.py:460-472), which already applies the same filter.
    """
    package = _v3_package_skeleton()
    package["products"] = [
        {
            "product_name": "BestCoffer Filter",
            "brand_id": 24,
            "feature_name": None,
            "sentiment": None,
            "snippets": [],
            "formula_status": "ok",
        },
        {
            "product_name": "BestCoffer Espresso",
            "brand_id": 24,
            "feature_name": None,
            "sentiment": None,
            "snippets": [],
            "formula_status": "ok",
        },
        # An entry with empty product_name must NOT count (matches `_clean` semantics).
        {
            "product_name": "",
            "brand_id": 24,
            "feature_name": None,
            "sentiment": None,
            "snippets": [],
            "formula_status": "ok",
        },
    ]

    normalized = _as_v3_package({"analyzer_fact_package_v3": package})

    assert normalized is not None
    topic_product = normalized.get("topic_product")
    assert isinstance(topic_product, dict), (
        "topic_product must be derived for v3 packages so _rollup_topic_product picks it up"
    )
    assert topic_product["status"] == "ok"
    assert topic_product["product_status"] == "ok"
    assert topic_product["product_fact_count"] == 2
    assert topic_product["topic_chain_count"] == 1
    assert topic_product["topic_chain_missing_response_ids"] == []
    assert topic_product["reason_codes"] == []


def test_v3_normalizer_derives_topic_product_when_no_products() -> None:
    """Case (ii): v3 payload with zero product mentions ->
    topic_product.status='empty', product_fact_count=0.
    """
    package = _v3_package_skeleton()
    package["products"] = []

    normalized = _as_v3_package({"analyzer_fact_package_v3": package})

    assert normalized is not None
    topic_product = normalized["topic_product"]
    assert topic_product["status"] == "empty"
    assert topic_product["product_status"] == "empty"
    assert topic_product["product_fact_count"] == 0
    # Topic chain is still complete (topic_id/prompt_id/query_id all set),
    # so chain_count remains 1 — this matches v1 semantics.
    assert topic_product["topic_chain_count"] == 1


def test_v3_normalizer_handles_malformed_payload_without_crashing() -> None:
    """Case (iii): malformed payloads must NOT crash the normalizer.

    Variants we exercise:
      - Empty payload: not a v3 package -> normalizer returns None
        (no `topic_product` to assert; verifies the early-return path).
      - Missing `coverage`: again returns None.
      - `products` is not a list (corrupt fixture): topic_product is
        still derived with `product_fact_count=0`.
      - Missing `topic`/topic_id chain: topic_chain_count falls to 0.
    """
    # Empty payload — no v3 key at all
    assert _as_v3_package({}) is None
    # v3 key present but `analyzer_version` is wrong
    assert _as_v3_package({"analyzer_fact_package_v3": {"analyzer_version": "v2"}}) is None
    # Missing coverage block
    assert _as_v3_package({"analyzer_fact_package_v3": {"analyzer_version": "v3"}}) is None

    # Corrupt `products` (not a list)
    package = _v3_package_skeleton()
    package["products"] = "not-a-list"  # type: ignore[assignment]
    normalized = _as_v3_package({"analyzer_fact_package_v3": package})
    assert normalized is not None
    assert normalized["topic_product"]["product_fact_count"] == 0
    assert normalized["topic_product"]["status"] == "empty"

    # Missing topic chain entirely
    package = _v3_package_skeleton()
    package.pop("topic", None)
    package["topic_id"] = None
    package["prompt_id"] = None
    package["query_id"] = None
    normalized = _as_v3_package({"analyzer_fact_package_v3": package})
    assert normalized is not None
    assert normalized["topic_product"]["topic_chain_count"] == 0
    assert normalized["topic_product"]["product_fact_count"] == 0
    assert normalized["topic_product"]["status"] == "empty"


def test_v3_normalizer_preserves_explicit_topic_product_block() -> None:
    """If a future v3 fixture starts emitting `topic_product` directly,
    the normalizer must NOT clobber it. The derivation only runs when
    the key is absent."""
    package = _v3_package_skeleton()
    package["products"] = [
        {
            "product_name": "Already counted",
            "brand_id": 24,
            "feature_name": None,
            "sentiment": None,
            "snippets": [],
            "formula_status": "ok",
        },
    ]
    package["topic_product"] = {
        "status": "partial",
        "topic_chain_count": 99,
        "product_fact_count": 42,
        "topic_chain_missing_response_ids": [1, 2],
        "product_status": "partial",
        "reason_codes": ["pre_existing"],
    }

    normalized = _as_v3_package({"analyzer_fact_package_v3": package})

    assert normalized is not None
    # Explicit block survives unchanged — derivation does not overwrite.
    assert normalized["topic_product"]["status"] == "partial"
    assert normalized["topic_product"]["product_fact_count"] == 42
    assert normalized["topic_product"]["topic_chain_count"] == 99
    assert normalized["topic_product"]["reason_codes"] == ["pre_existing"]
