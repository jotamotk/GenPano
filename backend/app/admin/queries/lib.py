"""Pure helpers for the queries / stats API (Phase 9 slice 9a).

Stateless query-string normalizers + sort-clause whitelisting. No DB.
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


__all__ = [
    "DATE_PATTERN",
    "QUERIES_DEFAULT_SORT",
    "QUERIES_SORT_MAP",
    "is_iso_date",
    "normalize_sort",
    "split_pending_status",
]
