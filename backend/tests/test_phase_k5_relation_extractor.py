"""Phase K.5 — deterministic relation extractor unit tests."""

from __future__ import annotations

import pytest

from app.kg import extract_relations

# ── empty / edge cases ───────────────────────────────────


def test_empty_text_returns_empty():
    assert extract_relations("", brand_index={"Acme": 1, "Beta": 2}) == []


def test_empty_brand_index_returns_empty():
    assert extract_relations("Acme vs Beta", brand_index={}) == []


def test_single_brand_returns_empty():
    """Need at least 2 distinct brand mentions to extract a relation."""
    assert extract_relations("Acme is the best", brand_index={"Acme": 1, "Beta": 2}) == []


def test_self_pair_excluded():
    """Same brand on both sides shouldn't produce a candidate."""
    out = extract_relations("Acme vs Acme", brand_index={"Acme": 1})
    assert out == []


# ── COMPETES_WITH ────────────────────────────────────────


def test_extracts_vs_pattern():
    out = extract_relations(
        "Acme vs Beta — which is better?",
        brand_index={"Acme": 1, "Beta": 2},
    )
    assert len(out) == 1
    rel = out[0]
    assert rel["type"] == "COMPETES_WITH"
    assert {rel["a_id"], rel["b_id"]} == {1, 2}
    assert rel["confidence"] >= 0.75


def test_extracts_chinese_competition_pattern():
    out = extract_relations(
        "Acme 和 Beta 哪个更好",
        brand_index={"Acme": 1, "Beta": 2},
    )
    assert len(out) == 1
    assert out[0]["type"] == "COMPETES_WITH"


def test_competes_with_is_symmetric():
    """COMPETES_WITH dedupes by sorted ids regardless of order in text."""
    out = extract_relations(
        "Acme vs Beta. Beta vs Acme.",
        brand_index={"Acme": 1, "Beta": 2},
    )
    assert len(out) == 1
    assert (out[0]["a_id"], out[0]["b_id"]) == (1, 2)


# ── SAME_GROUP ───────────────────────────────────────────


def test_extracts_same_group_directional():
    out = extract_relations(
        "Acme 旗下 Beta 是其子品牌",
        brand_index={"Acme": 1, "Beta": 2},
    )
    matches = [r for r in out if r["type"] == "SAME_GROUP"]
    assert len(matches) == 1
    rel = matches[0]
    # Directional: A is parent
    assert rel["a_id"] == 1
    assert rel["b_id"] == 2


def test_extracts_owns_english():
    out = extract_relations(
        "Acme owns Beta",
        brand_index={"Acme": 1, "Beta": 2},
    )
    matches = [r for r in out if r["type"] == "SAME_GROUP"]
    assert len(matches) == 1
    assert matches[0]["a_id"] == 1
    assert matches[0]["b_id"] == 2


# ── SUBSTITUTES ──────────────────────────────────────────


def test_extracts_substitutes_directional():
    out = extract_relations(
        "Beta 是 Acme 的平替",
        brand_index={"Acme": 1, "Beta": 2},
    )
    matches = [r for r in out if r["type"] == "SUBSTITUTES"]
    assert len(matches) == 1
    rel = matches[0]
    # Beta is the alternative → Beta=2 is a, Acme=1 is b
    assert rel["a_id"] == 2
    assert rel["b_id"] == 1


# ── UPGRADES_TO ──────────────────────────────────────────


def test_extracts_upgrades_to():
    out = extract_relations(
        "Acme 升级到 Beta",
        brand_index={"Acme": 1, "Beta": 2},
    )
    matches = [r for r in out if r["type"] == "UPGRADES_TO"]
    assert len(matches) == 1
    rel = matches[0]
    assert rel["a_id"] == 1
    assert rel["b_id"] == 2


# ── PAIRS_WITH ───────────────────────────────────────────


def test_extracts_pairs_with():
    out = extract_relations(
        "Acme 搭配 Beta 一起使用效果更好",
        brand_index={"Acme": 1, "Beta": 2},
    )
    matches = [r for r in out if r["type"] == "PAIRS_WITH"]
    assert len(matches) == 1


# ── evidence dict ────────────────────────────────────────


def test_evidence_contains_snippet_and_source():
    out = extract_relations(
        "Acme vs Beta is the question",
        brand_index={"Acme": 1, "Beta": 2},
        source_id="resp-123",
    )
    assert len(out) == 1
    ev = out[0]["evidence"]
    assert "Acme" in ev["text_snippet"] or "vs" in ev["text_snippet"]
    assert ev["source_id"] == "resp-123"
    assert ev["pattern_type"] == "COMPETES_WITH"


def test_no_source_id_omits_field():
    out = extract_relations(
        "Acme vs Beta",
        brand_index={"Acme": 1, "Beta": 2},
    )
    assert "source_id" not in out[0]["evidence"]


# ── deduplication ────────────────────────────────────────


def test_dedupes_keeping_highest_confidence():
    """Same pair + type, two patterns match — keep the higher-confidence one."""
    text = "Acme vs Beta. Acme 对比 Beta."
    out = extract_relations(text, brand_index={"Acme": 1, "Beta": 2})
    competing = [r for r in out if r["type"] == "COMPETES_WITH"]
    assert len(competing) == 1
    # 'vs' has confidence 0.85, '对比' has 0.75 → keep 0.85
    assert competing[0]["confidence"] == pytest.approx(0.85)


# ── product entity_kind passthrough ──────────────────────


def test_entity_kind_product():
    out = extract_relations(
        "iPhone vs Pixel",
        brand_index={"iPhone": 100, "Pixel": 200},
        entity_kind="product",
    )
    assert len(out) == 1
    assert out[0]["entity_kind"] == "product"


# ── case-insensitive brand matching ──────────────────────


def test_case_insensitive_brand_match():
    out = extract_relations(
        "ACME VS BETA",
        brand_index={"Acme": 1, "Beta": 2},
    )
    assert len(out) == 1
    assert out[0]["type"] == "COMPETES_WITH"


# ── multiple distinct relations in one text ──────────────


def test_multiple_relations_in_one_text():
    text = "Acme vs Beta. Charlie 旗下 Delta."
    out = extract_relations(
        text,
        brand_index={"Acme": 1, "Beta": 2, "Charlie": 3, "Delta": 4},
    )
    types = {r["type"] for r in out}
    assert "COMPETES_WITH" in types
    assert "SAME_GROUP" in types
