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
from typing import Any

import httpx

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
            f"Topic Plan brand context search timed out after {timeout_seconds}s "
            f"({error_name})"
        )
    else:
        message = f"Topic Plan brand context search request failed ({error_name})"
    if detail:
        message += f": {detail}"
    return (
        message
        + ". Verify Ark network access, TOPIC_PLAN_WEB_RESEARCH_MODEL, and Volcengine Web Search entitlement."
    )


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


def _parse_brand_research(raw: str, allowed_names: list[str]) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(strip_markdown_fence(raw))
    except Exception:
        logger.warning("topic_plan web research returned non-json payload")
        return []
    items = data.get("brands") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    allowed = {name for name in allowed_names if name}
    cleaned: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if allowed and name not in allowed:
            continue
        out: dict[str, Any] = {"name": name}
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
                    out[key] = [v for v in value if isinstance(v, dict)][:12]
                else:
                    out[key] = [str(v).strip()[:120] for v in value if str(v).strip()][:10]
            elif isinstance(value, dict) and key == "claims":
                out[key] = value
        source_notes = item.get("source_notes")
        if isinstance(source_notes, list):
            out["source_notes"] = [
                {
                    "title": str(note.get("title") or "").strip()[:160],
                    "url": str(note.get("url") or "").strip()[:300],
                }
                for note in source_notes
                if isinstance(note, dict) and (note.get("title") or note.get("url"))
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
        schema = {
            "brands": [
                {
                    "name": "copy selected brand name exactly",
                    "industry": "concise industry/category summary",
                    "positioning": "concise market positioning",
                    "official_domains": ["official domains"],
                    "products": [
                        {
                            "name": "product or product line name",
                            "category": "category",
                            "key_features": ["features"],
                            "use_cases": ["use cases"],
                            "target_users": ["target users"],
                            "price_positioning": "pricing tier if known",
                        }
                    ],
                    "scenarios": [
                        {
                            "name": "scenario",
                            "pain_points": ["pain points"],
                            "decision_criteria": ["decision criteria"],
                            "buying_stage": "awareness|comparison|shortlist|purchase",
                        }
                    ],
                    "competitors": [
                        {
                            "name": "competitor brand",
                            "competitor_type": "direct|adjacent",
                            "overlap_category": "overlap category",
                            "comparison_axes": ["comparison axes"],
                            "relation_reason": "why comparable",
                        }
                    ],
                    "audience_hypotheses": [
                        {
                            "segment_name": "audience segment",
                            "needs": ["needs"],
                            "regions": ["regions"],
                            "buying_stage": "stage",
                        }
                    ],
                    "claims": {
                        "pros": ["advantages"],
                        "cons": ["limitations"],
                        "best_for": ["best-fit scenarios"],
                        "not_fit_for": ["poor-fit scenarios"],
                        "risks": ["risks"],
                        "price_perception": ["price perceptions"],
                    },
                    "consumer_questions": ["natural consumer topic angles"],
                    "source_notes": [{"title": "source title", "url": "source url"}],
                }
            ]
        }
        prompt = (
            "Use web search to research the selected brands for Topic Plan generation. "
            "Prefer official brand pages, product/category pages, major retailers, and credible encyclopedic sources. "
            "Return strict JSON only; do not include markdown. "
            "Do not invent facts. Summarize consumer-facing category, product, feature, audience, and scenario signals. "
            "The JSON must match this schema and each brands[].name must copy a selected brand name exactly.\n\n"
            + json.dumps(
                {
                    "industry_hint": industry,
                    "category_hint": category,
                    "selected_brands": compact_brands,
                    "output_schema": schema,
                },
                ensure_ascii=False,
            )
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
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(url, json=body, headers=headers)
        except httpx.RequestError as error:
            detail = _web_research_request_error_message(
                error,
                timeout_seconds=timeout_seconds,
            )
            if _env_bool("TOPIC_PLAN_REQUIRE_WEB_RESEARCH", True):
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
            if _env_bool("TOPIC_PLAN_REQUIRE_WEB_RESEARCH", True):
                raise TopicPlanLLMError("brand_context_search_failed", detail)
            logger.warning(detail)
            return []
        try:
            data = response.json()
        except Exception as error:
            if _env_bool("TOPIC_PLAN_REQUIRE_WEB_RESEARCH", True):
                raise TopicPlanLLMError(
                    "brand_context_search_failed",
                    "Topic Plan brand context search returned invalid JSON",
                ) from error
            return []
        result = _parse_brand_research(_responses_output_text(data), allowed_names)
        if not result and _env_bool("TOPIC_PLAN_REQUIRE_WEB_RESEARCH", True):
            raise TopicPlanLLMError(
                "brand_context_search_failed",
                "Topic Plan brand context search returned no usable brand context",
            )
        if _env_bool("TOPIC_PLAN_REQUIRE_WEB_RESEARCH", True):
            returned_names = {str(item.get("name") or "").strip().casefold() for item in result}
            missing_names = [
                name for name in allowed_names if name.strip().casefold() not in returned_names
            ]
            if missing_names:
                raise TopicPlanLLMError(
                    "brand_context_search_failed",
                    "Topic Plan brand context search missed selected brands: "
                    + ", ".join(missing_names[:5]),
                )
        return result

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
            os.getenv("TOPIC_PLAN_LLM_TIMEOUT_SECONDS") or 90, 90, 30, 240
        )
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
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(url, json=body, headers=headers)
        except httpx.RequestError as error:
            raise TopicPlanLLMError(
                "llm_call_failed", f"Doubao 2 topic generation failed: {error}"
            ) from error

        if response.status_code != 200:
            raise TopicPlanLLMError(
                "llm_call_failed",
                f"Doubao 2 returned HTTP {response.status_code}: "
                + _response_text_snippet(response),
            )
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
