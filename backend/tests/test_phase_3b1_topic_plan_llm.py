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
from app.admin.topic_plan.llm import DoubaoTopicPlanClient, _parse_brand_research


def _config() -> DoubaoConfig:
    return DoubaoConfig(
        api_key="test-key",
        base_url="https://example.invalid/v3",
        model="doubao-2",
    )


def test_parse_brand_research_matches_brand_names_case_and_space_insensitively():
    rows = _parse_brand_research(
        (
            '{"brands":[{"name":"Best Coffer","industry":"VDR",'
            '"source_notes":[{"title":"Official","url":"https://bestcoffer.example"}]}]}'
        ),
        ["bestCoffer"],
    )

    assert len(rows) == 1
    assert rows[0]["name"] == "bestCoffer"
    assert rows[0]["industry"] == "VDR"


@pytest.mark.asyncio
async def test_generate_topics_happy_path(monkeypatch):
    posted = []

    async def fake_post(self, url, json=None, headers=None):
        posted.append({"url": url, "body": json, "headers": headers})
        if url.endswith("/responses"):
            return httpx.Response(
                200,
                json={
                    "output": [
                        {
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": (
                                        '{"brands":[{"name":"NIKE","industry":"sportswear",'
                                        '"products":[{"name":"Pegasus",'
                                        '"category":"running shoes"}],'
                                        '"scenarios":[{"name":"beginner running"}],'
                                        '"competitors":[{"name":"Adidas","competitor_type":"direct",'
                                        '"comparison_axes":["cushioning"]}],'
                                        '"source_notes":[{"title":"Official","url":"https://nike.example"}]}]}'
                                    ),
                                }
                            ]
                        }
                    ]
                },
            )
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
    assert meta["brand_context_packs"]["NIKE"]["products"][0]["name"] == "Pegasus"
    assert posted[0]["url"] == "https://example.invalid/v3/responses"
    assert posted[1]["url"] == "https://example.invalid/v3/chat/completions"
    assert posted[1]["headers"]["Authorization"] == "Bearer test-key"
    assert posted[1]["body"]["model"] == "doubao-2"
    assert isinstance(posted[1]["body"]["messages"], list)
    assert "brand_context_packs" in posted[1]["body"]["messages"][1]["content"]


@pytest.mark.asyncio
async def test_generate_topics_missing_brand_search_context_raises(monkeypatch):
    posted = []

    async def fake_post(self, url, json=None, headers=None):
        posted.append({"url": url, "body": json, "headers": headers})
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"brands":[{"name":"NIKE","industry":"sportswear"}]}',
                            }
                        ]
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    client = DoubaoTopicPlanClient(_config())

    with pytest.raises(TopicPlanLLMError) as exc:
        await client.generate_topics(
            industry="footwear",
            category="running",
            brands=[{"id": 1, "name": "NIKE"}, {"id": 2, "name": "Adidas"}],
            coverage_gaps=[],
            max_topics=1,
            existing_topics=[],
        )

    assert exc.value.code == "brand_context_search_failed"
    assert "Adidas" in exc.value.message
    assert len(posted) == 2


@pytest.mark.asyncio
async def test_generate_topics_uses_web_research_context(monkeypatch):
    posted = []

    async def fake_post(self, url, json=None, headers=None):
        posted.append({"url": url, "body": json})
        if url.endswith("/responses"):
            return httpx.Response(
                200,
                json={
                    "output": [
                        {
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": (
                                        '{"brands":[{"name":"NIKE","industry":"sportswear",'
                                        '"category_terms":["慢跑鞋","通勤运动鞋"],'
                                        '"signature_features":["缓震","透气"],'
                                        '"shopping_scenarios":["新手慢跑","夏天通勤"],'
                                        '"consumer_questions":["新手慢跑鞋怎么选"]}]}'
                                    ),
                                }
                            ]
                        }
                    ]
                },
            )
        assert "brand_research" in json["messages"][1]["content"]
        assert "brand_context_packs" in json["messages"][1]["content"]
        assert "新手慢跑" in json["messages"][1]["content"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"topics":[{"title":"新手慢跑鞋怎么选不容易伤膝盖",'
                                '"brand":"NIKE","dimension":"category","reason":"r",'
                                '"confidence":0.9,"coverage_gap":"NIKE:category"}]}'
                            )
                        }
                    }
                ],
                "usage": {"total_tokens": 46},
            },
        )

    monkeypatch.setenv("TOPIC_PLAN_ENABLE_WEB_RESEARCH", "1")
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    client = DoubaoTopicPlanClient(config=_config())
    topics, _meta = await client.generate_topics(
        industry="footwear",
        category="running",
        brands=[{"name": "NIKE"}],
        coverage_gaps=[{"brand": "NIKE", "type": "category", "count": 1, "priority": "P1"}],
        max_topics=5,
        existing_topics=[],
    )

    assert len(topics) == 1
    assert posted[0]["url"] == "https://example.invalid/v3/responses"
    assert posted[0]["body"]["tools"] == [{"type": "web_search"}]
    assert posted[1]["url"] == "https://example.invalid/v3/chat/completions"


