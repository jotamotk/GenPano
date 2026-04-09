"""
Stage 2: 情感分析 — 火山引擎 NLP API

按 context_snippet 粒度分析情感极性和分数。
火山 NLP 比大模型便宜 10x+，延迟低（~50ms），适合批量处理。
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class SentimentResult:
    sentiment: str       # positive | neutral | negative
    score: float         # -1.0 ~ 1.0


class SentimentAnalyzer:
    """火山引擎 NLP 情感分析"""

    API_URL = "https://open.volcengineapi.com/api/v1/nlp/sentiment"
    MAX_BATCH = 8  # 单次请求最多分析条数

    def __init__(self):
        self.api_key = os.getenv("VOLC_NLP_API_KEY", "")
        self.api_url = os.getenv("VOLC_NLP_API_URL", self.API_URL)

    async def analyze(self, text: str) -> SentimentResult:
        """分析单条文本的情感"""
        results = await self.analyze_batch([text])
        return results[0]

    async def analyze_batch(self, snippets: list[str]) -> list[SentimentResult]:
        """
        批量分析 context_snippet 的情感。

        如果 API 不可用（无 key 或调用失败），回退到基于关键词的简单规则。
        """
        if not self.api_key:
            logger.warning("VOLC_NLP_API_KEY not set, using keyword fallback")
            return [self._keyword_fallback(s) for s in snippets]

        results: list[SentimentResult] = []

        # Process in batches
        for i in range(0, len(snippets), self.MAX_BATCH):
            batch = snippets[i:i + self.MAX_BATCH]
            batch_results = await self._call_api(batch)
            results.extend(batch_results)

        return results

    async def _call_api(self, texts: list[str]) -> list[SentimentResult]:
        """调用火山引擎 NLP 情感分析 API"""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    self.api_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"texts": texts},
                )
                resp.raise_for_status()
                data = resp.json()

            results = []
            for item in data.get("results", []):
                label = item.get("label", "neutral")
                score = item.get("score", 0.0)
                # Normalize label
                if label in ("positive", "pos"):
                    sentiment = "positive"
                elif label in ("negative", "neg"):
                    sentiment = "negative"
                else:
                    sentiment = "neutral"
                results.append(SentimentResult(sentiment=sentiment, score=score))

            # Pad with neutral if API returned fewer results
            while len(results) < len(texts):
                results.append(SentimentResult(sentiment="neutral", score=0.0))

            return results

        except Exception as e:
            logger.warning(f"Volcano NLP API call failed: {e}, using fallback")
            return [self._keyword_fallback(t) for t in texts]

    @staticmethod
    def _keyword_fallback(text: str) -> SentimentResult:
        """简单关键词规则兜底（API 不可用时使用）"""
        pos_keywords = [
            "推荐", "优秀", "出色", "领先", "首选", "最佳", "好评",
            "值得", "recommend", "excellent", "best", "great", "top",
            "优势", "强大", "创新", "高品质", "性价比",
        ]
        neg_keywords = [
            "不推荐", "缺点", "不足", "劣势", "差", "贵", "问题",
            "poor", "worst", "avoid", "drawback", "expensive",
            "投诉", "差评", "落后", "不如",
        ]

        text_lower = text.lower()
        pos_count = sum(1 for kw in pos_keywords if kw in text_lower)
        neg_count = sum(1 for kw in neg_keywords if kw in text_lower)

        if pos_count > neg_count:
            score = min(0.3 + pos_count * 0.15, 1.0)
            return SentimentResult(sentiment="positive", score=score)
        elif neg_count > pos_count:
            score = max(-0.3 - neg_count * 0.15, -1.0)
            return SentimentResult(sentiment="negative", score=score)
        else:
            return SentimentResult(sentiment="neutral", score=0.0)
