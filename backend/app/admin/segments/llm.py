"""Async Segment/Profile generation LLM service.

Port of admin_console/segment_profiles.py from sync OpenAI SDK to async
httpx, mirroring the topic_plan / prompt_matrix / query_pool pattern.

Public:
- ``SegmentProfileGenerationError`` — coded LLM failure.
- ``GenerationResult`` — returned by ``generate_segments`` /
  ``generate_profiles``.
- ``SegmentProfileGenerationService`` — async client. Reuses the
  Doubao/Ark config (``load_doubao_config``).
- ``validate_segment_candidates`` / ``validate_profile_candidates`` —
  pure-Python validators, exported for unit testing + slice 6b.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.admin.topic_plan.lib import (
    DoubaoConfig,
    TopicPlanLLMError,
    load_doubao_config,
)


class SegmentProfileGenerationError(Exception):
    """Coded error returned to the API layer when LLM output is unusable.

    Mirrors the admin_console error type field-for-field so existing
    tests + curl integrations that read ``.code`` keep working.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class GenerationResult:
    items: list[dict[str, Any]]
    model: str
    prompt: str
    usage: dict[str, Any]
    estimated_cost: float | None = None


def _bounded_count(value: Any, default: int, min_value: int, max_value: int) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = default
    return max(min_value, min(count, max_value))


def _slug(value: str, fallback: str = "segment") -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", value or "").strip("-").lower()
    return (text or fallback)[:24]


def _json_prompt(task: str, payload: dict[str, Any], schema_hint: dict[str, Any]) -> str:
    return (
        "You are generating Admin-reviewed Segment/Profile drafts for GENPANO.\n"
        "Return only strict JSON. Do not include markdown, comments, prose, or "
        "code fences.\n"
        "Validate all required fields, keep requested count or fewer, avoid "
        "duplicate names, and keep weights numeric, non-negative, and <= 1.\n"
        "The generated drafts are for human review before database insertion.\n"
        f"Task: {task}\n"
        f"Input: {json.dumps(payload, ensure_ascii=False, sort_keys=True)}\n"
        f"Output schema: {json.dumps(schema_hint, ensure_ascii=False, sort_keys=True)}"
    )


