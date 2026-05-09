"""Prompt Matrix helpers — pure-Python parsing / dedup / prompt-construction.

Vendored from ``admin_console/prompt_matrix.py``. Contracts unchanged so
admin_console + this module produce identical wire output during the
phased migration. ``PromptMatrixClient`` (sync OpenAI) is replaced by an
async httpx port in ``llm.py``; SQL helpers live in ``db.py``.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

try:
    from json_repair import repair_json
except Exception:  # pragma: no cover - optional dependency
    repair_json = None

# Reuse the topic_plan TopicPlanLLMError + load_doubao_config — same
# Doubao 2 config + same controlled-error type used across both modules.


ALLOWED_INTENTS = ("informational", "commercial", "transactional", "navigational")
ALLOWED_LANGUAGES = ("zh-CN", "en-US")
ALLOWED_PROMPT_SCOPES = ("non_branded", "branded", "competitive")
LEGACY_PROMPT_SCOPE_ALIASES = {"competitor": "competitive"}
ALLOWED_COMPETITIVE_TYPES = (
    "direct_comparison",
    "brand_alternative",
    "product_alternative",
    "switching",
    "shortlist",
)
REVIEW_STATUSES = {"pending", "approved", "rejected"}
DEFAULT_MAX_PROMPTS = 10
MAX_PROMPTS_HARD_LIMIT = 100_000

INTENT_LABELS = {
    "informational": "Information seeking",
    "commercial": "Purchase comparison",
    "transactional": "Ready to act",
    "navigational": "Specific lookup",
}

ADMIN_OR_OPERATIONS_TERMS = {
    "crm",
    "private domain",
    "member operation",
    "membership operation",
    "retention campaign",
    "conversion funnel",
    "admin dashboard",
    "后台",
    "运营后台",
    "私域",
    "会员运营",
    "用户运营",
    "渠道运营",
    "客户分层",
    "人群包",
    "触达",
    "转化率",
    "生命周期",
    "动销",
}

QUESTION_SIGNALS = {
    "how",
    "what",
    "which",
    "why",
    "where",
    "when",
    "can",
    "should",
    "is",
    "are",
    "does",
    "do",
    "怎么",
    "如何",
    "哪",
    "吗",
    "什么",
    "推荐",
    "适合",
    "区别",
    "值得",
    "怎么买",
    "在哪里买",
    "去哪里",
    "价格",
    "好吗",
    "嘛",
    "不踩雷",
    "够用",
    "耐造",
}

ENGLISH_TEMPLATE_PHRASES = (
    "how should i",
    "which factors",
    "what should i",
    "what is the best",
    "where can i",
    "should i choose",
)

STILTED_PROMPT_PHRASES = (
    "高端奢侈品集团旗下",
    "顶级奢侈品集团旗下",
    "LVMH",
    "路威酩轩",
    "Moet Hennessy",
    "集团旗下",
    "旗下",
    "产品线",
    "品类线",
    "奢品品牌",
    "品牌档次",
    "高端收藏级",
    "爆款新款",
    "热门款",
    "知名品牌",
    "市场表现",
    "趋势分析",
    "用户画像",
    "转化路径",
    "性价比更高更值得",
    "更合适性价比更高",
    "哪个档次的产品更适合",
    "具体有什么区别呀",
    "what suitable gift options",
    "under top luxury groups",
    "cost performance",
    "more suitable and cost-effective",
    "recommended popular shades",
)

CONSUMER_ALIAS_OVERRIDES = {
    "lvmh": ["LV", "Dior", "迪奥", "Sephora", "丝芙兰", "大牌香水", "大牌包"],
    "moethennessylouisvuitton": ["LV", "Dior", "迪奥", "Sephora", "丝芙兰", "大牌香水", "大牌包"],
    "路威酩轩": ["LV", "Dior", "迪奥", "Sephora", "丝芙兰", "大牌香水", "大牌包"],
}


class PromptMatrixError(ValueError):
    """Controlled error returned to the API layer for Prompt Matrix failures."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _normalize_taxonomy_token(value: Any) -> str:
    raw = str(value or "").strip()
    raw = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", raw)
    return raw.lower().replace("-", "_")


def normalize_prompt_scope(value: Any) -> str:
    """Normalize the Prompt-layer scope taxonomy.

    Missing scope defaults to non_branded for backward compatibility with
    existing Prompt rows; invalid explicit values are schema errors so LLM
    mistakes are visible instead of silently drifting into Query Pool.
    """
    raw = _normalize_taxonomy_token(value)
    if not raw:
        return "non_branded"
    raw = LEGACY_PROMPT_SCOPE_ALIASES.get(raw, raw)
    if raw not in ALLOWED_PROMPT_SCOPES:
        raise PromptMatrixError(
            "llm_schema_invalid",
            "prompt_scope must be one of "
            + ", ".join(ALLOWED_PROMPT_SCOPES)
            + " (legacy alias: competitor)",
        )
    return raw


def normalize_competitive_type(scope: Any, value: Any) -> str | None:
    """Validate the competitive sub-taxonomy.

    Only competitive prompts may carry a competitive_type. Older rows may
    omit the field, but new LLM output is rejected so the prompt intent does
    not blur again at Query Pool time.
    """
    prompt_scope = normalize_prompt_scope(scope)
    raw = _normalize_taxonomy_token(value)
    if prompt_scope != "competitive":
        if raw:
            raise PromptMatrixError(
                "llm_schema_invalid",
                "competitive_type is only allowed when prompt_scope is competitive",
            )
        return None
    if not raw:
        raise PromptMatrixError(
            "llm_schema_invalid",
            "competitive_type is required when prompt_scope is competitive",
        )
    if raw not in ALLOWED_COMPETITIVE_TYPES:
        raise PromptMatrixError(
            "llm_schema_invalid",
            "competitive_type must be one of " + ", ".join(ALLOWED_COMPETITIVE_TYPES),
        )
    return raw


