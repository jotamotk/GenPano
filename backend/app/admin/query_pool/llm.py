"""Async httpx Query Pool LLM client.

Mirrors admin_console.app.QueryPoolLLMClient field-for-field but on
``httpx.AsyncClient`` so the worker can run inside FastAPI's event
loop (no thread per run). Same Doubao/Ark OpenAI-compatible wire
format as ``DoubaoTopicPlanClient`` and ``PromptMatrixClient``.

Public:
- ``QueryPoolLLMClient.generate_query_batches(contexts)`` — async
  generator yielding ``(queries, batch_meta)`` per LLM batch.
- ``build_query_pool_llm_messages(contexts)`` — system + user content
  builder used by both the client and tests.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.admin.query_pool.text_clean import (
    _clamp_int,
    parse_query_pool_llm_queries,
    query_pool_chunked,
    query_pool_llm_batch_size,
    query_pool_llm_error_detail,
    query_pool_llm_response_error_detail,
    query_pool_usage_to_dict,
)
from app.admin.topic_plan.lib import (
    DoubaoConfig,
    TopicPlanLLMError,
    load_doubao_config,
)


def build_query_pool_llm_messages(contexts: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Build the system + user messages for one batch.

    Vendored verbatim from admin_console — every prompt rule (CJK length
    limits, forbidden internal terms, full-question requirement, etc.)
    is exactly what the existing operators expect.
    """
    schema = {
        "queries": [
            {
                "candidate_key": "copy candidate_key exactly",
                "query": "a natural consumer query",
            }
        ]
    }
    payload = {"candidates": contexts, "output_schema": schema}
    system = (
        "你是 GENPANO Query Pool 的真实消费者 Query 生成器。"
        "你只负责把 Prompt + Topic + Segment/Profile 的上下文改写成真实消费者会搜索或询问的一句话。"
        "只返回严格 JSON，不要返回 Markdown，不要解释。"
    )
    user = (
        "请为 payload.candidates 中的每个 candidate_key 生成 1 条 Query。\n"
        "Layer definitions:\n"
        "Topic layer = high-level, reusable, brand-neutral consumer demand boundary; it should not contain selected brand or competitor names.\n"
        "Prompt layer = natural user question and already owns prompt_scope: non_branded, branded, competitor.\n"
        "Query layer = Prompt plus Segment/Profile context. Query must preserve prompt_scope and must not introduce new brands or competitors.\n"
        "prompt_scope rules: non_branded queries must not add brand/competitor names; branded queries keep the brand already present in Prompt; competitor queries keep the comparison/alternative framing and do not invent concrete competitors if Prompt did not name them.\n\n"
        "前置质检规则，生成时必须主动满足，不要依赖后端修复或丢弃：\n"
        "A. 避免 query_not_natural：每条都必须像真实消费者直接输入的一句话。\n"
        "B. 避免内部词：不要出现 Segment/Profile/用户画像/persona/admin/后台/调度/执行引擎等词。\n"
        "C. 避免标题短语：不能只输出 Topic 标题、关键词、人群标签或商品卖点。\n"
        "D. 避免产品漂移：品牌、产品、品类、场景必须和 Prompt/Topic 保持一致。\n"
        "E. 避免非完整问题：必须有可回答的疑问或决策意图。\n"
        "被修复的 query_repaired 会进入质量指标，无法修复的会进入 rejected_sample；请尽量一次生成可通过质检的结果。\n"
        "核心规则：\n"
        "1. Query 必须像真实消费者在搜索框、社媒、购物前或和 LLM 对话时会直接输入的一句话。\n"
        "2. Prompt 是任务意图，Topic 是主题边界，Segment/Profile 是消费者背景；三者都要影响最终 Query。\n"
        "3. 不要机械替换模板变量，不要写“请以某某视角回答”，要把 Profile 的年龄、城市、预算、需求、顾虑自然融入。\n"
        "4. 不同 Profile 即使属于重叠 Segment，也应该因为预算、场景、顾虑不同而生成不同问法。\n"
        "5. 不要出现 Segment/Profile/用户画像/persona/admin/后台/调度/执行引擎等内部词。\n"
        "6. 不要写运营分析、品牌方策略、CRM、市场表现、转化路径；只写消费者会问的问题。\n"
        "7. 中文 Query 通常 10-36 个汉字；英文 Query 通常 7-18 个词。按原 Prompt 的语言自然输出。\n"
        "8. 可以有口语感：怎么选、值不值、会不会踩雷、适不适合、哪款更稳、预算内怎么买。\n"
        "9. 每条都必须是完整问题，不要只输出标题、短语、卖点词或人群标签；中文建议带"
        "“怎么/哪款/会不会/适合吗/值得吗/？”等提问信号。\n"
        "10. 如果 Profile 强调预算，不要生硬写“价格敏感型”，可以写“预算有限 / 不想太贵 / 值不值”。\n"
        "11. 如果 Profile 强调送礼、通勤、敏感肌、学生党、刚入职等场景，要用消费者自己的说法表达。\n"
        "12. 保持 Query 和 Prompt/Topic 的产品、品类、品牌或场景一致，不要漂移到其他产品。\n"
        "13. 输出必须严格匹配 output_schema；queries 数量必须等于 candidates 数量。\n\n"
        "好例子：\n"
        "Prompt: 预算内怎么选大牌香水？ Profile: 刚入职白领，送礼不踩雷，价格别太夸张\n"
        "Query: 刚入职送人大牌香水，哪款不太贵又不容易踩雷？\n"
        "Prompt: 敏感肌修复面霜怎么选？ Profile: 屏障不稳，担心刺激\n"
        "Query: 敏感肌屏障不稳，修复面霜怎么选才不刺激？\n\n"
        "payload:\n" + json.dumps(payload, ensure_ascii=False)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


class QueryPoolLLMClient:
    """Async OpenAI-compatible client targetting Doubao/Ark."""

    def __init__(self, config: DoubaoConfig | None = None) -> None:
        try:
            self.config = config or load_doubao_config()
        except TopicPlanLLMError:
            raise

    async def generate_query_batches(
        self, contexts: list[dict[str, Any]]
    ) -> AsyncIterator[tuple[dict[str, str], dict[str, Any]]]:
        """Yield ``(queries, meta)`` per batch so the worker can stream
        progress (insert rows + update preflight_summary between batches).
        """
        batch_size = query_pool_llm_batch_size()
        for batch in query_pool_chunked(contexts, batch_size):
            queries, meta = await self._generate_query_batch(batch)
            yield queries, meta

    async def _generate_query_batch(
        self, contexts: list[dict[str, Any]]
    ) -> tuple[dict[str, str], dict[str, Any]]:
        """One LLM HTTP call against the chat-completions endpoint."""
        timeout_seconds = _clamp_int(os.getenv("QUERY_POOL_LLM_TIMEOUT_SECONDS"), 90, 30, 240)
        max_tokens = _clamp_int(
            os.getenv("QUERY_POOL_LLM_MAX_TOKENS") or (1024 + len(contexts) * 320),
            4096,
            512,
            12000,
        )
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        body = {
            "model": self.config.model,
            "messages": build_query_pool_llm_messages(contexts),
            "temperature": 0.25,
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
            raise TopicPlanLLMError(
                "llm_call_failed",
                "Query Pool LLM generation failed: " + query_pool_llm_error_detail(error),
            ) from error

        if response.status_code != 200:
            raise TopicPlanLLMError(
                "llm_call_failed",
                "Query Pool LLM generation failed: "
                + query_pool_llm_response_error_detail(response),
            )
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise TopicPlanLLMError("llm_call_failed", "Query Pool LLM returned no choices")
        content = (choices[0].get("message") or {}).get("content") or "{}"
        # validate_queries=False so the caller can salvage borderline output
        # via query_pool_repair_query_text in candidates_from_llm_queries.
        queries = parse_query_pool_llm_queries(
            content,
            [c["candidate_key"] for c in contexts],
            validate_queries=False,
        )
        usage = query_pool_usage_to_dict(data.get("usage"))
        return queries, {"model": self.config.model, "usage": usage}
