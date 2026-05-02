"""Prompt Matrix helpers for the query_tool admin console.

This module stays free of Flask and database dependencies so generation
planning, LLM parsing, safety gates, de-dupe, and review state can be tested
without secrets or a live database.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

try:
    from json_repair import repair_json
except Exception:  # pragma: no cover - optional dependency
    repair_json = None

try:
    from .topic_plan import TopicPlanLLMError, load_doubao_config
except ImportError:  # pragma: no cover - direct script execution
    from topic_plan import TopicPlanLLMError, load_doubao_config


ALLOWED_INTENTS = ("informational", "commercial", "transactional", "navigational")
ALLOWED_LANGUAGES = ("zh-CN", "en-US")
REVIEW_STATUSES = {"pending", "approved", "rejected"}

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


def estimate_generation_count(
    *,
    selected_topics: Any,
    intent_count: Any,
    language_count: Any,
    max_per_topic: Any,
    max_prompts: Any,
) -> int:
    topic_count = clamp_int(selected_topics, 0, 0, 1_000_000)
    per_topic = len(intent_language_combinations(intent_count, language_count, max_per_topic))
    raw_total = topic_count * per_topic
    cap = clamp_int(max_prompts, raw_total, 1, 1_000_000)
    return min(raw_total, cap)


def normalize_prompt_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    return "".join(ch for ch in normalized if ch.isalnum())


def consumer_aliases_for_brand_name(name: str, aliases: Any = None) -> list[str]:
    raw_terms = [name]
    if isinstance(aliases, str):
        try:
            aliases = json.loads(aliases)
        except Exception:
            aliases = [aliases]
    if isinstance(aliases, (list, tuple)):
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


def consumer_aliases_for_topic(topic: dict[str, Any], known_brands: list[dict[str, Any]]) -> list[str]:
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
        if SequenceMatcher(None, current, other).ratio() >= 0.9:
            return True
    return False


def dedupe_prompt_candidates(
    candidates: list[LLMPromptCandidate],
    existing_texts: list[str],
    max_count: int | None = None,
) -> tuple[list[LLMPromptCandidate], list[dict[str, str]]]:
    normalized = {normalize_prompt_text(text) for text in existing_texts if text}
    normalized.discard("")
    accepted: list[LLMPromptCandidate] = []
    skipped: list[dict[str, str]] = []

    for item in candidates:
        if max_count is not None and len(accepted) >= max_count:
            skipped.append({"text": item.text, "reason": "over_limit"})
            continue
        if is_near_duplicate_prompt(item.text, normalized):
            skipped.append({"text": item.text, "reason": "duplicate"})
            continue
        accepted.append(item)
        normalized.add(normalize_prompt_text(item.text))
    return accepted, skipped


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


def topic_relevance_terms(topic: dict[str, Any], known_brands: list[dict[str, Any]] | None = None) -> set[str]:
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


def _load_json_object(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    cleaned = strip_markdown_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except Exception as first_error:
        if repair_json is None:
            raise PromptMatrixError("llm_json_invalid", "LLM returned invalid JSON") from first_error
        try:
            parsed = json.loads(repair_json(cleaned))
        except Exception as repair_error:
            raise PromptMatrixError("llm_json_invalid", "LLM returned invalid JSON") from repair_error
    if not isinstance(parsed, dict):
        raise PromptMatrixError("llm_schema_invalid", "LLM JSON root must be an object")
    return parsed


def _topic_lookup_key(value: Any) -> int:
    text = str(value or "").strip()
    if text.upper().startswith("T-"):
        text = text[2:]
    if not text.isdigit():
        raise PromptMatrixError("llm_schema_invalid", "Prompt topic_id must be an integer or T-* id")
    return int(text)


def _topic_dimension(topic: dict[str, Any]) -> str:
    return str(
        topic.get("dimension_key")
        or topic.get("dimension")
        or topic.get("category")
        or ""
    ).strip().lower()


def parse_llm_prompt_candidates(
    raw: str | dict[str, Any],
    *,
    topics_by_id: dict[int, dict[str, Any]],
    known_brands: list[dict[str, Any]],
    default_template_strategy: str = "latest",
    default_template_version: str = "v1",
) -> list[LLMPromptCandidate]:
    data = _load_json_object(raw)
    prompts = data.get("prompts")
    if not isinstance(prompts, list):
        raise PromptMatrixError("llm_schema_invalid", "LLM JSON must contain a prompts array")

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
        raw_tags = item.get("tags") if isinstance(item.get("tags"), dict) else {}
        tags = {key: value for key, value in raw_tags.items() if key != "engines"}

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
        if has_category_brand_leak(text, topic_dimension=_topic_dimension(topic), known_brands=known_brands):
            raise PromptMatrixError(
                "category_brand_leak",
                f"Prompt item #{index + 1} leaks a brand name in a category topic",
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
                    "source": tags.get("source") or "prompt_matrix",
                    "routing": tags.get("routing") or "deferred_to_query_pool",
                },
            )
        )
    return parsed


def transition_candidate_status(current_status: str, requested_status: str) -> str:
    current = (current_status or "").strip().lower()
    requested = (requested_status or "").strip().lower()
    if requested not in {"approved", "rejected"}:
        raise PromptMatrixError("invalid_review_status", "Review status must be approved or rejected")
    if current not in REVIEW_STATUSES:
        raise PromptMatrixError("invalid_current_status", "Candidate has an invalid current status")
    if current != "pending":
        raise PromptMatrixError("candidate_already_reviewed", "Candidate has already been reviewed")
    return requested


def prompt_generation_config(payload: dict[str, Any]) -> dict[str, Any]:
    intent_count = clamp_int(payload.get("intent_count"), 4, 1, len(ALLOWED_INTENTS))
    language_count = clamp_int(payload.get("language_count"), 2, 1, len(ALLOWED_LANGUAGES))
    max_per_topic = clamp_int(payload.get("max_per_topic"), 4, 1, len(ALLOWED_INTENTS) * len(ALLOWED_LANGUAGES))
    max_prompts = clamp_int(payload.get("max_prompts"), 8000, 1, 100_000)
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
) -> list[dict[str, str]]:
    topic_payload = [
        {
            "topic_id": int(topic.get("raw_id") or topic.get("id")),
            "title": topic.get("title") or topic.get("text") or "",
            "brand": topic.get("brand") or topic.get("brand_name") or "",
            "consumer_aliases": consumer_aliases_for_topic(topic, known_brands),
            "dimension": _topic_dimension(topic) or "brand",
            "required_focus_terms": sorted(topic_relevance_terms(topic, known_brands))[:12],
        }
        for topic in topics
    ]
    schema = {
        "prompts": [
            {
                "topic_id": 123,
                "intent": "informational|commercial|transactional|navigational",
                "language": "zh-CN|en-US",
                "template_strategy": config.get("template_strategy", "latest"),
                "template_version": "v1",
                "text": "A natural consumer question",
                "confidence": 0.0,
                "reason": "Why this prompt covers the gap",
                "tags": {"source": "prompt_matrix", "routing": "deferred_to_query_pool"},
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
        "existing_prompts": existing_prompts[:300],
        "output_schema": schema,
    }
    system = (
        "你是 GENPANO 的真实用户问法生成器。你写的每一句都要像一个普通人准备搜索、购买、送礼、"
        "使用或避坑时会直接问出来的话。不要写 SEO 标题、导购稿、运营任务、后台指令或翻译腔。"
        "只返回严格 JSON，不要返回 Markdown。"
    )
    user = (
        "请根据 payload 生成 Prompt Matrix 候选。\n"
        "核心任务：对每个 topic / intent / language 组合，生成 1 条自然、有场景、像真人会问的问题。\n\n"
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
        "22. 最多返回 max_prompts 条，字段必须严格匹配 output_schema。\n\n"
        "好坏示例：\n"
        "Bad zh-CN: 高端奢侈品集团旗下的香水线哪些性价比更高？\n"
        "Good zh-CN: 想买大牌香水，哪些系列不太贵又好闻？\n"
        "Bad zh-CN: 打算送礼物给职场女性，LVMH旗下的产品选哪个更合适性价比更高？\n"
        "Good zh-CN: 送职场女生大牌礼物，选香水还是小皮具更稳？\n"
        "Bad en-US: What suitable gift options under LVMH are there for working women?\n"
        "Good en-US: Is perfume or a small leather good a safer luxury gift for someone at work?\n"
        "Bad en-US: Which product has higher cost performance and is worth buying?\n"
        "Good en-US: Which one feels worth the price without being too flashy?\n\n"
        "payload:\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def chunked(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    size = max(1, size)
    return [items[index : index + size] for index in range(0, len(items), size)]


def usage_to_dict(usage_obj: Any) -> dict[str, Any]:
    if usage_obj is None:
        return {}
    if hasattr(usage_obj, "model_dump"):
        return usage_obj.model_dump()
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


class PromptMatrixClient:
    """Small OpenAI-compatible client using the project's Doubao/Ark config."""

    def __init__(self, config: Any | None = None):
        try:
            self.config = config or load_doubao_config()
        except TopicPlanLLMError as error:
            raise PromptMatrixError(error.code, error.message) from error

    def generate_prompts(
        self,
        *,
        topics: list[dict[str, Any]],
        config: dict[str, Any],
        known_brands: list[dict[str, Any]],
        existing_prompts: list[str],
    ) -> tuple[list[LLMPromptCandidate], dict[str, Any]]:
        all_prompts: list[LLMPromptCandidate] = []
        usage: dict[str, Any] = {}
        batches = 0
        for prompts, meta in self.generate_prompt_batches(
            topics=topics,
            config=config,
            known_brands=known_brands,
            existing_prompts=existing_prompts,
        ):
            all_prompts.extend(prompts)
            usage = merge_usage(usage, meta.get("usage") or {})
            batches += 1
        return all_prompts, {"model": self.config.model, "usage": usage, "batches": batches}

    def generate_prompt_batches(
        self,
        *,
        topics: list[dict[str, Any]],
        config: dict[str, Any],
        known_brands: list[dict[str, Any]],
        existing_prompts: list[str],
    ):
        if not topics:
            return
        batch_size = clamp_int(os.getenv("PROMPT_MATRIX_LLM_TOPICS_PER_REQUEST"), 2, 1, 5)
        max_prompts = clamp_int(config.get("max_prompts"), 8000, 1, 100_000)
        generated_prompts: list[LLMPromptCandidate] = []
        for batch in chunked(topics, batch_size):
            remaining = max_prompts - len(generated_prompts)
            if remaining <= 0:
                break
            batch_config = dict(config)
            batch_config["max_prompts"] = min(
                remaining,
                estimate_generation_count(
                    selected_topics=len(batch),
                    intent_count=config.get("intent_count"),
                    language_count=config.get("language_count"),
                    max_per_topic=config.get("max_per_topic"),
                    max_prompts=remaining,
                ),
            )
            prompts, meta = self._generate_prompt_batch(
                topics=batch,
                config=batch_config,
                known_brands=known_brands,
                existing_prompts=existing_prompts + [item.text for item in generated_prompts],
            )
            batch_prompts = prompts[:remaining]
            generated_prompts.extend(batch_prompts)
            yield batch_prompts, meta

    def _generate_prompt_batch(
        self,
        *,
        topics: list[dict[str, Any]],
        config: dict[str, Any],
        known_brands: list[dict[str, Any]],
        existing_prompts: list[str],
    ) -> tuple[list[LLMPromptCandidate], dict[str, Any]]:
        try:
            from openai import OpenAI
        except Exception as error:  # pragma: no cover - environment dependent
            raise PromptMatrixError("llm_client_unavailable", "OpenAI-compatible client is unavailable") from error

        messages = build_prompt_matrix_messages(
            topics=topics,
            config=config,
            known_brands=known_brands,
            existing_prompts=existing_prompts,
        )
        timeout_seconds = clamp_int(
            os.getenv("PROMPT_MATRIX_LLM_TIMEOUT_SECONDS") or getattr(self.config, "timeout", None) or 90,
            90,
            60,
            240,
        )
        expected = max(1, int(config.get("max_prompts") or 1))
        max_tokens = clamp_int(
            os.getenv("PROMPT_MATRIX_LLM_MAX_TOKENS") or (1024 + expected * 1024),
            4096,
            1024,
            8192,
        )
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
                max_tokens=max_tokens,
                timeout=timeout_seconds,
            )
        except Exception as error:
            raise PromptMatrixError(
                "llm_call_failed",
                "Prompt Matrix generation failed: " + llm_error_detail(error),
            ) from error

        content = response.choices[0].message.content or "{}"
        topics_by_id = {
            int(topic.get("raw_id") or topic.get("id")): topic
            for topic in topics
            if str(topic.get("raw_id") or topic.get("id") or "").isdigit()
        }
        prompts = parse_llm_prompt_candidates(
            content,
            topics_by_id=topics_by_id,
            known_brands=known_brands,
            default_template_strategy=config.get("template_strategy") or "latest",
            default_template_version="v1",
        )
        usage = usage_to_dict(getattr(response, "usage", None))
        return prompts, {"model": self.config.model, "usage": usage}
