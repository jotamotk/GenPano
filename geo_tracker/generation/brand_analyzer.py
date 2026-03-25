"""
品牌分析器
输入品牌信息 → GLM API → 结构化输出 Topics + Prompts + Competitors
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

from zhipuai import ZhipuAI

logger = logging.getLogger(__name__)

GLM_MODEL   = os.getenv("GLM_MODEL", "glm-5")
ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY", "")


@dataclass
class TopicResult:
    text: str
    category: str   # awareness | comparison | recommendation | problem_solving


@dataclass
class PromptResult:
    topic_index: int
    text: str
    intent: str
    language: str   # zh | en


@dataclass
class CompetitorResult:
    name: str
    website: str
    confidence: float


@dataclass
class BrandAnalysisResult:
    topics:      list[TopicResult]
    prompts:     list[PromptResult]
    competitors: list[CompetitorResult]


ANALYSIS_SYSTEM_PROMPT = """你是一名资深的品牌GEO（生成式引擎优化）分析师。
你的任务是基于品牌信息，生成用于检测该品牌在大语言模型中可见度的分析数据。
请严格按照JSON格式输出，不要添加任何解释文字。"""

ANALYSIS_USER_TEMPLATE = """
请基于以下品牌信息，生成用于GEO检测的完整分析数据：

品牌名称：{brand_name}
官方网站：{website}
行业：{industry}
品牌描述：{description}
目标市场：{target_market}

请输出以下JSON结构（注意：prompts中中英文各占一半）：

{{
  "topics": [
    {{
      "text": "话题描述（10字以内）",
      "category": "awareness|comparison|recommendation|problem_solving之一"
    }}
    // 共10个话题，覆盖品牌核心业务场景
  ],
  "prompts": [
    {{
      "topic_index": 0,
      "text": "用户在LLM中的真实提问（自然语言）",
      "intent": "awareness|comparison|recommendation|problem_solving之一",
      "language": "zh|en"
    }}
    // 每个话题生成3个prompts，共30个。中英文各15个
  ],
  "competitors": [
    {{
      "name": "竞品名称",
      "website": "官网域名",
      "confidence": 0.0到1.0的置信度
    }}
    // 8-12个直接竞品，按相关度排序
  ]
}}
"""


class BrandAnalyzer:
    def __init__(self):
        self.client = ZhipuAI(api_key=ZHIPU_API_KEY)

    async def analyze(
        self,
        brand_name: str,
        website: str,
        industry: str,
        description: str,
        target_market: str = "中国大陆",
    ) -> BrandAnalysisResult:

        user_msg = ANALYSIS_USER_TEMPLATE.format(
            brand_name=brand_name,
            website=website,
            industry=industry,
            description=description,
            target_market=target_market,
        )

        import time
        for attempt in range(5):
            try:
                response = self.client.chat.completions.create(
                    model=GLM_MODEL,
                    messages=[
                        {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                )
                break
            except Exception as e:
                if "429" in str(e) or "1302" in str(e):
                    wait = 60 * (attempt + 1)
                    logger.warning(f"GLM 429 rate limit, waiting {wait}s (attempt {attempt+1}/5)…")
                    time.sleep(wait)
                else:
                    raise

        raw = response.choices[0].message.content.strip()

        # 清理 markdown 代码块（如果有）
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        data = json.loads(raw)
        return self._parse(data)

    def _parse(self, data: dict) -> BrandAnalysisResult:
        topics = [
            TopicResult(text=t["text"], category=t["category"])
            for t in data.get("topics", [])
        ]
        prompts = [
            PromptResult(
                topic_index=p["topic_index"],
                text=p["text"],
                intent=p["intent"],
                language=p.get("language", "zh"),
            )
            for p in data.get("prompts", [])
        ]
        competitors = [
            CompetitorResult(
                name=c["name"],
                website=c["website"],
                confidence=float(c.get("confidence", 0.8)),
            )
            for c in data.get("competitors", [])
        ]
        return BrandAnalysisResult(topics=topics, prompts=prompts, competitors=competitors)
