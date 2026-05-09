"""Text-cleanup + LLM-output-parsing helpers for Query Pool generation.

Vendored from admin_console/app.py 2072-2310 / 2352-2425. Pure Python — no
DB, no LLM. The worker uses these for:
- Stripping ``⁠```⁠json`` fences off LLM responses
- Normalizing / validating each rendered query string
- Repairing broken queries via context-aware fallbacks (for example a
  Chinese profile with empty LLM output yields a Chinese consumer-style
  fallback so the run isn't entirely lost)
- Parsing the final ``queries`` JSON shape into a ``{candidate_key: query}``
  map and ultimately into ``QueryGenerationCandidate`` row dicts

``TopicPlanLLMError`` is reused (instead of a query-pool-specific subclass)
to keep parity with admin_console — every error code below ends up in
``llm_error`` / ``llm_*`` shapes the SPA already understands.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from typing import Any

from app.admin.prompt_matrix.lib import is_natural_user_prompt
from app.admin.topic_plan.lib import TopicPlanLLMError

try:
    from json_repair import repair_json
except Exception:  # pragma: no cover - optional dependency
    repair_json = None


def _clamp_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        n = int(value) if value is not None and value != "" else default
    except (TypeError, ValueError):
        n = default
    return max(low, min(n, high))


QUERY_POOL_FORBIDDEN_QUERY_TERMS = (
    "segment",
    "profile",
    "persona",
    "user persona",
    "用户画像",
    "画像",
    "后台",
    "运营",
    "调度",
    "执行引擎",
    "engine",
    "scheduler",
)


def query_pool_strip_markdown_fence(raw: str | None) -> str:
    text = (raw or "").strip()
    if not text.startswith("```"):
        return text
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def query_pool_load_json_object(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return {"queries": raw}
    cleaned = query_pool_strip_markdown_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except Exception as first_error:
        if repair_json is None:
            raise TopicPlanLLMError(
                "llm_json_invalid", "LLM returned invalid JSON"
            ) from first_error
        try:
            parsed = json.loads(repair_json(cleaned))
        except Exception as repair_error:
            raise TopicPlanLLMError(
                "llm_json_invalid", "LLM returned invalid JSON"
            ) from repair_error
    if isinstance(parsed, list):
        return {"queries": parsed}
    if not isinstance(parsed, dict):
        raise TopicPlanLLMError("llm_schema_invalid", "LLM JSON root must be an object")
    return parsed


def query_pool_extract_llm_items(data: dict[str, Any], root_key: str) -> list[Any]:
    items = data.get(root_key)
    if isinstance(items, list):
        return items
    singular_key = (
        "query" if root_key == "queries" else root_key[:-1] if root_key.endswith("s") else ""
    )
    for key in (singular_key, "drafts", "candidates", "choices", "items", "results"):
        if not key:
            continue
        value = data.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [value]
    if data.get("candidate_key") or data.get("query"):
        return [data]
    raise TopicPlanLLMError("llm_schema_invalid", f"LLM JSON must contain a {root_key} array")


def query_pool_normalize_query_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def query_pool_clean_query_text(value: Any, candidate_key: str) -> str:
    """Validate the LLM-rendered query: length, forbidden terms, naturalness.

    Raises ``TopicPlanLLMError`` (caller may catch + try repair).
    """
    query = query_pool_normalize_query_text(value)
    if len(query) < 4 or len(query) > 160:
        raise TopicPlanLLMError(
            "query_length_invalid",
            f"LLM query for {candidate_key} must be 4-160 characters",
        )
    lowered = query.casefold()
    for term in QUERY_POOL_FORBIDDEN_QUERY_TERMS:
        if term.casefold() in lowered:
            raise TopicPlanLLMError(
                "query_contains_internal_terms",
                f"LLM query for {candidate_key} contains internal product wording",
            )
    if not is_natural_user_prompt(query):
        raise TopicPlanLLMError(
            "query_not_natural",
            f"LLM query for {candidate_key} must sound like a real consumer question",
        )
    return query


def query_pool_has_cjk(text: Any) -> bool:
    return bool(re.search(r"[一-鿿]", str(text or "")))


def query_pool_sanitize_consumer_seed(value: Any) -> str:
    """Strip prompt-template syntax + forbidden internal terms."""
    text = query_pool_normalize_query_text(value)
    text = re.sub(r"\{\{?[^{}]+\}?\}", " ", text)
    text = re.sub(r"\[[^\]]+\]", " ", text)
    for phrase in ("请以", "请从", "视角", "角度", "回答", "作为", "扮演"):
        text = text.replace(phrase, " ")
    for term in QUERY_POOL_FORBIDDEN_QUERY_TERMS:
        text = re.sub(re.escape(term), " ", text, flags=re.IGNORECASE)
    text = query_pool_normalize_query_text(text)
    return text.strip(" ,，。.!！?？:：;；、")


def query_pool_candidate_fallback_query(context: dict[str, Any] | None) -> str:
    """Build a context-aware default query when LLM output is unusable."""
    context = context or {}
    subject = query_pool_sanitize_consumer_seed(
        context.get("topic_text") or context.get("prompt_text") or ""
    )
    need = query_pool_sanitize_consumer_seed(context.get("profile_need") or "")
    profile = query_pool_sanitize_consumer_seed(
        context.get("profile_demographic")
        or context.get("profile_name")
        or context.get("segment_name")
        or ""
    )
    seed = subject
    if need and subject and need not in subject:
        seed = f"{need}，{subject}" if query_pool_has_cjk(need + subject) else f"{need}, {subject}"
    elif need:
        seed = need
    elif profile and subject:
        seed = (
            f"{profile}，{subject}"
            if query_pool_has_cjk(profile + subject)
            else f"{profile}, {subject}"
        )
    elif profile:
        seed = profile

    seed = query_pool_sanitize_consumer_seed(seed)[:120]
    if query_pool_has_cjk(seed):
        seed = seed or "这个产品"
        if is_natural_user_prompt(seed):
            return seed if seed.endswith(("?", "？")) else seed + "？"
        return seed.rstrip("？?") + "怎么选？"
    seed = seed or "this product"
    seed = seed.rstrip("?")
    if is_natural_user_prompt(seed):
        return seed + "?"
    return f"Which option is worth buying for {seed}?"


QUERY_POOL_SAFE_FALLBACK_QUERIES_ZH = (
    "这个产品怎么选才不踩雷？",
    "这类产品哪款更适合日常用？",
    "预算有限的话哪款更值得买？",
    "第一次买这类产品怎么选比较稳？",
    "买这类产品主要看什么才不容易后悔？",
    "这类产品适合我这种情况买吗？",
)

QUERY_POOL_SAFE_FALLBACK_QUERIES_EN = (
    "Which option is worth buying?",
    "How should I choose this product?",
    "What should I check before buying this?",
    "Which one is better for everyday use?",
    "Is this product worth it on a budget?",
    "How do I avoid picking the wrong one?",
)


def query_pool_safe_fallback_queries(
    context: dict[str, Any] | None, candidate_key: str, *, prefer_cjk: bool = False
) -> list[str]:
    """Stable per-candidate rotation of generic fallbacks."""
    context_text = json.dumps(context or {}, ensure_ascii=False)
    use_cjk = prefer_cjk or query_pool_has_cjk(context_text)
    variants = list(
        QUERY_POOL_SAFE_FALLBACK_QUERIES_ZH if use_cjk else QUERY_POOL_SAFE_FALLBACK_QUERIES_EN
    )
    if not variants:
        return []
    digest = hashlib.sha256(str(candidate_key or "").encode("utf-8")).hexdigest()
    offset = int(digest[:8], 16) % len(variants)
    return list(variants[offset:]) + list(variants[:offset])


def query_pool_repair_query_text(
    value: Any,
    context: dict[str, Any] | None,
    candidate_key: str,
) -> str:
    """Try to salvage a borderline LLM output via guided rewrites.

    Walks attempts: original → CJK/EN suffix nudges → context-shaped
    fallback → safe per-candidate fallback rotation. Returns the first
    that passes ``query_pool_clean_query_text``; re-raises otherwise.
    """
    query = query_pool_normalize_query_text(value)
    attempts: list[str] = []
    if query:
        attempts.append(query)
        if query_pool_has_cjk(query):
            attempts.append(query.rstrip("。.!！?？,，、;；") + "怎么选？")
            attempts.append(query.rstrip("。.!！?？,，、;；") + "值不值得买？")
        else:
            seed = query.rstrip(".!?")
            attempts.append(f"Which {seed} is worth buying?")
            attempts.append(f"How should I choose {seed}?")
    attempts.append(query_pool_candidate_fallback_query(context))
    attempts.extend(
        query_pool_safe_fallback_queries(
            context, candidate_key, prefer_cjk=query_pool_has_cjk(query)
        )
    )

    last_error: TopicPlanLLMError | None = None
    for attempt in attempts:
        try:
            return query_pool_clean_query_text(attempt, candidate_key)
        except TopicPlanLLMError as error:
            last_error = error
    if last_error:
        raise last_error
    raise TopicPlanLLMError(
        "query_not_natural",
        f"LLM query for {candidate_key} must sound like a real consumer question",
    )


def parse_query_pool_llm_queries(
    raw: Any,
    expected_keys: list[str],
    *,
    validate_queries: bool = True,
) -> dict[str, str]:
    """Parse the LLM-returned ``queries`` array into ``{candidate_key: query}``.

    Validates the schema strictly: each item must reference one of the
    expected keys, no duplicates, all keys covered. With
    ``validate_queries=True`` each query is also run through
    ``query_pool_clean_query_text``; the worker passes False so it can
    salvage borderline outputs via ``query_pool_repair_query_text``.
    """
    expected = [str(key) for key in expected_keys]
    expected_set = set(expected)
    data = query_pool_load_json_object(raw)
    queries = query_pool_extract_llm_items(data, "queries")
    parsed: dict[str, str] = {}
    for index, item in enumerate(queries):
        if not isinstance(item, dict):
            raise TopicPlanLLMError(
                "llm_schema_invalid", f"Query item #{index + 1} must be an object"
            )
        candidate_key = str(item.get("candidate_key") or "").strip()
        if candidate_key not in expected_set:
            raise TopicPlanLLMError(
                "llm_schema_invalid",
                f"LLM returned unknown candidate_key: {candidate_key or '<empty>'}",
            )
        if candidate_key in parsed:
            raise TopicPlanLLMError(
                "llm_schema_invalid",
                f"LLM returned duplicate candidate_key: {candidate_key}",
            )
        query_value = query_pool_normalize_query_text(item.get("query"))
        parsed[candidate_key] = (
            query_pool_clean_query_text(query_value, candidate_key)
            if validate_queries
            else query_value
        )
    missing = [key for key in expected if key not in parsed]
    if missing:
        raise TopicPlanLLMError(
            "llm_schema_invalid",
            "LLM missing query for candidate_key: " + ", ".join(missing[:5]),
        )
    return {key: parsed[key] for key in expected}


def query_pool_usage_to_dict(usage_obj: Any) -> dict[str, Any]:
    """Coerce an OpenAI-style usage object into a plain dict."""
    if usage_obj is None:
        return {}
    if hasattr(usage_obj, "model_dump"):
        dumped = usage_obj.model_dump()
        return dict(dumped) if isinstance(dumped, dict) else {}
    if isinstance(usage_obj, dict):
        return dict(usage_obj)
    return {
        key: getattr(usage_obj, key)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        if hasattr(usage_obj, key)
    }


def query_pool_merge_usage(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Sum numeric counters; first-wins for non-numeric keys."""
    merged = dict(left or {})
    for key, value in (right or {}).items():
        if isinstance(value, (int, float)) and isinstance(merged.get(key), (int, float)):
            merged[key] += value
        elif key not in merged:
            merged[key] = value
    return merged


