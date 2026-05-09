# ruff: noqa: RUF001
"""Async Segment/Profile generation LLM service.

Port of admin_console/segment_profiles.py from sync OpenAI SDK to async
httpx, mirroring the topic_plan / prompt_matrix / query_pool pattern.

Public:
- ``SegmentProfileGenerationError`` — coded LLM failure.
- ``GenerationResult`` — returned by ``generate_segments`` /
  ``generate_profiles``.
- ``SegmentProfileGenerationService`` — async client. Reuses the
  Doubao/Ark config (``load_doubao_config``).
- ``validate_segment_candidates`` / ``validate_profile_candidates`` —
  pure-Python validators, exported for unit testing + slice 6b.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.admin.topic_plan.lib import (
    DoubaoConfig,
    TopicPlanLLMError,
    load_doubao_config,
)

try:  # optional dependency, same pattern as topic_plan / prompt_matrix
    from json_repair import repair_json
except Exception:  # pragma: no cover
    repair_json = None


class SegmentProfileGenerationError(Exception):
    """Coded error returned to the API layer when LLM output is unusable.

    Mirrors the admin_console error type field-for-field so existing
    tests + curl integrations that read ``.code`` keep working.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class GenerationResult:
    items: list[dict[str, Any]]
    model: str
    prompt: str
    usage: dict[str, Any]
    estimated_cost: float | None = None


def _bounded_count(value: Any, default: int, min_value: int, max_value: int) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = default
    return max(min_value, min(count, max_value))


def _slug(value: str, fallback: str = "segment") -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", value or "").strip("-").lower()
    return (text or fallback)[:24]


def _json_prompt(task: str, payload: dict[str, Any], schema_hint: dict[str, Any]) -> str:
    return (
        "你正在为 GENPANO Admin 生成供运营审核的 Segment/Profile 草稿。\n"
        "只返回严格 JSON，不要输出 markdown、注释、解释文字或代码块。\n"
        "必须围绕 Input 中的 brand_name、industry、positioning、product、"
        "generation_goal、generation_constraints 生成；"
        "如果这些字段互相冲突，以 brand_name 和 industry 为最高优先级。\n"
        "不要套用无关行业的样例，不要把美妆、护肤、香氛、礼赠等场景迁移到非相关品牌。\n"
        "默认使用中文撰写 name、note、regions、income 等可读字段；品牌名和专有名词保持原文；"
        "只有 Input 明确要求英文时才使用英文。\n"
        "Segment 必须是可进入 Query Pool 采样的业务/需求/决策场景分层，"
        "Profile 必须从所属 Segment 的真实边界继续细分。\n"
        "校验必填字段，数量不超过请求值，避免重复名称，weights 必须是 0 到 1 的数字。\n"
        "生成内容会先由人工审核，再写入数据库。\n"
        "不同品牌、不同产品必须生成不同 Segment；如果 Input.product 非空，"
        "必须优先围绕该产品的品类、"
        "描述和使用场景生成，而不是只生成品牌整体人群。\n"
        f"Task: {task}\n"
        f"Input: {json.dumps(payload, ensure_ascii=False, sort_keys=True)}\n"
        f"Output schema: {json.dumps(schema_hint, ensure_ascii=False, sort_keys=True)}"
    )


def _strip_markdown_fence(raw: str) -> str:
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
        return {"items": raw}
    cleaned = _strip_markdown_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except Exception as first_error:
        if repair_json is None:
            raise SegmentProfileGenerationError(
                "llm_json_invalid", "LLM returned invalid JSON"
            ) from first_error
        try:
            parsed = json.loads(repair_json(cleaned))
        except Exception as repair_error:
            raise SegmentProfileGenerationError(
                "llm_json_invalid", "LLM returned invalid JSON"
            ) from repair_error
    if isinstance(parsed, list):
        return {"items": parsed}
    if not isinstance(parsed, dict):
        raise SegmentProfileGenerationError("llm_schema_invalid", "LLM JSON root must be an object")
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
    if root_key == "segments" and data.get("name"):
        return [data]
    if root_key == "profiles" and data.get("name"):
        return [data]
    raise SegmentProfileGenerationError(
        "llm_schema_invalid", f"LLM JSON must contain a {root_key} array"
    )


