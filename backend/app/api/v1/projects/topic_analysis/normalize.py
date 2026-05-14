"""Pure data-normalization helpers extracted from `_topic_analysis_service.py`.

Phase 1 of splitting the 2575-LOC god-module (Epic #885, design #887). Every
function here is stateless and pure — no DB, no async, no SQL. They are
re-exported by `_topic_analysis_service.py` so existing import paths
continue to work.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def _response_preview(value: Any, max_chars: int = 280) -> str | None:
    if value is None:
        return None
    preview = " ".join(str(value).split())
    if not preview:
        return None
    return preview[:max_chars]


def _date_key(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _timestamp_key(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _round(value: Any, digits: int = 4) -> float | None:
    num = _as_float(value)
    return round(num, digits) if num is not None else None


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _pct(numerator: int | float, denominator: int | float, digits: int = 4) -> float | None:
    if not denominator:
        return None
    return round(float(numerator) / float(denominator), digits)


def _normalize_key(value: Any) -> str | None:
    if value is None:
        return None
    norm = str(value).strip().lower().replace("-", "_")
    return norm or None


def _coerce_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}
