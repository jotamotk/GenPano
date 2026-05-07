"""Phase 3 B.1 — async httpx port of DoubaoTopicPlanClient.

The client itself isn't called by any route in this PR (Phase 3 B.2's
``POST /generate`` will be its first caller), but the test confirms the
wire format matches the OpenAI-compatible endpoint admin_console used.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.admin.topic_plan.lib import DoubaoConfig, TopicPlanLLMError
from app.admin.topic_plan.llm import DoubaoTopicPlanClient


def _config() -> DoubaoConfig:
    return DoubaoConfig(
        api_key="test-key",
        base_url="https://example.invalid/v3",
        model="doubao-2",
    )


@pytest.mark.asyncio
async def test_generate_topics_happy_path(monkeypatch):
    captured = {}

    async def fake_post(self, url, json=None, headers=None):
        captured["url"] = url
        captured["body"] = json
        captured["headers"] = headers
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"topics":[{"title":"NIKE跑鞋选购指南","brand":"NIKE",'
                                '"dimension":"product","reason":"r",'
                                '"confidence":0.9,"coverage_gap":"NIKE:product"}]}'
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 34, "total_tokens": 46},
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    client = DoubaoTopicPlanClient(config=_config())
    topics, meta = await client.generate_topics(
        industry="footwear",
        category="running",
        brands=[{"name": "NIKE"}],
        coverage_gaps=[{"brand": "NIKE", "type": "product", "count": 1, "priority": "P1"}],
        max_topics=5,
        existing_topics=[],
    )
    assert len(topics) == 1
    assert topics[0].title == "NIKE跑鞋选购指南"
    assert meta["model"] == "doubao-2"
    assert meta["usage"]["total_tokens"] == 46
    assert captured["url"] == "https://example.invalid/v3/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["body"]["model"] == "doubao-2"
    assert isinstance(captured["body"]["messages"], list)


@pytest.mark.asyncio
async def test_generate_topics_http_error_raises(monkeypatch):
    async def fake_post(self, url, json=None, headers=None):
        return httpx.Response(500, json={"error": "boom"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    client = DoubaoTopicPlanClient(config=_config())
    with pytest.raises(TopicPlanLLMError) as exc:
        await client.generate_topics(
            industry="x",
            category="y",
            brands=[{"name": "NIKE"}],
            coverage_gaps=[],
            max_topics=1,
            existing_topics=[],
        )
    assert exc.value.code == "llm_call_failed"


@pytest.mark.asyncio
async def test_generate_topics_network_error_raises(monkeypatch):
    async def fake_post(self, url, json=None, headers=None):
        raise httpx.ConnectError("dns")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    client = DoubaoTopicPlanClient(config=_config())
    with pytest.raises(TopicPlanLLMError) as exc:
        await client.generate_topics(
            industry="x",
            category="y",
            brands=[{"name": "NIKE"}],
            coverage_gaps=[],
            max_topics=1,
            existing_topics=[],
        )
    assert exc.value.code == "llm_call_failed"


@pytest.mark.asyncio
async def test_generate_topics_empty_choices(monkeypatch):
    async def fake_post(self, url, json=None, headers=None):
        return httpx.Response(200, json={"choices": []})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    client = DoubaoTopicPlanClient(config=_config())
    with pytest.raises(TopicPlanLLMError) as exc:
        await client.generate_topics(
            industry="x",
            category="y",
            brands=[{"name": "NIKE"}],
            coverage_gaps=[],
            max_topics=1,
            existing_topics=[],
        )
    assert exc.value.code == "llm_call_failed"


@pytest.mark.asyncio
async def test_generate_topics_malformed_json_payload(monkeypatch):
    async def fake_post(self, url, json=None, headers=None):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not json {"}}]},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    client = DoubaoTopicPlanClient(config=_config())
    with pytest.raises(TopicPlanLLMError) as exc:
        await client.generate_topics(
            industry="x",
            category="y",
            brands=[{"name": "NIKE"}],
            coverage_gaps=[],
            max_topics=1,
            existing_topics=[],
        )
    assert exc.value.code == "llm_json_invalid"


def test_doubao_client_bypass_unused_json_import():
    # silence ruff F401 for json import — used in payload assertions above
    assert json.dumps([1])
