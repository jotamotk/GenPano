"""Prompt Matrix async LLM client error handling tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.admin.prompt_matrix.lib import PromptMatrixError
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
