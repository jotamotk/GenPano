"""Topic Plan helpers for the Admin console.

This module intentionally has no Flask or database dependency so the risky
parts of Topic Plan (LLM parsing, schema validation, de-dupe, review state)
can be tested without secrets or a live database.
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


ALLOWED_TOPIC_DIMENSIONS = {"brand", "product", "category", "scenario", "question"}
REVIEW_STATUSES = {"pending", "approved", "rejected"}

CONSUMER_ALIAS_OVERRIDES = {
    "lvmh": ["LV", "Dior", "迪奥", "Sephora", "丝芙兰", "大牌香水", "大牌包"],
    "moethennessylouisvuitton": ["LV", "Dior", "迪奥", "Sephora", "丝芙兰", "大牌香水", "大牌包"],
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


def _bounded_int(value: Any, default: int, min_value: int, max_value: int) -> int:
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
            key = key.strip().lstrip("\ufeff")
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
        source.get("ARK_MODEL")
        or source.get("DOUBAO_MODEL")
        or source.get("LLM_MODEL")
        or ""
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
    if isinstance(aliases, (list, tuple)):
        raw_terms.extend(aliases)

    result: list[str] = []
    normalized_terms = []
    for raw in raw_terms:
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        normalized = normalize_topic_title(text)
        normalized_terms.append(normalized)
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


def is_natural_consumer_topic(title: str) -> bool:
    raw = (title or "").strip()
    if len(raw) < 4 or len(raw) > 80:
        return False
    lowered = raw.casefold()
    if any(term.casefold() in lowered for term in STILTED_TOPIC_TERMS):
        return False
    if any(term.casefold() in lowered for term in ("operations", "strategy", "analysis", "crm")):
        return False
    return any(signal.casefold() in lowered for signal in CONSUMER_TOPIC_SIGNALS)


def is_near_duplicate_title(title: str, existing_normalized: set[str]) -> bool:
    current = normalize_topic_title(title)
    if not current:
        return True
    if current in existing_normalized:
        return True
    for other in existing_normalized:
        if len(current) >= 5 and len(other) >= 5 and (current in other or other in current):
            return True
        # Module B-4: loosen 0.92 → 0.96 — close-but-not-identical phrasings of
        # the same idea now slip through as separate topics. Strict 0.92 was
        # eating ~30% of generated batches.
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


def _load_json_object(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    cleaned = strip_markdown_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except Exception as first_error:
        if repair_json is None:
            raise TopicPlanLLMError("llm_json_invalid", "LLM returned invalid JSON") from first_error
        try:
            parsed = json.loads(repair_json(cleaned))
        except Exception as repair_error:
            raise TopicPlanLLMError("llm_json_invalid", "LLM returned invalid JSON") from repair_error
    if not isinstance(parsed, dict):
        raise TopicPlanLLMError("llm_schema_invalid", "LLM JSON root must be an object")
    return parsed


def parse_llm_topics(raw: str | dict[str, Any]) -> list[LLMTopic]:
    data = _load_json_object(raw)
    topics = data.get("topics")
    if not isinstance(topics, list):
        raise TopicPlanLLMError("llm_schema_invalid", "LLM JSON must contain a topics array")

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
            confidence = float(item.get("confidence"))
        except (TypeError, ValueError) as error:
            raise TopicPlanLLMError(
                "llm_schema_invalid",
                f"Topic item #{index + 1} confidence must be a number",
            ) from error

        if not title:
            raise TopicPlanLLMError("llm_schema_invalid", f"Topic item #{index + 1} title is required")
        if not brand:
            raise TopicPlanLLMError("llm_schema_invalid", f"Topic item #{index + 1} brand is required")
        if dimension not in ALLOWED_TOPIC_DIMENSIONS:
            raise TopicPlanLLMError(
                "llm_schema_invalid",
                f"Topic item #{index + 1} dimension must be one of "
                + ", ".join(sorted(ALLOWED_TOPIC_DIMENSIONS)),
            )
        if not reason:
            raise TopicPlanLLMError("llm_schema_invalid", f"Topic item #{index + 1} reason is required")
        if not coverage_gap:
            raise TopicPlanLLMError(
                "llm_schema_invalid",
                f"Topic item #{index + 1} coverage_gap is required",
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

    Skipped items now carry structured ``reason`` codes so the API can
    surface a per-reason breakdown to the UI:

      - ``duplicate_db``         existing title (or near-duplicate) in DB
      - ``duplicate_intra_batch`` LLM repeated itself in this batch
      - ``looks_like_prompt``    layer violation: this is a Prompt, not a Topic
      - ``looks_like_query``     layer violation: this is a Query
      - ``over_limit``           accepted enough already, this is the tail
    """
    from ._layer_classifier import reject_reason as _reject_reason

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
            layer_reason = _reject_reason(item.title, "topic")
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
    """Module B-2: send the LLM a mix of recency + breadth instead of the
    naive ``items[:300]`` slice, so the LLM "knows" what the long tail of
    the topic library already covers and stops re-generating it.
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
    """Module B-1: ask the LLM for ``ceil(target * multiplier)`` so dedup +
    layer-violation losses still leave us at ``target`` accepted.
    """
    import math

    return max(int(math.ceil(target * multiplier)), target + min_buffer)


def repair_single_brand_placeholders(topics: list[LLMTopic], brands: list[dict[str, Any]]) -> list[LLMTopic]:
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
        raise TopicPlanLLMError("invalid_review_status", "Review status must be approved or rejected")
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
        # Module C-5: include brand description + target_market when present.
        # These are already on the brands table but were not previously surfaced
        # to the LLM, so generated topics stayed at "brand-level platitudes"
        # rather than reflecting the brand's actual positioning / market.
        if brand.get("description"):
            entry["description"] = str(brand["description"])[:600]
        if brand.get("target_market"):
            entry["target_market"] = str(brand["target_market"])[:120]
        # Module C-4: products are SKU-level focus subjects. When admin selects
        # specific product ids in the generate request, those products are
        # passed here so the LLM can produce topics that mention concrete SKUs.
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
                "product_name": "...optional, copy from selected_brands[].products[].name when title focuses on a specific product",
                "reason": "...",
                "confidence": 0.0,
                "coverage_gap": "...",
            }
        ]
    }
    banned_title_terms = [
        "\u4f1a\u5458",
        "\u79c1\u57df",
        "\u590d\u8d2d",
        "\u6e20\u9053",
        "\u89e6\u8fbe",
        "CRM",
        "\u6570\u636e\u8fd0\u8425",
        "\u8f6c\u5316",
        "\u95e8\u5e97\u8fd0\u8425",
        "\u5ba2\u6237\u5206\u5c42",
        "\u751f\u547d\u5468\u671f",
        "\u52a8\u9500",
        "LVMH",
        "\u8def\u5a01\u9149\u8f69",
        "\u65d7\u4e0b",
        "\u96c6\u56e2",
        "\u4ea7\u54c1\u7ebf",
        "\u54c1\u7c7b\u7ebf",
        "\u6838\u5fc3\u54c1\u7c7b",
        "\u5962\u54c1\u54c1\u724c",
        "\u54c1\u724c\u6863\u6b21",
        "\u9ad8\u7aef\u6536\u85cf\u7ea7",
        "\u7206\u6b3e\u65b0\u6b3e",
        "\u70ed\u95e8\u6b3e",
        "\u77e5\u540d\u54c1\u724c",
        "\u5e02\u573a\u8868\u73b0",
        "\u5e03\u5c40\u7b56\u7565",
        "\u8d8b\u52bf\u5206\u6790",
    ]
    consumer_title_examples = [
        "\u9999\u5948\u513f\u53e3\u7ea2\u70ed\u95e8\u8272\u53f7\u600e\u4e48\u9009",
        "NIKE\u8dd1\u978b\u9002\u5408\u65b0\u624b\u6162\u8dd1\u5417",
        "\u53ef\u53e3\u53ef\u4e50\u65e0\u7cd6\u548c\u666e\u901a\u7248\u53e3\u611f\u533a\u522b",
        "\u5b9d\u9a6c\u65b0\u80fd\u6e90\u8f66\u65e5\u5e38\u901a\u52e4\u4f53\u9a8c\u600e\u4e48\u6837",
        "\u9884\u7b97\u4e00\u4e07\u5de6\u53f3\u9001\u5973\u751f\u5927\u724c\u5305\u600e\u4e48\u9009",
        "\u60f3\u4e70\u5927\u724c\u9999\u6c34\u9001\u4eba\u54ea\u79cd\u5473\u9053\u4e0d\u5bb9\u6613\u8e29\u96f7",
        "LV\u5165\u95e8\u6b3e\u5305\u5305\u4e70\u54ea\u53ea\u66f4\u5b9e\u7528",
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
        "output_schema": schema,
    }
    # Module 0.5: prepend the layer-boundary header so the LLM knows it must
    # produce *Topics* (noun-phrase research areas), not Prompts or Queries.
    from ._layer_classifier import LAYER_BOUNDARY_PROMPT
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
        "Hard rules:\n"
        f"1. The only allowed brand values are: {payload['allowed_brand_names_text']}.\n"
        "2. topics[].brand must copy exactly one allowed brand value. Do not use brand id, numbers, aliases, or any other brand.\n"
        "3. topics[].title must be Chinese and sound like a real consumer search, shopping, comparison, review, usage, gifting, or troubleshooting question.\n"
        "4. Do not write topics for brand operators, CRM teams, retail teams, private-domain operations, member operations, or channel operations.\n"
        "5. Never include banned_title_terms in topics[].title. Especially avoid member, private-domain, repurchase, channel, CRM, conversion, data-operations, and lifecycle wording.\n"
        "6. topics[].reason must be Chinese for an admin reviewer, but it should explain consumer intent and coverage gap, not an internal operations plan.\n"
        "7. Each title must be about the selected brand, industry, category, and coverage_gaps, but must not expose internal coverage mechanics.\n"
        "8. If a selected brand is a holding company or corporate group, do not force the legal/group name into the title. Use selected_brands[].consumer_aliases when they sound like consumer words, or ask the category/scenario directly without naming the group.\n"
        "9. Never write phrases like 旗下, 集团, 产品线, 品类线, 品牌档次, 知名品牌, 爆款新款, 市场表现, 趋势分析, 用户画像, 转化路径.\n"
        "10. Good group-brand style: 预算一万左右送女生大牌包怎么选 / 想买大牌香水送人哪种味道不容易踩雷 / LV入门款包包买哪只更实用.\n"
        "11. Bad group-brand style: LVMH旗下的香水线哪些性价比更高 / LVMH集团旗下的奢品品牌档次是怎么划分的.\n"
        "12. Avoid duplicates or near-duplicates with existing_topics.\n"
        "13. dimension must be one of brand, product, category, scenario, question.\n"
        "14. If allowed brand values are masked as question marks by the model, use the same placeholder consistently in title, brand, and coverage_gap.\n"
        "15. If allowed_brand_names and coverage_gaps are non-empty, return at least 1 candidate.\n"
        "16. Return at most max_topics items and match output_schema exactly.\n"
        "17. If selected_brands[].products is non-empty, AT LEAST 60% of generated topics MUST mention or specifically be about one of those product names (or its aliases). Spread coverage across products — do not put every topic on the same SKU.\n"
        "18. When a topic is specifically about a product, set topics[].dimension='product' and topics[].product_name to the exact product name from selected_brands[].products[].name. Otherwise omit product_name.\n"
        "19. When selected_brands[].description or target_market is provided, let those flavor the topic angles (e.g. premium positioning → gifting / collection topics; mass-market → price / availability / value topics). Do NOT quote those fields verbatim into titles.\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


class DoubaoTopicPlanClient:
    """Small OpenAI-compatible client for Volcengine Ark / Doubao 2."""

    def __init__(self, config: DoubaoConfig | None = None):
        self.config = config or load_doubao_config()

    def generate_topics(
        self,
        *,
        industry: str,
        category: str,
        brands: list[dict[str, Any]],
        coverage_gaps: list[dict[str, Any]],
        max_topics: int,
        existing_topics: list[str],
    ) -> tuple[list[LLMTopic], dict[str, Any]]:
        try:
            from openai import OpenAI
        except Exception as error:  # pragma: no cover - environment dependent
            raise TopicPlanLLMError("llm_client_unavailable", "OpenAI-compatible client is unavailable") from error

        messages = build_topic_plan_messages(
            industry=industry,
            category=category,
            brands=brands,
            coverage_gaps=coverage_gaps,
            max_topics=max_topics,
            existing_topics=existing_topics,
        )
        timeout_seconds = _bounded_int(os.getenv("TOPIC_PLAN_LLM_TIMEOUT_SECONDS") or 90, 90, 30, 240)
        client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=timeout_seconds,
        )
        try:
            response = client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=0.1,
                timeout=timeout_seconds,
            )
        except Exception as error:
            raise TopicPlanLLMError("llm_call_failed", "Doubao 2 topic generation failed") from error

        content = response.choices[0].message.content or "{}"
        topics = repair_single_brand_placeholders(parse_llm_topics(content), brands)
        usage_obj = getattr(response, "usage", None)
        usage = {}
        if usage_obj is not None:
            if hasattr(usage_obj, "model_dump"):
                usage = usage_obj.model_dump()
            elif isinstance(usage_obj, dict):
                usage = dict(usage_obj)
            else:
                usage = {
                    key: getattr(usage_obj, key)
                    for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                    if hasattr(usage_obj, key)
                }
        return topics, {"model": self.config.model, "usage": usage}