def query_pool_llm_error_detail(error: Exception) -> str:
    parts = [type(error).__name__]
    status_code = getattr(error, "status_code", None)
    if status_code:
        parts.append(f"status={status_code}")
    message = str(error).strip()
    if message:
        parts.append(message[:500])
    return ": ".join(parts)


def query_pool_chunked(items: list[Any], size: int) -> list[list[Any]]:
    size = max(1, int(size or 1))
    return [items[i : i + size] for i in range(0, len(items), size)]


def query_pool_llm_batch_size() -> int:
    return _clamp_int(os.getenv("QUERY_POOL_LLM_BATCH_SIZE"), 8, 1, 25)


def query_pool_candidates_from_llm_queries(
    contexts: list[dict[str, Any]],
    llm_queries: dict[str, str],
    llm_meta: dict[str, Any] | None = None,
    *,
    start_seq: int = 1,
    seen_hashes: set[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Convert LLM batch output into insertable candidate dicts.

    Per-context: clean → on failure repair (counts as ``query_repaired``)
    → on dup-hash skip (counts as ``duplicate_review``) → emit candidate.
    Returns ``(candidates, stats)``; ``stats`` carries the counters
    later folded into ``preflight_summary.by_reason``.

    The worker passes a shared ``seen_hashes`` set across batches so
    cross-batch duplicates are also caught.
    """
    if not isinstance(llm_queries, dict):
        raise TopicPlanLLMError("llm_schema_invalid", "LLM query generator must return a dict")

    candidates: list[dict[str, Any]] = []
    duplicate_review = 0
    query_repaired = 0
    rejected_by_reason: dict[str, int] = {}
    rejected_sample: list[dict[str, Any]] = []
    seen = seen_hashes if seen_hashes is not None else set()
    llm_meta = llm_meta or {}
    llm_model = llm_meta.get("model")
    llm_usage = llm_meta.get("usage") or {}

    for context in contexts:
        candidate_key = context["candidate_key"]
        if candidate_key not in llm_queries:
            raise TopicPlanLLMError(
                "llm_schema_invalid", f"LLM missing query for candidate_key: {candidate_key}"
            )
        rendered_query = query_pool_normalize_query_text(llm_queries.get(candidate_key))
        try:
            rendered_query = query_pool_clean_query_text(rendered_query, candidate_key)
        except TopicPlanLLMError as clean_error:
            try:
                rendered_query = query_pool_repair_query_text(
                    rendered_query, context, candidate_key
                )
                query_repaired += 1
            except TopicPlanLLMError as repair_error:
                reason = repair_error.code or clean_error.code or "query_not_natural"
                rejected_by_reason[reason] = int(rejected_by_reason.get(reason) or 0) + 1
                if len(rejected_sample) < 20:
                    rejected_sample.append(
                        {
                            "candidate_key": candidate_key,
                            "reason": reason,
                            "text": rendered_query,
                        }
                    )
                continue
        # Dedup against everything seen so far in this run.
        # ``is_natural_user_prompt`` already normalized whitespace via
        # query_pool_clean_query_text; sha256 over the rendered text
        # gives us a cheap stable key for both batch and cross-batch
        # duplicate detection.
        render_hash = hashlib.sha256(rendered_query.encode("utf-8")).hexdigest()
        if render_hash in seen:
            duplicate_review += 1
            continue
        seen.add(render_hash)
        candidates.append(
            {
                "id": str(uuid.uuid4()),
                "candidate_seq": int(start_seq) + len(candidates),
                "prompt_id": context["prompt_id"],
                "segment_id": context["segment_id"],
                "profile_id": context["profile_id"],
                "rendered_query": rendered_query,
                "render_hash": render_hash,
                "candidate_status": "candidate",
                "generation_method": "llm",
                "llm_model": llm_model,
                "llm_usage": llm_usage,
            }
        )
    rejected_total = sum(int(c or 0) for c in rejected_by_reason.values())
    return candidates, {
        "duplicate_review": duplicate_review,
        "query_repaired": query_repaired,
        "rejected_total": rejected_total,
        "by_reason": rejected_by_reason,
        "rejected_sample": rejected_sample,
    }