@dataclass(frozen=True)
class LLMPromptCandidate:
    topic_id: int
    intent: str
    language: str
    text: str
    template_strategy: str
    template_version: str
    confidence: float
    reason: str
    tags: dict[str, Any]
    competitive_type: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "topic_id": self.topic_id,
            "intent": self.intent,
            "language": self.language,
            "text": self.text,
            "template_strategy": self.template_strategy,
            "template_version": self.template_version,
            "confidence": self.confidence,
            "reason": self.reason,
            "tags": self.tags,
            "competitive_type": self.competitive_type,
        }


def clamp_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(parsed, max_value))


def selected_intents(intent_count: Any) -> list[str]:
    return list(ALLOWED_INTENTS[: clamp_int(intent_count, 4, 1, len(ALLOWED_INTENTS))])


def selected_languages(language_count: Any) -> list[str]:
    return list(ALLOWED_LANGUAGES[: clamp_int(language_count, 2, 1, len(ALLOWED_LANGUAGES))])


def intent_language_combinations(
    intent_count: Any,
    language_count: Any,
    max_per_topic: Any,
) -> list[dict[str, str]]:
    limit = clamp_int(max_per_topic, 4, 1, len(ALLOWED_INTENTS) * len(ALLOWED_LANGUAGES))
    combos = [
        {"intent": intent, "language": language}
        for intent in selected_intents(intent_count)
        for language in selected_languages(language_count)
    ]
    return combos[:limit]


def _topic_has_explicit_brand_anchor(topic: dict[str, Any]) -> bool:
    return any(
        str(topic.get(key) or "").strip()
        for key in ("brand", "brand_name", "brandName", "product_name", "productName")
    )


def _scope_rotation_for_topic(topic: dict[str, Any]) -> list[dict[str, str]]:
    if _topic_has_explicit_brand_anchor(topic):
        return [
            {"prompt_scope": "branded"},
            {"prompt_scope": "competitive", "competitive_type": "direct_comparison"},
            {"prompt_scope": "competitive", "competitive_type": "brand_alternative"},
            {"prompt_scope": "non_branded"},
            {"prompt_scope": "competitive", "competitive_type": "product_alternative"},
            {"prompt_scope": "competitive", "competitive_type": "switching"},
            {"prompt_scope": "competitive", "competitive_type": "shortlist"},
        ]
    return [
        {"prompt_scope": "non_branded"},
        {"prompt_scope": "competitive", "competitive_type": "shortlist"},
        {"prompt_scope": "competitive", "competitive_type": "product_alternative"},
        {"prompt_scope": "competitive", "competitive_type": "brand_alternative"},
    ]


def build_prompt_generation_slots(
    *,
    topic: dict[str, Any],
    combinations: list[dict[str, Any]],
    max_per_topic: Any,
) -> list[dict[str, Any]]:
    """Assign prompt scope/type inside the existing per-topic quota.

    The slot count is capped by max_per_topic and the existing intent/language
    combinations, so adding prompt scopes never multiplies generation volume.
    """
    limit = clamp_int(max_per_topic, len(combinations), 1, len(ALLOWED_INTENTS) * len(ALLOWED_LANGUAGES))
    base_slots = combinations[:limit]
    rotation = _scope_rotation_for_topic(topic)
    slots: list[dict[str, Any]] = []
    for index, combo in enumerate(base_slots):
        scope = rotation[index % len(rotation)]
        slot: dict[str, Any] = {
            "intent": str(combo.get("intent") or "").strip(),
            "language": str(combo.get("language") or combo.get("lang") or "").strip(),
            "prompt_scope": scope["prompt_scope"],
        }
        if scope.get("competitive_type"):
            slot["competitive_type"] = scope["competitive_type"]
        slots.append(slot)
    return slots


def estimate_generation_count(
    *,
    selected_topics: Any,
    intent_count: Any,
    language_count: Any,
    max_per_topic: Any,
    max_prompts: Any,
) -> int:
    raw_total = prompt_generation_raw_count(
        selected_topics=selected_topics,
        intent_count=intent_count,
        language_count=language_count,
        max_per_topic=max_per_topic,
    )
    cap = clamp_int(max_prompts, raw_total, 1, 1_000_000)
    return min(raw_total, cap)


def prompt_generation_raw_count(
    *,
    selected_topics: Any,
    intent_count: Any,
    language_count: Any,
    max_per_topic: Any,
) -> int:
    topic_count = clamp_int(selected_topics, 0, 0, 1_000_000)
    per_topic = len(intent_language_combinations(intent_count, language_count, max_per_topic))
    return topic_count * per_topic


def prompt_generation_max_prompts_cap(raw_prompt_count: Any) -> int:
    raw_total = clamp_int(raw_prompt_count, 0, 0, 1_000_000)
    return max(DEFAULT_MAX_PROMPTS, raw_total * 2)


def normalize_prompt_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    return "".join(ch for ch in normalized if ch.isalnum())


def consumer_aliases_for_brand_name(name: str, aliases: Any = None) -> list[str]:
    raw_terms: list[Any] = [name]
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
        normalized = normalize_prompt_text(text)
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


