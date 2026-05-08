"""Pure helpers for the admin/hot_topics package (Phase 8 slice 8b).

Stateless validation + normalization. No DB / no httpx. Tested in
isolation by ``tests/test_phase_8b_admin_hot_topics.py``.

Public:
- ``HOT_TOPIC_STATUSES`` / ``HOT_TOPIC_BATCH_ACTIONS`` — allowed values.
- ``HotTopicValidationError`` — coded validation error.
- ``parse_create_payload(payload)`` — POST /hot-topics body validator.
- ``parse_update_payload(payload)`` — PUT /hot-topics/{id} body validator.
- ``parse_batch_payload(payload)`` — POST /hot-topics/batch validator.
- ``parse_collect_payload(payload)`` — POST /hot-topics/collect normalizer.
- ``hot_topic_row_to_dict(row)`` — admin_console-compat wire shape.
"""

from __future__ import annotations

from typing import Any

HOT_TOPIC_STATUSES = ("draft", "active", "expired", "rejected")
HOT_TOPIC_CREATE_STATUSES = ("draft", "active")
HOT_TOPIC_BATCH_ACTIONS = ("status", "industry", "brand", "delete")

# Browser-source collectors live in geo_tracker; the lightweight ones
# (baidu / zhihu / llm_search) live in admin_console.hotspot_collectors.
HOT_TOPIC_BROWSER_SOURCES = frozenset({"douyin", "xhs"})
HOT_TOPIC_SOURCE_ALIASES = {
    "xiaohongshu": "xhs",
    "red": "xhs",
    "xiaohongshu_hots": "xhs",
}


class HotTopicValidationError(Exception):
    """Coded validation error returned to the API layer (HTTP 400)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _coerce_int(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise HotTopicValidationError("invalid_brand_id", "brand_id must be an integer") from None


def _normalize_status_field(
    raw: Any, allowed: tuple[str, ...], code: str = "invalid_status"
) -> str:
    text = str(raw or "").strip().lower()
    if text not in allowed:
        raise HotTopicValidationError(code, f"status must be one of {sorted(allowed)}")
    return text


def _bounded_int(raw: Any, default: int, lo: int, hi: int) -> int:
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(n, hi))


def parse_create_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Validate POST /api/admin/hot-topics body."""
    payload = payload or {}
    title = str(payload.get("title") or "").strip()
    if not title:
        raise HotTopicValidationError("title_required", "title is required")
    summary = str(payload.get("summary") or "").strip() or None
    category = str(payload.get("category") or "").strip() or None
    industry = str(payload.get("industry") or "").strip() or None
    source = str(payload.get("source") or "manual").strip().lower() or "manual"
    brand_id = _coerce_int(payload.get("brand_id"))
    days = _bounded_int(payload.get("effective_days") or 14, 14, 1, 90)
    status_default = "active" if source == "manual" else "draft"
    raw_status = str(payload.get("status") or status_default).strip().lower()
    if raw_status not in HOT_TOPIC_CREATE_STATUSES:
        raw_status = "active"
    return {
        "title": title[:512],
        "summary": summary,
        "category": category,
        "industry": industry,
        "source": source,
        "brand_id": brand_id,
        "effective_days": days,
        "status": raw_status,
    }


