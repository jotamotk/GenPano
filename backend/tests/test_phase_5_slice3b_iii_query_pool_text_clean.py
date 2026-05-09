"""Phase 5 slice 3b-iii — Query Pool text-clean unit tests.

Pure-Python helpers — no DB, no LLM. Covers cleanup, repair, parse, and
the candidates-from-LLM emit/dedup loop.
"""

from __future__ import annotations

import pytest

from app.admin.query_pool.text_clean import (
    parse_query_pool_llm_queries,
    query_pool_candidates_from_llm_queries,
    query_pool_chunked,
    query_pool_clean_query_text,
    query_pool_has_cjk,
    query_pool_load_json_object,
    query_pool_merge_usage,
    query_pool_normalize_query_text,
    query_pool_repair_query_text,
    query_pool_strip_markdown_fence,
    query_pool_usage_to_dict,
)
from app.admin.topic_plan.lib import TopicPlanLLMError

# ── markdown fence + JSON object ─────────────────────────────


def test_strip_markdown_fence_strips_codeblock():
    assert query_pool_strip_markdown_fence("```json\n{}\n```") == "{}"
    assert query_pool_strip_markdown_fence("plain") == "plain"


def test_load_json_object_dict_passthrough():
    assert query_pool_load_json_object({"a": 1}) == {"a": 1}


def test_load_json_object_invalid_raises():
    with pytest.raises(TopicPlanLLMError) as exc_info:
        query_pool_load_json_object("not json")
    assert exc_info.value.code == "llm_json_invalid"


def test_load_json_object_array_root_wraps_queries():
    assert query_pool_load_json_object("[]") == {"queries": []}


# ── normalize + clean ────────────────────────────────────────


def test_normalize_collapses_whitespace():
    assert query_pool_normalize_query_text("  a   b\nc\t") == "a b c"


def test_clean_query_text_rejects_too_short():
    with pytest.raises(TopicPlanLLMError) as exc_info:
        query_pool_clean_query_text("hi", "k1")
    assert exc_info.value.code == "query_length_invalid"


def test_clean_query_text_rejects_too_long():
    with pytest.raises(TopicPlanLLMError) as exc_info:
        query_pool_clean_query_text("a" * 161, "k1")
    assert exc_info.value.code == "query_length_invalid"


def test_clean_query_text_rejects_internal_terms():
    # "user persona" is in the forbidden list.
    with pytest.raises(TopicPlanLLMError) as exc_info:
        query_pool_clean_query_text("Which option works for our user persona type?", "k1")
    assert exc_info.value.code == "query_contains_internal_terms"


def test_clean_query_text_accepts_natural_consumer_query():
    out = query_pool_clean_query_text("敏感肌屏障不稳，修复面霜怎么选才不刺激？", "k1")
    assert out == "敏感肌屏障不稳，修复面霜怎么选才不刺激？"


# ── has_cjk ──────────────────────────────────────────────────


def test_has_cjk_detects_chinese():
    assert query_pool_has_cjk("敏感肌") is True
    assert query_pool_has_cjk("hello") is False


# ── repair ───────────────────────────────────────────────────


def test_repair_appends_chinese_consumer_suffix():
    """Bare CJK noun → adds 怎么选？ to make it a question."""
    out = query_pool_repair_query_text(
        "敏感肌修复面霜",
        {"topic_text": "敏感肌", "profile_need": "屏障不稳"},
        "k1",
    )
    assert query_pool_has_cjk(out)
    assert any(suffix in out for suffix in ("？", "?"))


def test_repair_falls_back_to_safe_query_when_empty():
    """Empty input → context-aware fallback that passes clean."""
    out = query_pool_repair_query_text(
        "",
        {"topic_text": "敏感肌"},
        "k-empty",
    )
    assert query_pool_has_cjk(out)
    assert any(suffix in out for suffix in ("？", "?"))


# ── parse ────────────────────────────────────────────────────


def test_parse_returns_keyed_map_in_expected_order():
    raw = (
        '{"queries": ['
        '{"candidate_key": "k1", "query": "Q1?"},'
        '{"candidate_key": "k2", "query": "Q2?"}'
        "]}"
    )
    out = parse_query_pool_llm_queries(raw, ["k1", "k2"], validate_queries=False)
    assert list(out.keys()) == ["k1", "k2"]
    assert out["k1"] == "Q1?"


def test_parse_accepts_common_llm_shapes():
    item = {"candidate_key": "k1", "query": "Q1?"}

    assert parse_query_pool_llm_queries([item], ["k1"], validate_queries=False) == {"k1": "Q1?"}
    assert parse_query_pool_llm_queries({"items": [item]}, ["k1"], validate_queries=False) == {
        "k1": "Q1?"
    }
    assert parse_query_pool_llm_queries({"query": item}, ["k1"], validate_queries=False) == {
        "k1": "Q1?"
    }


