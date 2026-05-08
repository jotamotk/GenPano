"""Pure (no-DB, no-LLM) Query Pool helpers — Phase 5 slice 3b-i.

Vendored from ``admin_console/app.py`` 1813-2069 / 2313-2484 minus DB and
LLM-touching code. Same input shapes; same output shapes.

These helpers run during preflight (dry-run) and during the real
assemble worker; keeping them pure makes them unit-testable without
spinning up a Postgres or any LLM client.

Constants:
- ``QUERY_POOL_ENGINE_POLICIES``: legal ``desired_engine_policy`` values.
- ``QUERY_POOL_PROFILE_STRATEGIES``: balanced (default) / core / full.
- ``QUERY_POOL_OVERFLOW_POLICIES``: split / hold (the only policies the
  legacy admin_console ever sent).

Helpers:
- ``query_pool_config(payload)`` — coerce + validate request config block
- ``query_pool_selection_payload(payload)`` — normalize prompt selection
- ``sample_query_pool_profiles(...)`` — deterministic profile sampler
- ``query_pool_candidate_contexts(...)`` — Prompt x Profile expansion
- ``query_pool_summary(...)`` — assemble preflight_summary dict
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

QUERY_POOL_ENGINE_POLICIES = {
    "inherit",
    "balanced",
    "quality_first",
    "cost_guarded",
    "coverage_first",
    "domestic_only",
    "global_only",
    "benchmark_panel",
}
QUERY_POOL_PROFILE_STRATEGIES = {"balanced", "core", "full"}
QUERY_POOL_OVERFLOW_POLICIES = {"split", "hold"}
QUERY_POOL_PROMPT_SCOPES = {"non_branded", "branded", "competitor"}


def _clamp_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        n = int(value) if value is not None and value != "" else default
    except (TypeError, ValueError):
        n = default
    return max(low, min(n, high))


def _admin_float(value: Any, default: float) -> float:
    try:
        return float(value) if value is not None and value != "" else float(default)
    except (TypeError, ValueError):
        return float(default)


def _prompt_scope_from_prompt(prompt: dict[str, Any]) -> str:
    tags_value = prompt.get("tags")
    tags: dict[str, Any] = tags_value if isinstance(tags_value, dict) else {}
    if isinstance(tags_value, str):
        try:
            parsed_tags = json.loads(tags_value)
        except Exception:
            parsed_tags = {}
        tags = parsed_tags if isinstance(parsed_tags, dict) else {}
    raw = (
        prompt.get("prompt_scope")
        or prompt.get("promptScope")
        or tags.get("prompt_scope")
        or tags.get("promptScope")
        or "non_branded"
    )
    scope = str(raw or "").strip().lower().replace("-", "_")
    return scope if scope in QUERY_POOL_PROMPT_SCOPES else "non_branded"


def query_pool_config(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Validate and normalize ``payload`` (the SPA-supplied request body).

    Pulls the optional inner ``config`` dict if present; falls back to the
    top-level payload. Raises ``ValueError`` with a stable code for invalid
    enum values; clamps numeric ranges silently.
    """
    payload = payload or {}
    raw = payload.get("config") if isinstance(payload.get("config"), dict) else payload
    if not isinstance(raw, dict):
        raw = {}
    profiles_per_prompt = _clamp_int(
        raw.get("profiles_per_prompt") or raw.get("profilesPerPrompt"), 3, 1, 50
    )
    max_candidates = _clamp_int(
        raw.get("max_candidates") or raw.get("maxQueries"), 12000, 1, 1_000_000
    )
    desired_engine_policy = str(
        raw.get("desired_engine_policy") or raw.get("desiredEnginePolicy") or "inherit"
    ).strip()
    if desired_engine_policy not in QUERY_POOL_ENGINE_POLICIES:
        raise ValueError("invalid_desired_engine_policy")
    profile_strategy = str(
        raw.get("profile_strategy") or raw.get("profileStrategy") or "balanced"
    ).strip()
    if profile_strategy not in QUERY_POOL_PROFILE_STRATEGIES:
        raise ValueError("invalid_profile_strategy")
    overflow_policy = str(
        raw.get("overflow_policy") or raw.get("overflowPolicy") or "split"
    ).strip()
    if overflow_policy not in QUERY_POOL_OVERFLOW_POLICIES:
        raise ValueError("invalid_overflow_policy")
    return {
        "profiles_per_prompt": profiles_per_prompt,
        "profile_strategy": profile_strategy,
        "desired_engine_policy": desired_engine_policy,
        "engine_panel_id": str(raw.get("engine_panel_id") or raw.get("enginePanelId") or "").strip()
        or None,
        "max_candidates": max_candidates,
        "overflow_policy": overflow_policy,
        "budget_cap": _admin_float(raw.get("budget_cap") or raw.get("budgetCap"), 0),
        "intake_window": str(
            raw.get("intake_window") or raw.get("scheduleWindow") or "next"
        ).strip(),
        "dedupe_policy": str(
            raw.get("dedupe_policy") or raw.get("dedupePolicy") or "merge"
        ).strip(),
        "priority_mode": str(raw.get("priority_mode") or raw.get("priorityMode") or "gap").strip(),
    }


