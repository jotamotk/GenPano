"""Pure helpers for the analyzer API (Phase 9 slice 9c).

Stateless validators for the trigger / rerun write paths. No DB.
"""

from __future__ import annotations

import re
from typing import Any

ANALYZER_TRIGGER_ACTIONS = ("analyze", "aggregate", "reanalyze")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class AnalyzerValidationError(Exception):
    """Coded validation error returned to the API layer (HTTP 400)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def parse_trigger_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Validate POST /api/analyzer/trigger body. Required: ``date``
    (YYYY-MM-DD); ``action`` defaults to ``analyze``.
    """
    payload = payload or {}
    action = str(payload.get("action") or "analyze").strip().lower()
    if action not in ANALYZER_TRIGGER_ACTIONS:
        raise AnalyzerValidationError(
            "invalid_action",
            f"action must be one of {sorted(ANALYZER_TRIGGER_ACTIONS)}",
        )
    date_str = str(payload.get("date") or "").strip()
    if not date_str:
        raise AnalyzerValidationError("date_required", "date is required")
    if not DATE_PATTERN.match(date_str):
        raise AnalyzerValidationError("invalid_date", "date must be ISO YYYY-MM-DD")
    raw_brand = payload.get("brand_id")
    brand_id: int | None
    if raw_brand is None or raw_brand == "":
        brand_id = None
    else:
        try:
            brand_id = int(raw_brand)
        except (TypeError, ValueError) as error:
            raise AnalyzerValidationError(
                "invalid_brand_id", "brand_id must be an integer or null"
            ) from error
    return {"action": action, "date": date_str, "brand_id": brand_id}


__all__ = [
    "ANALYZER_TRIGGER_ACTIONS",
    "AnalyzerValidationError",
    "parse_trigger_payload",
]
