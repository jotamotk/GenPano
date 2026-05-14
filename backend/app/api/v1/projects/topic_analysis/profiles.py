"""Profile-name lookup + brand fact term expansion.

Phase 3b of splitting `_topic_analysis_service.py` (Epic #885, design #887).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._legacy_lookups import BRAND_NAME_COLUMNS, brand_table_columns
from app.api.v1.projects.topic_analysis.legacy_schema import (
    legacy_table_columns,
    legacy_table_exists,
)


def _profile_name(profile_id: Any, profile_names: dict[str, str]) -> str:
    if profile_id is None:
        return "Unknown profile"
    return profile_names.get(str(profile_id), "Unknown profile")


def _clean_fact_term(value: Any) -> str | None:
    if value is None:
        return None
    term = str(value).strip().lower()
    return term or None


def _expand_brand_fact_terms(values: set[str]) -> list[str]:
    terms: set[str] = set()
    for value in values:
        term = _clean_fact_term(value)
        if not term:
            continue
        terms.add(term)
        if "雅诗兰黛" in term:
            terms.add(term.replace("雅诗兰黛", "雅思兰黛"))
        if "雅思兰黛" in term:
            terms.add(term.replace("雅思兰黛", "雅诗兰黛"))
    return sorted(terms)


async def _brand_fact_terms(session: AsyncSession, brand_id: int) -> list[str]:
    cols = await brand_table_columns(session)
    name_cols = [c for c in BRAND_NAME_COLUMNS if c in cols]
    if not name_cols:
        return []

    try:
        row = (
            await session.execute(
                text(f"SELECT {', '.join(name_cols)} FROM brands WHERE id = :id"),
                {"id": brand_id},
            )
        ).one_or_none()
    except Exception:
        return []
    if row is None:
        return []
    terms = {term for value in row for term in [_clean_fact_term(value)] if term}
    return _expand_brand_fact_terms(terms)


async def _profile_names_for_ids(
    session: AsyncSession,
    profile_ids: set[str],
) -> dict[str, str]:
    wanted = {str(pid) for pid in profile_ids if pid is not None and str(pid)}
    if not wanted or not await legacy_table_exists(session, "profiles"):
        return {}
    cols = await legacy_table_columns(session, "profiles")
    if "id" not in cols:
        return {}
    name_expr = "name" if "name" in cols else None
    if name_expr is None:
        return {}
    placeholders: list[str] = []
    params: dict[str, Any] = {}
    for i, pid in enumerate(sorted(wanted)):
        key = f"profile_id_{i}"
        placeholders.append(f":{key}")
        params[key] = pid
    rows = (
        (
            await session.execute(
                text(
                    f"""
                    SELECT CAST(id AS TEXT) AS id, {name_expr} AS name
                    FROM profiles
                    WHERE CAST(id AS TEXT) IN ({", ".join(placeholders)})
                    """
                ),
                params,
            )
        )
        .mappings()
        .all()
    )
    return {
        str(row["id"]): str(row["name"])
        for row in rows
        if row.get("id") is not None and row.get("name")
    }


async def _profile_names_for_rows(
    session: AsyncSession,
    rows: list[dict[str, Any]],
) -> dict[str, str]:
    return await _profile_names_for_ids(
        session,
        {str(row["profile_id"]) for row in rows if row.get("profile_id") is not None},
    )