def _usage_to_dict(usage_obj: Any) -> dict[str, Any]:
    if usage_obj is None:
        return {}
    if hasattr(usage_obj, "model_dump"):
        dumped = usage_obj.model_dump()
        return dict(dumped) if isinstance(dumped, dict) else {}
    if isinstance(usage_obj, dict):
        return dict(usage_obj)
    return {
        key: getattr(usage_obj, key)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        if hasattr(usage_obj, key)
    }


# ---------------------------------------------------------------------------
# Validation helpers (pure-Python — also used by slice 6b)
# ---------------------------------------------------------------------------


def _has_any(raw: dict[str, Any], *keys: str) -> bool:
    return any(key in raw and raw.get(key) not in (None, "") for key in keys)


def _require_any(raw: dict[str, Any], label: str, *keys: str) -> None:
    if not _has_any(raw, *keys):
        raise SegmentProfileGenerationError("missing_llm_field", f"{label} is required")


def _normalize_weight(value: Any, default: float, label: str = "weight") -> float:
    if value in (None, ""):
        return default
    raw_str = str(value).strip()
    try:
        number = float(raw_str.rstrip("%"))
    except (TypeError, ValueError) as exc:
        raise SegmentProfileGenerationError("invalid_weight", f"{label} must be numeric") from exc
    if raw_str.endswith("%"):
        number = number / 100.0
    if number < 0 or number > 1:
        raise SegmentProfileGenerationError("invalid_weight", f"{label} must be between 0 and 1")
    return number


def _normalize_profile_weight(value: Any, default: float = 1.0) -> float:
    """Profiles use relative sampling weight, not Segment share — value
    may exceed 1 (admin_console capped at 10)."""
    if value in (None, ""):
        return default
    try:
        raw = str(value).strip()
        number = float(raw.rstrip("%"))
    except (TypeError, ValueError):
        return default
    if raw.endswith("%"):
        number = number / 100.0
    if number < 0:
        raise SegmentProfileGenerationError("invalid_weight", "Profile weight must be non-negative")
    return min(number, 10.0)


