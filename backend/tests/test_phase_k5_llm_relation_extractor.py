"""Phase K.5 — LLM relation extractor smoke + fallback tests.

Verifies:
  - When the LLM is disabled (`GENPANO_KG_LLM_DISABLED=1`) the extractor
    falls through to the regex extractor and still produces results.
  - `_normalize_llm_output` handles malformed / partial LLM output without
    raising (silent skip of bad rows).
  - Symmetric edges (COMPETES_WITH, PAIRS_WITH) get id-sorted so dedup
    downstream sees a canonical form.
  - The cache key is deterministic for the same input.
"""

from __future__ import annotations

import pytest

from app.kg.llm_relation_extractor import (
    _cache_key,
    _normalize_llm_output,
    extract_relations_llm,
)


@pytest.mark.asyncio
async def test_falls_back_to_regex_when_llm_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GENPANO_KG_LLM_DISABLED", "1")
    monkeypatch.setenv("GENPANO_KG_LLM_NO_REDIS", "1")
    text = "雅诗兰黛 vs 兰蔻 哪个更适合干皮?"
    brand_index = {"雅诗兰黛": 1001, "兰蔻": 1002}
    result = await extract_relations_llm(text, brand_index=brand_index)
    # Regex extractor should pick up the COMPETES_WITH relation
    assert any(r["type"] == "COMPETES_WITH" for r in result), result


def test_normalize_skips_malformed_rows() -> None:
    raw = [
        {"a_name": "A", "b_name": "B", "type": "COMPETES_WITH", "confidence": 0.9},
        {"a_name": "Unknown", "b_name": "B", "type": "COMPETES_WITH"},  # unknown brand
        {"a_name": "A", "b_name": "A", "type": "COMPETES_WITH"},  # self-edge
        {"a_name": "A", "b_name": "B", "type": "BOGUS_TYPE"},  # invalid type
        "not a dict",  # malformed
    ]
    out = _normalize_llm_output(
        raw,  # type: ignore[arg-type]
        brand_index={"A": 1, "B": 2},
        entity_kind="brand",
        source_id="resp-1",
    )
    assert len(out) == 1
    assert out[0]["a_id"] == 1 and out[0]["b_id"] == 2
    assert out[0]["confidence"] == 0.9
    assert out[0]["evidence"]["extractor"] == "llm_v1"
    assert out[0]["evidence"]["source_id"] == "resp-1"


def test_normalize_sorts_symmetric_edges() -> None:
    raw = [
        {"a_name": "B", "b_name": "A", "type": "COMPETES_WITH", "confidence": 0.8},
    ]
    out = _normalize_llm_output(
        raw,
        brand_index={"A": 1, "B": 2},
        entity_kind="brand",
        source_id=None,
    )
    assert len(out) == 1
    # 1 < 2; symmetric edge canonicalized to (1, 2)
    assert out[0]["a_id"] == 1
    assert out[0]["b_id"] == 2


def test_normalize_keeps_directional_edges() -> None:
    raw = [
        # SAME_GROUP is directional: a is parent, b is child
        {"a_name": "B", "b_name": "A", "type": "SAME_GROUP", "confidence": 0.9},
    ]
    out = _normalize_llm_output(
        raw,
        brand_index={"A": 1, "B": 2},
        entity_kind="brand",
        source_id=None,
    )
    assert len(out) == 1
    assert out[0]["a_id"] == 2
    assert out[0]["b_id"] == 1


def test_cache_key_deterministic() -> None:
    text = "Some text"
    bi = {"A": 1, "B": 2}
    k1 = _cache_key(text, bi)
    k2 = _cache_key(text, dict(reversed(list(bi.items()))))
    assert k1 == k2, "cache key should be order-independent"
    k3 = _cache_key(text + "x", bi)
    assert k1 != k3
