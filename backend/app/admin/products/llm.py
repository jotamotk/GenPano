"""Async LLM port for product discovery (Phase 8 slice 8a).

Mirrors brand_management/llm.py and topic_plan/llm.py: sync
``openai.OpenAI`` client replaced with httpx.AsyncClient against an
OpenAI-compatible chat completions endpoint (Volcengine Ark / Doubao).

Public:
- ``ProductDiscoveryResult`` — return shape for ``discover_products``.
- ``discover_products(brand, *, query, limit)`` — async LLM call;
  raises ``TopicPlanLLMError`` on transport / schema problems.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.admin.products.lib import coerce_product_aliases
from app.admin.topic_plan.lib import (
    TopicPlanLLMError,
    load_doubao_config,
)


@dataclass
class ProductDiscoveryResult:
    items: list[dict[str, Any]]
    model: str
    usage: dict[str, Any] = field(default_factory=dict)


def _bounded_int(raw: Any, default: int, lo: int, hi: int) -> int:
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(n, hi))


def _strip_markdown_fence(raw: str) -> str:
    text = (raw or "").strip()
    if not text.startswith("```"):
        return text
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _parse_response(raw: str | dict[str, Any]) -> list[dict[str, Any]]:
    """Mirror admin_console ``_parse_product_discovery_response``."""
    try:
        data = raw if isinstance(raw, dict) else json.loads(_strip_markdown_fence(str(raw or "")))
    except Exception as error:
        raise TopicPlanLLMError(
            "llm_json_invalid", "Product discovery returned invalid JSON"
        ) from error
    products = data.get("products") if isinstance(data, dict) else None
    if not isinstance(products, list):
        raise TopicPlanLLMError(
            "llm_schema_invalid",
            "Product discovery JSON must contain a products array",
        )

    parsed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(products):
        if not isinstance(item, dict):
            raise TopicPlanLLMError(
                "llm_schema_invalid", f"Product item #{index + 1} must be an object"
            )
        name = str(item.get("name") or "").strip()
        if not name:
            raise TopicPlanLLMError(
                "llm_schema_invalid", f"Product item #{index + 1} is missing name"
            )
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        parsed.append(
            {
                "name": name[:256],
                "sku": str(item.get("sku") or "").strip()[:128],
                "category": str(item.get("category") or "").strip()[:128],
                "description": str(item.get("description") or "").strip(),
                "aliases": coerce_product_aliases(item.get("aliases")),
            }
        )
    return parsed


def _build_messages(brand: dict[str, Any], *, query: str, limit: int) -> list[dict[str, Any]]:
    payload = {
        "brand": {
            "name": brand.get("name") or "",
            "aliases": brand.get("aliases") or [],
            "industry": brand.get("industry") or "",
            "target_market": brand.get("target_market") or "",
            "description": brand.get("description") or "",
        },
        "operator_hint": query or "",
        "limit": limit,
    }
    system = (
        "You discover real, commercially meaningful products/SKUs for a brand. "
        "Use current public knowledge when available. Return strict JSON only."
    )
    user = (
        "Find products that should be tracked in GENPANO Admin. "
        "Prefer flagship, current, high-search-interest products. "
        'Return JSON: {"products":[{"name":"...","sku":"...",'
        '"category":"...","description":"...","aliases":["..."]}]}. '
        "Do not invent internal product codes. Keep names concise.\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def llm_status_code_for_error(error: Exception) -> int:
    """Return the HTTP status to surface for an LLM-discovery failure.
    Matches admin_console line 6035: 503 for transport/llm-tagged
    errors, 502 for upstream-shaped errors."""
    if not isinstance(error, TopicPlanLLMError):
        return 503
    code = str(getattr(error, "code", "") or "")
    if code.startswith("llm_"):
        return 503
    return 502


async def discover_products(
    brand: dict[str, Any], *, query: str = "", limit: int = 8
) -> ProductDiscoveryResult:
    cfg = load_doubao_config()
    timeout_seconds = _bounded_int(
        os.getenv("PRODUCT_DISCOVERY_LLM_TIMEOUT_SECONDS") or 90, 90, 30, 240
    )
    url = cfg.base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": cfg.model,
        "messages": _build_messages(brand, query=query, limit=limit),
        "temperature": 0.2,
        "max_tokens": max(1024, min(4096, 512 + limit * 320)),
    }
    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(url, json=body, headers=headers)
    except httpx.RequestError as error:
        raise TopicPlanLLMError("llm_call_failed", "Product discovery LLM call failed") from error
    if response.status_code != 200:
        raise TopicPlanLLMError(
            "llm_call_failed",
            f"Product discovery LLM returned HTTP {response.status_code}",
        )
    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise TopicPlanLLMError("llm_call_failed", "Product discovery LLM returned no choices")
    content = (choices[0].get("message") or {}).get("content") or "{}"
    items = _parse_response(content)
    usage = data.get("usage") or {}
    model = data.get("model") or cfg.model
    return ProductDiscoveryResult(items=items, model=model, usage=dict(usage))


__all__ = [
    "ProductDiscoveryResult",
    "discover_products",
    "llm_status_code_for_error",
]