def _first_non_empty(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in raw and raw.get(key) not in (None, ""):
            return raw.get(key)
    return None


_FALLBACKABLE_GENERATION_ERRORS = {
    "llm_json_invalid",
    "llm_schema_invalid",
    "missing_llm_field",
    "invalid_llm_output",
    "duplicate_segment_name",
    "invalid_segment_status",
    "invalid_weight",
}


def _should_fallback_generation(error: SegmentProfileGenerationError, allow_fallback: bool) -> bool:
    return allow_fallback or error.code in _FALLBACKABLE_GENERATION_ERRORS


def _normalise_product_contexts(
    products: list[dict[str, Any]] | None = None,
    *,
    product_id: str | int | None = None,
    product_name: str = "",
    product_category: str = "",
    product_description: str = "",
    product_sku: str = "",
) -> list[dict[str, str]]:
    raw_items: list[dict[str, Any]] = []
    if isinstance(products, list):
        raw_items.extend(item for item in products if isinstance(item, dict))
    if product_id or product_name or product_category or product_description or product_sku:
        raw_items.append(
            {
                "product_id": product_id,
                "product_name": product_name,
                "product_category": product_category,
                "product_description": product_description,
                "product_sku": product_sku,
            }
        )

    normalised: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw_items:
        product = {
            "product_id": str(item.get("product_id") or item.get("id") or "").strip(),
            "product_name": str(item.get("product_name") or item.get("name") or "").strip(),
            "product_category": str(
                item.get("product_category") or item.get("category") or ""
            ).strip(),
            "product_description": str(
                item.get("product_description") or item.get("description") or ""
            ).strip(),
            "product_sku": str(item.get("product_sku") or item.get("sku") or "").strip(),
        }
        product = {key: value for key, value in product.items() if value}
        key = product.get("product_id") or product.get("product_name")
        if not key or key.casefold() in seen:
            continue
        seen.add(key.casefold())
        normalised.append(product)
    return normalised[:12]


def _profile_status(value: Any) -> str:
    status = str(value or "draft").strip().lower()
    aliases = {
        "enabled": "active",
        "live": "active",
        "启用": "active",
        "已启用": "active",
        "有效": "active",
        "草稿": "draft",
        "待审核": "draft",
        "暂停": "paused",
        "停用": "paused",
    }
    return aliases.get(status, status if status in {"active", "draft", "paused"} else "draft")


def _coerce_persona_json(value: Any, *, demographic: str, need: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return {"items": value}
    if isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list):
                return {"items": parsed}
        except Exception:
            pass
        return {"summary": text, "demographic": demographic, "need": need}
    return {"demographic": demographic, "need": need}


def validate_segment_candidates(items: list[Any], max_count: int) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise SegmentProfileGenerationError("invalid_llm_output", "Segment output must be a list")
    seen_names: set[str] = set()
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(items[:max_count], start=1):
        if not isinstance(raw, dict):
            continue
        name = str(
            _first_non_empty(raw, "name", "segment_name", "segmentName", "title") or ""
        ).strip()
        if not name:
            raise SegmentProfileGenerationError("invalid_llm_output", "Segment name is required")
        normalized = name.lower()
        if normalized in seen_names:
            raise SegmentProfileGenerationError(
                "duplicate_segment_name", f"Duplicate Segment name: {name}"
            )
        seen_names.add(normalized)
        status = str(raw.get("status") or "draft").strip().lower()
        if status not in {"active", "draft", "paused"}:
            raise SegmentProfileGenerationError(
                "invalid_segment_status", f"Invalid Segment status: {status}"
            )
        weight = _normalize_weight(
            _first_non_empty(
                raw,
                "weight",
                "share",
                "audience_share",
                "audienceShare",
                "sampling_weight",
                "samplingWeight",
            ),
            0.15,
            "Segment weight",
        )
        segment_id = (
            str(_first_non_empty(raw, "id", "code") or f"SEG-DRAFT-{index:03d}").strip().upper()
        )
        sampling_rate = str(
            _first_non_empty(
                raw,
                "sampling_rate",
                "samplingRate",
                "sample_rate",
                "sampleRate",
                "sample_ratio",
                "sampleRatio",
                "audience_share",
                "audienceShare",
                "share",
            )
            or f"{round(weight * 100)}%"
        ).strip()
        rows.append(
            {
                "id": segment_id,
                "code": str(_first_non_empty(raw, "code", "id") or segment_id).strip().upper(),
                "name": name,
                "industry": str(
                    _first_non_empty(
                        raw,
                        "industry",
                        "industry_name",
                        "industryName",
                        "category",
                        "vertical",
                    )
                    or ""
                ).strip(),
                "status": status,
                "weight": weight,
                "age_range": str(
                    _first_non_empty(
                        raw,
                        "age_range",
                        "ageRange",
                        "age_group",
                        "ageGroup",
                        "age",
                        "ages",
                    )
                    or ""
                ).strip(),
                "income": str(
                    _first_non_empty(
                        raw,
                        "income",
                        "income_level",
                        "incomeLevel",
                        "income_range",
                        "incomeRange",
                    )
                    or ""
                ).strip(),
                "regions": str(
                    _first_non_empty(
                        raw,
                        "regions",
                        "region",
                        "location",
                        "locations",
                        "geo",
                        "market",
                    )
                    or ""
                ).strip(),
                "sampling_rate": sampling_rate,
                "note": str(
                    _first_non_empty(
                        raw,
                        "note",
                        "description",
                        "summary",
                        "reason",
                        "rationale",
                        "insight",
                    )
                    or ""
                ).strip(),
            }
        )
    return rows


def validate_profile_candidates(items: list[Any], max_count: int) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise SegmentProfileGenerationError("invalid_llm_output", "Profile output must be a list")
    seen_names: set[str] = set()
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(items[:max_count], start=1):
        if not isinstance(raw, dict):
            continue
        name = str(
            _first_non_empty(raw, "name", "profile_name", "profileName", "title") or ""
        ).strip()
        if not name:
            continue
        normalized = name.lower()
        if normalized in seen_names:
            continue
        seen_names.add(normalized)
        demographic = str(
            _first_non_empty(raw, "demographic", "persona", "profile", "description", "画像") or ""
        ).strip()
        need = str(
            _first_non_empty(raw, "need", "needs", "demand", "pain_point", "需求") or ""
        ).strip()
        if not demographic or not need:
            continue
        profile_id = (
            str(
                _first_non_empty(raw, "id", "code", "profile_id", "profileId")
                or f"P-DRAFT-{index:03d}"
            )
            .strip()
            .upper()
        )
        persona_source = _first_non_empty(raw, "persona_json", "personaJson", "persona")
        rows.append(
            {
                "id": profile_id,
                "code": str(
                    _first_non_empty(raw, "code", "id", "profile_id", "profileId") or profile_id
                )
                .strip()
                .upper(),
                "name": name,
                "demographic": demographic,
                "need": need,
                "weight": _normalize_profile_weight(raw.get("weight"), 1.0),
                "status": _profile_status(raw.get("status")),
                "persona_json": _coerce_persona_json(
                    persona_source, demographic=demographic, need=need
                ),
            }
        )
    if not rows:
        raise SegmentProfileGenerationError(
            "missing_llm_field", "No complete Profile drafts were returned"
        )
    return rows


# ---------------------------------------------------------------------------
# Async LLM service
# ---------------------------------------------------------------------------


class SegmentProfileGenerationService:
    """Async OpenAI-compatible Segment/Profile generation client.

    ``async generate_segments`` / ``async generate_profiles`` send one
    chat-completions request and return ``GenerationResult``. On
    LLM-side failure raises ``SegmentProfileGenerationError`` (the
    route handler maps this back to 502/503 via
    ``segment_profile_generation_status``).
    """

    def __init__(
        self,
        model: str | None = None,
        config: DoubaoConfig | None = None,
        allow_fallback: bool | None = None,
    ):
        self.model_override = (model or os.getenv("SEGMENT_PROFILE_LLM_MODEL") or "").strip()
        self.config = config
        self.allow_fallback = (
            allow_fallback
            if allow_fallback is not None
            else os.getenv("SEGMENT_PROFILE_LLM_ALLOW_FALLBACK", "0") == "1"
        )

    def _llm_config(self) -> DoubaoConfig:
        try:
            return self.config or load_doubao_config()
        except TopicPlanLLMError as error:
            raise SegmentProfileGenerationError(error.code, error.message) from error

    async def _call_llm_json(
        self, *, prompt: str, root_key: str, max_count: int
    ) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
        config = self._llm_config()
        model = self.model_override or getattr(config, "model", "")
        timeout_seconds = _bounded_count(
            os.getenv("SEGMENT_PROFILE_LLM_TIMEOUT_SECONDS") or 90, 90, 30, 240
        )
        max_tokens = _bounded_count(
            os.getenv("SEGMENT_PROFILE_LLM_MAX_TOKENS") or (1200 + max_count * 450),
            4096,
            800,
            8192,
        )
        url = config.base_url.rstrip("/") + "/chat/completions"
        body = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a precise data generator for an Admin "
                        "operations console. Output valid JSON only. Never "
                        "generate Query text here."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(url, json=body, headers=headers)
        except httpx.RequestError as error:
            raise SegmentProfileGenerationError(
                "llm_call_failed",
                "Segment/Profile LLM generation failed: " + str(error)[:500],
            ) from error

        if response.status_code != 200:
            raise SegmentProfileGenerationError(
                "llm_call_failed",
                f"Segment/Profile LLM generation failed: HTTP {response.status_code}",
            )
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise SegmentProfileGenerationError(
                "llm_call_failed", "Segment/Profile LLM returned no choices"
            )
        content = (choices[0].get("message") or {}).get("content") or "{}"
        parsed = _load_json_object(content)
        items = _extract_llm_items(parsed, root_key)
        return items, model, _usage_to_dict(data.get("usage"))

    async def generate_segments(
        self,
        *,
        brand_name: str,
        industry: str,
        count: int,
        status: str,
        positioning: str,
        product_id: str | int | None = None,
        product_name: str = "",
        product_category: str = "",
        product_description: str = "",
        products: list[dict[str, Any]] | None = None,
        goal: str = "",
        constraints: str = "",
    ) -> GenerationResult:
        count = _bounded_count(count, 6, 1, 20)
        status = status if status in {"active", "draft", "paused"} else "draft"
        product_contexts = _normalise_product_contexts(
            products,
            product_id=product_id,
            product_name=product_name,
            product_category=product_category,
            product_description=product_description,
        )
        payload = {
            "brand_name": brand_name,
            "industry": industry,
            "count": count,
            "status": status,
            "positioning": positioning,
            "product_scope": "selected_products" if product_contexts else "brand",
            "product": product_contexts[0] if len(product_contexts) == 1 else {},
            "products": product_contexts,
            "generation_goal": (
                "生成可进入 Query Pool 采样的客户/用户/采购决策 Segment。如果 products 非空，"
                "必须围绕所选产品分别生成有差异的 Segment；如果 products 为空，则基于品牌整体生成。"
                "覆盖核心高意向客户、预算/采购决策者、技术/安全评估者、竞品替换者、"
                "风险/合规关注者和新客教育人群。"
            ),
            "generation_constraints": (
                "每个 Segment 必须与所选品牌、行业和产品上下文强相关，写清采样边界、触发场景、"
                "决策关注点和排除口径；Segment 名称不得空泛，不得重复；禁止生成与行业或产品无关的"
                "美妆、护肤、香氛、礼赠等内容。"
            ),
        }
        prompt = _json_prompt(
            "generate_segments",
            payload,
            {
                "segments": [
                    {
                        "id": "SEG-CODE",
                        "name": "string",
                        "industry": "string",
                        "status": "draft|active|paused",
                        "weight": 0.15,
                        "age_range": "string",
                        "income": "string",
                        "regions": "string",
                        "sampling_rate": "string",
                        "note": "string",
                    }
                ]
            },
        )
        try:
            raw_items, model, usage = await self._call_llm_json(
                prompt=prompt, root_key="segments", max_count=count
            )
            return GenerationResult(
                items=validate_segment_candidates(raw_items, count),
                model=model,
                prompt=prompt,
                usage=usage,
                estimated_cost=None,
            )
        except SegmentProfileGenerationError as error:
            if not _should_fallback_generation(error, self.allow_fallback):
                raise
        return self._fallback_segments(
            brand_name=brand_name,
            industry=industry,
            product_names=[item.get("product_name", "") for item in product_contexts],
            count=count,
            status=status,
            prompt=prompt,
        )

    def _fallback_segments(
        self,
        *,
        brand_name: str,
        industry: str,
        count: int,
        status: str,
        prompt: str,
        product_names: list[str] | None = None,
    ) -> GenerationResult:
        """Deterministic fallback used only when ``allow_fallback`` is set
        — admin_console has the same opt-in path for ops dry-runs."""
        brand = (brand_name or "Brand").strip() or "Brand"
        industry_name = (industry or "General").strip() or "General"
        product_labels = [name.strip() for name in product_names or [] if name.strip()]
        product_label = " / ".join(product_labels[:3])
        subject = f"{brand} {product_label}".strip() if product_label else brand
        brand_slug = _slug(f"{brand}-{product_label}" if product_label else brand, "brand").upper()
        archetypes = [
            (
                "核心高意向评估者",
                "企业决策团队",
                "中高预算",
                "一线/新一线及重点行业城市",
                "32%",
                f"正在评估 {industry_name} 方案，并需要判断 {subject} 是否匹配当前业务问题。",
            ),
            (
                "技术验证与集成评估者",
                "技术/安全团队",
                "中高预算",
                "重点行业客户",
                "24%",
                f"关注 {subject} 在 {industry_name} 场景下的能力边界、集成成本和验证证据。",
            ),
            (
                "预算与采购决策者",
                "采购/财务负责人",
                "中等预算",
                "全国企业客户",
                "18%",
                f"比较 {subject} 的采购成本、合同条件、服务范围和落地风险。",
            ),
            (
                "风险与合规关注者",
                "法务/合规/风控团队",
                "中高预算",
                "监管敏感行业",
                "16%",
                f"重点确认 {subject} 是否满足 {industry_name} 相关合规、审计和风险控制要求。",
            ),
            (
                "竞品替换评估者",
                "存量系统负责人",
                "中高预算",
                "重点城市/重点行业",
                "14%",
                f"已有替代方案或竞品系统，正在判断切换到 {subject} 的收益、成本和迁移风险。",
            ),
            (
                "新场景教育人群",
                "业务/数字化团队",
                "中等预算",
                "一线至二线城市",
                "12%",
                f"刚开始理解 {industry_name} 需求，需要低门槛材料解释 {subject} 的使用场景和价值。",
            ),
            (
                "存量扩容升级用户",
                "现有客户团队",
                "高预算",
                "存量客户区域",
                "10%",
                f"已使用 {subject} 或同类能力，关注扩容、升级、续约和长期服务稳定性。",
            ),
            (
                "谨慎验证型评审者",
                "跨部门评审团队",
                "中高预算",
                "重点行业城市",
                "8%",
                f"会系统排查 {subject} 在 {industry_name} 场景下的负面反馈、适配风险和服务承诺。",
            ),
        ]
        items: list[dict[str, Any]] = []
        for index in range(count):
            title, age, income, regions, sampling, note = archetypes[index % len(archetypes)]
            items.append(
                {
                    "id": f"SEG-{brand_slug}-{index + 1:03d}",
                    "name": f"{subject} - {title}",
                    "industry": industry_name,
                    "status": status,
                    "weight": max(0.05, round(0.30 - index * 0.02, 2)),
                    "age_range": age,
                    "income": income,
                    "regions": regions,
                    "sampling_rate": sampling,
                    "note": note,
                }
            )
        return GenerationResult(
            items=validate_segment_candidates(items, count),
            model="fallback-segment-profile-v1",
            prompt=prompt,
            usage={"total_tokens": 0, "source": "deterministic_fallback"},
            estimated_cost=0.0,
        )

    async def generate_profiles(
        self,
        *,
        segment: dict[str, Any],
        brand_name: str,
        count: int,
        goal: str,
        constraints: str,
        products: list[dict[str, Any]] | None = None,
    ) -> GenerationResult:
        """Generate Profile drafts for one Segment (LLM single-shot).

        Mirrors admin_console.SegmentProfileGenerationService.generate_profiles
        line-for-line; the only difference is ``_call_llm_json`` is async
        + httpx instead of sync OpenAI SDK.
        """
        count = _bounded_count(count, 6, 1, 50)
        product_contexts = _normalise_product_contexts(products)
        payload = {
            "segment": segment,
            "brand_name": brand_name,
            "count": count,
            "goal": goal,
            "constraints": constraints,
            "product_scope": "selected_products" if product_contexts else "brand",
            "products": product_contexts,
        }
        prompt = _json_prompt(
            "generate_profiles",
            payload,
            {
                "profiles": [
                    {
                        "id": "P-CODE",
                        "name": "string",
                        "demographic": "string",
                        "need": "string",
                        "weight": 1.0,
                        "status": "draft|active|paused",
                        "persona_json": {},
                    }
                ]
            },
        )
        try:
            raw_items, model, usage = await self._call_llm_json(
                prompt=prompt, root_key="profiles", max_count=count
            )
            return GenerationResult(
                items=validate_profile_candidates(raw_items, count),
                model=model,
                prompt=prompt,
                usage=usage,
                estimated_cost=None,
            )
        except SegmentProfileGenerationError as error:
            if not _should_fallback_generation(error, self.allow_fallback):
                raise
        return self._fallback_profiles(
            segment=segment,
            brand_name=brand_name,
            count=count,
            prompt=prompt,
            product_names=[item.get("product_name", "") for item in product_contexts],
        )

    def _fallback_profiles(
        self,
        *,
        segment: dict[str, Any],
        brand_name: str,
        count: int,
        prompt: str,
        product_names: list[str] | None = None,
    ) -> GenerationResult:
        """Deterministic fallback used only when ``allow_fallback`` is set."""
        segment_id = str(segment.get("id") or segment.get("code") or "SEG").upper()
        suffix = re.sub(r"[^A-Z0-9]+", "-", segment_id).strip("-")[-18:] or "SEG"
        brand = (brand_name or "Brand").strip() or "Brand"
        product_labels = [name.strip() for name in product_names or [] if name.strip()]
        product_label = " / ".join(product_labels[:3])
        subject = f"{brand} {product_label}".strip() if product_label else brand
        base_demo = " / ".join(
            value
            for value in [
                str(segment.get("age_range") or segment.get("ageRange") or "").strip(),
                str(segment.get("income") or "").strip(),
                str(segment.get("regions") or "").strip(),
            ]
            if value
        ) or str(segment.get("name") or "Segment")
        archetypes = [
            ("Evidence seeker", "Needs proof, comparisons, expert backing, and real reviews."),
            (
                "Promotion optimizer",
                "Compares bundles, official channels, discounts, and final price.",
            ),
            (
                "Scenario buyer",
                "Frames the question around a concrete occasion and risk of mismatch.",
            ),
            (
                "Competitor comparer",
                "Needs a direct standard for comparing substitutes and trade-offs.",
            ),
            ("Repeat buyer", "Cares about long-term experience, availability, and upgrade value."),
            ("First-time buyer", "Needs a simple buying path and beginner-friendly explanation."),
            ("Risk checker", "Looks for downsides, after-sales risk, and negative feedback."),
            (
                "Channel verifier",
                "Needs trusted source, authenticity, and purchase-channel guidance.",
            ),
        ]
        items: list[dict[str, Any]] = []
        for index in range(count):
            title, need = archetypes[index % len(archetypes)]
            items.append(
                {
                    "id": f"P-{suffix}-{index + 1:02d}",
                    "name": title,
                    "demographic": base_demo,
                    "need": f"{subject}: {need}",
                    "weight": min(1.0, round(0.8 + (index % 5) * 0.05, 2)),
                    "status": "draft",
                    "persona_json": {
                        "segment_id": segment_id,
                        "brand": brand,
                        "products": product_labels,
                        "archetype": title,
                    },
                }
            )
        return GenerationResult(
            items=validate_profile_candidates(items, count),
            model="fallback-segment-profile-v1",
            prompt=prompt,
            usage={"total_tokens": 0, "source": "deterministic_fallback"},
            estimated_cost=0.0,
        )


def segment_profile_generation_status(error: SegmentProfileGenerationError) -> int:
    """Map LLM error code → HTTP status. 503 for upstream / config issues
    (operator can retry); 502 for schema / validation failures (input
    needs reshaping)."""
    return (
        503
        if error.code in {"llm_config_missing", "llm_client_unavailable", "llm_call_failed"}
        else 502
    )


def drafts_with_brand_context(
    items: list[dict[str, Any]] | None,
    *,
    brand_id: str | None = None,
    brand_name: str = "",
    segment_id: str | None = None,
) -> list[dict[str, Any]]:
    """Annotate LLM drafts with the brand context the operator selected
    so the SPA can render brand-aware preview without re-fetching."""
    drafts: list[dict[str, Any]] = []
    for item in items or []:
        draft = dict(item or {})
        if segment_id is not None:
            draft.setdefault("segment_id", str(segment_id).strip().upper())
        draft["brand_id"] = draft.get("brand_id") or brand_id
        draft["brand_name"] = draft.get("brand_name") or draft.get("brandName") or brand_name or ""
        drafts.append(draft)
    return drafts