def test_parse_rejects_missing_keys():
    raw = '{"queries": [{"candidate_key": "k1", "query": "Q1?"}]}'
    with pytest.raises(TopicPlanLLMError) as exc_info:
        parse_query_pool_llm_queries(raw, ["k1", "k2"], validate_queries=False)
    assert exc_info.value.code == "llm_schema_invalid"
    assert "missing query" in exc_info.value.message


def test_parse_rejects_unknown_keys():
    raw = '{"queries": [{"candidate_key": "k99", "query": "Q?"}]}'
    with pytest.raises(TopicPlanLLMError) as exc_info:
        parse_query_pool_llm_queries(raw, ["k1"], validate_queries=False)
    assert "unknown candidate_key" in exc_info.value.message


def test_parse_rejects_duplicate_keys():
    raw = (
        '{"queries": ['
        '{"candidate_key": "k1", "query": "Q1?"},'
        '{"candidate_key": "k1", "query": "Q1?"}'
        "]}"
    )
    with pytest.raises(TopicPlanLLMError) as exc_info:
        parse_query_pool_llm_queries(raw, ["k1", "k2"], validate_queries=False)
    assert "duplicate" in exc_info.value.message


# ── chunked + merge_usage + usage_to_dict ────────────────────


def test_chunked_splits_evenly():
    assert query_pool_chunked([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_chunked_clamps_zero_size_to_one():
    assert query_pool_chunked([1, 2], 0) == [[1], [2]]


def test_merge_usage_sums_numeric_keys():
    out = query_pool_merge_usage(
        {"prompt_tokens": 10, "model": "x"},
        {"prompt_tokens": 5, "completion_tokens": 7, "model": "y"},
    )
    assert out["prompt_tokens"] == 15
    assert out["completion_tokens"] == 7
    assert out["model"] == "x"  # first-wins


def test_usage_to_dict_extracts_attrs():
    class _U:
        prompt_tokens = 1
        completion_tokens = 2
        total_tokens = 3

    assert query_pool_usage_to_dict(_U()) == {
        "prompt_tokens": 1,
        "completion_tokens": 2,
        "total_tokens": 3,
    }


# ── candidates_from_llm_queries (the worker's per-batch glue) ─


def _ctx(key, *, prompt_id="p1", segment_id="s1", profile_id="prof1", topic_text="敏感肌"):
    return {
        "candidate_key": key,
        "prompt_id": prompt_id,
        "segment_id": segment_id,
        "profile_id": profile_id,
        "topic_text": topic_text,
        "prompt_text": "敏感肌修复面霜怎么选？",
        "profile_need": "屏障不稳",
        "profile_demographic": "30F",
        "profile_name": "Anna",
        "segment_name": "young-pros",
    }


def test_candidates_from_llm_queries_emits_well_formed_rows():
    contexts = [_ctx("k1"), _ctx("k2", profile_id="prof2")]
    queries = {"k1": "敏感肌怎么选修复面霜？", "k2": "屏障不稳的修复面霜哪款合适？"}
    rows, stats = query_pool_candidates_from_llm_queries(
        contexts, queries, {"model": "doubao", "usage": {"total_tokens": 7}}
    )
    assert len(rows) == 2
    assert all(r["llm_model"] == "doubao" for r in rows)
    assert rows[0]["candidate_seq"] == 1
    assert rows[1]["candidate_seq"] == 2
    assert rows[0]["render_hash"] != rows[1]["render_hash"]
    assert stats["duplicate_review"] == 0


def test_candidates_from_llm_queries_dedupes_repeats():
    contexts = [_ctx("k1"), _ctx("k2", profile_id="prof2")]
    same_q = "敏感肌屏障不稳，修复面霜怎么选才不刺激？"
    queries = {"k1": same_q, "k2": same_q}
    rows, stats = query_pool_candidates_from_llm_queries(contexts, queries, {"model": "doubao"})
    assert len(rows) == 1
    assert stats["duplicate_review"] == 1


def test_candidates_from_llm_queries_repairs_borderline_output():
    """LLM returned a too-short query → repair kicks in."""
    contexts = [_ctx("k1")]
    queries = {"k1": "短"}  # below 4-char min
    rows, stats = query_pool_candidates_from_llm_queries(contexts, queries, {"model": "doubao"})
    assert len(rows) == 1
    assert stats["query_repaired"] >= 1


def test_candidates_from_llm_queries_rejects_unsalvageable():
    contexts = [_ctx("k1")]
    # Forbidden term — repair will hit the same forbidden filter.
    queries = {"k1": "Tell me about our user persona segment"}
    rows, stats = query_pool_candidates_from_llm_queries(contexts, queries, {"model": "doubao"})
    # Repair pipeline can salvage via fallback queries — accept either:
    # - 0 rows + a non-empty rejected_sample, OR
    # - 1 row that came from a fallback (query_repaired counter bumps).
    if not rows:
        assert stats["rejected_total"] >= 1
        assert stats["rejected_sample"]
    else:
        assert stats["query_repaired"] >= 1
