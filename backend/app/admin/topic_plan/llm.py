"""Async httpx port of admin_console's DoubaoTopicPlanClient.

The original sync client used `openai.OpenAI` which is sync-only and
brings the OpenAI SDK as a dep. Here we POST directly to the
OpenAI-compatible chat completions endpoint via httpx.AsyncClient — same
wire format, no extra dep.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from app.admin.topic_plan.lib import (
    DoubaoConfig,
    LLMTopic,
    TopicPlanLLMError,
    bounded_int,
    build_topic_plan_messages,
    load_doubao_config,
    parse_llm_topics,
    repair_single_brand_placeholders,
)


class DoubaoTopicPlanClient:
    """Small OpenAI-compatible async client for Volcengine Ark / Doubao 2."""

    def __init__(self, config: DoubaoConfig | None = None) -> None:
        self.config = config or load_doubao_config()

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
        messages = build_topic_plan_messages(
            industry=industry,
            category=category,
            brands=brands,
            coverage_gaps=coverage_gaps,
            max_topics=max_topics,
            existing_topics=existing_topics,
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
                "llm_call_failed", "Doubao 2 topic generation failed"
            ) from error

        if response.status_code != 200:
            raise TopicPlanLLMError(
                "llm_call_failed",
                f"Doubao 2 returned HTTP {response.status_code}",
            )
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise TopicPlanLLMError("llm_call_failed", "Doubao 2 returned no choices")
        content = (choices[0].get("message") or {}).get("content") or "{}"
        topics = repair_single_brand_placeholders(parse_llm_topics(content), brands)
        usage = data.get("usage") or {}
        return topics, {"model": self.config.model, "usage": dict(usage)}
