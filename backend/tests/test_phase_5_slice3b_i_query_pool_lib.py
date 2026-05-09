"""Phase 5 slice 3b-i — Query Pool pure-helper unit tests.

Covers ``app/admin/query_pool/lib.py`` (no DB, no LLM):
- query_pool_config: defaults, clamping, invalid-enum errors
- query_pool_selection_payload: explicit / filtered / payload fallback
- query_pool_weight: pure
- query_pool_stable_rank: deterministic per (seed, segment, profile)
- sample_query_pool_profiles: balanced / core / full strategies
- query_pool_candidate_contexts: cap behaviour + overflow=hold raise
- query_pool_summary: shape + coverage math
"""

from __future__ import annotations

import pytest

from app.admin.query_pool.lib import (
    QUERY_POOL_ENGINE_POLICIES,
    QUERY_POOL_OVERFLOW_POLICIES,
    QUERY_POOL_PROFILE_STRATEGIES,
    query_pool_candidate_contexts,
    query_pool_config,
    query_pool_selection_payload,
    query_pool_stable_rank,
    query_pool_summary,
    query_pool_weight,
    sample_query_pool_profiles,
)

# ── query_pool_config ────────────────────────────────────────────


def test_config_defaults_when_payload_empty():
    cfg = query_pool_config({})
    assert cfg["profiles_per_prompt"] == 3
    assert cfg["max_candidates"] == 12000
    assert cfg["desired_engine_policy"] == "inherit"
    assert cfg["profile_strategy"] == "balanced"
    assert cfg["overflow_policy"] == "split"
    assert cfg["engine_panel_id"] is None


def test_config_clamps_profiles_per_prompt_into_range():
    # Falsy 0 falls back to the default-3 (matches admin_console's `or` chain),
    # then clamps a too-large value into the [1, 50] range.
    assert query_pool_config({"profiles_per_prompt": 0})["profiles_per_prompt"] == 3
    assert query_pool_config({"profiles_per_prompt": 999})["profiles_per_prompt"] == 50


def test_config_accepts_camel_case_keys():
    cfg = query_pool_config(
        {"profilesPerPrompt": 7, "maxQueries": 50, "desiredEnginePolicy": "balanced"}
    )
    assert cfg["profiles_per_prompt"] == 7
    assert cfg["max_candidates"] == 50
    assert cfg["desired_engine_policy"] == "balanced"


def test_config_reads_inner_config_block():
    cfg = query_pool_config({"config": {"profiles_per_prompt": 5}})
    assert cfg["profiles_per_prompt"] == 5


def test_config_invalid_enum_raises_value_error():
    with pytest.raises(ValueError, match="invalid_desired_engine_policy"):
        query_pool_config({"desired_engine_policy": "bogus"})
    with pytest.raises(ValueError, match="invalid_profile_strategy"):
        query_pool_config({"profile_strategy": "weird"})
    with pytest.raises(ValueError, match="invalid_overflow_policy"):
        query_pool_config({"overflow_policy": "panic"})


def test_constants_are_frozen_set_like_and_complete():
    assert "inherit" in QUERY_POOL_ENGINE_POLICIES
    assert QUERY_POOL_PROFILE_STRATEGIES == {"balanced", "core", "full"}
    assert QUERY_POOL_OVERFLOW_POLICIES == {"split", "hold"}


# ── query_pool_selection_payload ─────────────────────────────────


def test_selection_explicit_dedupes_and_strips():
    out = query_pool_selection_payload({"prompt_ids": [" 1 ", "2", "1", ""]})
    assert out == {"mode": "explicit", "prompt_ids": ["1", "2"]}


def test_selection_filtered_passes_through_filters():
    out = query_pool_selection_payload(
        {
            "selection": {
                "mode": "filtered",
                "filters": {"intent": "commercial"},
                "excluded_prompt_ids": ["x", "x", "y"],
            }
        }
    )
    assert out["mode"] == "filtered"
    assert out["filters"] == {"intent": "commercial"}
    assert out["excluded_prompt_ids"] == ["x", "y"]


def test_selection_falls_back_to_payload_top_level():
    out = query_pool_selection_payload({"mode": "filtered", "filters": {"q": "skin"}})
    assert out["mode"] == "filtered"
    assert out["filters"] == {"q": "skin"}


# ── weight + stable rank ─────────────────────────────────────────


def test_weight_zero_when_either_factor_zero():
    assert query_pool_weight({"segment_weight": 0, "profile_weight": 5}) == 0
    assert query_pool_weight({"segment_weight": 4, "profile_weight": 0}) == 0
    assert query_pool_weight({"segment_weight": 4, "profile_weight": 5}) == 20


def test_stable_rank_deterministic_and_changes_with_seed():
    row = {"segment_id": "s1", "profile_id": "p1"}
    assert query_pool_stable_rank(row, "seedA") == query_pool_stable_rank(row, "seedA")
    assert query_pool_stable_rank(row, "seedA") != query_pool_stable_rank(row, "seedB")


# ── sample_query_pool_profiles ────────────────────────────────────


def _row(seg, sw, prof, pw):
    return {
        "segment_id": seg,
        "segment_weight": sw,
        "profile_id": prof,
        "profile_weight": pw,
    }