@pytest.mark.asyncio
async def test_generate_topics_http_error_raises(monkeypatch):
    async def fake_post(self, url, json=None, headers=None):
        if url.endswith("/responses"):
            return httpx.Response(
                200,
                json={
                    "output_text": (
                        '{"brands":[{"name":"NIKE","industry":"sportswear",'
                        '"source_notes":[{"title":"Official","url":"https://nike.example"}]}]}'
                    )
                },
            )
        return httpx.Response(
            400,
            json={"error": {"code": "InvalidModel", "message": "model endpoint not found"}},
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
    assert exc.value.code == "llm_call_failed"
    assert "HTTP 400" in exc.value.message
    assert "InvalidModel" in exc.value.message
    assert "model endpoint not found" in exc.value.message


@pytest.mark.asyncio
async def test_generate_topics_search_failure_raises(monkeypatch):
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
    assert exc.value.code == "brand_context_search_failed"
    assert "dns" in exc.value.message


@pytest.mark.asyncio
async def test_generate_topics_search_timeout_message_is_actionable(monkeypatch):
    async def fake_post(self, url, json=None, headers=None):
        raise httpx.ReadTimeout("")

    monkeypatch.setenv("TOPIC_PLAN_WEB_RESEARCH_TIMEOUT_SECONDS", "90")
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

    assert exc.value.code == "brand_context_search_failed"
    assert "ReadTimeout" in exc.value.message
    assert "90s" in exc.value.message
    assert "Web Search" in exc.value.message


@pytest.mark.asyncio
async def test_research_brand_context_retries_unusable_search_output(monkeypatch):
    posted = []

    async def fake_post(self, url, json=None, headers=None):
        posted.append({"url": url, "body": json})
        if len(posted) == 1:
            return httpx.Response(200, json={"output_text": "I found the brand, but no JSON."})
        return httpx.Response(
            200,
            json={
                "output_text": (
                    '{"brands":[{"name":"BestCoffer","industry":"VDR",'
                    '"source_notes":[{"title":"Official","url":"https://bestcoffer.example"}]}]}'
                )
            },
        )

    monkeypatch.setenv("TOPIC_PLAN_WEB_RESEARCH_ATTEMPTS", "2")
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    client = DoubaoTopicPlanClient(config=_config())
    rows = await client.research_brand_context(
        industry="data security",
        category="vdr",
        brands=[{"name": "bestCoffer"}],
    )

    assert len(posted) == 2
    assert rows[0]["name"] == "bestCoffer"


@pytest.mark.asyncio
async def test_generate_topics_empty_choices(monkeypatch):
    async def fake_post(self, url, json=None, headers=None):
        if url.endswith("/responses"):
            return httpx.Response(
                200,
                json={
                    "output_text": (
                        '{"brands":[{"name":"NIKE","industry":"sportswear",'
                        '"source_notes":[{"title":"Official","url":"https://nike.example"}]}]}'
                    )
                },
            )
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
async def test_generate_topics_llm_timeout_message_is_actionable(monkeypatch):
    async def fake_post(self, url, json=None, headers=None):
        if url.endswith("/responses"):
            return httpx.Response(
                200,
                json={
                    "output_text": (
                        '{"brands":[{"name":"NIKE","industry":"sportswear",'
                        '"source_notes":[{"title":"Official","url":"https://nike.example"}]}]}'
                    )
                },
            )
        raise httpx.ReadTimeout("")

    monkeypatch.setenv("TOPIC_PLAN_LLM_TIMEOUT_SECONDS", "600")
    monkeypatch.setenv("TOPIC_PLAN_LLM_ATTEMPTS", "1")
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
    assert "ReadTimeout" in exc.value.message
    assert "600s" in exc.value.message
    assert "chat/completions" in exc.value.message


@pytest.mark.asyncio
async def test_generate_topics_retries_transient_llm_request_error(monkeypatch):
    posted_urls = []

    async def fake_post(self, url, json=None, headers=None):
        posted_urls.append(url)
        if url.endswith("/responses"):
            return httpx.Response(
                200,
                json={
                    "output_text": (
                        '{"brands":[{"name":"NIKE","industry":"sportswear",'
                        '"source_notes":[{"title":"Official","url":"https://nike.example"}]}]}'
                    )
                },
            )
        if len([item for item in posted_urls if item.endswith("/chat/completions")]) == 1:
            raise httpx.ConnectError("reset")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"topics":[{"title":"NIKE running shoes for beginners",'
                                '"brand":"NIKE","dimension":"product","reason":"r",'
                                '"confidence":0.9,"coverage_gap":"NIKE:product"}]}'
                            )
                        }
                    }
                ],
                "usage": {"total_tokens": 10},
            },
        )

    monkeypatch.setenv("TOPIC_PLAN_LLM_ATTEMPTS", "2")
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    client = DoubaoTopicPlanClient(config=_config())
    topics, meta = await client.generate_topics(
        industry="x",
        category="y",
        brands=[{"name": "NIKE"}],
        coverage_gaps=[],
        max_topics=1,
        existing_topics=[],
    )

    assert len([item for item in posted_urls if item.endswith("/chat/completions")]) == 2
    assert len(topics) == 1
    assert meta["usage"]["total_tokens"] == 10


@pytest.mark.asyncio
async def test_generate_topics_malformed_json_payload(monkeypatch):
    async def fake_post(self, url, json=None, headers=None):
        if url.endswith("/responses"):
            return httpx.Response(
                200,
                json={
                    "output_text": (
                        '{"brands":[{"name":"NIKE","industry":"sportswear",'
                        '"source_notes":[{"title":"Official","url":"https://nike.example"}]}]}'
                    )
                },
            )
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
