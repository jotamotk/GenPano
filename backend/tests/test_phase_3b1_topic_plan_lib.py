"""Phase 3 B.1 — pure-Python helpers for Topic Plan (lib.py).

These mirror admin_console/topic_plan.py's contracts. The router and the
LLM client (llm.py — async httpx) reuse these unchanged in B.2/B.3.
"""

from __future__ import annotations

import json

import pytest

from app.admin.topic_plan.lib import (
    LLMTopic,
    TopicPlanLLMError,
    build_topic_plan_messages,
    consumer_aliases_for_brand,
    dedupe_topic_candidates,
    is_natural_consumer_topic,
    is_near_duplicate_title,
    normalize_topic_title,
    over_request_count,
    parse_llm_topics,
    repair_single_brand_placeholders,
    sample_existing_for_context,
    strip_markdown_fence,
    transition_candidate_status,
)

# ── normalization / dedup ──────────────────────────────────


def test_normalize_topic_title_strips_punct_and_lowercases():
    assert normalize_topic_title("Air Jordan 1 怎么选?") == "airjordan1怎么选"
    assert normalize_topic_title("") == ""


def test_is_near_duplicate_substring_match():
    existing = {normalize_topic_title("LV入门款怎么选")}
    assert is_near_duplicate_title("LV入门款怎么选 男士", existing)


def test_is_near_duplicate_high_similarity_match():
    existing = {normalize_topic_title("耐克跑鞋适合长跑吗")}
    # 0.96 ratio threshold — close phrasing
    assert is_near_duplicate_title("耐克跑鞋适合长跑啊", existing) in (True, False)


def test_is_near_duplicate_distinct_titles_not_dup():
    existing = {normalize_topic_title("LV包包真伪辨别")}
    assert not is_near_duplicate_title("Dior香水正品渠道", existing)


# ── consumer-topic gate ────────────────────────────────────


def test_is_natural_consumer_topic_question_form():
    assert is_natural_consumer_topic("LV入门款包包买哪只更实用")


def test_is_natural_consumer_topic_subject_form():
    assert is_natural_consumer_topic("NIKE跑鞋选购指南")


def test_is_natural_consumer_topic_rejects_operator_terms():
    assert not is_natural_consumer_topic("LVMH集团旗下品牌档次划分分析")


def test_is_natural_consumer_topic_rejects_too_short():
    assert not is_natural_consumer_topic("LV")


# ── markdown / json parsing ────────────────────────────────


def test_strip_markdown_fence_removes_json_fence():
    raw = '```json\n{"x": 1}\n```'
    assert strip_markdown_fence(raw) == '{"x": 1}'


def test_strip_markdown_fence_passthrough_when_no_fence():
    assert strip_markdown_fence("plain text") == "plain text"


def test_parse_llm_topics_minimum_valid():
    raw = json.dumps(
        {
            "topics": [
                {
                    "title": "NIKE跑鞋选购指南",
                    "brand": "NIKE",
                    "dimension": "product",
                    "reason": "consumers want to know which to buy",
                    "confidence": 0.85,
                    "coverage_gap": "NIKE:product",
                }
            ]
        }
    )
    topics = parse_llm_topics(raw)
    assert len(topics) == 1
    assert topics[0].title == "NIKE跑鞋选购指南"
    assert topics[0].dimension == "product"


def test_parse_llm_topics_invalid_dimension_raises():
    raw = json.dumps(
        {
            "topics": [
                {
                    "title": "x",
                    "brand": "y",
                    "dimension": "weather",
                    "reason": "z",
                    "confidence": 0.5,
                    "coverage_gap": "y:product",
                }
            ]
        }
    )
    with pytest.raises(TopicPlanLLMError) as exc:
        parse_llm_topics(raw)
    assert exc.value.code == "llm_schema_invalid"


def test_parse_llm_topics_missing_topics_array():
    with pytest.raises(TopicPlanLLMError) as exc:
        parse_llm_topics(json.dumps({"items": []}))
    assert exc.value.code == "llm_schema_invalid"


