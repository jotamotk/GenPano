"""Common query parameter parsing for time-range / engine / profile filters.

Used by Brand Mode + Industry Mode + Phase D / RP read endpoints to ensure a
consistent contract:

    /v1/projects/:id/metrics?from=2026-04-01&to=2026-04-30&engine=chatgpt,doubao&profileGroupId=pg-001

Per ADR / PRD §4.7.x: every read endpoint accepts these four params.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from fastapi import Query

from app.core.errors import validation_error

ALLOWED_ENGINES = frozenset({"chatgpt", "doubao", "deepseek"})


@dataclass
class TimeRangeParams:
    from_date: date
    to_date: date

    def __init__(
        self,
        from_: str | None = Query(None, alias="from", description="ISO date YYYY-MM-DD"),
        to: str | None = Query(None, description="ISO date YYYY-MM-DD"),
    ) -> None:
        today = date.today()
        if to is None:
            to_d = today
        else:
            try:
                to_d = date.fromisoformat(to)
            except ValueError as exc:
                raise validation_error("to", "must be ISO date YYYY-MM-DD") from exc
        if from_ is None:
            from_d = to_d - timedelta(days=29)  # default 30d window
        else:
            try:
                from_d = date.fromisoformat(from_)
            except ValueError as exc:
                raise validation_error("from", "must be ISO date YYYY-MM-DD") from exc
        if from_d > to_d:
            raise validation_error("from", "must be <= to")
        self.from_date = from_d
        self.to_date = to_d


def parse_engines(
    engine: str | None = Query(None, description="csv: chatgpt,doubao,deepseek"),
) -> list[str] | None:
    if engine is None or engine == "":
        return None
    items = [e.strip().lower() for e in engine.split(",") if e.strip()]
    bad = [e for e in items if e not in ALLOWED_ENGINES]
    if bad:
        raise validation_error("engine", f"unknown engine(s): {','.join(bad)}")
    return items


def parse_profile_group(
    profile_group_id: str | None = Query(None, alias="profileGroupId"),
) -> str | None:
    return profile_group_id
