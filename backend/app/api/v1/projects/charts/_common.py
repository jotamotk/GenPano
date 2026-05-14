"""Shared helpers for chart-data services.

Extracted from `_charts_service.py` as the first step of splitting the
god-module (Epic #885, tracking issue #886). Every public symbol here is
re-exported by `charts/__init__.py` so callers may use either import path.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.api.v1.projects._topic_analysis_service import AnalysisFilters

DEFAULT_WINDOW_DAYS = 30


def _resolve_window(from_date: date | None, to_date: date | None) -> tuple[date, date]:
    today = date.today()
    to_d = to_date or today
    from_d = from_date or (to_d - timedelta(days=DEFAULT_WINDOW_DAYS - 1))
    return from_d, to_d


def _period(from_d: date, to_d: date) -> dict[str, str]:
    return {"from": from_d.isoformat(), "to": to_d.isoformat()}


def _dt_range(from_d: date, to_d: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(from_d, datetime.min.time()),
        datetime.combine(to_d, datetime.max.time()),
    )


def _admin_filters(
    from_d: date,
    to_d: date,
    *,
    engines: list[str] | None = None,
    segment_id: str | None = None,
    profile_id: str | None = None,
) -> AnalysisFilters:
    return AnalysisFilters(
        from_date=from_d,
        to_date=to_d,
        engines=tuple(engines) if engines else None,
        segment_id=segment_id,
        profile_id=profile_id,
    )


def _chart_counts(**counts: int) -> dict[str, int]:
    return {key: int(value or 0) for key, value in counts.items()}


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out