def query_pool_selection_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize prompt selection — ``explicit`` (id list) or ``filtered``.

    The SPA can send either:
      ``{"selection": {"mode": "explicit", "prompt_ids": [...]}}`` or
      ``{"selection": {"mode": "filtered", "filters": {...},
                        "excluded_prompt_ids": [...]}}``.
    Falls back to top-level ``prompt_ids`` / ``filters`` if no
    ``selection`` block is present.
    """
    payload = payload or {}
    selection_raw = payload.get("selection")
    selection = selection_raw if isinstance(selection_raw, dict) else {}
    mode = selection.get("mode") or payload.get("mode") or "explicit"
    if mode == "filtered":
        excluded = [
            str(item).strip()
            for item in (selection.get("excluded_prompt_ids") or [])
            if str(item).strip()
        ]
        return {
            "mode": "filtered",
            "filters": selection.get("filters") or payload.get("filters") or {},
            "excluded_prompt_ids": list(dict.fromkeys(excluded)),
        }
    prompt_ids = selection.get("prompt_ids") or payload.get("prompt_ids") or []
    prompt_ids = [str(item).strip() for item in prompt_ids if str(item).strip()]
    return {"mode": "explicit", "prompt_ids": list(dict.fromkeys(prompt_ids))}


def query_pool_weight(row: dict[str, Any]) -> float:
    return max(float(row.get("segment_weight") or 0), 0.0) * max(
        float(row.get("profile_weight") or 0), 0.0
    )


def query_pool_stable_rank(row: dict[str, Any], seed: str) -> int:
    """Deterministic per-(seed, segment, profile) tiebreaker."""
    identity = f"{seed}|{row.get('segment_id')}|{row.get('profile_id')}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def sample_query_pool_profiles(
    profile_pool: list[dict[str, Any]],
    count: int,
    *,
    strategy: str = "balanced",
    seed: str = "",
) -> list[dict[str, Any]]:
    """Deterministic, weight-aware profile sampler.

    Strategies:
    - ``balanced`` (default): top-K by (segment_weight * profile_weight)
    - ``core``: only profiles in the highest-weighted segment
    - ``full``: round-robin across distinct segments first, then fill
    """
    n = max(int(count or 0), 0)
    if n <= 0:
        return []
    valid = [dict(row) for row in profile_pool if query_pool_weight(row) > 0]
    if not valid:
        return []
    if strategy == "core":
        max_segment_weight = max(float(row.get("segment_weight") or 0) for row in valid)
        valid = [
            row for row in valid if float(row.get("segment_weight") or 0) == max_segment_weight
        ]

    def weighted_key(row: dict[str, Any]) -> tuple[float, int, str]:
        return (
            -query_pool_weight(row),
            query_pool_stable_rank(row, seed),
            str(row.get("profile_id") or ""),
        )

    if strategy == "full":
        chosen: list[dict[str, Any]] = []
        seen_profiles: set[Any] = set()
        groups: dict[Any, list[dict[str, Any]]] = {}
        for row in valid:
            groups.setdefault(row.get("segment_id"), []).append(row)
        for _segment_id, rows in sorted(
            groups.items(),
            key=lambda item: (
                -max(query_pool_weight(r) for r in item[1]),
                str(item[0] or ""),
            ),
        ):
            best = sorted(rows, key=weighted_key)[0]
            chosen.append(best)
            seen_profiles.add(best.get("profile_id"))
            if len(chosen) >= n:
                return chosen
        for row in sorted(valid, key=weighted_key):
            if row.get("profile_id") in seen_profiles:
                continue
            chosen.append(row)
            if len(chosen) >= n:
                break
        return chosen

    return sorted(valid, key=weighted_key)[:n]


def query_pool_candidate_contexts(
    prompt_rows: list[dict[str, Any]],
    profile_pool: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    """Build (Prompt x sampled-Profiles) context list for LLM rendering.

    Raises ``ValueError("query_pool_candidate_cap_exceeded")`` when the
    naive cross-product would breach ``max_candidates`` AND the operator
    chose ``overflow_policy=hold`` (the strict opt-out). Returns
    ``(contexts, raw_estimated)`` — ``raw_estimated`` is always the
    pre-cap product so summary can show "would have produced N".
    """
    profiles_per_prompt = int(config["profiles_per_prompt"])
    max_candidates = int(config["max_candidates"])
    raw_estimated = len(prompt_rows) * profiles_per_prompt
    if raw_estimated > max_candidates and config["overflow_policy"] == "hold":
        raise ValueError("query_pool_candidate_cap_exceeded")

    contexts: list[dict[str, Any]] = []
    for prompt in prompt_rows:
        prompt_scope = _prompt_scope_from_prompt(prompt)
        sampled_profiles = sample_query_pool_profiles(
            profile_pool,
            profiles_per_prompt,
            strategy=config["profile_strategy"],
            seed=str(prompt.get("id")),
        )
        for profile in sampled_profiles:
            if len(contexts) >= max_candidates:
                break
            prompt_id = str(prompt.get("id") or "")
            segment_id = str(profile.get("segment_id") or "")
            profile_id = str(profile.get("profile_id") or "")
            contexts.append(
                {
                    "candidate_key": (f"{prompt_id}|{segment_id}|{profile_id}|{len(contexts) + 1}"),
                    "prompt_id": prompt_id,
                    "prompt_text": (prompt.get("templateText") or prompt.get("text") or "").strip(),
                    "prompt_scope": prompt_scope,
                    "topic_id": str(prompt.get("topic_id") or ""),
                    "topic_text": str(prompt.get("topic_text") or "").strip(),
                    "segment_id": segment_id,
                    "segment_name": str(profile.get("segment_name") or "").strip(),
                    "profile_id": profile_id,
                    "profile_name": str(profile.get("profile_name") or "").strip(),
                    "profile_demographic": str(profile.get("profile_demographic") or "").strip(),
                    "profile_need": str(profile.get("profile_need") or "").strip(),
                }
            )
    return contexts, raw_estimated


def query_pool_summary(
    *,
    contexts: list[dict[str, Any]],
    profile_pool: list[dict[str, Any]],
    config: dict[str, Any],
    raw_estimated: int,
    candidates: list[dict[str, Any]] | None = None,
    render_failures: int = 0,
    duplicate_review: int = 0,
    query_repaired: int = 0,
    rejected_by_reason: dict[str, int] | None = None,
    rejected_sample: list[dict[str, Any]] | None = None,
    generation_method: str = "llm",
    llm_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the ``preflight_summary`` JSON shipped on the run row.

    Same shape preflight + assemble + worker emit; readers (SPA, tests)
    rely on this contract.
    """
    candidate_rows = candidates or []
    represented_source = candidate_rows if candidates is not None else contexts
    represented_segments = {
        row.get("segment_id") for row in represented_source if row.get("segment_id")
    }
    represented_profiles = {
        row.get("profile_id") for row in represented_source if row.get("profile_id")
    }
    active_segments = {row.get("segment_id") for row in profile_pool if query_pool_weight(row) > 0}
    active_profiles = {row.get("profile_id") for row in profile_pool if query_pool_weight(row) > 0}
    assembled = len(candidate_rows) if candidates is not None else len(contexts)
    attempted = len(contexts) if contexts else assembled + render_failures + duplicate_review
    rejected_by_reason = rejected_by_reason or {}
    quality_rejected = sum(int(count or 0) for count in rejected_by_reason.values())
    rejected_total = int(render_failures or 0) + int(duplicate_review or 0) + quality_rejected
    by_reason: dict[str, int] = {}
    if duplicate_review:
        by_reason["duplicate_review"] = int(duplicate_review)
    if render_failures:
        by_reason["render_failure"] = int(render_failures)
    for reason, count in rejected_by_reason.items():
        if count:
            by_reason[reason] = int(count)
    if query_repaired:
        by_reason["query_repaired"] = int(query_repaired)
    meta = dict(llm_meta or {})
    return {
        "requested": int(raw_estimated or attempted or 0),
        "accepted": int(assembled),
        "rejected_total": rejected_total,
        "by_reason": by_reason,
        "rejected_sample": list(rejected_sample or [])[:20],
        "quality_blocked": assembled == 0 and rejected_total > 0,
        "candidate_ready": assembled,
        "render_pass_rate": round(assembled / attempted, 4) if attempted else 0,
        "segment_coverage": (
            round(len(represented_segments) / len(active_segments), 4) if active_segments else 0
        ),
        "profile_coverage": (
            round(len(represented_profiles) / len(active_profiles), 4) if active_profiles else 0
        ),
        "profiles_per_prompt": int(config["profiles_per_prompt"]),
        "duplicate_review": duplicate_review,
        "render_failures": render_failures,
        "query_repaired": query_repaired,
        "scheduler_intake": "ready" if assembled else "blocked",
        "candidate_cap_reached": raw_estimated > int(config["max_candidates"]),
        "raw_candidates_estimated": raw_estimated,
        "generation_method": generation_method,
        "llm_model": meta.get("model"),
        "llm_usage": meta.get("usage") or {},
        "llm_batches": meta.get("batches", 0),
    }