def parse_update_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Sparse `{column: value}` mapping for PUT /hot-topics/{id}.

    The ``effective_until`` column is computed from ``effective_days``
    via SQL ``NOW() + INTERVAL`` in the db layer — we surface only the
    raw integer here so the helper stays SQL-free."""
    payload = payload or {}
    out: dict[str, Any] = {}
    if "title" in payload:
        title = str(payload.get("title") or "").strip()
        if not title:
            raise HotTopicValidationError("title_required", "title is required")
        out["title"] = title[:512]
    for key in ("summary", "category", "industry", "source_url"):
        if key in payload:
            out[key] = str(payload.get(key) or "").strip() or None
    if "brand_id" in payload:
        out["brand_id"] = _coerce_int(payload.get("brand_id"))
    if "status" in payload:
        out["status"] = _normalize_status_field(payload.get("status"), HOT_TOPIC_STATUSES)
    if "effective_days" in payload:
        raw_days = payload.get("effective_days")
        try:
            d = int(raw_days) if raw_days is not None else 0
        except (TypeError, ValueError) as error:
            raise HotTopicValidationError(
                "invalid_effective_days", "effective_days must be 1-90"
            ) from error
        if d < 1 or d > 90:
            raise HotTopicValidationError("invalid_effective_days", "effective_days must be 1-90")
        out["effective_days"] = d
    return out


def parse_batch_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """POST /api/admin/hot-topics/batch validator.

    Returns ``{ids, action, status?, industry?, brand_id?}``. Raises
    ``HotTopicValidationError`` for missing ids / invalid action / status.
    """
    payload = payload or {}
    raw_ids = payload.get("ids") or []
    if not isinstance(raw_ids, list):
        raw_ids = []
    ids: list[int] = []
    for value in raw_ids:
        try:
            hot_id = int(value)
        except (TypeError, ValueError):
            continue
        if hot_id > 0 and hot_id not in ids:
            ids.append(hot_id)
    ids = ids[:500]
    if not ids:
        raise HotTopicValidationError("ids_required", "ids must be a non-empty list")
    action = str(payload.get("action") or "").strip().lower()
    if action not in HOT_TOPIC_BATCH_ACTIONS:
        raise HotTopicValidationError(
            "invalid_action", f"action must be one of {sorted(HOT_TOPIC_BATCH_ACTIONS)}"
        )
    out: dict[str, Any] = {"ids": ids, "action": action}
    if action == "status":
        out["status"] = _normalize_status_field(payload.get("status"), HOT_TOPIC_STATUSES)
    elif action == "industry":
        industry = str(payload.get("industry") or "").strip() or None
        out["industry"] = industry
    elif action == "brand":
        out["brand_id"] = _coerce_int(payload.get("brand_id"))
    return out


def parse_collect_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize POST /api/admin/hot-topics/collect body.

    Returns ``{sources, browser_sources, local_sources, industry,
    brand_id}``. Source aliases (xiaohongshu → xhs) are applied here so
    downstream code only sees canonical names.
    """
    payload = payload or {}
    sources_raw = payload.get("sources") or ["baidu", "zhihu", "llm_search"]
    if isinstance(sources_raw, str):
        raw_iter = [s.strip() for s in sources_raw.split(",") if s.strip()]
    elif isinstance(sources_raw, list):
        raw_iter = [str(s).strip() for s in sources_raw if str(s).strip()]
    else:
        raw_iter = []
    sources = [HOT_TOPIC_SOURCE_ALIASES.get(s.lower(), s.lower()) for s in raw_iter]
    # Dedupe but preserve order.
    seen: set[str] = set()
    deduped: list[str] = []
    for src in sources:
        if src and src not in seen:
            seen.add(src)
            deduped.append(src)
    sources = deduped
    browser_sources = [s for s in sources if s in HOT_TOPIC_BROWSER_SOURCES]
    local_sources = [s for s in sources if s not in HOT_TOPIC_BROWSER_SOURCES]
    industry = str(payload.get("industry") or "").strip() or None
    brand_id = _coerce_int(payload.get("brand_id"))
    return {
        "sources": sources,
        "browser_sources": browser_sources,
        "local_sources": local_sources,
        "industry": industry,
        "brand_id": brand_id,
    }


def hot_topic_row_to_dict(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Wire shape mirror of admin_console ``_hot_topic_row``."""
    if not row:
        return None
    effective_from = row.get("effective_from")
    effective_until = row.get("effective_until")
    created_at = row.get("created_at")
    updated_at = row.get("updated_at")
    return {
        "id": row.get("id"),
        "title": row.get("title"),
        "summary": row.get("summary") or "",
        "category": row.get("category") or "",
        "source": row.get("source") or "manual",
        "source_url": row.get("source_url") or "",
        "raw_rank": row.get("raw_rank"),
        "raw_metric": row.get("raw_metric") or "",
        "industry": row.get("industry") or "",
        "brand_id": row.get("brand_id"),
        "brand_name": row.get("brand_name"),
        "effective_from": (
            effective_from.isoformat()
            if effective_from is not None and hasattr(effective_from, "isoformat")
            else None
        ),
        "effective_until": (
            effective_until.isoformat()
            if effective_until is not None and hasattr(effective_until, "isoformat")
            else None
        ),
        "status": row.get("status") or "active",
        "days_remaining": row.get("days_remaining"),
        "created_at": (
            created_at.isoformat()
            if created_at is not None and hasattr(created_at, "isoformat")
            else None
        ),
        "updated_at": (
            updated_at.isoformat()
            if updated_at is not None and hasattr(updated_at, "isoformat")
            else None
        ),
    }


__all__ = [
    "HOT_TOPIC_BATCH_ACTIONS",
    "HOT_TOPIC_BROWSER_SOURCES",
    "HOT_TOPIC_CREATE_STATUSES",
    "HOT_TOPIC_SOURCE_ALIASES",
    "HOT_TOPIC_STATUSES",
    "HotTopicValidationError",
    "hot_topic_row_to_dict",
    "parse_batch_payload",
    "parse_collect_payload",
    "parse_create_payload",
    "parse_update_payload",
]
