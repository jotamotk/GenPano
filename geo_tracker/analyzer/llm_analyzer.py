"""
Stage 3: 豆包大模型分析

通过火山引擎 Ark API（OpenAI 兼容）调用豆包大模型，完成：
- 品牌检测验证 + 补全
- 位置/详细度分析
- 情感驱动因子提取
- 产品特性/场景/价格定位提取
- 三维度归类
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

from openai import AsyncOpenAI

from geo_tracker.analyzer.brand_detector import DetectedBrand
from geo_tracker.analyzer.prompts import ANALYSIS_SYSTEM, ANALYSIS_USER

logger = logging.getLogger(__name__)


@dataclass
class DriverResult:
    driver_text: str
    polarity: str
    category: str
    strength: float = 0.5
    source_quote: str = ""


@dataclass
class ProductFeatureResult:
    feature_name: str
    feature_sentiment: str = "neutral"
    scenario: str | None = None
    price_positioning: str | None = None
    context_snippet: str = ""


@dataclass
class BrandAnalysis:
    brand_name: str
    product_name: str | None = None
    position_type: str = "mentioned_only"
    position_rank: int | None = None
    detail_level: str = "passing"
    sentiment: str = "neutral"           # positive | neutral | negative
    sentiment_score: float = 0.0         # -1.0 ~ 1.0
    sentiment_drivers: list[DriverResult] = field(default_factory=list)
    product_features: list[ProductFeatureResult] = field(default_factory=list)


@dataclass
class DimensionResult:
    industry: str = ""
    company: str = ""
    product: str = ""
    category: str = ""


@dataclass
class LLMAnalysisResult:
    brands: list[BrandAnalysis] = field(default_factory=list)
    dimension: DimensionResult = field(default_factory=DimensionResult)
    raw_json: dict | None = None


class LLMAnalyzer:
    """豆包大模型做结构化分析"""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=os.getenv("ARK_API_KEY", ""),
            base_url=os.getenv(
                "ARK_BASE_URL",
                "https://ark.cn-beijing.volces.com/api/v3",
            ),
        )
        self.model = os.getenv("ARK_MODEL", "doubao-pro-32k")

    async def analyze(
        self,
        response_text: str,
        detected_brands: list[DetectedBrand],
        intent: str,
        target_brand: str,
        target_aliases: list[str] | None = None,
        competitors: list[str] | None = None,
    ) -> LLMAnalysisResult:
        """
        调用豆包大模型分析 AI 回答。

        Args:
            response_text: AI 原始回答文本
            detected_brands: Stage 1 预检测到的品牌列表
            intent: prompt 意图 (brand/non_brand/comparison)
            target_brand: 目标品牌名
            target_aliases: 目标品牌别名列表
            competitors: 竞品名称列表
        """
        if not self.client.api_key:
            logger.warning("ARK_API_KEY not set, returning empty analysis")
            return LLMAnalysisResult()

        pre_detected = ", ".join(
            f"{d.brand_name}({d.mention_count}次)"
            for d in detected_brands
        ) or "无"

        prompt = ANALYSIS_USER.format(
            target_brand=target_brand,
            target_aliases=", ".join(target_aliases or []),
            competitors=", ".join(competitors or []),
            pre_detected_brands=pre_detected,
            intent=intent,
            response_text=response_text[:4000],  # Truncate to avoid token overflow
        )

        try:
            completion = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": ANALYSIS_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )

            raw_text = completion.choices[0].message.content or ""
            # Strip markdown code fences if present (```json ... ```)
            stripped = raw_text.strip()
            if stripped.startswith("```"):
                # Remove opening fence (```json or ```)
                first_newline = stripped.index("\n")
                stripped = stripped[first_newline + 1:]
                # Remove closing fence
                if stripped.endswith("```"):
                    stripped = stripped[:-3].strip()
            raw_json = json.loads(stripped)
            return self._parse_result(raw_json)

        except json.JSONDecodeError as e:
            logger.warning(f"LLM returned invalid JSON: {e}\nRaw: {raw_text[:500]}")
            return LLMAnalysisResult()
        except Exception as e:
            logger.exception(f"LLM analysis failed: {e}")
            return LLMAnalysisResult()

    def _parse_result(self, data: dict) -> LLMAnalysisResult:
        """Parse LLM JSON output into structured result."""
        result = LLMAnalysisResult(raw_json=data)

        # Parse brands
        for b in data.get("brands", []):
            drivers = [
                DriverResult(
                    driver_text=d.get("driver_text", ""),
                    polarity=d.get("polarity", "positive"),
                    category=d.get("category", "other"),
                    strength=float(d.get("strength", 0.5)),
                    source_quote=d.get("source_quote", ""),
                )
                for d in b.get("sentiment_drivers", [])
            ]
            features = [
                ProductFeatureResult(
                    feature_name=f.get("feature_name", ""),
                    feature_sentiment=f.get("feature_sentiment", "neutral"),
                    scenario=f.get("scenario"),
                    price_positioning=f.get("price_positioning"),
                    context_snippet=f.get("context_snippet", ""),
                )
                for f in b.get("product_features", [])
            ]
            result.brands.append(BrandAnalysis(
                brand_name=b.get("brand_name", ""),
                product_name=b.get("product_name"),
                position_type=b.get("position_type", "mentioned_only"),
                position_rank=b.get("position_rank"),
                detail_level=b.get("detail_level", "passing"),
                sentiment=b.get("sentiment", "neutral"),
                sentiment_score=float(b.get("sentiment_score", 0.0)),
                sentiment_drivers=drivers,
                product_features=features,
            ))

        # Parse dimension
        dim = data.get("dimension", {})
        result.dimension = DimensionResult(
            industry=dim.get("industry", ""),
            company=dim.get("company", ""),
            product=dim.get("product", ""),
            category=dim.get("category", ""),
        )

        return result
