"""Topic Plan helpers — pure-Python parsing / dedup / prompt-construction.

Mirrors the contracts of ``admin_console.topic_plan`` so the same shape of
LLM output, candidate dedup, and review-state transitions is enforced
here. The DoubaoTopicPlanClient (LLM call) lives in ``llm.py`` (async
httpx port); SQL helpers live in ``db.py`` (SQLAlchemy port). This module
intentionally has no DB or HTTP dependency so it can be unit-tested in
isolation.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

try:
    from json_repair import repair_json
except Exception:  # pragma: no cover - optional dependency
    repair_json = None

from app.admin.topic_plan.layer_classifier import (
    LAYER_BOUNDARY_PROMPT,
)
from app.admin.topic_plan.layer_classifier import (
    reject_reason as _layer_reject_reason,
)

ALLOWED_TOPIC_DIMENSIONS = {"brand", "product", "category", "scenario", "question"}
REVIEW_STATUSES = {"pending", "approved", "rejected"}

CONSUMER_ALIAS_OVERRIDES = {
    "lvmh": ["LV", "Dior", "迪奥", "Sephora", "丝芙兰", "大牌香水", "大牌包"],
    "moethennessylouisvuitton": [
        "LV",
        "Dior",
        "迪奥",
        "Sephora",
        "丝芙兰",
        "大牌香水",
        "大牌包",
    ],
    "路威酩轩": ["LV", "Dior", "迪奥", "Sephora", "丝芙兰", "大牌香水", "大牌包"],
}

STILTED_TOPIC_TERMS = (
    "LVMH",
    "路威酩轩",
    "Moet Hennessy",
    "旗下",
    "集团",
    "产品线",
    "品类线",
    "核心品类",
    "奢品品牌",
    "品牌档次",
    "档次是怎么划分",
    "高端收藏级",
    "爆款新款",
    "热门款",
    "知名品牌",
    "市场表现",
    "布局策略",
    "趋势分析",
    "用户画像",
    "转化路径",
    "私域",
    "CRM",
    "会员权益",
    "客流",
    "营销",
)

CONSUMER_TOPIC_SIGNALS = (
    "?",
    "？",
    "怎么",
    "哪",
    "什么",
    "好不好",
    "好吗",
    "值不值",
    "值得",
    "推荐",
    "适合",
    "区别",
    "会不会",
    "吗",
    "嘛",
    "要不要",
    "能不能",
    "怎么买",
    "不踩雷",
    "够用",
    "耐造",
)

CONSUMER_TOPIC_SUBJECT_SIGNALS = (
    "选购",
    "选择",
    "指南",
    "攻略",
    "技巧",
    "方法",
    "测评",
    "评测",
    "对比",
    "辨别",
    "真伪",
    "正品",
    "购买",
    "途径",
    "售后",
    "退换货",
    "政策",
    "整理",
    "清洗",
    "修复",
    "处理",
    "护理",
    "尺码",
    "穿搭",
    "性价比",
    "缓震",
    "抓地力",
    "支撑",
    "防水",
    "保暖",
    "透气",
    "适配性",
)


class TopicPlanLLMError(ValueError):
    """Controlled error returned to the API layer when LLM output is unusable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class DoubaoConfig:
    api_key: str
    base_url: str
    model: str


@dataclass(frozen=True)
class LLMTopic:
    title: str
    brand: str
    dimension: str
    reason: str
    confidence: float
    coverage_gap: str
    product_name: str | None = None

    def as_dict(self) -> dict[str, Any]:
        d = {
            "title": self.title,
            "brand": self.brand,
            "dimension": self.dimension,
            "reason": self.reason,
            "confidence": self.confidence,
            "coverage_gap": self.coverage_gap,
        }
        if self.product_name:
            d["product_name"] = self.product_name
        return d


