"""Async Brand Management LLM service.

Port of admin_console/brand_management.py BrandManagementService — sync
OpenAI SDK replaced with httpx.AsyncClient (matches the topic_plan /
prompt_matrix / query_pool / segments LLM port pattern).

Public:
- ``BrandGenerationResult`` — returned by ``generate_brands`` /
  ``enrich_brand_by_name``.
- ``BrandManagementService`` — async client. Reuses Doubao/Ark config.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.admin.brand_management.lib import (
    BrandManagementError,
    brand_enrich_context,
    brand_schema_hint,
    coerce_str_list,
    extract_llm_items,
    normalize_brand_draft,
    validate_brand_candidates,
)
from app.admin.topic_plan.lib import (
    DoubaoConfig,
    TopicPlanLLMError,
    load_doubao_config,
)


@dataclass
class BrandGenerationResult:
    items: list[dict[str, Any]]
    model: str
    prompt: str
    usage: dict[str, Any]
    estimated_cost: float | None = None


def _bounded_count(value: Any, default: int, min_value: int, max_value: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(min_value, min(n, max_value))


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
        raise BrandManagementError("llm_json_invalid", "LLM returned invalid JSON") from error
    if not isinstance(parsed, dict):
        raise BrandManagementError("llm_schema_invalid", "LLM JSON root must be an object")
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


def _json_prompt(task: str, payload: dict[str, Any], schema_hint: dict[str, Any]) -> str:
    return (
        "You are generating Admin-reviewed Brand drafts for the GENPANO knowledge graph.\n"
        "Return only strict JSON. Do not include markdown, comments, prose, or "
        "code fences.\n"
        "Validate all required fields, keep requested count or fewer, avoid duplicate names, "
        "and prefer real, commercially significant brands in the requested industry/region.\n"
        "Each brand must be a verifiable, commonly recognized company so it can be added as a "
        "node in the industry knowledge graph. Suggested competitors will be projected as "
        "COMPETES_WITH edges, so list 1-4 well-known peers.\n"
        f"Task: {task}\n"
        f"Input: {json.dumps(payload, ensure_ascii=False, sort_keys=True)}\n"
        f"Output schema: {json.dumps(schema_hint, ensure_ascii=False, sort_keys=True)}"
    )


class BrandManagementService:
    """Async OpenAI-compatible Brand draft generation client."""

    def __init__(
        self,
        model: str | None = None,
        config: DoubaoConfig | None = None,
        allow_fallback: bool | None = None,
        timeout_seconds: int | None = None,
    ):
        self.model_override = (model or os.getenv("BRAND_MANAGEMENT_LLM_MODEL") or "").strip()
        self.config = config
        self.timeout_seconds = timeout_seconds
        self.allow_fallback = (
            allow_fallback
            if allow_fallback is not None
            else os.getenv("BRAND_MANAGEMENT_LLM_ALLOW_FALLBACK", "0") == "1"
        )

    def _llm_config(self) -> DoubaoConfig:
        try:
            return self.config or load_doubao_config()
        except TopicPlanLLMError as error:
            raise BrandManagementError(error.code, error.message) from error

    async def _call_llm_json(
        self, *, prompt: str, root_key: str, max_count: int
    ) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
        config = self._llm_config()
        model = self.model_override or getattr(config, "model", "")
        timeout_source = (
            self.timeout_seconds
            if self.timeout_seconds is not None
            else os.getenv("BRAND_MANAGEMENT_LLM_TIMEOUT_SECONDS") or 90
        )
        timeout_seconds = _bounded_count(timeout_source, 90, 5, 240)
        max_tokens = _bounded_count(
            os.getenv("BRAND_MANAGEMENT_LLM_MAX_TOKENS") or (1500 + max_count * 480),
            5120,
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
                        "You are a precise data generator for an Admin operations console. "
                        "Output valid JSON only. Never invent fictional brands."
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
            raise BrandManagementError(
                "llm_call_failed",
                "Brand management LLM generation failed: " + str(error)[:500],
            ) from error

        if response.status_code != 200:
            raise BrandManagementError(
                "llm_call_failed",
                f"Brand management LLM generation failed: HTTP {response.status_code}",
            )
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise BrandManagementError(
                "llm_call_failed", "Brand management LLM returned no choices"
            )
        content = (choices[0].get("message") or {}).get("content") or "{}"
        parsed = _load_json_object(content)
        items = extract_llm_items(parsed, root_key)
        return items, model, _usage_to_dict(data.get("usage"))

    async def generate_brands(
        self,
        *,
        industry: str,
        count: int,
        region: str = "",
        positioning: str = "",
        seed_brands: list[str] | None = None,
        constraints: str = "",
        language: str = "auto",
    ) -> BrandGenerationResult:
        """Generate brand drafts for an industry. ``seed_brands`` lists
        already-known brands the LLM should avoid duplicating."""
        industry = (industry or "").strip()
        if not industry:
            raise BrandManagementError("missing_industry", "industry is required")
        count = _bounded_count(count, 8, 1, 30)
        seeds = coerce_str_list(seed_brands or [], max_items=64, max_len=256)
        payload = {
            "industry": industry,
            "count": count,
            "region": (region or "").strip(),
            "positioning": (positioning or "").strip(),
            "constraints": (constraints or "").strip(),
            "language": (language or "auto").strip().lower(),
            "exclude_brands": seeds,
        }
        prompt = _json_prompt("generate_brands", payload, brand_schema_hint())
        try:
            raw_items, model, usage = await self._call_llm_json(
                prompt=prompt, root_key="brands", max_count=count
            )
            drafts = validate_brand_candidates(raw_items, count)
            for draft in drafts:
                if not draft.get("industry"):
                    draft["industry"] = industry
            return BrandGenerationResult(
                items=drafts,
                model=model,
                prompt=prompt,
                usage=usage,
                estimated_cost=None,
            )
        except BrandManagementError:
            if not self.allow_fallback:
                raise
        return self._fallback_brands(
            industry=industry,
            count=count,
            region=(region or "").strip(),
            seeds=seeds,
            prompt=prompt,
        )

    async def enrich_brand_by_name(
        self, *, name: str, context: dict[str, Any] | None = None
    ) -> BrandGenerationResult:
        """LLM-fill the rest of a brand record from a name + filled fields.

        Returns 1-5 candidate brands so the operator can pick one when
        the name is ambiguous (e.g. "Apple" → fruit company vs. tech).
        """
        name = (name or "").strip()
        if not name:
            raise BrandManagementError("missing_brand_name", "Brand name is required")
        filled_fields = brand_enrich_context(context)
        payload = {"brand_name": name, "filled_fields": filled_fields}
        prompt = (
            "You are enriching ONE Brand entry for the GENPANO knowledge graph.\n"
            "Return only strict JSON. Do not include markdown, comments, prose, or "
            "code fences.\n"
            "Use `filled_fields` as disambiguating context. More filled fields should "
            "narrow the result more precisely, similar to search filters. If "
            "`brand_name` is ambiguous, return 1-5 candidate brands instead of "
            "guessing; the Admin operator will choose one. If the filled fields "
            "identify a single brand, return one candidate. Use real, publicly "
            "known facts about each brand. Do NOT invent. If a field is genuinely "
            "unknown, return null or an empty array. Do not restrict industry to "
            "an existing list; if the brand belongs to a new industry, return that "
            "new industry string.\n"
            "The output `brands` array must contain 1-5 candidate brands whose names "
            "match or clearly correspond to the requested brand name.\n"
            "Suggested competitors (1-4 well-known peers) become COMPETES_WITH edges "
            "in the knowledge graph; SAME_GROUP only when truly part of the same parent.\n"
            "Task: enrich_brand\n"
            f"Input: {json.dumps(payload, ensure_ascii=False)}\n"
            f"Output schema: {json.dumps(brand_schema_hint(), ensure_ascii=False, sort_keys=True)}"
        )
        try:
            raw_items, model, usage = await self._call_llm_json(
                prompt=prompt, root_key="brands", max_count=5
            )
            drafts = validate_brand_candidates(raw_items, max_count=5, dedupe_names=False)
            if drafts and not drafts[0].get("name"):
                drafts[0]["name"] = name
            return BrandGenerationResult(
                items=drafts,
                model=model,
                prompt=prompt,
                usage=usage,
                estimated_cost=None,
            )
        except BrandManagementError:
            if not self.allow_fallback:
                raise
        stub = normalize_brand_draft({"name": name, "source": "llm", "status": "draft"})
        return BrandGenerationResult(
            items=[stub],
            model="fallback-brand-management-v1",
            prompt=prompt,
            usage={"total_tokens": 0, "source": "deterministic_fallback"},
            estimated_cost=0.0,
        )

    def _fallback_brands(
        self,
        *,
        industry: str,
        count: int,
        region: str,
        seeds: list[str],
        prompt: str,
    ) -> BrandGenerationResult:
        """Deterministic placeholder used only when ``allow_fallback``."""
        archetypes = [
            ("Heritage Leader", "Established global benchmark player.", "global"),
            ("Premium Challenger", "Premium-priced challenger with design focus.", "global"),
            ("Mass Market Leader", "Mass-market volume leader with deep distribution.", "global"),
            ("DTC Disruptor", "Digitally native direct-to-consumer disruptor.", "global"),
            ("Regional Champion", "Strong presence in core regional market.", region or "regional"),
            ("Value Specialist", "Value-tier specialist with sharp pricing.", "global"),
            ("Niche Specialist", "Niche category specialist with cult following.", "global"),
            ("Tech-First Entrant", "Tech-driven new entrant with platform play.", "global"),
        ]
        existing = {seed.casefold() for seed in seeds}
        items: list[dict[str, Any]] = []
        for index in range(count):
            archetype, summary, market = archetypes[index % len(archetypes)]
            base_name = f"{industry.title()} {archetype}"
            counter = 1
            candidate = base_name
            while candidate.casefold() in existing:
                counter += 1
                candidate = f"{base_name} {counter}"
            existing.add(candidate.casefold())
            items.append(
                {
                    "name": candidate,
                    "name_zh": None,
                    "name_en": candidate,
                    "industry": industry,
                    "target_market": region or market,
                    "description": f"{summary} Auto-generated fallback for {industry}.",
                    "positioning": archetype,
                    "headquarters": "",
                    "founded_year": None,
                    "aliases": [],
                    "official_domains": [],
                    "competitors": [],
                    "tags": [],
                    "status": "draft",
                }
            )
        drafts = validate_brand_candidates(items, count)
        return BrandGenerationResult(
            items=drafts,
            model="fallback-brand-management-v1",
            prompt=prompt,
            usage={"total_tokens": 0, "source": "deterministic_fallback"},
            estimated_cost=0.0,
        )


def brand_enrich_timeout_seconds() -> int:
    """Per-request timeout cap for brand enrich (admin_console default 90s)."""
    try:
        value = int(os.getenv("BRAND_MANAGEMENT_ENRICH_TIMEOUT_SECONDS") or 90)
    except (TypeError, ValueError):
        value = 90
    return max(30, min(value, 240))
