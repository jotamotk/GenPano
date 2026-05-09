"""Async httpx port of admin_console's PromptMatrixClient.

Same wire format as the OpenAI-compatible Doubao endpoint admin_console
used; sync OpenAI SDK replaced with httpx.AsyncClient (matches the
DoubaoTopicPlanClient port shipped in Phase 3 B.1).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.admin.prompt_matrix.lib import (
    DEFAULT_MAX_PROMPTS,
    MAX_PROMPTS_HARD_LIMIT,
    LLMPromptCandidate,
    PromptMatrixError,
    build_prompt_matrix_messages,
    chunked,
    clamp_int,
    estimate_generation_count,
    llm_error_detail,
    llm_response_error_detail,
    merge_usage,
    over_request_count,
    parse_llm_prompt_candidates,
    usage_to_dict,
)
from app.admin.topic_plan.lib import (
    DoubaoConfig,
    TopicPlanLLMError,
    load_doubao_config,
)


class PromptMatrixClient:
    """Small OpenAI-compatible async client for Volcengine Ark / Doubao 2."""

    def __init__(self, config: DoubaoConfig | None = None) -> None:
        try:
            self.config = config or load_doubao_config()
        except TopicPlanLLMError as error:
            raise PromptMatrixError(error.code, error.message) from error

    async def generate_prompts(
        self,
        *,
        topics: list[dict[str, Any]],
        config: dict[str, Any],
        known_brands: list[dict[str, Any]],
        existing_prompts: list[str],
    ) -> tuple[list[LLMPromptCandidate], dict[str, Any]]:
        all_prompts: list[LLMPromptCandidate] = []
        usage: dict[str, Any] = {}
        batches = 0
        async for prompts, meta in self.generate_prompt_batches(
            topics=topics,
            config=config,
            known_brands=known_brands,
            existing_prompts=existing_prompts,
        ):
            all_prompts.extend(prompts)
            usage = merge_usage(usage, meta.get("usage") or {})
            batches += 1
        return all_prompts, {"model": self.config.model, "usage": usage, "batches": batches}

    async def generate_prompt_batches(
        self,
        *,
        topics: list[dict[str, Any]],
        config: dict[str, Any],
        known_brands: list[dict[str, Any]],
        existing_prompts: list[str],
        active_hotspots: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[tuple[list[LLMPromptCandidate], dict[str, Any]]]:
        if not topics:
            return
        batch_size = clamp_int(os.getenv("PROMPT_MATRIX_LLM_TOPICS_PER_REQUEST"), 2, 1, 5)
        max_prompts = clamp_int(
            config.get("max_prompts"), DEFAULT_MAX_PROMPTS, 1, MAX_PROMPTS_HARD_LIMIT
        )
        generated_prompts: list[LLMPromptCandidate] = []
        for batch in chunked(topics, batch_size):
            remaining = max_prompts - len(generated_prompts)
            if remaining <= 0:
                break
            batch_config = dict(config)
            target = min(
                remaining,
                estimate_generation_count(
                    selected_topics=len(batch),
                    intent_count=config.get("intent_count"),
                    language_count=config.get("language_count"),
                    max_per_topic=config.get("max_per_topic"),
                    max_prompts=remaining,
                ),
            )
            batch_config["max_prompts"] = over_request_count(target)
            prompts, meta = await self._generate_prompt_batch(
                topics=batch,
                config=batch_config,
                known_brands=known_brands,
                existing_prompts=existing_prompts + [item.text for item in generated_prompts],
                active_hotspots=active_hotspots,
            )
            batch_prompts = prompts[:target]
            generated_prompts.extend(batch_prompts)
            yield batch_prompts, meta

    async def _generate_prompt_batch(
        self,
        *,
        topics: list[dict[str, Any]],
        config: dict[str, Any],
        known_brands: list[dict[str, Any]],
        existing_prompts: list[str],
        active_hotspots: list[dict[str, Any]] | None = None,
    ) -> tuple[list[LLMPromptCandidate], dict[str, Any]]:
        messages = build_prompt_matrix_messages(
            topics=topics,
            config=config,
            known_brands=known_brands,
            existing_prompts=existing_prompts,
            active_hotspots=active_hotspots,
        )
        timeout_seconds = clamp_int(
            os.getenv("PROMPT_MATRIX_LLM_TIMEOUT_SECONDS") or 90,
            90,
            60,
            240,
        )
        expected = max(1, int(config.get("max_prompts") or 1))
        max_tokens = clamp_int(
            os.getenv("PROMPT_MATRIX_LLM_MAX_TOKENS") or (1024 + expected * 1024),
            4096,
            1024,
            8192,
        )
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        body = {
            "model": self.config.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(url, json=body, headers=headers)
        except httpx.RequestError as error:
            raise PromptMatrixError(
                "llm_call_failed",
                "Prompt Matrix generation failed: " + llm_error_detail(error),
            ) from error

        if response.status_code != 200:
            raise PromptMatrixError(
                "llm_call_failed",
                "Prompt Matrix generation failed: " + llm_response_error_detail(response),
            )
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise PromptMatrixError("llm_call_failed", "Prompt Matrix returned no choices")
        content = (choices[0].get("message") or {}).get("content") or "{}"
        topics_by_id: dict[int, dict[str, Any]] = {}
        for topic in topics:
            raw = topic.get("raw_id") or topic.get("id")
            if raw is None or not str(raw).isdigit():
                continue
            topics_by_id[int(raw)] = topic
        prompts = parse_llm_prompt_candidates(
            content,
            topics_by_id=topics_by_id,
            known_brands=known_brands,
            default_template_strategy=config.get("template_strategy") or "latest",
            default_template_version="v1",
        )
        usage = usage_to_dict(data.get("usage"))
        return prompts, {"model": self.config.model, "usage": usage}
