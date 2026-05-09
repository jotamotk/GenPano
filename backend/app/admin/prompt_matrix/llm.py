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
    build_prompt_generation_slots,
    build_prompt_matrix_messages,
    clamp_int,
    intent_language_combinations,
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

DEFAULT_LLM_TARGET_PROMPTS_PER_REQUEST = 12


def _topic_key(topic: dict[str, Any]) -> str | None:
    raw = topic.get("raw_id") or topic.get("id")
    if raw is None:
        return None
    try:
        return str(int(raw))
    except (TypeError, ValueError):
        return None


def _slots_for_topic(topic: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    combinations = config.get("combinations") or intent_language_combinations(
        config.get("intent_count"),
        config.get("language_count"),
        config.get("max_per_topic"),
    )
    return build_prompt_generation_slots(
        topic=topic,
        combinations=combinations,
        max_per_topic=config.get("max_per_topic"),
    )


def _slot_batches(
    *,
    topics: list[dict[str, Any]],
    config: dict[str, Any],
    max_topics: int,
    max_slots: int,
) -> list[tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], int]]:
    batches: list[tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], int]] = []
    current_topics: list[dict[str, Any]] = []
    current_slots: dict[str, list[dict[str, Any]]] = {}
    current_count = 0

    def flush() -> None:
        nonlocal current_topics, current_slots, current_count
        if current_count <= 0:
            return
        batches.append(
            (
                list(current_topics),
                {key: list(slots) for key, slots in current_slots.items()},
                current_count,
            )
        )
        current_topics = []
        current_slots = {}
        current_count = 0

    for topic in topics:
        key = _topic_key(topic)
        if key is None:
            continue
        remaining_slots = _slots_for_topic(topic, config)
        while remaining_slots:
            needs_new_topic = key not in current_slots
            topic_limit_hit = needs_new_topic and len(current_topics) >= max_topics
            if current_count and (topic_limit_hit or current_count >= max_slots):
                flush()
                continue

            room = max_slots - current_count
            if room <= 0:
                flush()
                continue

            if key not in current_slots:
                current_topics.append(topic)
                current_slots[key] = []
            take_count = min(len(remaining_slots), room)
            current_slots[key].extend(remaining_slots[:take_count])
            current_count += take_count
            remaining_slots = remaining_slots[take_count:]
            if current_count >= max_slots:
                flush()

    flush()
    return batches


def _limit_slots(
    slots_by_topic: dict[str, list[dict[str, Any]]],
    limit: int,
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    remaining = max(0, limit)
    for key, slots in slots_by_topic.items():
        if remaining <= 0:
            break
        selected = slots[:remaining]
        if selected:
            result[key] = selected
            remaining -= len(selected)
    return result


def _topics_for_slots(
    topics: list[dict[str, Any]], slots_by_topic: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    keys = set(slots_by_topic)
    return [topic for topic in topics if (_topic_key(topic) or "") in keys]


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
        max_slots_per_request = clamp_int(
            os.getenv("PROMPT_MATRIX_LLM_TARGET_PROMPTS_PER_REQUEST"),
            DEFAULT_LLM_TARGET_PROMPTS_PER_REQUEST,
            1,
            40,
        )
        max_prompts = clamp_int(
            config.get("max_prompts"), DEFAULT_MAX_PROMPTS, 1, MAX_PROMPTS_HARD_LIMIT
        )
        generated_prompts: list[LLMPromptCandidate] = []
        for batch, slots_by_topic, slot_count in _slot_batches(
            topics=topics,
            config=config,
            max_topics=batch_size,
            max_slots=max_slots_per_request,
        ):
            remaining = max_prompts - len(generated_prompts)
            if remaining <= 0:
                break
            batch_config = dict(config)
            target = min(remaining, slot_count)
            limited_slots = _limit_slots(slots_by_topic, target)
            batch = _topics_for_slots(batch, limited_slots)
            if not batch:
                continue
            batch_config["generation_slots_by_topic"] = limited_slots
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