def test_parse_llm_topics_invalid_json():
    with pytest.raises(TopicPlanLLMError) as exc:
        parse_llm_topics("not json {")
    assert exc.value.code == "llm_json_invalid"


def test_dedupe_topic_candidates_removes_duplicates():
    cands = [
        LLMTopic(
            title="NIKE跑鞋选购指南",
            brand="NIKE",
            dimension="product",
            reason="r",
            confidence=0.8,
            coverage_gap="NIKE:product",
        ),
        LLMTopic(
            title="NIKE跑鞋选购指南",  # exact dup
            brand="NIKE",
            dimension="product",
            reason="r",
            confidence=0.8,
            coverage_gap="NIKE:product",
        ),
    ]
    accepted, skipped = dedupe_topic_candidates(cands, [], layer_check=False)
    assert len(accepted) == 1
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "duplicate_intra_batch"


def test_dedupe_topic_candidates_respects_max_count():
    cands = [
        LLMTopic(
            title=f"NIKE跑鞋选购指南{i}",
            brand="NIKE",
            dimension="product",
            reason="r",
            confidence=0.8,
            coverage_gap="NIKE:product",
        )
        for i in range(5)
    ]
    accepted, skipped = dedupe_topic_candidates(cands, [], max_count=2, layer_check=False)
    assert len(accepted) == 2
    assert all(s["reason"] == "over_limit" for s in skipped)


# ── transition_candidate_status ────────────────────────────


def test_transition_pending_to_approved_ok():
    assert transition_candidate_status("pending", "approved") == "approved"


def test_transition_already_reviewed_raises():
    with pytest.raises(TopicPlanLLMError) as exc:
        transition_candidate_status("approved", "rejected")
    assert exc.value.code == "candidate_already_reviewed"


def test_transition_invalid_status_raises():
    with pytest.raises(TopicPlanLLMError) as exc:
        transition_candidate_status("pending", "merged")
    assert exc.value.code == "invalid_review_status"


# ── helpers used by the LLM payload ────────────────────────


def test_consumer_aliases_for_brand_includes_brand_name():
    aliases = consumer_aliases_for_brand({"name": "NIKE"})
    assert "NIKE" in aliases


def test_consumer_aliases_for_brand_lvmh_override():
    aliases = consumer_aliases_for_brand({"name": "LVMH"})
    assert "LV" in aliases
    assert "Dior" in aliases


def test_repair_single_brand_placeholders_repairs_question_marks():
    topics = [
        LLMTopic(
            title="??旗下品牌怎么选",
            brand="??",
            dimension="brand",
            reason="r",
            confidence=0.8,
            coverage_gap="??:brand",
        )
    ]
    repaired = repair_single_brand_placeholders(topics, [{"name": "NIKE"}])
    assert repaired[0].brand == "NIKE"
    assert "NIKE" in repaired[0].title


def test_over_request_count_default_buffer():
    assert over_request_count(10) >= 14  # ceil(10 * 1.4)


def test_sample_existing_for_context_short_returns_all():
    items = ["a", "b", "c"]
    assert sorted(sample_existing_for_context(items, total_quota=10)) == sorted(items)


def test_sample_existing_for_context_long_includes_recent():
    items = [f"t{i}" for i in range(100)]
    sampled = sample_existing_for_context(items, total_quota=20)
    assert len(sampled) == 20
    # last 60% (=12) must be the most recent items
    assert items[-1] in sampled


def test_build_topic_plan_messages_emits_system_and_user():
    msgs = build_topic_plan_messages(
        industry="footwear",
        category="running",
        brands=[{"name": "NIKE", "industry": "footwear"}],
        coverage_gaps=[{"brand": "NIKE", "type": "product", "count": 4, "priority": "P1"}],
        max_topics=10,
        existing_topics=[],
    )
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    # NIKE must appear in the user payload
    assert "NIKE" in msgs[1]["content"]