def test_sample_balanced_returns_top_k_by_weight_product():
    pool = [_row("s1", 2, "p1", 3), _row("s2", 1, "p2", 1), _row("s3", 4, "p3", 4)]
    out = sample_query_pool_profiles(pool, 2, strategy="balanced", seed="x")
    ids = [r["profile_id"] for r in out]
    assert ids == ["p3", "p1"]


def test_sample_core_only_keeps_top_segment():
    pool = [_row("s1", 5, "p1", 2), _row("s2", 1, "p2", 9)]
    out = sample_query_pool_profiles(pool, 5, strategy="core", seed="x")
    assert [r["segment_id"] for r in out] == ["s1"]


def test_sample_full_round_robins_segments_first():
    pool = [
        _row("s1", 5, "p1", 5),
        _row("s1", 5, "p2", 4),
        _row("s2", 4, "p3", 5),
        _row("s3", 3, "p4", 5),
    ]
    out = sample_query_pool_profiles(pool, 3, strategy="full", seed="x")
    segs = [r["segment_id"] for r in out]
    assert sorted(segs) == ["s1", "s2", "s3"]


def test_sample_count_zero_returns_empty():
    assert sample_query_pool_profiles([_row("s1", 1, "p1", 1)], 0) == []


def test_sample_drops_zero_weight_rows():
    pool = [_row("s1", 0, "p1", 5), _row("s2", 5, "p2", 5)]
    out = sample_query_pool_profiles(pool, 5, seed="x")
    assert [r["profile_id"] for r in out] == ["p2"]


# ── query_pool_candidate_contexts ────────────────────────────────


def _prompt(pid):
    return {"id": pid, "text": f"How is {pid}?", "topic_id": "t1", "topic_text": "topic"}


def test_contexts_pairs_each_prompt_with_sampled_profiles():
    prompts = [_prompt("a"), _prompt("b")]
    pool = [_row("s1", 5, "p1", 5), _row("s1", 4, "p2", 4)]
    cfg = query_pool_config({"profiles_per_prompt": 2})
    contexts, raw = query_pool_candidate_contexts(prompts, pool, cfg)
    assert raw == 4
    assert len(contexts) == 4
    keys = {c["candidate_key"] for c in contexts}
    assert len(keys) == 4
    assert all(c["prompt_id"] in {"a", "b"} for c in contexts)


def test_contexts_normalize_legacy_competitor_scope_from_prompt_tags():
    prompts = [{**_prompt("a"), "tags": {"prompt_scope": "competitor"}}]
    pool = [_row("s1", 5, "p1", 5)]
    cfg = query_pool_config({"profiles_per_prompt": 1})
    contexts, raw = query_pool_candidate_contexts(prompts, pool, cfg)

    assert raw == 1
    assert contexts[0]["prompt_scope"] == "competitive"


def test_contexts_parse_prompt_scope_from_json_string_tags():
    prompts = [{**_prompt("a"), "tags": '{"prompt_scope": "branded"}'}]
    pool = [_row("s1", 5, "p1", 5)]
    cfg = query_pool_config({"profiles_per_prompt": 1})
    contexts, _raw = query_pool_candidate_contexts(prompts, pool, cfg)

    assert contexts[0]["prompt_scope"] == "branded"


def test_contexts_caps_at_max_candidates():
    prompts = [_prompt(str(i)) for i in range(10)]
    pool = [_row("s1", 5, "p1", 5)]
    cfg = query_pool_config({"profiles_per_prompt": 2, "max_candidates": 3})
    contexts, raw = query_pool_candidate_contexts(prompts, pool, cfg)
    assert raw == 20
    assert len(contexts) == 3


def test_contexts_overflow_hold_raises_when_above_cap():
    prompts = [_prompt("a")]
    pool = [_row("s1", 5, "p1", 5)]
    cfg = query_pool_config(
        {"profiles_per_prompt": 5, "max_candidates": 3, "overflow_policy": "hold"}
    )
    with pytest.raises(ValueError, match="query_pool_candidate_cap_exceeded"):
        query_pool_candidate_contexts(prompts, pool, cfg)


# ── query_pool_summary ────────────────────────────────────────────


def test_summary_blocked_when_no_candidates_but_rejections():
    pool = [_row("s1", 5, "p1", 5)]
    cfg = query_pool_config({"profiles_per_prompt": 1})
    out = query_pool_summary(
        contexts=[],
        profile_pool=pool,
        config=cfg,
        raw_estimated=0,
        candidates=[],
        rejected_by_reason={"query_not_natural": 2},
    )
    assert out["accepted"] == 0
    assert out["quality_blocked"] is True
    assert out["scheduler_intake"] == "blocked"
    assert out["by_reason"]["query_not_natural"] == 2


def test_summary_dry_run_uses_contexts_for_coverage():
    pool = [_row("s1", 5, "p1", 5), _row("s2", 4, "p2", 4)]
    cfg = query_pool_config({"profiles_per_prompt": 2})
    contexts = [
        {"segment_id": "s1", "profile_id": "p1"},
        {"segment_id": "s2", "profile_id": "p2"},
    ]
    out = query_pool_summary(
        contexts=contexts,
        profile_pool=pool,
        config=cfg,
        raw_estimated=2,
        generation_method="llm_estimate",
    )
    assert out["accepted"] == 2
    assert out["segment_coverage"] == 1.0
    assert out["profile_coverage"] == 1.0
    assert out["scheduler_intake"] == "ready"
    assert out["generation_method"] == "llm_estimate"
