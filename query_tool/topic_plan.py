"""Topic Plan helpers for the query_tool admin console.

This module intentionally has no Flask or database dependency so the risky
parts of Topic Plan (LLM parsing, schema validation, de-dupe, review state)
can be tested without secrets or a live database.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

try:
    from json_repair import repair_json
except Exception:  # pragma: no cover - optional dependency
    repair_json = None


ALLOWED_TOPIC_DIMENSIONS = {"brand", "product", "category", "scenario", "question"}
REVIEW_STATUSES = {"pending", "approved", "rejected"}


class TopicPlanLLMError(ValueError):
    """Controlled error returned to the API layer when LLM output is unusable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class DoubaoConfig:
    api_key: str
    base_url: str
    model: str


@dataclass(frozen=True)
class LLMTopic:
    title: str
    brand: str
    dimension: str
    reason: str
    confidence: float
    coverage_gap: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "brand": self.brand,
            "dimension": self.dimension,
            "reason": self.reason,
            "confidence": self.confidence,
            "coverage_gap": self.coverage_gap,
        }


def load_doubao_config(env: dict[str, str] | None = None) -> DoubaoConfig:
    """Load Volcengine Ark / Doubao 2 settings from environment variables."""

    source = env or os.environ
    api_key = (
        source.get("ARK_API_KEY")
        or source.get("VOLCENGINE_ARK_API_KEY")
        or source.get("DOUBAO_API_KEY")
        or ""
    ).strip()
    base_url = (
        source.get("ARK_BASE_URL")
        or source.get("VOLCENGINE_ARK_BASE_URL")
        or source.get("DOUBAO_BASE_URL")
        or source.get("LLM_BASE_URL")
        or ""
    ).strip()
    model = (
        source.get("ARK_MODEL")
        or source.get("DOUBAO_MODEL")
        or source.get("LLM_MODEL")
        or ""
    ).strip()
    missing = []
    if not api_key:
        missing.append("ARK_API_KEY")
    if not base_url:
        missing.append("ARK_BASE_URL")
    if not model:
        missing.append("ARK_MODEL")
    if missing:
        raise TopicPlanLLMError(
            "llm_config_missing",
            "Doubao 2 configuration is missing: " + ", ".join(missing),
        )
    return DoubaoConfig(api_key=api_key, base_url=base_url, model=model)


def normalize_topic_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    return "".join(ch for ch in normalized if ch.isalnum())


def is_near_duplicate_title(title: str, existing_normalized: set[str]) -> bool:
    current = normalize_topic_title(title)
    if not current:
        return True
    if current in existing_normalized:
        return True
    for other in existing_normalized:
        if len(current) >= 5 and len(other) >= 5 and (current in other or other in current):
            return True
        if SequenceMatcher(None, current, other).ratio() >= 0.92:
            return True
    return False


