"""Prompt Matrix async LLM client error handling tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.admin.prompt_matrix.lib import (
    LLMPromptCandidate,
    PromptMatrixError,
    prompt_generation_config,
)
from app.admin.prompt_matrix.llm import PromptMatrixClient
from app.admin.topic_plan.lib import DoubaoConfig


def _config() -> DoubaoConfig:
    return DoubaoConfig(api_key="k", base_url="https://example.test/v1", model="doubao-pro")


def _topic() -> dict[str, object]:
    return {
        "raw_id": 1,
        "id": "T-1",
        "title": "running shoe comfort",
        "brand": "NIKE",
        "brand_id": 1,
        "dimension_key": "category",
        "dimension": "category",
        "coverage": "gap",
    }


def _generation_config() -> dict[str, object]:
    return {
        "intent_count": 1,
        "language_count": 1,
        "max_per_topic": 1,
        "max_prompts": 1,
        "template_strategy": "latest",
        "prompt_style": "natural",
        "audience_mode": "general",
    }


@pytest.mark.asyncio
async def test_large_per_topic_generation_splits_llm_calls_by_slot_count(monkeypatch) -> None:
    monkeypatch.setenv("PROMPT_MATRIX_LLM_TARGET_PROMPTS_PER_REQUEST", "12")

    class RecordingClient(PromptMatrixClient):
        def __init__(self) -> None:
            super().__init__(config=_config())
            self.slot_counts: list[int] = []

        async def _discover_topic_competitors(self, **kwargs):
            return {}

        async def _generate_prompt_batch(self, **kwargs):
            config = kwargs["config"]
            topics = kwargs["topics"]
            slots_by_topic = config.get("generation_slots_by_topic") or {}
            slot_count = sum(len(slots) for slots in slots_by_topic.values())
            self.slot_counts.append(slot_count)

            prompts: list[LLMPromptCandidate] = []
            for topic in topics:
                topic_id = int(topic["raw_id"])
                for index, slot in enumerate(slots_by_topic.get(str(topic_id), []), start=1):
                    scope = str(slot.get("prompt_scope") or "non_branded")
                    competitive_type = slot.get("competitive_type")
                    tags = {"prompt_scope": scope, "source": "prompt_matrix"}
                    if competitive_type:
                        tags["competitive_type"] = competitive_type
                    prompts.append(
                        LLMPromptCandidate(
                            topic_id=topic_id,
                            intent=str(slot["intent"]),
                            language=str(slot["language"]),
                            text=f"{topic['title']} generated prompt {index}",
                            template_strategy="latest",
                            template_version="v1",
                            confidence=0.8,
                            reason="covers requested slot",
                            tags=tags,
                            competitive_type=str(competitive_type) if competitive_type else None,
                        )
                    )
            return prompts, {"model": self.config.model, "usage": {}}

    client = RecordingClient()
    generated = 0
    async for prompts, _meta in client.generate_prompt_batches(
        topics=[_topic()],
        config=prompt_generation_config(
            {
                "intent_count": 4,
                "language_count": 2,
                "max_per_topic": 20,
                "max_prompts": 20,
            }
        ),
        known_brands=[],
        existing_prompts=[],
    ):
        generated += len(prompts)

    assert generated == 20
    assert client.slot_counts == [12, 8]


@pytest.mark.asyncio
async def test_competitive_slots_use_discovered_competitors(monkeypatch) -> None:
    monkeypatch.setenv("PROMPT_MATRIX_LLM_TARGET_PROMPTS_PER_REQUEST", "12")

    class RecordingClient(PromptMatrixClient):
        def __init__(self) -> None:
            super().__init__(config=_config())
            self.discovered = False
            self.recorded_slots: list[dict[str, object]] = []

        async def _discover_topic_competitors(self, **kwargs):
            self.discovered = True
            return {
                "1": [
                    {
                        "name": "Adidas",
                        "brand_id": 2,
                        "source": "llm",
                        "scenario_axes": ["comfort", "daily training"],
                    }
                ]
            }

        async def _generate_prompt_batch(self, **kwargs):
            config = kwargs["config"]
            slots_by_topic = config.get("generation_slots_by_topic") or {}
            self.recorded_slots.extend(slots_by_topic.get("1", []))
            competitive_slots = [
                slot
                for slot in slots_by_topic.get("1", [])
                if slot.get("prompt_scope") == "competitive"
            ]
            prompts = [
                LLMPromptCandidate(
                    topic_id=1,
                    intent=str(slot["intent"]),
                    language=str(slot["language"]),
                    text="Is NIKE better than Adidas for daily training comfort?",
                    template_strategy="latest",
                    template_version="v1",
                    confidence=0.8,
                    reason="covers competitor slot",
                    tags={
                        "prompt_scope": "competitive",
                        "competitive_type": slot["competitive_type"],
                        "competitor_name": slot["competitor_name"],
                        "competitor_brand_id": slot["competitor_brand_id"],
                    },
                    competitive_type=str(slot["competitive_type"]),
                )
                for slot in competitive_slots[:1]
            ]
            return prompts, {"model": self.config.model, "usage": {}}

    client = RecordingClient()
    generated: list[LLMPromptCandidate] = []
    async for prompts, _meta in client.generate_prompt_batches(
        topics=[_topic()],
        config=prompt_generation_config(
            {
                "intent_count": 4,
                "language_count": 2,
                "max_per_topic": 8,
                "max_prompts": 8,
            }
        ),
        known_brands=[],
        existing_prompts=[],
    ):
        generated.extend(prompts)

    competitive_slots = [
        slot for slot in client.recorded_slots if slot.get("prompt_scope") == "competitive"
    ]
    assert client.discovered is True
    assert competitive_slots
    assert {slot["competitor_name"] for slot in competitive_slots} == {"Adidas"}
    assert {slot["competitor_brand_id"] for slot in competitive_slots} == {2}
    assert all(slot.get("scenario_axis") for slot in competitive_slots)
    assert generated[0].tags["competitor_name"] == "Adidas"
    assert generated[0].tags["competitor_brand_id"] == 2


@pytest.mark.asyncio
async def test_competitive_slot_metadata_is_backfilled_when_llm_omits_it(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PROMPT_MATRIX_LLM_TARGET_PROMPTS_PER_REQUEST", "12")

    class BackfillClient(PromptMatrixClient):
        def __init__(self) -> None:
            super().__init__(config=_config())

        async def _discover_topic_competitors(self, **kwargs):
            return {
                "1": [
                    {
                        "name": "Adidas",
                        "brand_id": 2,
                        "source": "llm",
                        "scenario_axes": ["comfort"],
                    }
                ]
            }

        async def _generate_prompt_batch(self, **kwargs):
            slots_by_topic = kwargs["config"].get("generation_slots_by_topic") or {}
            slot = next(
                slot
                for slot in slots_by_topic.get("1", [])
                if slot.get("prompt_scope") == "competitive"
            )
            return (
                [
                    LLMPromptCandidate(
                        topic_id=1,
                        intent=str(slot["intent"]),
                        language=str(slot["language"]),
                        text="Is NIKE better than Adidas for beginner running shoes?",
                        template_strategy="latest",
                        template_version="v1",
                        confidence=0.8,
                        reason="covers competitor slot",
                        tags={
                            "prompt_scope": "competitive",
                            "competitive_type": slot["competitive_type"],
                        },
                        competitive_type=str(slot["competitive_type"]),
                    )
                ],
                {"model": self.config.model, "usage": {}},
            )

    client = BackfillClient()
    generated: list[LLMPromptCandidate] = []
    async for prompts, _meta in client.generate_prompt_batches(
        topics=[_topic()],
        config=prompt_generation_config(
            {
                "intent_count": 4,
                "language_count": 2,
                "max_per_topic": 8,
                "max_prompts": 8,
            }
        ),
        known_brands=[],
        existing_prompts=[],
    ):
        generated.extend(prompts)

    assert generated[0].tags["competitor_name"] == "Adidas"
    assert generated[0].tags["competitor_brand_id"] == 2
    assert generated[0].tags["scenario_axis"] == "comfort"


@pytest.mark.asyncio
async def test_prompt_generation_retries_transient_batch_failure(monkeypatch) -> None:
    monkeypatch.setenv("PROMPT_MATRIX_LLM_BATCH_RETRIES", "1")
    monkeypatch.setenv("PROMPT_MATRIX_LLM_RETRY_DELAY_SECONDS", "0")

    class RetryClient(PromptMatrixClient):
        def __init__(self) -> None:
            super().__init__(config=_config())
            self.attempts = 0

        async def _discover_topic_competitors(self, **kwargs):
            return {}

        async def _generate_prompt_batch(self, **kwargs):
            self.attempts += 1
            if self.attempts == 1:
                raise PromptMatrixError(
                    "llm_call_failed",
                    "Prompt Matrix generation failed: timeout",
                )
            return (
                [
                    LLMPromptCandidate(
                        topic_id=1,
                        intent="informational",
                        language="en-US",
                        text="Is NIKE good for beginner running shoes?",
                        template_strategy="latest",
                        template_version="v1",
                        confidence=0.8,
                        reason="covers requested slot",
                        tags={"prompt_scope": "branded", "source": "prompt_matrix"},
                    )
                ],
                {"model": self.config.model, "usage": {}},
            )

    client = RetryClient()
    generated: list[LLMPromptCandidate] = []
    async for prompts, _meta in client.generate_prompt_batches(
        topics=[_topic()],
        config=prompt_generation_config(
            {
                "intent_count": 1,
                "language_count": 1,
                "max_per_topic": 1,
                "max_prompts": 1,
            }
        ),
        known_brands=[],
        existing_prompts=[],
    ):
        generated.extend(prompts)

    assert client.attempts == 2
    assert len(generated) == 1


@pytest.mark.asyncio
async def test_http_error_includes_upstream_body() -> None:
    fake_resp = MagicMock(spec=httpx.Response)
    fake_resp.status_code = 429
    fake_resp.text = '{"error":{"message":"rate limit exceeded"}}'

    with patch("app.admin.prompt_matrix.llm.httpx.AsyncClient") as mock_client_cls:
        client_ctx = AsyncMock()
        client_ctx.__aenter__.return_value = client_ctx
        client_ctx.__aexit__.return_value = False
        client_ctx.post = AsyncMock(return_value=fake_resp)
        mock_client_cls.return_value = client_ctx

        client = PromptMatrixClient(config=_config())
        with pytest.raises(PromptMatrixError) as exc_info:
            async for _ in client.generate_prompt_batches(
                topics=[_topic()],
                config=_generation_config(),
                known_brands=[],
                existing_prompts=[],
            ):
                pass

    assert exc_info.value.code == "llm_call_failed"
    assert "rate limit exceeded" in exc_info.value.message
