"""DB-touching helpers for the Query Pool preflight + assemble flows.

Vendored from admin_console/app.py 1909-2019 (the prompt-row + profile-pool
queries). All queries use raw ``text()`` SQL because ``prompts`` is an
upstream stub in backend's ORM (ADR-002 — only ``id`` modeled). Defensive
``_table_exists`` / ``_table_columns`` checks via ``information_schema``
mirror admin_console: an empty test sqlite DB returns no rows, not an
exception.

Public API:
- ``fetch_prompt_ids_from_selection(session, selection, max_prompts)``
- ``fetch_query_pool_prompt_rows(session, prompt_ids)``
- ``fetch_query_pool_profile_pool(session, segment_ids=None)``
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _table_exists(session: AsyncSession, name: str) -> bool:
    """True iff ``public.<name>`` is registered in information_schema.

    Returns False on sqlite (which has no information_schema) so the
    surrounding helpers degrade to "no data" — matching admin_console.
    """
    try:
        row = (
            await session.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = :n LIMIT 1"
                ),
                {"n": name},
            )
        ).first()
    except Exception:
        return False
    return row is not None


async def _table_columns(session: AsyncSession, name: str) -> set[str]:
    try:
        result = await session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :n"
            ),
            {"n": name},
        )
    except Exception:
        return set()
    return {row[0] for row in result.all()}


def _parse_int_list(raw: Any) -> list[int]:
    """Accept comma-string / list / single int; ignore bad entries."""
    if raw is None or raw == "":
        return []
    items: list[Any]
    if isinstance(raw, str):
        items = raw.split(",")
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        items = [raw]
    out: list[int] = []
    for item in items:
        try:
            out.append(int(str(item).strip()))
        except (TypeError, ValueError):
            continue
    return out


async def fetch_prompt_ids_from_selection(
    session: AsyncSession,
    selection: dict[str, Any],
    max_prompts: int,
) -> list[str]:
    """Resolve the ``selection`` block to a concrete list of prompt ids.

    Explicit mode → returns the operator-supplied id list as-is.
    Filtered mode → executes a SELECT against ``prompts`` honoring
    intent / language / topic_ids / search and the ``status='active'``
    soft-delete column when present.
    """
    if selection["mode"] == "explicit":
        return list(selection["prompt_ids"])
    filters = selection.get("filters") or {}
    intent = (filters.get("intent") or "").strip().lower()
    language = (filters.get("language") or filters.get("lang") or "").strip()
    query = (filters.get("q") or filters.get("query") or "").strip()
    try:
        topic_ids = _parse_int_list(filters.get("topic_ids") or filters.get("topic_id"))
    except ValueError:
        topic_ids = []
    excluded = {str(x) for x in (selection.get("excluded_prompt_ids") or [])}
    if not await _table_exists(session, "prompts"):
        return []
    prompt_cols = await _table_columns(session, "prompts")
    if "id" not in prompt_cols:
        return []
    where: list[str] = []
    params: dict[str, Any] = {}
    if intent and "intent" in prompt_cols:
        where.append("p.intent = :intent")
        params["intent"] = intent
    if language and "language" in prompt_cols:
        where.append("p.language = :language")
        params["language"] = language
    if topic_ids and "topic_id" in prompt_cols:
        where.append("p.topic_id = ANY(:topic_ids)")
        params["topic_ids"] = topic_ids
    if query:
        where.append("(p.text ILIKE :like OR CAST(p.id AS TEXT) ILIKE :like)")
        params["like"] = f"%{query}%"
    if "status" in prompt_cols:
        where.append("COALESCE(p.status, 'active') = 'active'")
    where_clause = "WHERE " + " AND ".join(where) if where else ""
    params["limit"] = max_prompts
    sql = text(
        f"""
        SELECT CAST(p.id AS TEXT) AS id
        FROM prompts p
        {where_clause}
        ORDER BY p.id
        LIMIT :limit
        """
    )
    rows = (await session.execute(sql, params)).mappings().all()
    return [str(row["id"]) for row in rows if str(row["id"]) not in excluded]


async def fetch_query_pool_prompt_rows(
    session: AsyncSession,
    prompt_ids: list[str],
) -> list[dict[str, Any]]:
    """Fetch prompt + topic context rows ordered to match ``prompt_ids``."""
    prompt_ids = [str(item).strip() for item in prompt_ids if str(item).strip()]
    if not prompt_ids or not await _table_exists(session, "prompts"):
        return []
    prompt_cols = await _table_columns(session, "prompts")
    if not {"id", "text"}.issubset(prompt_cols):
        return []
    topic_join = ""
    topic_select = "NULL::text AS topic_text"
    if (
        "topic_id" in prompt_cols
        and await _table_exists(session, "topics")
        and "id" in await _table_columns(session, "topics")
    ):
        topic_join = "LEFT JOIN topics t ON t.id = p.topic_id"
        topic_select = "t.text AS topic_text"
    topic_id_select = "p.topic_id" if "topic_id" in prompt_cols else "NULL::text AS topic_id"
    status_where = "AND COALESCE(p.status, 'active') = 'active'" if "status" in prompt_cols else ""
    sql = text(
        f"""
        SELECT CAST(p.id AS TEXT) AS id, {topic_id_select}, p.text, {topic_select}
        FROM prompts p
        {topic_join}
        WHERE CAST(p.id AS TEXT) = ANY(:prompt_ids)
        {status_where}
        """
    )
    result = await session.execute(sql, {"prompt_ids": prompt_ids})
    rows_by_id = {str(row["id"]): dict(row) for row in result.mappings().all()}
    return [rows_by_id[pid] for pid in prompt_ids if pid in rows_by_id]


async def fetch_query_pool_profile_pool(
    session: AsyncSession,
    *,
    segment_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Active segments JOIN active profiles, weight-prioritized.

    Filters: ``is_deleted=False`` on both, ``status='active'`` on both,
    weight > 0 on both. Ordering matches admin_console — segment weight
    DESC then profile weight DESC then ids — so deterministic samplers
    upstream get a stable seed.
    """
    if not (await _table_exists(session, "segments") and await _table_exists(session, "profiles")):
        return []
    sids = [str(s).strip().upper() for s in (segment_ids or []) if str(s).strip()]
    where = [
        "COALESCE(s.is_deleted, FALSE) = FALSE",
        "COALESCE(p.is_deleted, FALSE) = FALSE",
        "COALESCE(s.status, 'draft') = 'active'",
        "COALESCE(p.status, 'draft') = 'active'",
        "COALESCE(s.weight, 0) > 0",
        "COALESCE(p.weight, 0) > 0",
    ]
    params: dict[str, Any] = {}
    if sids:
        where.append("s.id = ANY(:sids)")
        params["sids"] = sids
    sql = text(
        f"""
        SELECT
            s.id AS segment_id,
            s.name AS segment_name,
            COALESCE(s.weight, 0) AS segment_weight,
            COALESCE(p.code, CAST(p.id AS TEXT)) AS profile_id,
            p.name AS profile_name,
            p.demographic AS profile_demographic,
            p.need AS profile_need,
            COALESCE(p.weight, 0) AS profile_weight
        FROM segments s
        JOIN profiles p ON p.segment_id = s.id
        WHERE {" AND ".join(where)}
        ORDER BY s.weight DESC, p.weight DESC, s.id, p.id
        """
    )
    return [dict(r) for r in (await session.execute(sql, params)).mappings().all()]
