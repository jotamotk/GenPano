"""Phase 5 slice 3b-iii — Query Pool async LLM client tests.

Mocks ``httpx.AsyncClient.post`` so we exercise wire-format parsing,
batch boundaries, error mapping — without making real network calls.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.admin.query_pool.lib import query_pool_candidate_contexts
from app.admin.query_pool.llm import QueryPoolLLMClient, build_query_pool_llm_messages
from app.admin.topic_plan.lib import DoubaoConfig, TopicPlanLLMError


def _config():
    return DoubaoConfig(api_key="k", base_url="https://example.test/v1", model="doubao-pro")


def _ctx(key, **overrides):
    base = {
        "candidate_key": key,
        "prompt_id": "p1",
        "segment_id": "s1",
        "profile_id": "prof1",
        "topic_text": "敏感肌",
        "prompt_text": "敏感肌怎么选？",
        "profile_need": "屏障不稳",
        "profile_demographic": "30F",
        "profile_name": "Anna",
        "segment_name": "young-pros",
    }
    base.update(overrides)
    return base


def test_build_messages_returns_system_and_user():
    msgs = build_query_pool_llm_messages([_ctx("k1")])
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert "k1" in msgs[1]["content"]
    assert "前置质检规则" in msgs[1]["content"]
    assert "产品漂移" in msgs[1]["content"]
    assert "不要依赖后端修复或丢弃" in msgs[1]["content"]
    assert "Topic layer" in msgs[1]["content"]
    assert "Prompt layer" in msgs[1]["content"]
    assert "Query layer" in msgs[1]["content"]
    assert "prompt_scope" in msgs[1]["content"]
    assert "non_branded" in msgs[1]["content"]
    assert "branded" in msgs[1]["content"]
    assert "competitive" in msgs[1]["content"]
    assert "competitive_type" in msgs[1]["content"]
    assert "competitor_name" in msgs[1]["content"]
    assert "comparison_axis" in msgs[1]["content"]
    assert "brand_context_version" in msgs[1]["content"]


def test_query_pool_context_inherits_competitive_scope_and_type():
    contexts, raw_estimated = query_pool_candidate_contexts(
        [
            {
                "id": "p1",
                "text": "Is NIKE better than Adidas for beginner running shoes?",
                "topic_id": 1,
                "topic_text": "beginner running shoes",
                "tags": {"prompt_scope": "competitor", "competitive_type": "switching"},
            }
        ],
        [
            {
                "segment_id": "s1",
                "profile_id": "prof1",
                "segment_weight": 1,
                "profile_weight": 1,
                "profile_name": "Anna",
            }
        ],
        {
            "profiles_per_prompt": 1,
            "profile_strategy": "balanced",
            "max_candidates": 10,
            "overflow_policy": "split",
        },
    )

    assert raw_estimated == 1
    assert contexts[0]["prompt_scope"] == "competitive"
    assert contexts[0]["competitive_type"] == "switching"


@pytest.mark.asyncio
async def test_generate_query_batches_yields_per_batch_with_meta():
    contexts = [_ctx(f"k{i}") for i in range(3)]
    response_payload = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"queries": [{"candidate_key": "k0", "query": "Q0?"},'
                        '{"candidate_key": "k1", "query": "Q1?"},'
                        '{"candidate_key": "k2", "query": "Q2?"}]}'
                    )
                }
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }
    fake_resp = MagicMock(spec=httpx.Response)
    fake_resp.status_code = 200
    fake_resp.json.return_value = response_payload

    with patch("app.admin.query_pool.llm.httpx.AsyncClient") as mock_client_cls:
        client_ctx = AsyncMock()
        client_ctx.__aenter__.return_value = client_ctx
        client_ctx.__aexit__.return_value = False
        client_ctx.post = AsyncMock(return_value=fake_resp)
        mock_client_cls.return_value = client_ctx

        # batch size of 8 default → 1 batch covers all 3 contexts.
        os.environ.pop("QUERY_POOL_LLM_BATCH_SIZE", None)
        client = QueryPoolLLMClient(config=_config())
        out = []
        async for queries, meta in client.generate_query_batches(contexts):
            out.append((queries, meta))

    assert len(out) == 1
    queries, meta = out[0]
    assert sorted(queries.keys()) == ["k0", "k1", "k2"]
    assert meta["model"] == "doubao-pro"
    assert meta["usage"]["total_tokens"] == 30


@pytest.mark.asyncio
async def test_generate_query_batches_split_at_batch_size_boundary(monkeypatch):
    monkeypatch.setenv("QUERY_POOL_LLM_BATCH_SIZE", "2")
    contexts = [_ctx(f"k{i}") for i in range(5)]

    fake_resp = MagicMock(spec=httpx.Response)
    fake_resp.status_code = 200
    # The mocked post returns ALL contexts' keys regardless of batch — but
    # the parser only validates that all expected_keys for THIS batch are
    # present; it accepts unknown extras only as "unknown candidate_key"
    # errors, so we tailor each batch's expected output via side_effect.
    posted = []

    async def fake_post(url, json, headers):
        posted.append(json)
        # Pull candidates from the user message of this batch and emit a
        # response that matches them exactly.
        user_content = json["messages"][1]["content"]
        # Crude: find each "k{i}" mentioned in the user content.
        keys = []
        for i in range(10):
            if f'"k{i}"' in user_content:
                keys.append(f"k{i}")
        body = {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"queries": ['
                            + ",".join(
                                f'{{"candidate_key": "{k}", "query": "Q-{k}?"}}' for k in keys
                            )
                            + "]}"
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 1},
        }
        return MagicMock(status_code=200, json=lambda: body, spec=httpx.Response)

    with patch("app.admin.query_pool.llm.httpx.AsyncClient") as mock_client_cls:
        client_ctx = AsyncMock()
        client_ctx.__aenter__.return_value = client_ctx
        client_ctx.__aexit__.return_value = False
        client_ctx.post = AsyncMock(side_effect=fake_post)
        mock_client_cls.return_value = client_ctx

        client = QueryPoolLLMClient(config=_config())
        batches = []
        async for queries, _meta in client.generate_query_batches(contexts):
            batches.append(queries)

    # 5 contexts, batch_size=2 → 3 batches (sizes 2/2/1).
    assert len(batches) == 3
    assert len(batches[0]) == 2
    assert len(batches[1]) == 2
    assert len(batches[2]) == 1


@pytest.mark.asyncio
async def test_http_error_raises_llm_call_failed():
    fake_resp = MagicMock(spec=httpx.Response)
    fake_resp.status_code = 503
    fake_resp.text = '{"error":{"message":"upstream quota exceeded"}}'
    with patch("app.admin.query_pool.llm.httpx.AsyncClient") as mock_client_cls:
        client_ctx = AsyncMock()
        client_ctx.__aenter__.return_value = client_ctx
        client_ctx.__aexit__.return_value = False
        client_ctx.post = AsyncMock(return_value=fake_resp)
        mock_client_cls.return_value = client_ctx

        client = QueryPoolLLMClient(config=_config())
        with pytest.raises(TopicPlanLLMError) as exc_info:
            async for _ in client.generate_query_batches([_ctx("k1")]):
                pass
        assert exc_info.value.code == "llm_call_failed"
        assert "upstream quota exceeded" in exc_info.value.message


@pytest.mark.asyncio
async def test_request_error_raises_llm_call_failed():
    with patch("app.admin.query_pool.llm.httpx.AsyncClient") as mock_client_cls:
        client_ctx = AsyncMock()
        client_ctx.__aenter__.return_value = client_ctx
        client_ctx.__aexit__.return_value = False
        client_ctx.post = AsyncMock(side_effect=httpx.ConnectError("boom"))
        mock_client_cls.return_value = client_ctx

        client = QueryPoolLLMClient(config=_config())
        with pytest.raises(TopicPlanLLMError) as exc_info:
            async for _ in client.generate_query_batches([_ctx("k1")]):
                pass
        assert exc_info.value.code == "llm_call_failed"