def _parse_env_value(raw_value: str) -> str:
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def bounded_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    """Parse ``value`` to int, clamp to [min_value, max_value], default on failure."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(min_value, min(number, max_value))


def _read_dotenv_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists() or not path.is_file():
        return values
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            key = key.strip().lstrip("﻿")
            if key:
                values[key] = _parse_env_value(raw_value)
    except OSError:
        return values
    return values


def _topic_plan_env() -> dict[str, str]:
    module_dir = Path(__file__).resolve().parent
    candidates = [
        Path.cwd() / ".env",
        module_dir / ".env",
        module_dir.parent / ".env",
        module_dir.parent.parent / ".env",
    ]
    source: dict[str, str] = {}
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        source.update(_read_dotenv_file(resolved))
    source.update(os.environ)
    return source


def load_doubao_config(env: dict[str, str] | None = None) -> DoubaoConfig:
    """Load Volcengine Ark / Doubao 2 settings from environment variables."""
    source = env or _topic_plan_env()
    api_key = (
        source.get("ARK_API_KEY")
        or source.get("VOLCENGINE_ARK_API_KEY")
        or source.get("DOUBAO_API_KEY")
        or ""
    ).strip()
    base_url = (
        source.get("ARK_BASE_URL")
        or source.get("VOLCENGINE_ARK_BASE_URL")
        or source.get("DOUBAO_BASE_URL")
        or source.get("LLM_BASE_URL")
        or ""
    ).strip()
    model = (
        source.get("ARK_MODEL") or source.get("DOUBAO_MODEL") or source.get("LLM_MODEL") or ""
    ).strip()
    missing = []
    if not api_key:
        missing.append("ARK_API_KEY")
    if not base_url:
        missing.append("ARK_BASE_URL")
    if not model:
        missing.append("ARK_MODEL")
    if missing:
        raise TopicPlanLLMError(
            "llm_config_missing",
            "Doubao 2 configuration is missing: " + ", ".join(missing),
        )
    return DoubaoConfig(api_key=api_key, base_url=base_url, model=model)


def normalize_topic_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    return "".join(ch for ch in normalized if ch.isalnum())


def consumer_aliases_for_brand(brand: dict[str, Any]) -> list[str]:
    raw_terms = [brand.get("name"), brand.get("name_en"), brand.get("name_zh")]
    aliases = brand.get("aliases")
    if isinstance(aliases, str):
        try:
            aliases = json.loads(aliases)
        except Exception:
            aliases = [aliases]
    if isinstance(aliases, list | tuple):
        raw_terms.extend(aliases)

    result: list[str] = []
    for raw in raw_terms:
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        normalized = normalize_topic_title(text)
        used_override = False
        for key, values in CONSUMER_ALIAS_OVERRIDES.items():
            if key in normalized or normalized in key:
                used_override = True
                for value in values:
                    if value not in result:
                        result.append(value)
        if used_override:
            continue
        if text not in result and len(normalized) <= 12 and "company" not in text.casefold():
            result.append(text)
    return result[:10]


def brand_title_terms(brand: dict[str, Any]) -> list[str]:
    """Terms that count as the selected brand being visible in a title.

    This intentionally uses only the brand's own names and configured aliases.
    ``consumer_aliases_for_brand`` may include generic substitutes such as
    "大牌香水" for holding companies, and those should remain valid
    brand-neutral topic wording.
    """
    raw_terms = [brand.get("name"), brand.get("name_en"), brand.get("name_zh")]
    aliases = brand.get("aliases")
    if isinstance(aliases, str):
        try:
            aliases = json.loads(aliases)
        except Exception:
            aliases = [aliases]
    if isinstance(aliases, list | tuple):
        raw_terms.extend(aliases)

    terms: list[str] = []
    seen: set[str] = set()
    for raw in raw_terms:
        if raw is None:
            continue
        text = str(raw).strip()
        normalized = normalize_topic_title(text)
        if len(normalized) < 2 or normalized in seen:
            continue
        terms.append(text)
        seen.add(normalized)
    return terms


def is_title_brand_named(title: str, brand: dict[str, Any]) -> bool:
    """Return True when a topic title visibly contains the brand name/alias."""
    title_norm = normalize_topic_title(title)
    if not title_norm:
        return False
    return any(normalize_topic_title(term) in title_norm for term in brand_title_terms(brand))


def is_natural_consumer_topic(title: str) -> bool:
    raw = (title or "").strip()
    if len(raw) < 4 or len(raw) > 80:
        return False
    lowered = raw.casefold()
    if any(term.casefold() in lowered for term in STILTED_TOPIC_TERMS):
        return False
    if any(term.casefold() in lowered for term in ("operations", "strategy", "analysis", "crm")):
        return False
    if any(signal.casefold() in lowered for signal in CONSUMER_TOPIC_SIGNALS):
        return True
    return any(signal.casefold() in lowered for signal in CONSUMER_TOPIC_SUBJECT_SIGNALS)


def is_near_duplicate_title(title: str, existing_normalized: set[str]) -> bool:
    current = normalize_topic_title(title)
    if not current:
        return True
    if current in existing_normalized:
        return True
    for other in existing_normalized:
        if len(current) >= 5 and len(other) >= 5 and (current in other or other in current):
            return True
        if SequenceMatcher(None, current, other).ratio() >= 0.96:
            return True
    return False


def strip_markdown_fence(raw: str) -> str:
    text = (raw or "").strip()
    if not text.startswith("```"):
        return text
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _load_json_object(raw: str | dict[str, Any] | list[Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return {"topics": raw}
    cleaned = strip_markdown_fence(raw)
    if not cleaned.lstrip().startswith(("{", "[")):
        raise TopicPlanLLMError("llm_json_invalid", "LLM returned invalid JSON")
    try:
        parsed = json.loads(cleaned)
    except Exception as first_error:
        if repair_json is None:
            raise TopicPlanLLMError(
                "llm_json_invalid", "LLM returned invalid JSON"
            ) from first_error
        try:
            parsed = json.loads(repair_json(cleaned))
        except Exception as repair_error:
            raise TopicPlanLLMError(
                "llm_json_invalid", "LLM returned invalid JSON"
            ) from repair_error
    if isinstance(parsed, list):
        return {"topics": parsed}
    if not isinstance(parsed, dict):
        raise TopicPlanLLMError("llm_schema_invalid", "LLM JSON root must be an object")
    return parsed


def _extract_llm_items(data: dict[str, Any], root_key: str) -> list[Any]:
    items = data.get(root_key)
    if isinstance(items, list):
        return items
    singular_key = root_key[:-1] if root_key.endswith("s") else ""
    for key in (singular_key, "drafts", "candidates", "choices", "items", "results"):
        if not key:
            continue
        value = data.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [value]
    if data.get("title"):
        return [data]
    raise TopicPlanLLMError("llm_schema_invalid", f"LLM JSON must contain a {root_key} array")


def parse_llm_topics(raw: str | dict[str, Any] | list[Any]) -> list[LLMTopic]:
    data = _load_json_object(raw)
    topics = _extract_llm_items(data, "topics")

    parsed: list[LLMTopic] = []
    for index, item in enumerate(topics):
        if not isinstance(item, dict):
            raise TopicPlanLLMError(
                "llm_schema_invalid",
                f"Topic item #{index + 1} must be an object",
            )
        title = str(item.get("title") or "").strip()
        brand = str(item.get("brand") or "").strip()
        dimension = str(item.get("dimension") or "").strip().lower()
        reason = str(item.get("reason") or "").strip()
        coverage_gap = str(item.get("coverage_gap") or "").strip()
        try:
            confidence = float(item.get("confidence"))  # type: ignore[arg-type]
        except (TypeError, ValueError) as error:
            raise TopicPlanLLMError(
                "llm_schema_invalid",
                f"Topic item #{index + 1} confidence must be a number",
            ) from error

        if not title:
            raise TopicPlanLLMError(
                "llm_schema_invalid", f"Topic item #{index + 1} title is required"
            )
        if not brand:
            raise TopicPlanLLMError(
                "llm_schema_invalid", f"Topic item #{index + 1} brand is required"
            )
        if dimension not in ALLOWED_TOPIC_DIMENSIONS:
            raise TopicPlanLLMError(
                "llm_schema_invalid",
                f"Topic item #{index + 1} dimension must be one of "
                + ", ".join(sorted(ALLOWED_TOPIC_DIMENSIONS)),
            )
        if not reason:
            raise TopicPlanLLMError(
                "llm_schema_invalid", f"Topic item #{index + 1} reason is required"
            )
        if not coverage_gap:
            raise TopicPlanLLMError(
                "llm_schema_invalid", f"Topic item #{index + 1} coverage_gap is required"
            )
        if confidence < 0 or confidence > 1:
            raise TopicPlanLLMError(
                "llm_schema_invalid",
                f"Topic item #{index + 1} confidence must be between 0 and 1",
            )

        product_name = item.get("product_name")
        if isinstance(product_name, str):
            product_name = product_name.strip() or None
        else:
            product_name = None
        parsed.append(
            LLMTopic(
                title=title,
                brand=brand,
                dimension=dimension,
                reason=reason,
                confidence=confidence,
                coverage_gap=coverage_gap,
                product_name=product_name,
            )
        )
    return parsed


def dedupe_topic_candidates(
    candidates: list[LLMTopic],
    existing_titles: list[str],
    max_count: int | None = None,
    *,
    layer_check: bool = True,
) -> tuple[list[LLMTopic], list[dict[str, Any]]]:
    """Dedupe + (optionally) layer-boundary check.

    Skipped items carry structured ``reason`` codes:
      - ``duplicate_db``         existing title (or near-dup) in DB
      - ``duplicate_intra_batch`` LLM repeated itself in this batch
      - ``looks_like_prompt``    layer violation: a Prompt, not a Topic
      - ``looks_like_query``     layer violation: a Query
      - ``over_limit``           accepted enough already, this is the tail
    """
    db_normalized = {normalize_topic_title(title) for title in existing_titles if title}
    db_normalized.discard("")
    batch_normalized: set[str] = set()
    accepted: list[LLMTopic] = []
    skipped: list[dict[str, Any]] = []

    for item in candidates:
        if max_count is not None and len(accepted) >= max_count:
            skipped.append({"title": item.title, "reason": "over_limit"})
            continue
        if layer_check:
            layer_reason = _layer_reject_reason(item.title, "topic")
            if layer_reason is not None:
                skipped.append({"title": item.title, "reason": layer_reason})
                continue
        if is_near_duplicate_title(item.title, db_normalized):
            skipped.append({"title": item.title, "reason": "duplicate_db"})
            continue
        if is_near_duplicate_title(item.title, batch_normalized):
            skipped.append({"title": item.title, "reason": "duplicate_intra_batch"})
            continue
        accepted.append(item)
        batch_normalized.add(normalize_topic_title(item.title))
    return accepted, skipped


def sample_existing_for_context(items: list[str], total_quota: int = 400) -> list[str]:
    """Send the LLM a mix of recency + breadth so it sees the long tail of
    the topic library and stops re-generating it.
    """
    import random

    if not items:
        return []
    if len(items) <= total_quota:
        return list(items)
    recent_n = int(total_quota * 0.6)
    recent = items[-recent_n:]
    older = items[:-recent_n]
    sampled_old = random.sample(older, min(len(older), total_quota - len(recent)))
    return list(recent) + sampled_old


def over_request_count(target: int, *, multiplier: float = 1.4, min_buffer: int = 5) -> int:
    """Ask the LLM for ``ceil(target * multiplier)`` so dedup + layer-violation
    losses still leave us at ``target`` accepted.
    """
    import math

    return max(math.ceil(target * multiplier), target + min_buffer)


def repair_single_brand_placeholders(
    topics: list[LLMTopic], brands: list[dict[str, Any]]
) -> list[LLMTopic]:
    allowed_brand_names = [str(brand.get("name") or "").strip() for brand in brands]
    allowed_brand_names = [name for name in allowed_brand_names if name]
    if len(allowed_brand_names) != 1:
        return topics

    selected_brand = allowed_brand_names[0]
    repaired: list[LLMTopic] = []
    for topic in topics:
        if topic.brand == selected_brand:
            repaired.append(topic)
            continue
        brand_text = (topic.brand or "").strip()
        is_placeholder = bool(brand_text) and set(brand_text) <= {"?"}
        if not is_placeholder:
            repaired.append(topic)
            continue

        repaired.append(
            LLMTopic(
                title=topic.title.replace(brand_text, selected_brand),
                brand=selected_brand,
                dimension=topic.dimension,
                reason=topic.reason.replace(brand_text, selected_brand),
                confidence=topic.confidence,
                coverage_gap=topic.coverage_gap.replace(brand_text, selected_brand),
                product_name=topic.product_name,
            )
        )
    return repaired


def transition_candidate_status(current_status: str, requested_status: str) -> str:
    current = (current_status or "").strip().lower()
    requested = (requested_status or "").strip().lower()
    if requested not in {"approved", "rejected"}:
        raise TopicPlanLLMError(
            "invalid_review_status", "Review status must be approved or rejected"
        )
    if current not in REVIEW_STATUSES:
        raise TopicPlanLLMError("invalid_current_status", "Candidate has an invalid current status")
    if current != "pending":
        raise TopicPlanLLMError("candidate_already_reviewed", "Candidate has already been reviewed")
    return requested


def build_topic_plan_messages(
    *,
    industry: str,
    category: str,
    brands: list[dict[str, Any]],
    coverage_gaps: list[dict[str, Any]],
    max_topics: int,
    existing_topics: list[str],
    brand_research: list[dict[str, Any]] | None = None,
    brand_context_packs: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    allowed_brand_names = [str(brand.get("name") or "").strip() for brand in brands]
    allowed_brand_names = [name for name in allowed_brand_names if name]
    selected_brand_payload = []
    for brand in brands:
        name = str(brand.get("name") or "").strip()
        if not name:
            continue
        entry: dict[str, Any] = {
            "name": name,
            "industry": brand.get("industry") or brand.get("industry_name") or "",
            "topic_count": brand.get("topic_count", 0),
            "aliases": brand.get("aliases") or [],
            "consumer_aliases": consumer_aliases_for_brand(brand),
        }
        if brand.get("description"):
            entry["description"] = str(brand["description"])[:600]
        if brand.get("target_market"):
            entry["target_market"] = str(brand["target_market"])[:120]
        products = brand.get("products") or []
        if products:
            entry["products"] = [
                {
                    "name": str(p.get("name") or "").strip(),
                    "sku": str(p.get("sku") or "").strip() or None,
                    "category": str(p.get("category") or "").strip() or None,
                    "description": (str(p.get("description") or "")[:300]) or None,
                    "aliases": p.get("aliases") or [],
                }
                for p in products
                if str(p.get("name") or "").strip()
            ]
        selected_brand_payload.append(entry)
    schema = {
        "topics": [
            {
                "title": "...",
                "brand": "...",
                "dimension": "brand|product|category|scenario|question",
                "product_name": "...optional",
                "reason": "...",
                "confidence": 0.0,
                "coverage_gap": "...",
            }
        ]
    }
    banned_title_terms = [
        "会员",
        "私域",
        "复购",
        "渠道",
        "触达",
        "CRM",
        "数据运营",
        "转化",
        "门店运营",
        "客户分层",
        "生命周期",
        "动销",
        "LVMH",
        "路威酩轩",
        "旗下",
        "集团",
        "产品线",
        "品类线",
        "核心品类",
        "奢品品牌",
        "品牌档次",
        "高端收藏级",
        "爆款新款",
        "热门款",
        "知名品牌",
        "市场表现",
        "布局策略",
        "趋势分析",
    ]
    consumer_title_examples = [
        "口红热门色号挑选",
        "厚底慢跑鞋舒适度",
        "运动鞋真伪辨别",
        "篮球鞋抓地力测评",
        "儿童运动鞋尺码指南",
        "无糖可乐口感差异",
        "新能源车日常通勤体验",
        "送礼大牌包预算定位",
        "大牌香水送礼香调",
        "入门大牌包实用度",
    ]
    payload = {
        "industry": industry,
        "category": category,
        "selected_brands": selected_brand_payload,
        "allowed_brand_names": allowed_brand_names,
        "allowed_brand_names_text": ", ".join(allowed_brand_names),
        "coverage_gaps": coverage_gaps,
        "max_topics": max_topics,
        "existing_topics": existing_topics[:300],
        "generation_perspective": "consumer_search_and_shopping_intent",
        "banned_title_terms": banned_title_terms,
        "consumer_title_examples": consumer_title_examples,
        "brand_research": brand_research or [],
        "brand_context_packs": brand_context_packs or {},
        "output_schema": schema,
    }
    system = (
        LAYER_BOUNDARY_PROMPT.replace("{LAYER}", "topic")
        + "\n\n"
        + "You are the GENPANO Topic Plan generator for consumer-facing topics. "
        "Operators use the admin UI, but every topic title must represent real consumer demand. "
        "Return strict JSON only. No markdown. No explanations. "
        "Never introduce unselected brands, competitors, prompts, queries, table names, or engineering notes."
    )
    user = (
        "Generate consumer-facing Topic Plan candidates.\n"
        "Layer definitions:\n"
        "Topic layer = the high-level consumer demand subject. Topic titles must be brand-neutral: no selected brand names, aliases, competitor names, or legal holding-company names in topics[].title. The topics[].brand field is attribution only.\n"
        "Prompt layer = the natural user question generated later from a Topic. Prompt owns prompt_scope: non_branded, branded, competitor. Brand or competitor names may appear there only when the scope requires it.\n"
        "Query layer = a Prompt instantiated with one Segment/Profile. Query adds personal context and must preserve the Prompt scope instead of inventing new brands.\n\n"
        "Hard rules:\n"
        f"1. The only allowed brand values are: {payload['allowed_brand_names_text']}.\n"
        "2. topics[].brand must copy exactly one allowed brand value. Do not use brand id, numbers, aliases, or any other brand.\n"
        "3. topics[].title must be Chinese, sound like a real consumer search subject, and be brand-neutral. Title must be a noun phrase research subject (5-20 chars, like an article title); never a chat question, imperative, or AI-user dialogue. No question marks, no 怎么/如何/为什么/帮我/推荐 leading phrases, no first-person 我/我家/我们.\n"
        "4. Do not write topics for brand operators, CRM teams, retail teams, private-domain operations.\n"
        "5. Never include banned_title_terms, selected brand names, selected brand aliases, or competitors in topics[].title.\n"
        "6. topics[].reason must be Chinese for an admin reviewer; explain consumer intent and coverage gap.\n"
        "7. Each Topic must be useful for the selected brand, industry, category, and coverage_gaps, but the visible title should describe the reusable consumer need rather than naming the brand.\n"
        "8. If a selected brand is a holding company, do not force the legal/group name into the title.\n"
        "9. Never write phrases like 旗下, 集团, 产品线, 品类线, 品牌档次, 知名品牌, 爆款新款, 市场表现, 趋势分析, 用户画像, 转化路径.\n"
        "10. Avoid duplicates or near-duplicates with existing_topics.\n"
        "11. dimension must be one of brand, product, category, scenario, question.\n"
        "12. Return at most max_topics items and match output_schema exactly.\n"
        "13. If selected_brands[].products is non-empty, AT LEAST 60% of generated topics MUST be specifically about one of those products via topics[].product_name, while keeping topics[].title brand-neutral.\n"
        "14. When a topic is specifically about a product, set topics[].dimension='product' and topics[].product_name to the exact product name; if the product name contains the brand, do not copy that brand into topics[].title.\n"
        "15. Use brand_context_packs and brand_research to expand beyond the brand name: infer the real industry, category terms, product lines, signature features, target audiences, shopping scenarios, competitors, claims, and common consumer questions.\n"
        "16. All dimensions, including brand/product/category/scenario/question, must keep topics[].title brand-neutral and use consumer category, feature, scenario, or problem language instead.\n"
        "17. For category/scenario/question topics, prefer noun-phrase titles like 新手慢跑鞋膝盖友好选购 / 夏季通勤运动鞋透气挑选 / 送礼香水预算定位. Keep topics[].brand as the selected brand for attribution, but do not force that brand into the visible title. Do not phrase topics as questions or chat-style requests.\n"
        "18. Balance the batch: include reusable non-brand topics that downstream Prompt can later expand into non_branded, branded, and competitor prompts.\n"
        "19. Every topics[].title must use coherent, real-world terminology grounded in brand_context_packs, brand_research, or the selected brand's industry/products. Do not emit titles that combine unrelated category words, invented characters, or filler phrases (e.g., generic 选购指南/采购参考 suffixes appended to nonsense roots). If you cannot ground a topic in the provided context, omit it rather than hallucinating.\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