def consumer_aliases_for_topic(
    topic: dict[str, Any], known_brands: list[dict[str, Any]]
) -> list[str]:
    brand_name = str(topic.get("brand") or topic.get("brand_name") or "").strip()
    aliases: Any = topic.get("aliases")
    for brand in known_brands:
        if normalize_prompt_text(brand.get("name") or "") == normalize_prompt_text(brand_name):
            aliases = brand.get("aliases")
            break
    return consumer_aliases_for_brand_name(brand_name, aliases)


def contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def has_prompt_language_mismatch(text: str, language: str) -> bool:
    raw = (text or "").strip()
    lang = (language or "").strip()
    if not raw:
        return True
    lowered = raw.casefold()
    if lang == "en-US":
        return contains_cjk(raw)
    if lang == "zh-CN":
        if not contains_cjk(raw):
            return True
        return any(phrase in lowered for phrase in ENGLISH_TEMPLATE_PHRASES)
    return True


def is_near_duplicate_prompt(text: str, existing_normalized: set[str]) -> bool:
    current = normalize_prompt_text(text)
    if not current:
        return True
    if current in existing_normalized:
        return True
    for other in existing_normalized:
        if len(current) >= 12 and len(other) >= 12 and (current in other or other in current):
            return True
        # Module B-4: 0.9 → 0.96 (close paraphrases now slip through as
        # separate prompts); strict 0.9 was over-eating prompt batches.
        if SequenceMatcher(None, current, other).ratio() >= 0.96:
            return True
    return False


def dedupe_prompt_candidates(
    candidates: list[LLMPromptCandidate],
    existing_texts: list[str],
    max_count: int | None = None,
    *,
    layer_check: bool = True,
) -> tuple[list[LLMPromptCandidate], list[dict[str, Any]]]:
    """Dedupe + layer-boundary check. Skipped items carry structured
    ``reason`` codes so the API can surface a per-reason breakdown:

      - ``duplicate_db``         existing in DB
      - ``duplicate_intra_batch`` LLM repeated itself in this batch
      - ``looks_like_topic``     layer violation: this is a Topic, not a Prompt
      - ``looks_like_query``     layer violation: this carries personal anchors
      - ``over_limit``           accepted enough already, this is the tail
    """
    from app.admin.topic_plan.layer_classifier import reject_reason as _reject_reason

    db_normalized = {normalize_prompt_text(text) for text in existing_texts if text}
    db_normalized.discard("")
    batch_normalized: set[str] = set()
    accepted: list[LLMPromptCandidate] = []
    skipped: list[dict[str, Any]] = []

    for item in candidates:
        if max_count is not None and len(accepted) >= max_count:
            skipped.append({"text": item.text, "reason": "over_limit"})
            continue
        if layer_check:
            layer_reason = _reject_reason(item.text, "prompt")
            if layer_reason is not None:
                skipped.append({"text": item.text, "reason": layer_reason})
                continue
        if is_near_duplicate_prompt(item.text, db_normalized):
            skipped.append({"text": item.text, "reason": "duplicate_db"})
            continue
        if is_near_duplicate_prompt(item.text, batch_normalized):
            skipped.append({"text": item.text, "reason": "duplicate_intra_batch"})
            continue
        accepted.append(item)
        batch_normalized.add(normalize_prompt_text(item.text))
    return accepted, skipped