def strip_markdown_fence(raw: str) -> str:
    text = (raw or "").strip()
    if not text.startswith("```"):
        return text
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _load_json_object(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    cleaned = strip_markdown_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except Exception as first_error:
        if repair_json is None:
            raise TopicPlanLLMError("llm_json_invalid", "LLM returned invalid JSON") from first_error
        try:
            parsed = json.loads(repair_json(cleaned))
        except Exception as repair_error:
            raise TopicPlanLLMError("llm_json_invalid", "LLM returned invalid JSON") from repair_error
    if not isinstance(parsed, dict):
        raise TopicPlanLLMError("llm_schema_invalid", "LLM JSON root must be an object")
    return parsed


def parse_llm_topics(raw: str | dict[str, Any]) -> list[LLMTopic]:
    data = _load_json_object(raw)
    topics = data.get("topics")
    if not isinstance(topics, list):
        raise TopicPlanLLMError("llm_schema_invalid", "LLM JSON must contain a topics array")

    parsed: list[LLMTopic] = []
    for index, item in enumerate(topics):
        if not isinstance(item, dict):
            raise TopicPlanLLMError(
                "llm_schema_invalid",
                f"Topic item #{index + 1} must be an object",
            )
        title = str(item.get("title") or "").strip()
        brand = str(item.get("brand") or "").strip()
        dimension = str(item.get("dimension") or "").strip().lower()
        reason = str(item.get("reason") or "").strip()
        coverage_gap = str(item.get("coverage_gap") or "").strip()
        try:
            confidence = float(item.get("confidence"))
        except (TypeError, ValueError) as error:
            raise TopicPlanLLMError(
                "llm_schema_invalid",
                f"Topic item #{index + 1} confidence must be a number",
            ) from error

        if not title:
            raise TopicPlanLLMError("llm_schema_invalid", f"Topic item #{index + 1} title is required")
        if not brand:
            raise TopicPlanLLMError("llm_schema_invalid", f"Topic item #{index + 1} brand is required")
        if dimension not in ALLOWED_TOPIC_DIMENSIONS:
            raise TopicPlanLLMError(
                "llm_schema_invalid",
                f"Topic item #{index + 1} dimension must be one of "
                + ", ".join(sorted(ALLOWED_TOPIC_DIMENSIONS)),
            )
        if not reason:
            raise TopicPlanLLMError("llm_schema_invalid", f"Topic item #{index + 1} reason is required")
        if not coverage_gap:
            raise TopicPlanLLMError(
                "llm_schema_invalid",
                f"Topic item #{index + 1} coverage_gap is required",
            )
        if confidence < 0 or confidence > 1:
            raise TopicPlanLLMError(
                "llm_schema_invalid",
                f"Topic item #{index + 1} confidence must be between 0 and 1",
            )

        parsed.append(
            LLMTopic(
                title=title,
                brand=brand,
                dimension=dimension,
                reason=reason,
                confidence=confidence,
                coverage_gap=coverage_gap,
            )
        )
    return parsed


def dedupe_topic_candidates(
    candidates: list[LLMTopic],
    existing_titles: list[str],
    max_count: int | None = None,
) -> tuple[list[LLMTopic], list[dict[str, str]]]:
    normalized = {normalize_topic_title(title) for title in existing_titles if title}
    normalized.discard("")
    accepted: list[LLMTopic] = []
    skipped: list[dict[str, str]] = []

    for item in candidates:
        if max_count is not None and len(accepted) >= max_count:
            skipped.append({"title": item.title, "reason": "over_limit"})
            continue
        if is_near_duplicate_title(item.title, normalized):
            skipped.append({"title": item.title, "reason": "duplicate"})
            continue
        accepted.append(item)
        normalized.add(normalize_topic_title(item.title))
    return accepted, skipped


def repair_single_brand_placeholders(topics: list[LLMTopic], brands: list[dict[str, Any]]) -> list[LLMTopic]:
    allowed_brand_names = [str(brand.get("name") or "").strip() for brand in brands]
    allowed_brand_names = [name for name in allowed_brand_names if name]
    if len(allowed_brand_names) != 1:
        return topics

    selected_brand = allowed_brand_names[0]
    repaired: list[LLMTopic] = []
    for topic in topics:
        if topic.brand == selected_brand:
            repaired.append(topic)
            continue
        brand_text = (topic.brand or "").strip()
        is_placeholder = bool(brand_text) and set(brand_text) <= {"?"}
        if not is_placeholder:
            repaired.append(topic)
            continue

        repaired.append(
            LLMTopic(
                title=topic.title.replace(brand_text, selected_brand),
                brand=selected_brand,
                dimension=topic.dimension,
                reason=topic.reason.replace(brand_text, selected_brand),
                confidence=topic.confidence,
                coverage_gap=topic.coverage_gap.replace(brand_text, selected_brand),
            )
        )
    return repaired


def transition_candidate_status(current_status: str, requested_status: str) -> str:
    current = (current_status or "").strip().lower()
    requested = (requested_status or "").strip().lower()
    if requested not in {"approved", "rejected"}:
        raise TopicPlanLLMError("invalid_review_status", "Review status must be approved or rejected")
    if current not in REVIEW_STATUSES:
        raise TopicPlanLLMError("invalid_current_status", "Candidate has an invalid current status")
    if current != "pending":
        raise TopicPlanLLMError("candidate_already_reviewed", "Candidate has already been reviewed")
    return requested


def build_topic_plan_messages(
    *,
    industry: str,
    category: str,
    brands: list[dict[str, Any]],
    coverage_gaps: list[dict[str, Any]],
    max_topics: int,
    existing_topics: list[str],
) -> list[dict[str, str]]:
    allowed_brand_names = [str(brand.get("name") or "").strip() for brand in brands]
    allowed_brand_names = [name for name in allowed_brand_names if name]
    selected_brand_payload = [
        {
            "name": str(brand.get("name") or "").strip(),
            "industry": brand.get("industry") or brand.get("industry_name") or "",
            "topic_count": brand.get("topic_count", 0),
        }
        for brand in brands
        if str(brand.get("name") or "").strip()
    ]
    schema = {
        "topics": [
            {
                "title": "...",
                "brand": "...",
                "dimension": "brand|product|category|scenario|question",
                "reason": "...",
                "confidence": 0.0,
                "coverage_gap": "...",
            }
        ]
    }
    payload = {
        "industry": industry,
        "category": category,
        "selected_brands": selected_brand_payload,
        "allowed_brand_names": allowed_brand_names,
        "allowed_brand_names_text": "、".join(allowed_brand_names),
        "coverage_gaps": coverage_gaps,
        "max_topics": max_topics,
        "existing_topics": existing_topics[:300],
        "output_schema": schema,
    }
    system = (
        "You are the GENPANO Topic Plan generator for operations users. "
        "Return strict JSON only. No markdown. No explanations. "
        "Never introduce unselected brands, competitors, prompts, queries, table names, or engineering notes."
    )
    user = (
        "Generate Topic Plan candidates.\n"
        "Hard rules:\n"
        f"1. The only allowed brand values are: {payload['allowed_brand_names_text']}.\n"
        "2. topics[].brand must copy exactly one allowed brand value. Do not use brand id, numbers, aliases, or any other brand.\n"
        "3. Write title and reason in Chinese for an operations user.\n"
        "4. Each title must be about the selected brand, industry, category, and coverage_gaps.\n"
        "5. Avoid duplicates or near-duplicates with existing_topics.\n"
        "6. dimension must be one of brand, product, category, scenario, question.\n"
        "7. If allowed brand values are masked as question marks by the model, use the same placeholder consistently in title, brand, and coverage_gap.\n"
        "8. If allowed_brand_names and coverage_gaps are non-empty, return at least 1 candidate.\n"
        "9. Return at most max_topics items and match output_schema exactly.\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


class DoubaoTopicPlanClient:
    """Small OpenAI-compatible client for Volcengine Ark / Doubao 2."""

    def __init__(self, config: DoubaoConfig | None = None):
        self.config = config or load_doubao_config()

    def generate_topics(
        self,
        *,
        industry: str,
        category: str,
        brands: list[dict[str, Any]],
        coverage_gaps: list[dict[str, Any]],
        max_topics: int,
        existing_topics: list[str],
    ) -> tuple[list[LLMTopic], dict[str, Any]]:
        try:
            from openai import OpenAI
        except Exception as error:  # pragma: no cover - environment dependent
            raise TopicPlanLLMError("llm_client_unavailable", "OpenAI-compatible client is unavailable") from error

        messages = build_topic_plan_messages(
            industry=industry,
            category=category,
            brands=brands,
            coverage_gaps=coverage_gaps,
            max_topics=max_topics,
            existing_topics=existing_topics,
        )
        client = OpenAI(api_key=self.config.api_key, base_url=self.config.base_url)
        try:
            response = client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=0.1,
                timeout=90,
            )
        except Exception as error:
            raise TopicPlanLLMError("llm_call_failed", "Doubao 2 topic generation failed") from error

        content = response.choices[0].message.content or "{}"
        topics = repair_single_brand_placeholders(parse_llm_topics(content), brands)
        usage_obj = getattr(response, "usage", None)
        usage = {}
        if usage_obj is not None:
            if hasattr(usage_obj, "model_dump"):
                usage = usage_obj.model_dump()
            elif isinstance(usage_obj, dict):
                usage = dict(usage_obj)
            else:
                usage = {
                    key: getattr(usage_obj, key)
                    for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                    if hasattr(usage_obj, key)
                }
        return topics, {"model": self.config.model, "usage": usage}
