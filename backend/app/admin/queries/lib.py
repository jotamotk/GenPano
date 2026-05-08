"""Pure helpers for the queries / stats API (Phase 9 slice 9a + 9b).

Stateless query-string normalizers + sort-clause whitelisting + write
payload validators. No DB.
"""

from __future__ import annotations

import re
from typing import Any

QUERIES_SORT_MAP: dict[str, str] = {
    "id_desc": "q.id DESC",
    "id_asc": "q.id ASC",
    "status": "UPPER(q.status) ASC, q.id DESC",
}

QUERIES_DEFAULT_SORT = "id_desc"
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

CLEANUP_TYPES = ("unqueued", "all_pending", "failed_old")


class QueryValidationError(Exception):
    """Coded validation error returned to the API layer (HTTP 400)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def normalize_sort(value: Any) -> str:
    """Whitelist the sort key admin_console accepts. Falls back to
    ``id_desc`` for unknown values (defensive — admin_console did the
    same ``sort_map.get(sort, default)``)."""
    text = str(value or "").strip().lower()
    return QUERIES_SORT_MAP.get(text, QUERIES_SORT_MAP[QUERIES_DEFAULT_SORT])


def is_iso_date(value: Any) -> bool:
    return bool(DATE_PATTERN.match(str(value or "")))


def split_pending_status(value: Any) -> str | None:
    """admin_console UI splits ``pending`` into ``unqueued`` (status=pending
    AND queued_at IS NULL) + ``queued`` (status=pending AND queued_at IS
    NOT NULL). Returns ``unqueued`` / ``queued`` for those special tags;
    ``None`` for plain status values (caller compares case-insensitively).
    """
    text = str(value or "").strip().lower()
    if text == "unqueued":
        return "unqueued"
    if text == "queued":
        return "queued"
    return None


def parse_create_query_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Validate POST /api/queries body. Required: target_llm + query_text.
    brand_id is optional. Returns the dict the db helper INSERTs."""
    payload = payload or {}
    target_llm = str(payload.get("target_llm") or "").strip()
    query_text = str(payload.get("query_text") or "").strip()
    if not target_llm or not query_text:
        raise QueryValidationError("missing_required", "target_llm and query_text are required")
    raw_brand = payload.get("brand_id")
    brand_id: int | None
    if raw_brand is None or raw_brand == "":
        brand_id = None
    else:
        try:
            brand_id = int(raw_brand)
        except (TypeError, ValueError) as error:
            raise QueryValidationError(
                "invalid_brand_id", "brand_id must be an integer or null"
            ) from error
    return {
        "target_llm": target_llm,
        "query_text": query_text,
        "brand_id": brand_id,
    }


def parse_batch_trigger_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Validate POST /api/queries/batch_trigger body.

    Returns ``{ids?, brand_id?, topic_id?, prompt_id?, llm?, status?,
    query_id?, prompt_q?, max_count, dry_run, reason}``. Raises
    ``QueryValidationError`` for invalid ids list / out-of-range max.
    """
    payload = payload or {}
    out: dict[str, Any] = {
        "max_count": 2000,
        "dry_run": False,
        "reason": "batch_trigger",
    }
    raw_ids = payload.get("ids")
    if isinstance(raw_ids, list) and raw_ids:
        clean: list[int] = []
        for value in raw_ids:
            text = str(value).strip().lstrip("-")
            if text.isdigit():
                clean.append(int(value))
        if not clean:
            raise QueryValidationError("ids_empty_or_invalid", "ids 列表为空或无效")
        out["ids"] = clean
    else:
        for key, target in (
            ("brand_id", "brand_id"),
            ("topic_id", "topic_id"),
            ("prompt_id", "prompt_id"),
            ("id", "query_id"),
        ):
            raw = payload.get(key)
            if raw is None or raw == "":
                continue
            try:
                out[target] = int(raw)
            except (TypeError, ValueError) as error:
                raise QueryValidationError(f"invalid_{key}", f"{key} must be an integer") from error
        for key in ("llm", "status", "q"):
            text = str(payload.get(key) or "").strip()
            if text:
                out["prompt_q" if key == "q" else key] = text
    raw_max = payload.get("max")
    if raw_max is not None and raw_max != "":
        try:
            mx = int(raw_max)
        except (TypeError, ValueError) as error:
            raise QueryValidationError("invalid_max", "max must be a positive integer") from error
        if mx < 1:
            raise QueryValidationError("invalid_max", "max must be at least 1")
        out["max_count"] = mx
    out["dry_run"] = bool(payload.get("dry_run"))
    raw_reason = str(payload.get("reason") or "batch_trigger").strip() or "batch_trigger"
    out["reason"] = raw_reason
    return out


def parse_cleanup_query_args(args: dict[str, Any] | None) -> dict[str, Any]:
    """Validate query-string args for DELETE /api/queries/cleanup.

    Returns ``{type, dry_run, days}``. Raises ``QueryValidationError``
    when ``type`` is missing / not in the allowlist.
    """
    args = args or {}
    cleanup_type = str(args.get("type") or "").strip().lower()
    if cleanup_type not in CLEANUP_TYPES:
        raise QueryValidationError(
            "invalid_type", f"type must be one of: {', '.join(CLEANUP_TYPES)}"
        )
    dry_run = str(args.get("dry_run") or "").lower() in ("1", "true", "yes")
    raw_days = args.get("days") or 30
    try:
        days = max(1, int(raw_days))
    except (TypeError, ValueError):
        days = 30
    return {"type": cleanup_type, "dry_run": dry_run, "days": days}


__all__ = [
    "CLEANUP_TYPES",
    "DATE_PATTERN",
    "QUERIES_DEFAULT_SORT",
    "QUERIES_SORT_MAP",
    "QueryValidationError",
    "is_iso_date",
    "normalize_sort",
    "parse_batch_trigger_payload",
    "parse_cleanup_query_args",
    "parse_create_query_payload",
    "split_pending_status",
]
