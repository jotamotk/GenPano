"""Brand Management LLM generation boundary for the Admin console.

Provides reviewable brand drafts that can be created either:
1. Automatically from an industry seed (LLM-generated)
2. Manually via the CRUD form

Drafts are returned without writing to the database — the caller decides whether
to persist them. The schema is intentionally aligned with the legacy ``brands``
table (id, name, industry, target_market, description, aliases) plus the
``kg_brands`` columns (name_zh, name_en, official_domains, group_id, status) so
that approved brands are trivial to project as nodes in the industry knowledge
graph. ``competitors`` (peer brand suggestions) double as candidate
``kg_brand_relations`` edges of type COMPETES_WITH.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from typing import Any, Iterable

try:
    from json_repair import repair_json
except Exception:  # pragma: no cover - optional dependency
    repair_json = None

try:
    from .topic_plan import TopicPlanLLMError, load_doubao_config
except ImportError:  # pragma: no cover - script import fallback
    from topic_plan import TopicPlanLLMError, load_doubao_config


ALLOWED_BRAND_STATUSES = ("active", "draft", "archived", "pending")
ALLOWED_BRAND_SOURCES = ("manual", "llm", "import")
ALLOWED_RELATION_TYPES = ("COMPETES_WITH", "SAME_GROUP")


class BrandManagementError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class BrandGenerationResult:
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


def _strip_markdown_fence(raw: str) -> str:
    text = (raw or "").strip()
    if not text.startswith("```"):
        return text
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _load_json_object(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    cleaned = _strip_markdown_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except Exception as first_error:
        if repair_json is None:
            raise BrandManagementError("llm_json_invalid", "LLM returned invalid JSON") from first_error
        try:
            parsed = json.loads(repair_json(cleaned))
        except Exception as repair_error:
            raise BrandManagementError("llm_json_invalid", "LLM returned invalid JSON") from repair_error
    if not isinstance(parsed, dict):
        raise BrandManagementError("llm_schema_invalid", "LLM JSON root must be an object")
    return parsed


def _usage_to_dict(usage_obj: Any) -> dict[str, Any]:
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


def _coerce_str_list(value: Any, *, max_items: int = 16, max_len: int = 128) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                value = parsed
            else:
                value = [s.strip() for s in re.split(r"[,;\n]", value) if s.strip()]
        except Exception:
            value = [s.strip() for s in re.split(r"[,;\n]", value) if s.strip()]
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item).strip()[:max_len]
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= max_items:
            break
    return out


def _normalize_brand_status(value: Any, default: str = "draft") -> str:
    text = str(value or default).strip().lower()
    aliases = {
        "approved": "active",
        "enabled": "active",
        "live": "active",
        "启用": "active",
        "已启用": "active",
        "草稿": "draft",
        "待审核": "pending",
        "审核中": "pending",
        "归档": "archived",
        "下线": "archived",
    }
    text = aliases.get(text, text)
    return text if text in ALLOWED_BRAND_STATUSES else default


def _normalize_brand_source(value: Any, default: str = "manual") -> str:
    text = str(value or default).strip().lower()
    return text if text in ALLOWED_BRAND_SOURCES else default


def _normalize_relation_type(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    aliases = {
        "COMPETITOR": "COMPETES_WITH",
        "COMPETES": "COMPETES_WITH",
        "RIVAL": "COMPETES_WITH",
        "SAME-GROUP": "SAME_GROUP",
        "SAME_GROUP": "SAME_GROUP",
        "GROUP": "SAME_GROUP",
        "PARENT": "SAME_GROUP",
    }
    text = aliases.get(text, text)
    return text if text in ALLOWED_RELATION_TYPES else None


def _normalize_competitors(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = [v.strip() for v in re.split(r"[,;\n]", value) if v.strip()]
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in value:
        if isinstance(entry, str):
            name = entry.strip()
            if not name:
                continue
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append({"name": name[:256], "type": "COMPETES_WITH", "note": ""})
        elif isinstance(entry, dict):
            name = str(entry.get("name") or entry.get("brand") or "").strip()
            if not name:
                continue
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            relation = _normalize_relation_type(entry.get("type") or entry.get("relation")) or "COMPETES_WITH"
            note = str(entry.get("note") or entry.get("reason") or "").strip()[:512]
            out.append({"name": name[:256], "type": relation, "note": note})
        if len(out) >= 16:
            break
    return out


def normalize_brand_draft(raw: dict[str, Any], *, default_industry: str = "") -> dict[str, Any]:
    """Coerce a single brand-shaped dict into the canonical draft schema."""
    if not isinstance(raw, dict):
        raise BrandManagementError("invalid_brand_payload", "Brand entry must be a JSON object")

    def first(*keys: str, default: Any = "") -> Any:
        for key in keys:
            if key in raw and raw.get(key) not in (None, ""):
                return raw.get(key)
        return default

    name = str(first("name", "primary_name", "brand", "brand_name") or "").strip()
    if not name:
        raise BrandManagementError("missing_brand_name", "Brand name is required")

    name_zh = str(first("name_zh", "zh", "chinese_name", "中文名") or "").strip()
    name_en = str(first("name_en", "en", "english_name", "english") or "").strip()
    industry = str(first("industry", "industry_name", "行业") or default_industry or "").strip()
    target_market = str(first("target_market", "market", "region") or "").strip()
    description = str(first("description", "summary", "intro", "简介") or "").strip()
    positioning = str(first("positioning", "tagline", "定位") or "").strip()
    headquarters = str(first("headquarters", "hq", "总部") or "").strip()
    founded_year_raw = first("founded_year", "founded", "year", "成立年份")
    try:
        founded_year = int(founded_year_raw) if founded_year_raw not in (None, "") else None
    except (TypeError, ValueError):
        founded_year = None
    if founded_year is not None and (founded_year < 1500 or founded_year > 2100):
        founded_year = None

    aliases = _coerce_str_list(first("aliases", "alias", "synonyms", "别名"))
    official_domains = _coerce_str_list(first("official_domains", "domains", "website", "url"), max_items=8, max_len=255)
    competitors = _normalize_competitors(first("competitors", "rivals", "peers", "relations"))
    tags = _coerce_str_list(first("tags", "labels", "标签"), max_items=10, max_len=64)

    status = _normalize_brand_status(first("status", default="draft"))
    source = _normalize_brand_source(first("source", default="manual"))

    return {
        "name": name[:256],
        "name_zh": name_zh[:256] or None,
        "name_en": name_en[:256] or None,
        "industry": industry[:128],
        "target_market": target_market[:128],
        "description": description[:2000],
        "positioning": positioning[:512],
        "headquarters": headquarters[:128],
        "founded_year": founded_year,
        "aliases": aliases,
        "official_domains": official_domains,
        "competitors": competitors,
        "tags": tags,
        "status": status,
        "source": source,
    }


def validate_brand_candidates(items: Iterable[Any], max_count: int) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise BrandManagementError("invalid_llm_output", "Brand output must be a list")
    seen_names: set[str] = set()
    drafts: list[dict[str, Any]] = []
    for raw in items[:max_count]:
        try:
            draft = normalize_brand_draft(raw)
        except BrandManagementError:
            continue
        key = (draft["name"] or "").casefold()
        if not key or key in seen_names:
            continue
        seen_names.add(key)
        draft["source"] = "llm"
        drafts.append(draft)
    if not drafts:
        raise BrandManagementError("missing_llm_field", "No usable brand drafts were returned")
    return drafts


def _json_prompt(task: str, payload: dict[str, Any], schema_hint: dict[str, Any]) -> str:
    return (
        "You are generating Admin-reviewed Brand drafts for the GENPANO knowledge graph.\n"
        "Return only strict JSON. Do not include markdown, comments, prose, or code fences.\n"
        "Validate all required fields, keep requested count or fewer, avoid duplicate names, "
        "and prefer real, commercially significant brands in the requested industry/region.\n"
        "Each brand must be a verifiable, commonly recognized company so it can be added as a "
        "node in the industry knowledge graph. Suggested competitors will be projected as "
        "COMPETES_WITH edges, so list 1-4 well-known peers.\n"
        f"Task: {task}\n"
        f"Input: {json.dumps(payload, ensure_ascii=False, sort_keys=True)}\n"
        f"Output schema: {json.dumps(schema_hint, ensure_ascii=False, sort_keys=True)}"
    )


def _brand_schema_hint() -> dict[str, Any]:
    return {
        "brands": [
            {
                "name": "string (primary brand name, English by default)",
                "name_zh": "中文名 or null",
                "name_en": "English name or null",
                "industry": "string",
                "target_market": "string (e.g. global / china / EU)",
                "description": "string (2-4 sentences)",
                "positioning": "string (one sentence)",
                "headquarters": "string",
                "founded_year": 1990,
                "aliases": ["string"],
                "official_domains": ["example.com"],
                "tags": ["string"],
                "competitors": [
                    {
                        "name": "string (peer brand)",
                        "type": "COMPETES_WITH | SAME_GROUP",
                        "note": "string",
                    }
                ],
                "status": "draft|active|pending|archived",
            }
        ]
    }


class BrandManagementService:
    """OpenAI-compatible Brand draft generation client.

    Mirrors :class:`SegmentProfileGenerationService` semantics: a single
    ``generate_brands`` entry point that returns reviewable drafts, using
    the project's Doubao/Ark configuration. When LLM generation fails and
    ``allow_fallback`` is enabled (default in tests / dev), a deterministic
    archetype-based fallback is used so the UI still receives drafts.
    """

    def __init__(
        self,
        model: str | None = None,
        config: Any | None = None,
        allow_fallback: bool | None = None,
    ):
        self.model_override = (model or os.getenv("BRAND_MANAGEMENT_LLM_MODEL") or "").strip()
        self.config = config
        self.allow_fallback = (
            allow_fallback
            if allow_fallback is not None
            else os.getenv("BRAND_MANAGEMENT_LLM_ALLOW_FALLBACK", "0") == "1"
        )

    def _llm_config(self) -> Any:
        try:
            return self.config or load_doubao_config()
        except TopicPlanLLMError as error:
            raise BrandManagementError(error.code, error.message) from error

    def _call_llm_json(
        self, *, prompt: str, root_key: str, max_count: int
    ) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
        try:
            from openai import OpenAI
        except Exception as error:  # pragma: no cover - environment dependent
            raise BrandManagementError(
                "llm_client_unavailable",
                "OpenAI-compatible client is unavailable",
            ) from error

        config = self._llm_config()
        model = self.model_override or getattr(config, "model", "")
        timeout_seconds = _bounded_count(
            os.getenv("BRAND_MANAGEMENT_LLM_TIMEOUT_SECONDS")
            or getattr(config, "timeout", None)
            or 90,
            90,
            30,
            240,
        )
        max_tokens = _bounded_count(
            os.getenv("BRAND_MANAGEMENT_LLM_MAX_TOKENS")
            or (1500 + max_count * 480),
            5120,
            800,
            8192,
        )
        client = OpenAI(
            api_key=getattr(config, "api_key", ""),
            base_url=getattr(config, "base_url", ""),
            timeout=timeout_seconds,
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a precise data generator for an Admin operations console. "
                    "Output valid JSON only. Never invent fictional brands."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,
                max_tokens=max_tokens,
                timeout=timeout_seconds,
            )
        except Exception as error:
            detail = str(error).strip()
            message = "Brand management LLM generation failed"
            if detail:
                message += ": " + detail[:500]
            raise BrandManagementError("llm_call_failed", message) from error

        content = response.choices[0].message.content or "{}"
        data = _load_json_object(content)
        items = data.get(root_key)
        if not isinstance(items, list):
            raise BrandManagementError(
                "llm_schema_invalid", f"LLM JSON must contain a {root_key} array"
            )
        return items, model, _usage_to_dict(getattr(response, "usage", None))

    def generate_brands(
        self,
        *,
        industry: str,
        count: int,
        region: str = "",
        positioning: str = "",
        seed_brands: list[str] | None = None,
        constraints: str = "",
        language: str = "auto",
    ) -> BrandGenerationResult:
        """Generate brand drafts for an industry.

        ``seed_brands`` lists already-known brands the LLM should avoid duplicating.
        ``language`` is a soft hint: ``auto``, ``zh-CN``, ``en-US``, ``mixed``.
        """
        industry = (industry or "").strip()
        if not industry:
            raise BrandManagementError("missing_industry", "industry is required")
        count = _bounded_count(count, 8, 1, 30)
        seeds = _coerce_str_list(seed_brands or [], max_items=64, max_len=256)
        payload = {
            "industry": industry,
            "count": count,
            "region": (region or "").strip(),
            "positioning": (positioning or "").strip(),
            "constraints": (constraints or "").strip(),
            "language": (language or "auto").strip().lower(),
            "exclude_brands": seeds,
        }
        prompt = _json_prompt("generate_brands", payload, _brand_schema_hint())
        try:
            raw_items, model, usage = self._call_llm_json(
                prompt=prompt, root_key="brands", max_count=count
            )
            drafts = validate_brand_candidates(raw_items, count)
            for draft in drafts:
                if not draft.get("industry"):
                    draft["industry"] = industry
            return BrandGenerationResult(
                items=drafts,
                model=model,
                prompt=prompt,
                usage=usage,
                estimated_cost=None,
            )
        except BrandManagementError:
            if not self.allow_fallback:
                raise
        return self._fallback_brands(
            industry=industry,
            count=count,
            region=(region or "").strip(),
            seeds=seeds,
            prompt=prompt,
        )

    def _fallback_brands(
        self,
        *,
        industry: str,
        count: int,
        region: str,
        seeds: list[str],
        prompt: str,
    ) -> BrandGenerationResult:
        """Deterministic placeholder used when LLM is unavailable."""
        archetypes = [
            ("Heritage Leader", "Established global benchmark player.", "global"),
            ("Premium Challenger", "Premium-priced challenger with design focus.", "global"),
            ("Mass Market Leader", "Mass-market volume leader with deep distribution.", "global"),
            ("DTC Disruptor", "Digitally native direct-to-consumer disruptor.", "global"),
            ("Regional Champion", "Strong presence in core regional market.", region or "regional"),
            ("Value Specialist", "Value-tier specialist with sharp pricing.", "global"),
            ("Niche Specialist", "Niche category specialist with cult following.", "global"),
            ("Tech-First Entrant", "Tech-driven new entrant with platform play.", "global"),
        ]
        existing = {seed.casefold() for seed in seeds}
        items: list[dict[str, Any]] = []
        for index in range(count):
            archetype, summary, market = archetypes[index % len(archetypes)]
            base_name = f"{industry.title()} {archetype}"
            counter = 1
            candidate = base_name
            while candidate.casefold() in existing:
                counter += 1
                candidate = f"{base_name} {counter}"
            existing.add(candidate.casefold())
            items.append(
                {
                    "name": candidate,
                    "name_zh": None,
                    "name_en": candidate,
                    "industry": industry,
                    "target_market": region or market,
                    "description": f"{summary} Auto-generated fallback for {industry}.",
                    "positioning": archetype,
                    "headquarters": "",
                    "founded_year": None,
                    "aliases": [],
                    "official_domains": [],
                    "competitors": [],
                    "tags": [archetype.lower().replace(" ", "-")],
                    "status": "draft",
                    "source": "llm",
                }
            )
        drafts = validate_brand_candidates(items, count)
        return BrandGenerationResult(
            items=drafts,
            model="fallback-brand-management-v1",
            prompt=prompt,
            usage={"total_tokens": 0, "source": "deterministic_fallback"},
            estimated_cost=0.0,
        )


def brand_to_kg_payload(draft: dict[str, Any], brand_id: int) -> dict[str, Any]:
    """Project a brand draft into the kg_brands row shape.

    The mapping is intentionally minimal so a brand record can be turned into
    a knowledge-graph node in one statement, and ``competitors`` into edges.
    """
    return {
        "brand_id": brand_id,
        "primary_name": draft.get("name"),
        "name_zh": draft.get("name_zh"),
        "name_en": draft.get("name_en"),
        "industry_id": None,
        "aliases": draft.get("aliases") or [],
        "official_domains": draft.get("official_domains") or [],
        "status": "approved" if draft.get("status") == "active" else "pending",
    }
