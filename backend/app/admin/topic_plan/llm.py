"""Async httpx port of admin_console's DoubaoTopicPlanClient.

The original sync client used `openai.OpenAI` which is sync-only and
brings the OpenAI SDK as a dep. Here we POST directly to the
OpenAI-compatible chat completions endpoint via httpx.AsyncClient — same
wire format, no extra dep.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from typing import Any

import httpx

try:
    from json_repair import repair_json
except Exception:  # pragma: no cover - optional dependency
    repair_json = None

from app.admin.brand_context import assemble_brand_context_pack
from app.admin.topic_plan.lib import (
    DoubaoConfig,
    LLMTopic,
    TopicPlanLLMError,
    bounded_int,
    build_topic_plan_messages,
    load_doubao_config,
    parse_llm_topics,
    repair_single_brand_placeholders,
    strip_markdown_fence,
)

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _response_text_snippet(response: httpx.Response, *, limit: int = 800) -> str:
    text = ""
    try:
        data = response.json()
        text = json.dumps(data, ensure_ascii=False)
    except Exception:
        text = response.text or ""
    text = " ".join(text.split())
    return text[:limit]


def _web_research_request_error_message(
    error: httpx.RequestError,
    *,
    timeout_seconds: int,
) -> str:
    error_name = error.__class__.__name__
    detail = str(error).strip()
    if isinstance(error, httpx.TimeoutException):
        message = (
            f"Topic Plan brand context search timed out after {timeout_seconds}s ({error_name})"
        )
    else:
        message = f"Topic Plan brand context search request failed ({error_name})"
    if detail:
        message += f": {detail}"
    return (
        message
        + ". Verify Ark network access, TOPIC_PLAN_WEB_RESEARCH_MODEL, and Volcengine Web Search entitlement."
    )


def _topic_generation_request_error_message(
    error: httpx.RequestError,
    *,
    timeout_seconds: int,
) -> str:
    error_name = error.__class__.__name__
    detail = str(error).strip()
    if isinstance(error, httpx.TimeoutException):
        message = (
            f"Doubao 2 topic generation chat/completions timed out after {timeout_seconds}s "
            f"({error_name})"
        )
    else:
        message = f"Doubao 2 topic generation chat/completions request failed ({error_name})"
    if detail:
        message += f": {detail}"
    return message + ". Verify Ark chat/completions network access and model availability."


def _search_status_is_retryable(status_code: int) -> bool:
    return status_code in {408, 409, 425, 429, 500, 502, 503, 504}


def _responses_output_text(data: dict[str, Any]) -> str:
    direct = data.get("output_text")
    if isinstance(direct, str):
        return direct.strip()
    chunks: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if isinstance(content, str):
            chunks.append(content)
            continue
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            text = part.get("text") or part.get("content")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunk.strip() for chunk in chunks if chunk and chunk.strip())


def _text_snippet(text: str, *, limit: int = 500) -> str:
    return " ".join((text or "").split())[:limit]


def _brand_name_key(value: str) -> str:
    return "".join(ch for ch in (value or "").casefold() if ch.isalnum())


def _as_research_payload(value: Any) -> dict[str, Any] | None:
    if isinstance(value, list):
        return {"brands": value}
    if isinstance(value, dict) and isinstance(value.get("brands"), list):
        return value
    return None


def _iter_json_values(text: str) -> Iterator[Any]:
    decoder = json.JSONDecoder()
    index = 0
    length = len(text)
    while index < length:
        while index < length and text[index] not in "{[":
            index += 1
        if index >= length:
            break
        try:
            value, end = decoder.raw_decode(text[index:])
        except Exception:
            index += 1
            continue
        yield value
        index += max(end, 1)


def _load_research_json(raw: str) -> dict[str, Any] | None:
    cleaned = strip_markdown_fence(raw)
    if not cleaned:
        return None
    try:
        parsed = json.loads(cleaned)
    except Exception:
        parsed = None
    payload = _as_research_payload(parsed)
    if payload is not None:
        return payload
    for value in _iter_json_values(cleaned):
        payload = _as_research_payload(value)
        if payload is not None:
            return payload
    if repair_json is not None:
        try:
            payload = _as_research_payload(json.loads(repair_json(cleaned)))
        except Exception:
            payload = None
        if payload is not None:
            return payload
    return None


def _parse_brand_research(raw: str, allowed_names: list[str]) -> list[dict[str, Any]]:
    if not raw:
        return []
    data = _load_research_json(raw)
    if data is None:
        logger.warning("topic_plan web research returned non-json payload")
        return []
    items = data.get("brands") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    allowed = {name for name in allowed_names if name}
    allowed_by_casefold = {name.casefold(): name for name in allowed}
    allowed_by_key = {_brand_name_key(name): name for name in allowed}
    cleaned: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        canonical_name = (
            name
            if name in allowed
            else allowed_by_casefold.get(name.casefold())
            or allowed_by_key.get(_brand_name_key(name))
        )
        if allowed and not canonical_name:
            continue
        out: dict[str, Any] = {"name": canonical_name or name}
        for key in (
            "industry",
            "positioning",
            "description",
            "category_terms",
            "product_lines",
            "signature_features",
            "target_audiences",
            "shopping_scenarios",
            "consumer_questions",
            "products",
            "scenarios",
            "competitors",
            "audience_hypotheses",
            "claims",
            "official_domains",
        ):
            value = item.get(key)
            if isinstance(value, str):
                out[key] = value[:400]
            elif isinstance(value, list):
                if key in {"products", "scenarios", "competitors", "audience_hypotheses"}:
                    normalized_items: list[dict[str, Any]] = []
                    for entry in value:
                        if isinstance(entry, dict):
                            normalized_items.append(entry)
                        else:
                            text = str(entry).strip()
                            if text:
                                normalized_items.append({"name": text[:240]})
                    out[key] = normalized_items[:12]
                else:
                    out[key] = [str(v).strip()[:120] for v in value if str(v).strip()][:10]
            elif isinstance(value, dict) and key == "claims":
                out[key] = value
        claims = item.get("claims")
        if isinstance(claims, list):
            out["claims"] = {"pros": [str(v).strip()[:160] for v in claims if str(v).strip()][:12]}
        source_notes = item.get("source_notes")
        if isinstance(source_notes, list):
            out["source_notes"] = [
                {
                    "title": str(note.get("title") or "").strip()[:160],
                    "url": str(note.get("url") or "").strip()[:300],
                    "snippet": str(note.get("snippet") or "").strip()[:300],
                    "source_type": str(note.get("source_type") or "web_search").strip()[:40],
                }
                for note in source_notes
                if isinstance(note, dict) and (note.get("title") or note.get("url"))
            ][:5]
            if not out.get("source_notes"):
                out["source_notes"] = [
                    {
                        "title": str(note).strip()[:160],
                        "url": "",
                        "snippet": "",
                        "source_type": "web_search",
                    }
                    for note in source_notes
                    if not isinstance(note, dict) and str(note).strip()
                ][:5]
        cleaned.append(out)
    return cleaned[: len(allowed_names) or 5]


class DoubaoTopicPlanClient:
    """Small OpenAI-compatible async client for Volcengine Ark / Doubao 2."""

    def __init__(self, config: DoubaoConfig | None = None) -> None:
        self.config = config or load_doubao_config()

    async def research_brand_context(
        self,
        *,
        industry: str,
        category: str,
        brands: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Search-backed enrichment for brand/category context."""
        if not _env_bool("TOPIC_PLAN_ENABLE_WEB_RESEARCH", True):
            if _env_bool("TOPIC_PLAN_REQUIRE_WEB_RESEARCH", True):
                raise TopicPlanLLMError(
                    "brand_context_search_failed",
                    "Topic Plan requires web research; TOPIC_PLAN_ENABLE_WEB_RESEARCH is off.",
                )
            return []
        allowed_names = [str(b.get("name") or "").strip() for b in brands]
        allowed_names = [name for name in allowed_names if name]
        if not allowed_names:
            return []

        timeout_seconds = bounded_int(
            os.getenv("TOPIC_PLAN_WEB_RESEARCH_TIMEOUT_SECONDS") or 120,
            120,
            20,
            240,
        )
        attempts = bounded_int(os.getenv("TOPIC_PLAN_WEB_RESEARCH_ATTEMPTS") or 2, 2, 1, 3)
        model = os.getenv("TOPIC_PLAN_WEB_RESEARCH_MODEL") or self.config.model
        url = self.config.base_url.rstrip("/") + "/responses"
        compact_brands = [
            {
                "name": b.get("name"),
                "industry": b.get("industry") or b.get("industry_name") or industry,
                "description": (str(b.get("description") or "")[:500]) or None,
                "target_market": (str(b.get("target_market") or "")[:160]) or None,
                "products": [
                    {
                        "name": p.get("name"),
                        "category": p.get("category"),
                        "description": (str(p.get("description") or "")[:220]) or None,
                    }
                    for p in (b.get("products") or [])[:8]
                    if p.get("name")
                ],
            }
            for b in brands
        ]
        selected_brand_rows: list[str] = []
        for brand in compact_brands:
            product_names = [
                str(product.get("name"))
                for product in (brand.get("products") or [])
                if isinstance(product, dict) and product.get("name")
            ]
            selected_brand_rows.append(
                f"- name: {brand.get('name')}; "
                f"industry_hint: {brand.get('industry') or industry or 'unknown'}; "
                f"description: {brand.get('description') or 'unknown'}; "
                f"target_market: {brand.get('target_market') or 'unknown'}; "
                f"known_products: {', '.join(product_names)}"
            )
        selected_brand_lines = "\n".join(selected_brand_rows)
        prompt = (
            "Use web search to research the selected brands for Topic Plan generation. "
            "Prefer official brand pages, product/category pages, major retailers, and credible encyclopedic sources. "
            "Return strict JSON only; do not include markdown or explanatory text. "
            "Do not copy the input back. "
            "Do not invent facts; if a field is not supported by sources, return an empty array or null. "
            "Summarize consumer-facing category, product, feature, audience, competitor, and scenario signals.\n\n"
            f"Industry hint: {industry or 'All industries'}\n"
            f"Category hint: {category or 'All categories'}\n"
            "Selected brands. Copy each output brands[].name exactly from these names:\n"
            f"{selected_brand_lines}\n\n"
            "Required output shape:\n"
            "- top-level object with key brands only.\n"
            "- brands: array. One object per selected brand.\n"
            "- each brand object fields: name, industry, positioning, official_domains, products, scenarios, competitors, audience_hypotheses, claims, consumer_questions, source_notes.\n"
            "- products: objects with name, category, key_features, use_cases, target_users, price_positioning.\n"
            "- scenarios: objects with name, pain_points, decision_criteria, buying_stage.\n"
            "- competitors: objects with name, competitor_type, overlap_category, comparison_axes, relation_reason. Use direct competitors when sources support them; otherwise use an empty array.\n"
            "- audience_hypotheses: objects with segment_name, needs, regions, buying_stage.\n"
            "- claims: object with pros, cons, best_for, not_fit_for, risks, price_perception arrays.\n"
            "- source_notes: objects with title, url, snippet, source_type.\n"
        )
        body = {
            "model": model,
            "tools": [{"type": "web_search"}],
            "input": [{"role": "user", "content": prompt}],
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        require_research = _env_bool("TOPIC_PLAN_REQUIRE_WEB_RESEARCH", True)
        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                    response = await client.post(url, json=body, headers=headers)
            except httpx.RequestError as error:
                detail = _web_research_request_error_message(
                    error,
                    timeout_seconds=timeout_seconds,
                )
                if attempt < attempts and not isinstance(error, httpx.TimeoutException):
                    logger.warning(
                        "%s Retrying Topic Plan brand context search (%s/%s).",
                        detail,
                        attempt + 1,
                        attempts,
                    )
                    continue
                if require_research:
                    raise TopicPlanLLMError(
                        "brand_context_search_failed",
                        detail,
                    ) from error
                logger.warning(detail)
                return []
            if response.status_code != 200:
                detail = (
                    f"Topic Plan brand context search returned HTTP {response.status_code}: "
                    + _response_text_snippet(response, limit=400)
                )
                if attempt < attempts and _search_status_is_retryable(response.status_code):
                    logger.warning(
                        "%s Retrying Topic Plan brand context search (%s/%s).",
                        detail,
                        attempt + 1,
                        attempts,
                    )
                    continue
                if require_research:
                    raise TopicPlanLLMError("brand_context_search_failed", detail)
                logger.warning(detail)
                return []
            try:
                data = response.json()
            except Exception as error:
                detail = "Topic Plan brand context search returned invalid JSON"
                if attempt < attempts:
                    logger.warning(
                        "%s. Retrying Topic Plan brand context search (%s/%s).",
                        detail,
                        attempt + 1,
                        attempts,
                    )
                    continue
                if require_research:
                    raise TopicPlanLLMError("brand_context_search_failed", detail) from error
                return []
            raw_output = _responses_output_text(data)
            result = _parse_brand_research(raw_output, allowed_names)
            if result:
                if require_research:
                    returned_names = {
                        _brand_name_key(str(item.get("name") or "")) for item in result
                    }
                    missing_names = [
                        name
                        for name in allowed_names
                        if _brand_name_key(name) not in returned_names
                    ]
                    if missing_names:
                        detail = (
                            "Topic Plan brand context search missed selected brands: "
                            + ", ".join(missing_names[:5])
                        )
                        if attempt < attempts:
                            logger.warning(
                                "%s. Retrying Topic Plan brand context search (%s/%s).",
                                detail,
                                attempt + 1,
                                attempts,
                            )
                            continue
                        raise TopicPlanLLMError("brand_context_search_failed", detail)
                return result
            detail = "Topic Plan brand context search returned no usable brand context"
            snippet = _text_snippet(raw_output, limit=300)
            if snippet:
                detail += f": {snippet}"
            if attempt < attempts:
                logger.warning(
                    "%s. Retrying Topic Plan brand context search (%s/%s).",
                    detail,
                    attempt + 1,
                    attempts,
                )
                continue
            if require_research:
                raise TopicPlanLLMError("brand_context_search_failed", detail)
            logger.warning(detail)
            return []
        return []

    async def generate_topics(
        self,
        *,
        industry: str,
        category: str,
        brands: list[dict[str, Any]],
        coverage_gaps: list[dict[str, Any]],
        max_topics: int,
        existing_topics: list[str],
    ) -> tuple[list[LLMTopic], dict[str, Any]]:
        brand_research = await self.research_brand_context(
            industry=industry,
            category=category,
            brands=brands,
        )
        search_by_name = {str(item.get("name") or ""): item for item in brand_research}
        brand_context_packs = {
            str(brand.get("name") or ""): assemble_brand_context_pack(
                brand=brand,
                search_context=search_by_name.get(str(brand.get("name") or "")),
            )
            for brand in brands
            if str(brand.get("name") or "")
        }
        messages = build_topic_plan_messages(
            industry=industry,
            category=category,
            brands=brands,
            coverage_gaps=coverage_gaps,
            max_topics=max_topics,
            existing_topics=existing_topics,
            brand_research=brand_research,
            brand_context_packs=brand_context_packs,
        )
        timeout_seconds = bounded_int(
            os.getenv("TOPIC_PLAN_LLM_TIMEOUT_SECONDS") or 600, 600, 30, 3600
        )
        attempts = bounded_int(os.getenv("TOPIC_PLAN_LLM_ATTEMPTS") or 2, 2, 1, 3)
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        body = {
            "model": self.config.model,
            "messages": messages,
            "temperature": 0.1,
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        response: httpx.Response | None = None
        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                    response = await client.post(url, json=body, headers=headers)
            except httpx.RequestError as error:
                detail = _topic_generation_request_error_message(
                    error,
                    timeout_seconds=timeout_seconds,
                )
                if attempt < attempts:
                    logger.warning(
                        "%s Retrying Doubao 2 topic generation (%s/%s).",
                        detail,
                        attempt + 1,
                        attempts,
                    )
                    continue
                raise TopicPlanLLMError("llm_call_failed", detail) from error

            if response.status_code == 200:
                break
            detail = f"Doubao 2 returned HTTP {response.status_code}: " + _response_text_snippet(
                response
            )
            if attempt < attempts and _search_status_is_retryable(response.status_code):
                logger.warning(
                    "%s Retrying Doubao 2 topic generation (%s/%s).",
                    detail,
                    attempt + 1,
                    attempts,
                )
                continue
            raise TopicPlanLLMError("llm_call_failed", detail)

        if response is None:
            raise TopicPlanLLMError("llm_call_failed", "Doubao 2 topic generation did not run")
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise TopicPlanLLMError("llm_call_failed", "Doubao 2 returned no choices")
        content = (choices[0].get("message") or {}).get("content") or "{}"
        topics = repair_single_brand_placeholders(parse_llm_topics(content), brands)
        usage = data.get("usage") or {}
        return topics, {
            "model": self.config.model,
            "usage": dict(usage),
            "brand_context_packs": brand_context_packs,
        }
