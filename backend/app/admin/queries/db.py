"""DB operations for the queries / stats API (Phase 9 slice 9a).

Both ``queries`` and ``llm_responses`` are admin_console-era tables not
in genpano_models (ADR-002). Defensive ``_table_exists`` probes return
empty / zero values when the tables aren't on the DB (sqlite tests).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.queries.lib import (
    is_iso_date,
    normalize_sort,
    split_pending_status,
)

logger = logging.getLogger(__name__)


def _isoformat(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


async def _table_exists(session: AsyncSession, name: str) -> bool:
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


async def fetch_status_stats(session: AsyncSession) -> dict[str, Any]:
    """Return ``{total, done, pending, running, failed}`` aggregated from
    ``queries.status``. Empty / zeroed when the table doesn't exist."""
    empty = {"total": 0, "done": 0, "pending": 0, "running": 0, "failed": 0}
    if not await _table_exists(session, "queries"):
        return empty
    sql = text(
        "SELECT UPPER(status) AS status, COUNT(*) AS count FROM queries GROUP BY UPPER(status)"
    )
    rows = (await session.execute(sql)).mappings().all()
    counts = {str(r.get("status") or ""): int(r.get("count") or 0) for r in rows}
    total = sum(counts.values())
    return {
        "total": total,
        "done": counts.get("DONE", 0),
        "pending": counts.get("PENDING", 0),
        "running": counts.get("RUNNING", 0),
        "failed": counts.get("FAILED", 0),
    }


async def list_queries(
    session: AsyncSession,
    *,
    llm: str | None = None,
    status: str | None = None,
    brand_id: int | None = None,
    topic_id: int | None = None,
    prompt_id: int | None = None,
    query_id: int | None = None,
    prompt_q: str | None = None,
    date_filter: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
    sort: str = "id_desc",
    include_count: bool = False,
) -> tuple[list[dict[str, Any]], int | None, dict[str, int] | None]:
    """Filtered list of queries with the joined wire shape admin.html
    expects. Returns ``(rows, total, by_status)`` where total/by_status
    are ``None`` when ``include_count`` is False (admin_console parity).

    Empty when ``queries`` table doesn't exist (sqlite test fixture).
    """
    if not await _table_exists(session, "queries"):
        return [], (0 if include_count else None), ({} if include_count else None)

    where: list[str] = []
    params: dict[str, Any] = {"limit": int(limit), "offset": int(offset)}

    if query_id is not None:
        where.append("q.id = :query_id")
        params["query_id"] = query_id
    if llm:
        where.append("q.target_llm = :llm")
        params["llm"] = llm
    if status:
        special = split_pending_status(status)
        if special == "unqueued":
            where.append("LOWER(q.status) = 'pending' AND q.queued_at IS NULL")
        elif special == "queued":
            where.append("LOWER(q.status) = 'pending' AND q.queued_at IS NOT NULL")
        else:
            where.append("UPPER(q.status) = UPPER(:status_filter)")
            params["status_filter"] = status
    if date_filter and is_iso_date(date_filter):
        where.append("q.created_at::date = :date_filter")
        params["date_filter"] = date_filter
    if date_from and is_iso_date(date_from):
        where.append("q.created_at::date >= :date_from")
        params["date_from"] = date_from
    if date_to and is_iso_date(date_to):
        where.append("q.created_at::date <= :date_to")
        params["date_to"] = date_to
    if brand_id is not None:
        where.append("q.brand_id = :brand_id")
        params["brand_id"] = brand_id
    if topic_id is not None:
        where.append("q.prompt_id IN (SELECT id FROM prompts WHERE topic_id = :topic_id)")
        params["topic_id"] = topic_id
    if prompt_id is not None:
        where.append("q.prompt_id = :prompt_id")
        params["prompt_id"] = prompt_id
    if prompt_q:
        where.append("q.query_text ILIKE :prompt_q")
        params["prompt_q"] = f"%{prompt_q}%"
    where_clause = " AND ".join(where) if where else "1=1"

    total: int | None = None
    by_status: dict[str, int] | None = None
    if include_count:
        cnt_row = (
            (
                await session.execute(
                    text(f"SELECT COUNT(*) AS cnt FROM queries q WHERE {where_clause}"),
                    params,
                )
            )
            .mappings()
            .first()
        )
        total = int((dict(cnt_row) if cnt_row else {}).get("cnt") or 0)

        status_rows = (
            (
                await session.execute(
                    text(
                        f"""
                    SELECT
                        CASE
                            WHEN LOWER(q.status) = 'pending' AND q.queued_at IS NULL
                                THEN 'unqueued'
                            WHEN LOWER(q.status) = 'pending' AND q.queued_at IS NOT NULL
                                THEN 'queued'
                            ELSE LOWER(q.status)
                        END AS st,
                        COUNT(*) AS cnt
                    FROM queries q WHERE {where_clause}
                    GROUP BY 1
                    """
                    ),
                    params,
                )
            )
            .mappings()
            .all()
        )
        by_status = {(r.get("st") or "unknown"): int(r.get("cnt") or 0) for r in status_rows}
        pending_legacy = by_status.get("unqueued", 0) + by_status.get("queued", 0)
        if pending_legacy:
            by_status["pending"] = pending_legacy

    sql = text(
        f"""
        SELECT
            q.id,
            q.target_llm,
            q.status,
            q.query_text,
            q.brand_id,
            q.profile_id,
            q.account_id,
            q.created_at,
            q.executed_at,
            q.retry_count,
            q.queued_at,
            q.started_at,
            q.finished_at,
            q.latency_ms,
            q.retry_reason,
            q.prompt_id,
            pr.text as prompt_text,
            t.id as topic_id,
            t.text as topic_text,
            r.raw_text as response,
            r.llm_version,
            r.citations_json as citations,
            p.name as profile_name,
            p.location as profile_location,
            p.country_code as profile_country,
            a.phone_number as account_label,
            a.llm_name as account_llm
        FROM queries q
        LEFT JOIN llm_responses r ON q.id = r.query_id
        LEFT JOIN profiles p ON q.profile_id::text = p.id::text
        LEFT JOIN llm_accounts a ON q.account_id = a.id
        LEFT JOIN prompts pr ON q.prompt_id = pr.id
        LEFT JOIN topics t ON pr.topic_id = t.id
        WHERE {where_clause}
        ORDER BY {normalize_sort(sort)}
        LIMIT :limit OFFSET :offset
        """
    )
    rows = (await session.execute(sql, params)).mappings().all()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        for ts_field in ("created_at", "executed_at", "queued_at", "started_at", "finished_at"):
            item[ts_field] = _isoformat(item.get(ts_field))
        out.append(item)
    return out, total, by_status


__all__ = ["fetch_status_stats", "list_queries"]