def _strip_markdown_fence(raw: str) -> str:
    text = (raw or "").strip()
    if not text.startswith("```"):
        return text
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _load_json_object(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    cleaned = _strip_markdown_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except Exception as error:
        raise SegmentProfileGenerationError(
            "llm_json_invalid", "LLM returned invalid JSON"
        ) from error
    if not isinstance(parsed, dict):
        raise SegmentProfileGenerationError("llm_schema_invalid", "LLM JSON root must be an object")
    return parsed


def _usage_to_dict(usage_obj: Any) -> dict[str, Any]:
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


# ---------------------------------------------------------------------------
# Validation helpers (pure-Python — also used by slice 6b)
# ---------------------------------------------------------------------------


def _has_any(raw: dict[str, Any], *keys: str) -> bool:
    return any(key in raw and raw.get(key) not in (None, "") for key in keys)


def _require_any(raw: dict[str, Any], label: str, *keys: str) -> None:
    if not _has_any(raw, *keys):
        raise SegmentProfileGenerationError("missing_llm_field", f"{label} is required")


def _normalize_weight(value: Any, default: float, label: str = "weight") -> float:
    if value in (None, ""):
        return default
    raw_str = str(value).strip()
    try:
        number = float(raw_str.rstrip("%"))
    except (TypeError, ValueError) as exc:
        raise SegmentProfileGenerationError("invalid_weight", f"{label} must be numeric") from exc
    if raw_str.endswith("%"):
        number = number / 100.0
    if number < 0 or number > 1:
        raise SegmentProfileGenerationError("invalid_weight", f"{label} must be between 0 and 1")
    return number


def _normalize_profile_weight(value: Any, default: float = 1.0) -> float:
    """Profiles use relative sampling weight, not Segment share — value
    may exceed 1 (admin_console capped at 10)."""
    if value in (None, ""):
        return default
    try:
        raw = str(value).strip()
        number = float(raw.rstrip("%"))
    except (TypeError, ValueError):
        return default
    if raw.endswith("%"):
        number = number / 100.0
    if number < 0:
        raise SegmentProfileGenerationError("invalid_weight", "Profile weight must be non-negative")
    return min(number, 10.0)


def _first_non_empty(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in raw and raw.get(key) not in (None, ""):
            return raw.get(key)
    return None


def _profile_status(value: Any) -> str:
    status = str(value or "draft").strip().lower()
    aliases = {
        "enabled": "active",
        "live": "active",
        "启用": "active",
        "已启用": "active",
        "有效": "active",
        "草稿": "draft",
        "待审核": "draft",
        "暂停": "paused",
        "停用": "paused",
    }
    return aliases.get(status, status if status in {"active", "draft", "paused"} else "draft")


def _coerce_persona_json(value: Any, *, demographic: str, need: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return {"items": value}
    if isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list):
                return {"items": parsed}
        except Exception:
            pass
        return {"summary": text, "demographic": demographic, "need": need}
    return {"demographic": demographic, "need": need}


def validate_segment_candidates(
    items: list[dict[str, Any]], max_count: int
) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise SegmentProfileGenerationError("invalid_llm_output", "Segment output must be a list")
    seen_names: set[str] = set()
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(items[:max_count], start=1):
        _require_any(raw, "Segment id/code", "id", "code")
        for field in ("name", "industry", "status", "weight", "income", "regions", "note"):
            _require_any(raw, f"Segment {field}", field)
        _require_any(raw, "Segment age_range", "age_range", "ageRange")
        _require_any(raw, "Segment sampling_rate", "sampling_rate", "samplingRate")
        name = str(raw.get("name") or "").strip()
        if not name:
            raise SegmentProfileGenerationError("invalid_llm_output", "Segment name is required")
        normalized = name.lower()
        if normalized in seen_names:
            raise SegmentProfileGenerationError(
                "duplicate_segment_name", f"Duplicate Segment name: {name}"
            )
        seen_names.add(normalized)
        status = str(raw.get("status") or "draft").strip().lower()
        if status not in {"active", "draft", "paused"}:
            raise SegmentProfileGenerationError(
                "invalid_segment_status", f"Invalid Segment status: {status}"
            )
        weight = _normalize_weight(raw.get("weight"), 0.15, "Segment weight")
        rows.append(
            {
                "id": str(raw.get("id") or raw.get("code") or f"SEG-DRAFT-{index:03d}")
                .strip()
                .upper(),
                "code": str(raw.get("code") or raw.get("id") or f"SEG-DRAFT-{index:03d}")
                .strip()
                .upper(),
                "name": name,
                "industry": str(raw.get("industry") or "").strip(),
                "status": status,
                "weight": weight,
                "age_range": str(raw.get("age_range") or raw.get("ageRange") or "").strip(),
                "income": str(raw.get("income") or "").strip(),
                "regions": str(raw.get("regions") or "").strip(),
                "sampling_rate": str(
                    raw.get("sampling_rate") or raw.get("samplingRate") or ""
                ).strip(),
                "note": str(raw.get("note") or "").strip(),
            }
        )
    return rows


def validate_profile_candidates(
    items: list[Any], max_count: int
) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise SegmentProfileGenerationError("invalid_llm_output", "Profile output must be a list")
    seen_names: set[str] = set()
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(items[:max_count], start=1):
        if not isinstance(raw, dict):
            continue
        name = str(
            _first_non_empty(raw, "name", "profile_name", "profileName", "title") or ""
        ).strip()
        if not name:
            continue
        normalized = name.lower()
        if normalized in seen_names:
            continue
        seen_names.add(normalized)
        demographic = str(
            _first_non_empty(raw, "demographic", "persona", "profile", "description", "画像") or ""
        ).strip()
        need = str(
            _first_non_empty(raw, "need", "needs", "demand", "pain_point", "需求") or ""
        ).strip()
        if not demographic or not need:
            continue
        profile_id = (
            str(
                _first_non_empty(raw, "id", "code", "profile_id", "profileId")
                or f"P-DRAFT-{index:03d}"
            )
            .strip()
            .upper()
        )
        persona_source = _first_non_empty(raw, "persona_json", "personaJson", "persona")
        rows.append(
            {
                "id": profile_id,
                "code": str(
                    _first_non_empty(raw, "code", "id", "profile_id", "profileId") or profile_id
                )
                .strip()
                .upper(),
                "name": name,
                "demographic": demographic,
                "need": need,
                "weight": _normalize_profile_weight(raw.get("weight"), 1.0),
                "status": _profile_status(raw.get("status")),
                "persona_json": _coerce_persona_json(
                    persona_source, demographic=demographic, need=need
                ),
            }
        )
    if not rows:
        raise SegmentProfileGenerationError(
            "missing_llm_field", "No complete Profile drafts were returned"
        )
    return rows


# ---------------------------------------------------------------------------
# Async LLM service
# ---------------------------------------------------------------------------


class SegmentProfileGenerationService:
    """Async OpenAI-compatible Segment/Profile generation client.

    ``async generate_segments`` / ``async generate_profiles`` send one
    chat-completions request and return ``GenerationResult``. On
    LLM-side failure raises ``SegmentProfileGenerationError`` (the
    route handler maps this back to 502/503 via
    ``segment_profile_generation_status``).
    """

    def __init__(
        self,
        model: str | None = None,
        config: DoubaoConfig | None = None,
        allow_fallback: bool | None = None,
    ):
        self.model_override = (model or os.getenv("SEGMENT_PROFILE_LLM_MODEL") or "").strip()
        self.config = config
        self.allow_fallback = (
            allow_fallback
            if allow_fallback is not None
            else os.getenv("SEGMENT_PROFILE_LLM_ALLOW_FALLBACK", "0") == "1"
        )

    def _llm_config(self) -> DoubaoConfig:
        try:
            return self.config or load_doubao_config()
        except TopicPlanLLMError as error:
            raise SegmentProfileGenerationError(error.code, error.message) from error

    async def _call_llm_json(
        self, *, prompt: str, root_key: str, max_count: int
    ) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
        config = self._llm_config()
        model = self.model_override or getattr(config, "model", "")
        timeout_seconds = _bounded_count(
            os.getenv("SEGMENT_PROFILE_LLM_TIMEOUT_SECONDS") or 90, 90, 30, 240
        )
        max_tokens = _bounded_count(
            os.getenv("SEGMENT_PROFILE_LLM_MAX_TOKENS") or (1200 + max_count * 450),
            4096,
            800,
            8192,
        )
        url = config.base_url.rstrip("/") + "/chat/completions"
        body = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a precise data generator for an Admin "
                        "operations console. Output valid JSON only. Never "
                        "generate Query text here."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(url, json=body, headers=headers)
        except httpx.RequestError as error:
            raise SegmentProfileGenerationError(
                "llm_call_failed",
                "Segment/Profile LLM generation failed: " + str(error)[:500],
            ) from error

        if response.status_code != 200:
            raise SegmentProfileGenerationError(
                "llm_call_failed",
                f"Segment/Profile LLM generation failed: HTTP {response.status_code}",
            )
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise SegmentProfileGenerationError(
                "llm_call_failed", "Segment/Profile LLM returned no choices"
            )
        content = (choices[0].get("message") or {}).get("content") or "{}"
        parsed = _load_json_object(content)
        items = parsed.get(root_key)
        if not isinstance(items, list):
            raise SegmentProfileGenerationError(
                "llm_schema_invalid", f"LLM JSON must contain a {root_key} array"
            )
        return items, model, _usage_to_dict(data.get("usage"))

    async def generate_segments(
        self,
        *,
        brand_name: str,
        industry: str,
        count: int,
        status: str,
        positioning: str,
        goal: str,
        constraints: str,
    ) -> GenerationResult:
        count = _bounded_count(count, 6, 1, 20)
        status = status if status in {"active", "draft", "paused"} else "draft"
        payload = {
            "brand_name": brand_name,
            "industry": industry,
            "count": count,
            "status": status,
            "positioning": positioning,
            "goal": goal,
            "constraints": constraints,
        }
        prompt = _json_prompt(
            "generate_segments",
            payload,
            {
                "segments": [
                    {
                        "id": "SEG-CODE",
                        "name": "string",
                        "industry": "string",
                        "status": "draft|active|paused",
                        "weight": 0.15,
                        "age_range": "string",
                        "income": "string",
                        "regions": "string",
                        "sampling_rate": "string",
                        "note": "string",
                    }
                ]
            },
        )
        try:
            raw_items, model, usage = await self._call_llm_json(
                prompt=prompt, root_key="segments", max_count=count
            )
            return GenerationResult(
                items=validate_segment_candidates(raw_items, count),
                model=model,
                prompt=prompt,
                usage=usage,
                estimated_cost=None,
            )
        except SegmentProfileGenerationError:
            if not self.allow_fallback:
                raise
        return self._fallback_segments(
            brand_name=brand_name,
            industry=industry,
            count=count,
            status=status,
            prompt=prompt,
        )

    def _fallback_segments(
        self,
        *,
        brand_name: str,
        industry: str,
        count: int,
        status: str,
        prompt: str,
    ) -> GenerationResult:
        """Deterministic fallback used only when ``allow_fallback`` is set
        — admin_console has the same opt-in path for ops dry-runs."""
        brand = (brand_name or "Brand").strip() or "Brand"
        industry_name = (industry or "General").strip() or "General"
        brand_slug = _slug(brand, "brand").upper()
        archetypes = [
            (
                "Core high-intent buyers",
                "24-38",
                "mid-high",
                "tier 1 and new tier 1",
                "32%",
                "Evaluates category value and needs a clear reason to prefer the brand.",
            ),
            (
                "Evidence comparison buyers",
                "22-35",
                "mid-high",
                "tier 1 and new tier 1",
                "24%",
                "Compares proof, ingredients, authority, reviews, and alternatives.",
            ),
            (
                "Price and channel sensitive buyers",
                "24-42",
                "middle",
                "new tier 1 and tier 2",
                "18%",
                "Compares official channels, discounts, bundles, and final price.",
            ),
            (
                "Gift scenario decision makers",
                "26-45",
                "mid-high",
                "tier 1 and new tier 1",
                "16%",
                "Cares about packaging, recipient fit, budget, and purchase risk.",
            ),
            (
                "Competitor switchers",
                "24-40",
                "mid-high",
                "key cities",
                "14%",
                "Is choosing between this brand and substitute brands.",
            ),
            (
                "New category entrants",
                "20-32",
                "middle",
                "tier 1 and tier 2",
                "12%",
                "Needs simple entry paths and low-friction first purchase advice.",
            ),
            (
                "Repeat and upgrade users",
                "28-46",
                "high",
                "tier 1 and new tier 1",
                "10%",
                "Cares about upgrade value, long-term experience, and repurchase stability.",
            ),
            (
                "Risk-averse reviewers",
                "24-44",
                "mid-high",
                "key cities",
                "8%",
                "Looks for negative feedback, mismatch risk, and after-sales concerns.",
            ),
        ]
        items: list[dict[str, Any]] = []
        for index in range(count):
            title, age, income, regions, sampling, note = archetypes[index % len(archetypes)]
            items.append(
                {
                    "id": f"SEG-{brand_slug}-{index + 1:03d}",
                    "name": f"{brand} - {title}",
                    "industry": industry_name,
                    "status": status,
                    "weight": max(0.05, round(0.30 - index * 0.02, 2)),
                    "age_range": age,
                    "income": income,
                    "regions": regions,
                    "sampling_rate": sampling,
                    "note": note,
                }
            )
        return GenerationResult(
            items=validate_segment_candidates(items, count),
            model="fallback-segment-profile-v1",
            prompt=prompt,
            usage={"total_tokens": 0, "source": "deterministic_fallback"},
            estimated_cost=0.0,
        )


def segment_profile_generation_status(error: SegmentProfileGenerationError) -> int:
    """Map LLM error code → HTTP status. 503 for upstream / config issues
    (operator can retry); 502 for schema / validation failures (input
    needs reshaping)."""
    return (
        503
        if error.code in {"llm_config_missing", "llm_client_unavailable", "llm_call_failed"}
        else 502
    )


def drafts_with_brand_context(
    items: list[dict[str, Any]] | None,
    *,
    brand_id: str | None = None,
    brand_name: str = "",
    segment_id: str | None = None,
) -> list[dict[str, Any]]:
    """Annotate LLM drafts with the brand context the operator selected
    so the SPA can render brand-aware preview without re-fetching."""
    drafts: list[dict[str, Any]] = []
    for item in items or []:
        draft = dict(item or {})
        if segment_id is not None:
            draft.setdefault("segment_id", str(segment_id).strip().upper())
        draft["brand_id"] = draft.get("brand_id") or brand_id
        draft["brand_name"] = draft.get("brand_name") or draft.get("brandName") or brand_name or ""
        drafts.append(draft)
    return drafts
