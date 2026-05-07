"""Pure (no-DB) Brand Management helpers — Phase 7 slice 7a.

Vendored from admin_console/brand_management.py (constants, normalizers,
validators). Used by both CRUD routes (slice 7a) and the LLM generate /
enrich routes (slice 7a-bis).
"""

from __future__ import annotations

import json
import re
from typing import Any

ALLOWED_BRAND_STATUSES = ("active", "draft", "archived", "pending")
ALLOWED_BRAND_SOURCES = ("manual", "llm", "import")
ALLOWED_RELATION_TYPES = ("COMPETES_WITH", "SAME_GROUP")


class BrandManagementError(Exception):
    """Coded validation error returned to the API layer."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def coerce_str_list(value: Any, *, max_items: int = 16, max_len: int = 128) -> list[str]:
    """Accept JSON list / comma-separated / newline-separated strings;
    dedupe (case-insensitive) and cap to ``max_items``.
    """
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


def normalize_competitors(value: Any) -> list[dict[str, Any]]:
    """Coerce a competitors list (strings / dicts / JSON / CSV-string)
    into a normalized list of ``{name, type, note}`` records."""
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
            relation = (
                _normalize_relation_type(entry.get("type") or entry.get("relation"))
                or "COMPETES_WITH"
            )
            note = str(entry.get("note") or entry.get("reason") or "").strip()[:512]
            out.append({"name": name[:256], "type": relation, "note": note})
    return out


def normalize_brand_draft(raw: dict[str, Any], *, default_industry: str = "") -> dict[str, Any]:
    """Coerce a single brand-shaped dict into the canonical draft schema.

    Raises ``BrandManagementError`` for an invalid payload (must be a
    dict) or missing brand name. Caps long string fields and clamps
    ``founded_year`` to plausible bounds.
    """
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
        founded_year: int | None = (
            int(founded_year_raw) if founded_year_raw not in (None, "") else None
        )
    except (TypeError, ValueError):
        founded_year = None
    if founded_year is not None and (founded_year < 1500 or founded_year > 2100):
        founded_year = None

    aliases = coerce_str_list(first("aliases", "alias", "synonyms", "别名"))
    official_domains = coerce_str_list(
        first("official_domains", "domains", "website", "url"),
        max_items=8,
        max_len=255,
    )
    competitors = normalize_competitors(first("competitors", "rivals", "peers", "relations"))
    tags = coerce_str_list(first("tags", "labels", "标签"), max_items=10, max_len=64)

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


def normalize_brand_source_input(value: Any) -> str:
    """Trim a free-form source value, return ``""`` if invalid."""
    text = str(value or "").strip().lower()
    return text if text in ALLOWED_BRAND_SOURCES else ""


def brand_management_status_for_error(error: BrandManagementError) -> int:
    """Map a BrandManagementError code → HTTP status."""
    code = str(error.code or "")
    if code.startswith("llm_") or code in {"missing_llm_field", "invalid_llm_output"}:
        return 503
    if code in {"missing_industry", "missing_brand_name", "invalid_brand_payload"}:
        return 400
    return 500
