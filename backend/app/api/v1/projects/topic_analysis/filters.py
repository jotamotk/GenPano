"""Analysis filter dataclass + scope-condition SQL builders.

Phase 3a of splitting `_topic_analysis_service.py` (Epic #885, design #887).
Hosts `AnalysisFilters`, the date-window resolver, row-level filter matching,
and the SQL fragment builders used by query and brand scope conditions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.api.v1.projects.topic_analysis.normalize import _coerce_json, _normalize_key

DEFAULT_WINDOW_DAYS = 30


@dataclass(frozen=True)
class AnalysisFilters:
    from_date: date | None = None
    to_date: date | None = None
    engines: tuple[str, ...] | None = None
    segment_id: str | None = None
    profile_id: str | None = None
    dimensions: tuple[str, ...] | None = None
    intents: tuple[str, ...] | None = None
    prompt_scope: str | None = None

    @property
    def explicit(self) -> bool:
        return any(
            [
                self.from_date is not None,
                self.to_date is not None,
                bool(self.engines),
                bool(self.segment_id),
                bool(self.profile_id),
                bool(self.dimensions),
                bool(self.intents),
                bool(self.prompt_scope),
            ]
        )


def _resolve_window(filters: AnalysisFilters) -> tuple[date, date]:
    today = date.today()
    to_d = filters.to_date or today
    from_d = filters.from_date or (to_d - timedelta(days=DEFAULT_WINDOW_DAYS - 1))
    if from_d > to_d:
        from_d, to_d = to_d, from_d
    return from_d, to_d


def _text_scope_conditions(
    expressions: list[str],
    terms: list[str],
    params: dict[str, Any],
    *,
    prefix: str,
) -> list[str]:
    conditions: list[str] = []
    for idx, term in enumerate(terms):
        key = f"{prefix}_{idx}"
        params[key] = f"%{term}%"
        for expr in expressions:
            conditions.append(f"LOWER(COALESCE({expr}, '')) LIKE :{key}")
    return conditions


def _mention_name_condition(
    mention_cols: set[str],
    terms: list[str],
    params: dict[str, Any],
) -> str | None:
    if "brand_name" not in mention_cols or not terms:
        return None
    placeholders: list[str] = []
    for idx, term in enumerate(terms):
        key = f"brand_mention_term_{idx}"
        params[key] = term
        placeholders.append(f":{key}")
    return f"LOWER(TRIM(COALESCE(bm.brand_name, ''))) IN ({', '.join(placeholders)})"


def _target_mention_condition(
    mention_cols: set[str],
    brand_id: int | None,
    terms: list[str],
    params: dict[str, Any],
) -> str | None:
    parts: list[str] = []
    if brand_id is not None and "brand_id" in mention_cols:
        params["primary_brand_id"] = brand_id
        parts.append("bm.brand_id = :primary_brand_id")
    mention_name_condition = _mention_name_condition(mention_cols, terms, params)
    if mention_name_condition:
        parts.append(mention_name_condition)
    if not parts:
        return None
    return f"({' OR '.join(parts)})" if len(parts) > 1 else parts[0]


def _prompt_scope_from_row(row: dict[str, Any]) -> str:
    raw = row.get("prompt_scope")
    if raw is None:
        tags = _coerce_json(row.get("prompt_tags"))
        raw = tags.get("prompt_scope") or tags.get("promptScope")
    return _normalize_key(raw) or "non_branded"


def _is_non_branded_row(row: dict[str, Any]) -> bool:
    return _prompt_scope_from_row(row) == "non_branded"


def _row_matches_analysis_filters(row: dict[str, Any], filters: AnalysisFilters) -> bool:
    if filters.dimensions:
        allowed = {_normalize_key(v) for v in filters.dimensions}
        if _normalize_key(row.get("topic_dimension")) not in allowed:
            return False
    if filters.intents:
        allowed = {_normalize_key(v) for v in filters.intents}
        if _normalize_key(row.get("prompt_intent")) not in allowed:
            return False
    if filters.prompt_scope:
        if _prompt_scope_from_row(row) != _normalize_key(filters.prompt_scope):
            return False
    return True
