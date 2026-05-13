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

import httpx
from openai import AsyncOpenAI

try:
    from json_repair import repair_json
    HAS_JSON_REPAIR = True
except ImportError:
    HAS_JSON_REPAIR = False

from geo_tracker.analyzer.brand_detector import DetectedBrand
from geo_tracker.analyzer.position_type import normalize_position_type
from geo_tracker.analyzer.prompts import ANALYSIS_SYSTEM, ANALYSIS_USER
from geo_tracker.analyzer.v4_contract import (
    CATEGORY_PRODUCT_FEATURE_TYPES,
    DRIVER_TYPES,
    SENTIMENT_LABELS,
)

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
    parse_status: str = "ok"
    parse_error: str | None = None
    raw_output: str | None = None
    json_repaired: bool = False


def _is_numeric(value: object) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


class LLMAnalyzer:
    """豆包大模型做结构化分析"""

    def __init__(self):
        # trust_env=False ensures httpx ignores HTTP_PROXY/HTTPS_PROXY env vars,
        # preventing domestic ARK API calls from being routed through the overseas
        # proxy used for LLM scraping (Clash/V-Ninja).
        self.client = AsyncOpenAI(
            api_key=os.getenv("ARK_API_KEY", ""),
            base_url=os.getenv(
                "ARK_BASE_URL",
                "https://ark.cn-beijing.volces.com/api/v3",
            ),
            timeout=600.0,
            max_retries=1,
            http_client=httpx.AsyncClient(trust_env=False),
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
            return LLMAnalysisResult(
                parse_status="failed",
                parse_error="ARK_API_KEY not set",
            )

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
            logger.info(
                f"Calling ARK API: model={self.model}, "
                f"response_len={len(response_text)}, prompt_len={len(prompt)}"
            )
            completion = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": ANALYSIS_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )
            logger.info(f"ARK API returned in time, tokens={completion.usage}")

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

            try:
                raw_json = json.loads(stripped)
                json_repaired = False
            except json.JSONDecodeError as e:
                # Fall back to json_repair for malformed LLM output
                # (unescaped quotes, trailing commas, truncated JSON, etc.)
                if HAS_JSON_REPAIR:
                    logger.warning(
                        f"Strict JSON parse failed ({e}), attempting json_repair..."
                    )
                    repaired = repair_json(stripped)
                    raw_json = json.loads(repaired)
                    json_repaired = True
                    logger.info("json_repair recovered the JSON successfully")
                else:
                    raise
            return self._parse_result(
                raw_json,
                parse_status="json_repaired" if json_repaired else "ok",
                raw_output=raw_text,
                json_repaired=json_repaired,
            )

        except json.JSONDecodeError as e:
            logger.warning(f"LLM returned invalid JSON: {e}\nRaw: {raw_text[:500]}")
            return LLMAnalysisResult(
                parse_status="invalid_json",
                parse_error=str(e),
                raw_output=raw_text,
            )
        except Exception as e:
            logger.exception(f"LLM analysis failed: {e}")
            return LLMAnalysisResult(parse_status="failed", parse_error=str(e))

    def _parse_result(
        self,
        data: dict,
        *,
        parse_status: str = "ok",
        raw_output: str | None = None,
        json_repaired: bool = False,
    ) -> LLMAnalysisResult:
        """Parse LLM JSON output into structured result."""
        result = LLMAnalysisResult(
            raw_json=data,
            parse_status=parse_status,
            raw_output=raw_output,
            json_repaired=json_repaired,
        )

        if "analysis_meta" in data and "mentions" in data:
            self._parse_v4_projection(data, result)
            return result

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
                position_type=normalize_position_type(b.get("position_type")),
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

    def _parse_v4_projection(self, data: dict, result: LLMAnalysisResult) -> None:
        """Project analyzer_v4 packages back into legacy pipeline structs."""
        entities = {
            str(entity.get("entity_key")): entity
            for entity in data.get("entities", [])
            if isinstance(entity, dict) and entity.get("entity_key")
        }
        product_brand_entities: dict[str, dict] = {}

        def brand_display_name(entity: dict | None) -> str:
            return str(
                (entity or {}).get("canonical_name")
                or (entity or {}).get("raw_name")
                or ""
            ).strip()

        def link_product_brand(product_key: object, brand_key: object) -> None:
            product_entity = entities.get(str(product_key or ""))
            brand_entity = entities.get(str(brand_key or ""))
            if (
                not product_entity
                or not brand_entity
                or product_entity.get("entity_type") != "product"
                or brand_entity.get("entity_type") != "brand"
            ):
                return
            product_brand_entities[str(product_key)] = brand_entity

        for entity_key, entity in entities.items():
            if entity.get("entity_type") == "product":
                link_product_brand(entity_key, entity.get("brand_entity_key"))

        for feature in data.get("product_features", []):
            if isinstance(feature, dict):
                link_product_brand(
                    feature.get("product_entity_key"),
                    feature.get("brand_entity_key"),
                )

        for relation in data.get("relations", []):
            if (
                not isinstance(relation, dict)
                or relation.get("relation_type") != "belongs_to_brand"
            ):
                continue
            subject_key = str(relation.get("subject_entity_key") or "")
            object_key = str(relation.get("object_entity_key") or "")
            subject_entity = entities.get(subject_key)
            object_entity = entities.get(object_key)
            if (
                subject_entity
                and object_entity
                and subject_entity.get("entity_type") == "product"
                and object_entity.get("entity_type") == "brand"
            ):
                link_product_brand(subject_key, object_key)
            elif (
                subject_entity
                and object_entity
                and subject_entity.get("entity_type") == "brand"
                and object_entity.get("entity_type") == "product"
            ):
                link_product_brand(object_key, subject_key)

        def append_projection_flag(code: str, message: str, target_key: str) -> None:
            flags = data.setdefault("quality_flags", [])
            if not isinstance(flags, list):
                flags = []
                data["quality_flags"] = flags
            target = str(target_key or "")
            for flag in flags:
                if (
                    isinstance(flag, dict)
                    and flag.get("code") == code
                    and str(flag.get("target_key") or "") == target
                ):
                    return
            flags.append(
                {
                    "flag_key": f"flag_{code}_product_{target}",
                    "severity": "warning",
                    "code": code,
                    "message": message,
                    "target_type": "product",
                    "target_key": target,
                    "blocks_metric_readiness": True,
                }
            )

        def append_entity_quality_code(entity: dict, code: str) -> None:
            flags = entity.setdefault("quality_flags", [])
            if isinstance(flags, list) and code not in {
                str(flag.get("code") or flag) if isinstance(flag, dict) else str(flag)
                for flag in flags
            }:
                flags.append(code)

        drivers_by_mention: dict[str, list[dict]] = {}
        for driver in data.get("sentiment_drivers", []):
            if (
                isinstance(driver, dict)
                and driver.get("sentiment_label") in SENTIMENT_LABELS
                and driver.get("driver_type") in DRIVER_TYPES
                and _is_numeric(driver.get("confidence"))
            ):
                drivers_by_mention.setdefault(str(driver.get("mention_key")), []).append(driver)
        features_by_product: dict[str, list[dict]] = {}
        for feature in data.get("product_features", []):
            if (
                isinstance(feature, dict)
                and feature.get("feature_type") not in CATEGORY_PRODUCT_FEATURE_TYPES
                and _is_numeric(feature.get("confidence"))
            ):
                features_by_product.setdefault(str(feature.get("product_entity_key")), []).append(feature)

        for mention in data.get("mentions", []):
            if not isinstance(mention, dict):
                continue
            entity_key = str(mention.get("entity_key"))
            entity = entities.get(entity_key, {})
            entity_type = str(entity.get("entity_type") or mention.get("mention_type") or "brand")
            if entity_type not in {"brand", "product"}:
                continue
            raw_name = str(entity.get("raw_name") or mention.get("raw_text") or "")
            brand_name = raw_name
            product_name = None
            if entity_type == "product":
                product_name = raw_name
                brand_entity = None
                mention_brand_key = mention.get("brand_entity_key")
                if mention_brand_key:
                    candidate = entities.get(str(mention_brand_key))
                    if candidate and candidate.get("entity_type") == "brand":
                        brand_entity = candidate
                brand_entity = brand_entity or product_brand_entities.get(entity_key)
                brand_name = brand_display_name(brand_entity)
                if not brand_name:
                    append_entity_quality_code(entity, "brand_unresolved")
                    append_projection_flag(
                        "brand_unresolved",
                        "Product mention has no explicit resolved brand link.",
                        entity_key,
                    )
                    continue
            drivers = [
                DriverResult(
                    driver_text=str(driver.get("driver_summary") or ""),
                    polarity=str(driver.get("sentiment_label") or "unknown"),
                    category=str(driver.get("driver_type") or "other"),
                    strength=float(driver.get("confidence") or 0.5),
                    source_quote=str(driver.get("evidence_quote") or ""),
                )
                for driver in drivers_by_mention.get(str(mention.get("mention_key")), [])
            ]
            features = [
                ProductFeatureResult(
                    feature_name=str(feature.get("feature_name") or ""),
                    feature_sentiment="neutral",
                    scenario=str(feature.get("feature_type") or "") or None,
                    price_positioning=None,
                    context_snippet=str(feature.get("evidence_quote") or ""),
                )
                for feature in features_by_product.get(entity_key, [])
            ]
            result.brands.append(
                BrandAnalysis(
                    brand_name=brand_name,
                    product_name=product_name,
                    position_type=normalize_position_type(mention.get("position")),
                    position_rank=None,
                    detail_level="brief",
                    sentiment=str(mention.get("sentiment_label") or "unknown"),
                    sentiment_score=float(mention.get("sentiment_score") or 0.0),
                    sentiment_drivers=drivers,
                    product_features=features,
                )
            )