def sample_existing_for_context(items: list[str], total_quota: int = 400) -> list[str]:
    """Module B-2: send the LLM a mix of recency + breadth instead of the
    naive ``items[:300]`` slice (so the LLM "sees" what the long tail of
    the prompt library covers, not just the most-recent 300).
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

    return max(math.ceil(target * multiplier), target + min_buffer)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def brand_terms_from_brands(brands: list[dict[str, Any]]) -> list[str]:
    terms: list[str] = []
    for brand in brands:
        raw_terms = [brand.get("name"), brand.get("name_zh"), brand.get("name_en")]
        raw_terms.extend(_as_list(brand.get("aliases")))
        for raw in raw_terms:
            if raw is None:
                continue
            term = str(raw).strip()
            if len(normalize_prompt_text(term)) < 2:
                continue
            if term not in terms:
                terms.append(term)
    return terms


def detect_brand_leaks(text: str, brands: list[dict[str, Any]]) -> list[str]:
    normalized_text = normalize_prompt_text(text)
    leaks = []
    for term in brand_terms_from_brands(brands):
        if normalize_prompt_text(term) in normalized_text:
            leaks.append(term)
    return leaks


def _topic_anchor_terms(topic: dict[str, Any], known_brands: list[dict[str, Any]]) -> list[str]:
    terms: list[str] = []
    for raw in (
        topic.get("brand"),
        topic.get("brand_name"),
        topic.get("brandName"),
        topic.get("product_name"),
        topic.get("productName"),
        topic.get("product_sku"),
    ):
        if raw is not None:
            text = str(raw).strip()
            if text:
                terms.append(text)
    terms.extend(consumer_aliases_for_topic(topic, known_brands))
    product_aliases = topic.get("product_aliases") or topic.get("productAliases")
    if isinstance(product_aliases, str):
        try:
            product_aliases = json.loads(product_aliases)
        except Exception:
            product_aliases = [product_aliases]
    if isinstance(product_aliases, list | tuple):
        terms.extend(str(item).strip() for item in product_aliases if str(item).strip())
    deduped: list[str] = []
    for term in terms:
        if len(normalize_prompt_text(term)) >= 2 and term not in deduped:
            deduped.append(term)
    return deduped


def prompt_text_has_brand_anchor(
    text: str, topic: dict[str, Any], known_brands: list[dict[str, Any]]
) -> bool:
    normalized_text = normalize_prompt_text(text)
    for term in _topic_anchor_terms(topic, known_brands):
        normalized_term = normalize_prompt_text(term)
        if normalized_term and normalized_term in normalized_text:
            return True
    return False


COMPETITIVE_SIGNAL_TERMS = (
    "compare",
    "compared",
    "comparison",
    "versus",
    " vs ",
    " vs.",
    "better than",
    "alternative",
    "alternatives",
    "instead of",
    "switch",
    "switching",
    "replace",
    "similar",
    "shortlist",
    "top ",
    "competitor",
    "竞品",
    "对比",
    "比较",
    "替代",
    "平替",
    "换成",
    "换",
    "同类",
    "类似",
    "哪个好",
    "哪款更",
    "清单",
    "榜单",
)


def prompt_text_has_competitive_signal(text: str) -> bool:
    lowered = f" {str(text or '').casefold()} "
    return any(signal.casefold() in lowered for signal in COMPETITIVE_SIGNAL_TERMS)


def strip_brand_terms(text: str, brands: list[dict[str, Any]]) -> str:
    cleaned = str(text or "")
    for term in sorted(brand_terms_from_brands(brands), key=len, reverse=True):
        if not term:
            continue
        cleaned = re.sub(re.escape(term), "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -_/|,，、")
    return cleaned.strip()


TOPIC_RELEVANCE_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "what",
    "which",
    "how",
    "should",
    "choose",
    "best",
    "good",
    "better",
    "product",
    "products",
    "brand",
    "category",
    "options",
    "这个",
    "这些",
    "那个",
    "哪些",
    "哪款",
    "什么",
    "怎么",
    "如何",
    "应该",
    "适合",
    "推荐",
    "比较",
    "购买",
    "使用",
    "产品",
    "品牌",
}


def _topic_brand_terms(topic: dict[str, Any], known_brands: list[dict[str, Any]]) -> list[str]:
    terms = brand_terms_from_brands(known_brands)
    for raw in (topic.get("brand"), topic.get("brand_name"), topic.get("brandName")):
        if raw is None:
            continue
        term = str(raw).strip()
        if len(normalize_prompt_text(term)) >= 2 and term not in terms:
            terms.append(term)
    return terms


def _text_without_terms(text: str, terms: list[str]) -> str:
    cleaned = str(text or "")
    for term in sorted(terms, key=len, reverse=True):
        if not term:
            continue
        cleaned = re.sub(re.escape(term), " ", cleaned, flags=re.IGNORECASE)
    return cleaned


def _cjk_ngrams(value: str) -> set[str]:
    terms: set[str] = set()
    for seq in re.findall(r"[\u4e00-\u9fff]{2,}", value or ""):
        if len(seq) <= 4:
            terms.add(seq)
        for size in (2, 3):
            for index in range(0, max(0, len(seq) - size + 1)):
                terms.add(seq[index : index + size])
    return terms


def topic_relevance_terms(
    topic: dict[str, Any], known_brands: list[dict[str, Any]] | None = None
) -> set[str]:
    known_brands = known_brands or []
    title = str(topic.get("title") or topic.get("text") or topic.get("topic_text") or "").strip()
    brand_terms = _topic_brand_terms(topic, known_brands)
    content_text = _text_without_terms(title, brand_terms)
    terms = {
        token.casefold()
        for token in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9+.#_-]{1,}", content_text)
        if token.casefold() not in TOPIC_RELEVANCE_STOPWORDS
    }
    terms.update(
        term
        for term in _cjk_ngrams(content_text)
        if term not in TOPIC_RELEVANCE_STOPWORDS and len(normalize_prompt_text(term)) >= 2
    )
    if not terms and _topic_dimension(topic) == "brand":
        terms.update(
            normalize_prompt_text(term)
            for term in brand_terms
            if len(normalize_prompt_text(term)) >= 2
        )
    return {term for term in terms if term}


def is_prompt_relevant_to_topic(
    text: str,
    topic: dict[str, Any],
    known_brands: list[dict[str, Any]] | None = None,
    language: str | None = None,
) -> bool:
    terms = topic_relevance_terms(topic, known_brands)
    if not terms:
        return True
    if language == "en-US":
        ascii_terms = {term for term in terms if term.isascii()}
        if not ascii_terms:
            return True
        terms = ascii_terms
    normalized_text = normalize_prompt_text(text)
    lowered_text = str(text or "").casefold()
    for term in terms:
        normalized_term = normalize_prompt_text(term)
        if normalized_term and normalized_term in normalized_text:
            return True
        if term.isascii() and term.casefold() in lowered_text:
            return True
    return False


def has_category_brand_leak(
    text: str,
    *,
    topic_dimension: str,
    known_brands: list[dict[str, Any]],
) -> bool:
    return (topic_dimension or "").strip().lower() == "category" and bool(
        detect_brand_leaks(text, known_brands)
    )


def is_keyword_stuffing(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return True
    has_question_signal = has_question_like_signal(raw)
    tokenish = [token for token in re.split(r"[\s,，/|;；、]+", raw) if token]
    if len(tokenish) >= 4 and not has_question_signal:
        avg_len = sum(len(token) for token in tokenish) / len(tokenish)
        if avg_len <= 8:
            return True
    separators = sum(raw.count(ch) for ch in [",", "，", "/", "|", "、", ";", "；"])
    if separators >= 3 and separators >= max(1, len(tokenish) - 1) and not has_question_signal:
        return True
    return False


def has_question_like_signal(text: str) -> bool:
    lowered = (text or "").casefold()
    if "?" in lowered or "？" in lowered:
        return True
    return any(signal in lowered for signal in QUESTION_SIGNALS)


def is_stilted_prompt(text: str) -> bool:
    lowered = (text or "").casefold()
    if any(phrase.casefold() in lowered for phrase in STILTED_PROMPT_PHRASES):
        return True
    if lowered.count("性价比") >= 2:
        return True
    if lowered.startswith("what are the recommended"):
        return True
    return False


def is_natural_user_prompt(text: str) -> bool:
    raw = (text or "").strip()
    if len(raw) < 8 or len(raw) > 500:
        return False
    lowered = raw.casefold()
    if "{{" in raw or "}}" in raw:
        return False
    if any(term in lowered for term in ADMIN_OR_OPERATIONS_TERMS):
        return False
    if is_keyword_stuffing(raw):
        return False
    if is_stilted_prompt(raw):
        return False
    return has_question_like_signal(raw)


def is_valid_prompt_for_language(text: str, language: str) -> bool:
    return is_natural_user_prompt(text) and not has_prompt_language_mismatch(text, language)


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
        return {"prompts": raw}
    cleaned = strip_markdown_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except Exception as first_error:
        if repair_json is None:
            raise PromptMatrixError(
                "llm_json_invalid", "LLM returned invalid JSON"
            ) from first_error
        try:
            parsed = json.loads(repair_json(cleaned))
        except Exception as repair_error:
            raise PromptMatrixError(
                "llm_json_invalid", "LLM returned invalid JSON"
            ) from repair_error
    if isinstance(parsed, list):
        return {"prompts": parsed}
    if not isinstance(parsed, dict):
        raise PromptMatrixError("llm_schema_invalid", "LLM JSON root must be an object")
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
    if data.get("text"):
        return [data]
    raise PromptMatrixError("llm_schema_invalid", f"LLM JSON must contain a {root_key} array")


def _topic_lookup_key(value: Any) -> int:
    text = str(value or "").strip()
    if text.upper().startswith("T-"):
        text = text[2:]
    if not text.isdigit():
        raise PromptMatrixError(
            "llm_schema_invalid", "Prompt topic_id must be an integer or T-* id"
        )
    return int(text)


def _topic_dimension(topic: dict[str, Any]) -> str:
    return (
        str(topic.get("dimension_key") or topic.get("dimension") or topic.get("category") or "")
        .strip()
        .lower()
    )


def parse_llm_prompt_candidates(
    raw: str | dict[str, Any],
    *,
    topics_by_id: dict[int, dict[str, Any]],
    known_brands: list[dict[str, Any]],
    default_template_strategy: str = "latest",
    default_template_version: str = "v1",
) -> list[LLMPromptCandidate]:
    data = _load_json_object(raw)
    prompts = _extract_llm_items(data, "prompts")

    parsed: list[LLMPromptCandidate] = []
    for index, item in enumerate(prompts):
        if not isinstance(item, dict):
            raise PromptMatrixError(
                "llm_schema_invalid",
                f"Prompt item #{index + 1} must be an object",
            )
        topic_id = _topic_lookup_key(item.get("topic_id"))
        topic = topics_by_id.get(topic_id)
        if topic is None:
            raise PromptMatrixError(
                "llm_schema_invalid",
                f"Prompt item #{index + 1} references an unknown topic",
            )
        intent = str(item.get("intent") or "").strip().lower()
        language = str(item.get("language") or item.get("lang") or "").strip()
        text = str(item.get("text") or item.get("prompt") or "").strip()
        reason = str(item.get("reason") or "").strip()
        template_strategy = str(
            item.get("template_strategy") or default_template_strategy or "latest"
        ).strip()
        template_version = str(
            item.get("template_version") or default_template_version or "v1"
        ).strip()
        try:
            confidence = float(item.get("confidence", 0.75))
        except (TypeError, ValueError) as error:
            raise PromptMatrixError(
                "llm_schema_invalid",
                f"Prompt item #{index + 1} confidence must be a number",
            ) from error
        raw_tags_value = item.get("tags")
        raw_tags: dict[str, Any] = raw_tags_value if isinstance(raw_tags_value, dict) else {}
        tags = {key: value for key, value in raw_tags.items() if key != "engines"}
        prompt_scope = normalize_prompt_scope(
            item.get("prompt_scope")
            or item.get("promptScope")
            or tags.get("prompt_scope")
            or tags.get("promptScope")
        )
        competitive_type = normalize_competitive_type(
            prompt_scope,
            item.get("competitive_type")
            or item.get("competitiveType")
            or tags.get("competitive_type")
            or tags.get("competitiveType"),
        )
        tags.pop("promptScope", None)
        tags.pop("competitiveType", None)
        tags.pop("competitive_type", None)

        if intent not in ALLOWED_INTENTS:
            raise PromptMatrixError(
                "llm_schema_invalid",
                f"Prompt item #{index + 1} intent must be one of {', '.join(ALLOWED_INTENTS)}",
            )
        if language not in ALLOWED_LANGUAGES:
            raise PromptMatrixError(
                "llm_schema_invalid",
                f"Prompt item #{index + 1} language must be one of {', '.join(ALLOWED_LANGUAGES)}",
            )
        if confidence < 0 or confidence > 1:
            raise PromptMatrixError(
                "llm_schema_invalid",
                f"Prompt item #{index + 1} confidence must be between 0 and 1",
            )
        if not is_natural_user_prompt(text):
            raise PromptMatrixError(
                "prompt_not_natural",
                f"Prompt item #{index + 1} must be a natural consumer question",
            )
        if has_prompt_language_mismatch(text, language):
            raise PromptMatrixError(
                "prompt_language_mismatch",
                f"Prompt item #{index + 1} language does not match its text",
            )
        if prompt_scope == "non_branded":
            leaked_terms = detect_brand_leaks(text, known_brands)
            if leaked_terms:
                code = (
                    "category_brand_leak"
                    if _topic_dimension(topic) == "category"
                    else "prompt_scope_mismatch"
                )
                raise PromptMatrixError(
                    code,
                    f"Prompt item #{index + 1} leaks a brand name in non_branded scope",
                )
        if prompt_scope == "branded" and not prompt_text_has_brand_anchor(
            text, topic, known_brands
        ):
            raise PromptMatrixError(
                "prompt_scope_mismatch",
                f"Prompt item #{index + 1} is branded but does not include the topic brand or product",
            )
        if prompt_scope == "competitive" and not prompt_text_has_competitive_signal(text):
            raise PromptMatrixError(
                "prompt_scope_mismatch",
                f"Prompt item #{index + 1} is competitive but lacks comparison or alternative intent",
            )
        if not is_prompt_relevant_to_topic(text, topic, known_brands, language=language):
            raise PromptMatrixError(
                "prompt_topic_mismatch",
                f"Prompt item #{index + 1} does not match its source topic",
            )

        parsed.append(
            LLMPromptCandidate(
                topic_id=topic_id,
                intent=intent,
                language=language,
                text=text,
                template_strategy=template_strategy,
                template_version=template_version,
                confidence=confidence,
                reason=reason or INTENT_LABELS[intent],
                tags={
                    **tags,
                    "prompt_scope": prompt_scope,
                    **({"competitive_type": competitive_type} if competitive_type else {}),
                    "source": tags.get("source") or "prompt_matrix",
                    "routing": tags.get("routing") or "deferred_to_query_pool",
                },
                competitive_type=competitive_type,
            )
        )
    return parsed


def transition_candidate_status(current_status: str, requested_status: str) -> str:
    current = (current_status or "").strip().lower()
    requested = (requested_status or "").strip().lower()
    if requested not in {"approved", "rejected"}:
        raise PromptMatrixError(
            "invalid_review_status", "Review status must be approved or rejected"
        )
    if current not in REVIEW_STATUSES:
        raise PromptMatrixError("invalid_current_status", "Candidate has an invalid current status")
    if current != "pending":
        raise PromptMatrixError("candidate_already_reviewed", "Candidate has already been reviewed")
    return requested


def prompt_generation_config(payload: dict[str, Any]) -> dict[str, Any]:
    intent_count = clamp_int(payload.get("intent_count"), 4, 1, len(ALLOWED_INTENTS))
    language_count = clamp_int(payload.get("language_count"), 2, 1, len(ALLOWED_LANGUAGES))
    max_per_topic = clamp_int(
        payload.get("max_per_topic"), 4, 1, len(ALLOWED_INTENTS) * len(ALLOWED_LANGUAGES)
    )
    max_prompts = clamp_int(
        payload.get("max_prompts"), DEFAULT_MAX_PROMPTS, 1, MAX_PROMPTS_HARD_LIMIT
    )
    return {
        "intent_count": intent_count,
        "language_count": language_count,
        "intents": selected_intents(intent_count),
        "languages": selected_languages(language_count),
        "combinations": intent_language_combinations(intent_count, language_count, max_per_topic),
        "topic_priority": str(payload.get("topic_priority") or "gap_first"),
        "template_strategy": str(payload.get("template_strategy") or "latest"),
        "prompt_style": str(payload.get("prompt_style") or "natural"),
        "audience_mode": str(payload.get("audience_mode") or "general"),
        "max_per_topic": max_per_topic,
        "max_prompts": max_prompts,
        "overflow_policy": str(payload.get("overflow_policy") or "split"),
    }


def build_prompt_matrix_messages(
    *,
    topics: list[dict[str, Any]],
    config: dict[str, Any],
    known_brands: list[dict[str, Any]],
    existing_prompts: list[str],
    active_hotspots: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    topic_payload = []
    combinations = config.get("combinations") or intent_language_combinations(
        config.get("intent_count"),
        config.get("language_count"),
        config.get("max_per_topic"),
    )
    for topic in topics:
        topic_id_raw = topic.get("raw_id") or topic.get("id") or 0
        entry: dict[str, Any] = {
            "topic_id": int(topic_id_raw),
            "title": topic.get("title") or topic.get("text") or "",
            "brand": topic.get("brand") or topic.get("brand_name") or "",
            "consumer_aliases": consumer_aliases_for_topic(topic, known_brands),
            "dimension": _topic_dimension(topic) or "brand",
            "required_focus_terms": sorted(topic_relevance_terms(topic, known_brands))[:12],
            "generation_slots": build_prompt_generation_slots(
                topic=topic,
                combinations=combinations,
                max_per_topic=config.get("max_per_topic"),
            ),
        }
        # Module C-4: surface SKU context to the LLM when the topic is pinned
        # to a specific product. Prompts generated under this topic must
        # mention this product (rule 23 below).
        if topic.get("product_name"):
            entry["product"] = {
                "name": topic.get("product_name"),
                "sku": topic.get("product_sku") or None,
                "category": topic.get("product_category") or None,
                "description": (topic.get("product_description") or "")[:300] or None,
                "aliases": topic.get("product_aliases") or [],
            }
        topic_payload.append(entry)
    schema = {
        "prompts": [
            {
                "topic_id": 123,
                "intent": "informational|commercial|transactional|navigational",
                "language": "zh-CN|en-US",
                "prompt_scope": "non_branded|branded|competitive",
                "competitive_type": "direct_comparison|brand_alternative|product_alternative|switching|shortlist|null",
                "template_strategy": config.get("template_strategy", "latest"),
                "template_version": "v1",
                "text": "A natural consumer question",
                "confidence": 0.0,
                "reason": "Why this prompt covers the gap",
                "tags": {
                    "source": "prompt_matrix",
                    "routing": "deferred_to_query_pool",
                    "prompt_scope": "copy prompt_scope",
                    "competitive_type": "copy competitive_type when prompt_scope is competitive",
                },
            }
        ]
    }
    payload = {
        "topics": topic_payload,
        "intents": config.get("intents") or selected_intents(config.get("intent_count")),
        "languages": config.get("languages") or selected_languages(config.get("language_count")),
        "combinations_per_topic": config.get("combinations") or [],
        "max_per_topic": config.get("max_per_topic"),
        "max_prompts": config.get("max_prompts"),
        "template_strategy": config.get("template_strategy"),
        "prompt_style": config.get("prompt_style"),
        "audience_mode": config.get("audience_mode"),
        "known_brand_terms": brand_terms_from_brands(known_brands),
        "allowed_prompt_scopes": list(ALLOWED_PROMPT_SCOPES),
        "allowed_competitive_types": list(ALLOWED_COMPETITIVE_TYPES),
        "existing_prompts": existing_prompts[:300],
        "output_schema": schema,
    }
    # Module D-4: pass current hotspots so a fraction of generated prompts
    # can piggyback on what the user is currently talking about.
    if active_hotspots:
        payload["current_hotspots"] = [
            {
                "id": int(h["id"]),
                "title": h.get("title") or "",
                "summary": (h.get("summary") or "")[:300],
                "category": h.get("category") or None,
            }
            for h in active_hotspots
            if h.get("id") and h.get("title")
        ][:15]
    # Module 0.5: prepend the layer-boundary header so the LLM knows it must
    # produce *Prompts* (complete user inputs, no personal anchors), not Topics
    # (noun-phrase subjects) and not Queries (Profile-personalized text).
    from app.admin.topic_plan.layer_classifier import LAYER_BOUNDARY_PROMPT

    system = (
        LAYER_BOUNDARY_PROMPT.replace("{LAYER}", "prompt")
        + "\n\n"
        + "你是 GENPANO 的真实用户问法生成器。你写的每一句都要像一个普通人准备搜索、购买、送礼、"
        "使用或避坑时会直接问出来的话。不要写 SEO 标题、导购稿、运营任务、后台指令或翻译腔。"
        "只返回严格 JSON，不要返回 Markdown。"
    )
    user = (
        "请根据 payload 生成 Prompt Matrix 候选。\n"
        "核心任务：对每个 topic / intent / language 组合，生成 1 条自然、有场景、像真人会问的问题。\n\n"
        "Layer definitions:\n"
        "Topic layer = high-level, reusable, brand-neutral consumer demand subject. Do not turn Topic titles back into brand slogans.\n"
        "Prompt layer = complete natural user input. Prompt owns prompt_scope: non_branded, branded, competitive.\n"
        "Query layer = Prompt + Segment/Profile personal context. Do not add age, city, exact budget, persona, or first-person anchors here; Query Pool will do that.\n\n"
        "prompt_scope 规则：\n"
        "S1. 每条 output.prompts[i] 必须写 prompt_scope，且只能是 non_branded / branded / competitive；同时复制到 tags.prompt_scope。legacy competitor 只用于读取旧数据，新输出不要使用。\n"
        "S2. non_branded：围绕 topic.title 的品类、功能、场景或问题提问，禁止出现 known_brand_terms、selected brand alias 或竞品名。\n"
        "S3. branded：可以自然包含 topic.brand 或 consumer_aliases，用来问该品牌/该产品相关问题，但不要写成品牌营销标题。\n"
        "S4. competitive：必须按 generation_slots 中的 competitive_type 做替代、对比、平替、切换或 shortlist 角度；如果 payload 没给明确竞品，不要杜撰具体竞品名，可写“同类品牌/平替/竞品”。\n"
        "S5. Topic 层不存品牌词，品牌/竞品词只在 Prompt 的 branded 或 competitive scope 出现；Query 层只继承 scope 和 competitive_type 并加入 Profile。\n"
        "S6. 每条 prompt 必须对应 payload.topics[].generation_slots 里的一个槽位；不要因为 scope 增多而额外生成更多条。\n\n"
        "前置质检规则，生成时必须主动满足，不要依赖后端丢弃：\n"
        "A. 避免 prompt_not_natural：每条必须是完整的自然用户问题，有真实消费者意图。\n"
        "B. 避免 looks_like_topic：不要输出 SEO 标题、Topic 名词短语、关键词堆砌或导购栏目标题。\n"
        "C. 避免 looks_like_query：不要加入具体 Profile 的年龄、城市、预算、人设或第一人称执行细节；这些留给 Query Pool。\n"
        "D. 避免 prompt_language_mismatch：严格按 language 字段输出。\n"
        "E. 避免 category_brand_leak：category dimension 和 non_branded scope 的 prompt 禁止出现 known_brand_terms 里的品牌名或 alias。\n"
        "如果某个组合写不出自然问法，换一个更贴近 topic 的消费者角度，不要硬编内部词。\n\n"
        "真人问法规则，优先级最高：\n"
        "1. 尽量短，像搜索框或聊天里打出来的一句话；中文通常 12-32 个汉字，英文通常 7-18 个词。\n"
        "2. 可以有口语感：会不会、值不值、哪款、怎么选、送人合不合适、日常用够不够、容易踩雷吗。\n"
        "3. 不要总用“都有哪些 / 具体 / 性价比更高更值得买 / 产品线 / 旗下产品 / 高端奢侈品集团旗下”。\n"
        "4. 英文不要直译中文，不要写 What suitable gift options... / cost performance / under top luxury groups。\n"
        "5. luxury 场景里如果要表达性价比，中文优先写“不太离谱 / 值不值 / 预算内怎么选”，英文优先写 worth the price。\n\n"
        "Topic 贴合规则：\n"
        "6. 必须保留 topic.title 里的具体产品、品类、场景和问题，不要换成同品牌其他产品或泛品牌话题。\n"
        "7. 如果 topic.title 已经像用户问题，只做自然化改写；不要把它扩写成导购标题。\n"
        "8. 尽量自然包含 required_focus_terms 里的非品牌锚点；如果没有合适锚点，也不能偏离原 topic。\n"
        "9. category dimension 的 topic 禁止出现 known_brand_terms 里的任何品牌名或 alias。不要用“某集团旗下”硬替代，直接问品类本身。\n"
        "10. 如果 topic 或 brand 是控股集团/公司名（比如 LVMH、路威酩轩），不要复制公司名，也不要写“旗下/集团/产品线/品牌档次”。优先使用 topic.consumer_aliases 里更像消费者会说的词，或者直接围绕大牌包、香水、礼物、皮具、腕表等场景提问。\n"
        "11. 反例：topic 是“混油皮夏天用的防晒霜”，不能生成口红、香水、包包、品牌历史。\n"
        "12. 正例：topic 是“混油皮夏天用的防晒霜”，可以生成“混油皮夏天用这款防晒会不会搓泥？”\n\n"
        "意图写法：\n"
        "13. informational：了解/判断，像“这款到底适不适合我？”\n"
        "14. commercial：买前比较，像“预算内哪款更值得？”\n"
        "15. transactional：准备购买或下单前确认，像“在哪里买比较稳？”“怎么避坑？”\n"
        "16. navigational：找官网、评价、购买入口或真实反馈来源。\n\n"
        "语言规则：\n"
        "17. language=zh-CN 时输出中文自然问句，可以包含必要英文品牌名、产品名或场景词，比如 Nike、hiking、Gore-Tex。\n"
        "18. language=en-US 时输出英文自然问句，不要混入中文字符。\n"
        "19. 不要使用 {{brand_name}} 这类模板变量。\n"
        "20. 不要决定执行引擎，也不要返回 tags.engines；引擎只在 Query Pool / Tracker 最终调度时决定。\n"
        "21. tags.routing 固定写 deferred_to_query_pool。\n"
        "22. 最多返回 max_prompts 条，字段必须严格匹配 output_schema。\n"
        "23. 如果 topic.product 存在，prompt 必须明确提到该产品（用 product.name 或 product.aliases 之一），不要泛化到品牌层面，保持 SKU 颗粒度。\n"
        "24. 如果 current_hotspots 非空，本批次约 20-30% 的 prompt 应蹭一个热点角度（可在文本里提到事件名/角度，不要硬塞日期），其他 prompt 保持 evergreen。蹭热点的 prompt 必须仍然是 Prompt 形态（不带个人化锚点）。\n"
        "25. 当一条 prompt 蹭了热点，请在 output.prompts[i].tags.hotspot_id 写上该 hotspot 的 id（来自 current_hotspots 里的 id 字段），便于后端入库时建立 FK。\n\n"
        "好坏示例：\n"
        "Bad zh-CN: 高端奢侈品集团旗下的香水线哪些性价比更高？\n"
        "Good zh-CN: 想买大牌香水，哪些系列不太贵又好闻？\n"
        "Bad zh-CN: 打算送礼物给职场女性，LVMH旗下的产品选哪个更合适性价比更高？\n"
        "Good zh-CN: 送职场女生大牌礼物，选香水还是小皮具更稳？\n"
        "Bad en-US: What suitable gift options under LVMH are there for working women?\n"
        "Good en-US: Is perfume or a small leather good a safer luxury gift for someone at work?\n"
        "Bad en-US: Which product has higher cost performance and is worth buying?\n"
        "Good en-US: Which one feels worth the price without being too flashy?\n\n"
        "payload:\n" + json.dumps(payload, ensure_ascii=False)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def chunked(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    size = max(1, size)
    return [items[index : index + size] for index in range(0, len(items), size)]


def usage_to_dict(usage_obj: Any) -> dict[str, Any]:
    if usage_obj is None:
        return {}
    if hasattr(usage_obj, "model_dump"):
        result: dict[str, Any] = usage_obj.model_dump()
        return result
    if isinstance(usage_obj, dict):
        return dict(usage_obj)
    return {
        key: getattr(usage_obj, key)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        if hasattr(usage_obj, key)
    }


def merge_usage(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left or {})
    for key, value in (right or {}).items():
        if isinstance(value, (int, float)) and isinstance(merged.get(key), (int, float)):
            merged[key] += value
        elif key not in merged:
            merged[key] = value
    return merged


def llm_error_detail(error: Exception) -> str:
    parts = [type(error).__name__]
    status_code = getattr(error, "status_code", None)
    if status_code:
        parts.append(f"status={status_code}")
    message = str(error).strip()
    if message:
        parts.append(message[:500])
    return ": ".join(parts)


def llm_response_error_detail(response: Any) -> str:
    status_code = getattr(response, "status_code", None)
    detail = f"HTTP {status_code}" if status_code else "HTTP error"
    try:
        text = (getattr(response, "text", "") or "").strip()
    except Exception:  # pragma: no cover - defensive for unusual response mocks
        text = ""
    if text:
        detail = f"{detail}: {text[:500]}"
    return detail
