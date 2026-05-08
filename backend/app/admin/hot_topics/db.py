"""DB operations for the admin/hot_topics package (Phase 8 slice 8b).

The ``hot_topics`` table is created by Alembic migration
``20260504_phase0_app`` (Phase 0 product tables). Defensive
``_table_exists`` probes mirror the products / brand_management
patterns so sqlite tests degrade gracefully.

Public:
- ``list_hot_topics(...)`` — filtered + paginated list with brand_name +
  days_remaining + status counts.
- ``get_hot_topic(...)`` — detail row for audit before/after.
- ``create_hot_topic(...)`` — INSERT with NOW() + INTERVAL effective_until.
- ``update_hot_topic(...)`` — sparse UPDATE; returns refreshed row.
- ``delete_hot_topic(...)`` — sets ``prompts.hotspot_id = NULL`` then DELETE,
  returns ``(deleted, unlinked)``.
- ``archive_expired(...)`` — flips active rows past effective_until → expired.
- ``batch_update_hot_topics(...)`` — bulk status / industry / brand / delete.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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


async def list_hot_topics(
    session: AsyncSession,
    *,
    status: str | None = None,
    source: str | None = None,
    industry: str | None = None,
    brand_id: int | None = None,
    limit: int = 100,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Returns ``(rows, counts_by_status)``. Empty dict + empty list when
    table is missing (sqlite tests)."""
    if not await _table_exists(session, "hot_topics"):
        return [], {}
    where: list[str] = []
    params: dict[str, Any] = {"limit": int(limit)}
    if status in {"draft", "active", "expired", "rejected"}:
        where.append("h.status = :status")
        params["status"] = status
    if source:
        where.append("h.source = :source")
        params["source"] = source
    if industry:
        where.append("h.industry = :industry")
        params["industry"] = industry
    if brand_id is not None:
        where.append("h.brand_id = :brand_id")
        params["brand_id"] = brand_id
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    sql = text(
        f"""
        SELECT h.id, h.title, h.summary, h.category, h.source, h.source_url,
               h.raw_rank, h.raw_metric, h.industry, h.brand_id,
               b.name AS brand_name,
               h.effective_from, h.effective_until, h.status,
               GREATEST(0, EXTRACT(DAY FROM (h.effective_until - NOW())))::int AS days_remaining,
               h.created_at, h.updated_at
        FROM hot_topics h
        LEFT JOIN brands b ON b.id = h.brand_id
        {where_sql}
        ORDER BY
            CASE h.status WHEN 'draft' THEN 0 WHEN 'active' THEN 1
                          WHEN 'expired' THEN 2 ELSE 3 END,
            h.effective_from DESC
        LIMIT :limit
        """
    )
    rows = (await session.execute(sql, params)).mappings().all()
    counts_rows = (
        (
            await session.execute(
                text("SELECT status, COUNT(*) AS c FROM hot_topics GROUP BY status")
            )
        )
        .mappings()
        .all()
    )
    counts = {str(r.get("status") or ""): int(r.get("c") or 0) for r in counts_rows}
    return [dict(r) for r in rows], counts


async def get_hot_topic(session: AsyncSession, hot_id: int) -> dict[str, Any] | None:
    if not await _table_exists(session, "hot_topics"):
        return None
    sql = text(
        """
        SELECT h.id, h.title, h.summary, h.category, h.source, h.source_url,
               h.raw_rank, h.raw_metric, h.industry, h.brand_id,
               b.name AS brand_name,
               h.effective_from, h.effective_until, h.status,
               GREATEST(0, EXTRACT(DAY FROM (h.effective_until - NOW())))::int AS days_remaining,
               h.created_at, h.updated_at
        FROM hot_topics h
        LEFT JOIN brands b ON b.id = h.brand_id
        WHERE h.id = :id
        """
    )
    row = (await session.execute(sql, {"id": hot_id})).mappings().first()
    if not row:
        return None
    item = dict(row)
    item["effective_from"] = _isoformat(item.get("effective_from"))
    item["effective_until"] = _isoformat(item.get("effective_until"))
    item["created_at"] = _isoformat(item.get("created_at"))
    item["updated_at"] = _isoformat(item.get("updated_at"))
    return item


async def create_hot_topic(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """INSERT with ``effective_until = NOW() + INTERVAL ':days days'``.
    Returns ``None`` when ``hot_topics`` table is missing."""
    if not await _table_exists(session, "hot_topics"):
        return None
    days = int(payload.get("effective_days") or 14)
    # ``INTERVAL ':n days'`` doesn't bind in psycopg/sqlalchemy; concat the int
    # after clamping it via parse_create_payload (1-90).
    sql = text(
        f"""
        INSERT INTO hot_topics
            (title, summary, category, source, industry, brand_id,
             effective_from, effective_until, status)
        VALUES
            (:title, :summary, :category, :source, :industry, :brand_id,
             NOW(), NOW() + INTERVAL '{int(days)} days', :status)
        RETURNING id, title, summary, category, source, source_url,
                  raw_rank, raw_metric, industry, brand_id,
                  effective_from, effective_until, status,
                  GREATEST(0, EXTRACT(DAY FROM (effective_until - NOW())))::int AS days_remaining,
                  created_at, updated_at
        """
    )
    row = (
        (
            await session.execute(
                sql,
                {
                    "title": payload["title"],
                    "summary": payload.get("summary"),
                    "category": payload.get("category"),
                    "source": payload.get("source"),
                    "industry": payload.get("industry"),
                    "brand_id": payload.get("brand_id"),
                    "status": payload.get("status"),
                },
            )
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    item = dict(row)
    if item.get("brand_id"):
        brand_row = (
            (
                await session.execute(
                    text("SELECT name FROM brands WHERE id = :id"),
                    {"id": item["brand_id"]},
                )
            )
            .mappings()
            .first()
        )
        item["brand_name"] = (dict(brand_row) if brand_row else {}).get("name")
    else:
        item["brand_name"] = None
    item["effective_from"] = _isoformat(item.get("effective_from"))
    item["effective_until"] = _isoformat(item.get("effective_until"))
    item["created_at"] = _isoformat(item.get("created_at"))
    item["updated_at"] = _isoformat(item.get("updated_at"))
    await session.commit()
    return item


async def update_hot_topic(
    session: AsyncSession,
    *,
    hot_id: int,
    fields: dict[str, Any],
) -> dict[str, Any] | None:
    """Sparse UPDATE. ``effective_days`` translates to ``effective_until
    = NOW() + INTERVAL`` in raw SQL. Returns ``None`` if not found."""
    if not await _table_exists(session, "hot_topics"):
        return None
    if not fields:
        return None
    set_pieces: list[str] = []
    params: dict[str, Any] = {"id": hot_id}
    for key, value in fields.items():
        if key == "effective_days":
            set_pieces.append(f"effective_until = NOW() + INTERVAL '{int(value)} days'")
        else:
            set_pieces.append(f"{key} = :{key}")
            params[key] = value
    set_pieces.append("updated_at = NOW()")
    sql = text(
        f"""
        UPDATE hot_topics
        SET {", ".join(set_pieces)}
        WHERE id = :id
        RETURNING id, title, summary, category, source, source_url,
                  raw_rank, raw_metric, industry, brand_id,
                  effective_from, effective_until, status,
                  GREATEST(0, EXTRACT(DAY FROM (effective_until - NOW())))::int AS days_remaining,
                  created_at, updated_at
        """
    )
    row = (await session.execute(sql, params)).mappings().first()
    if not row:
        await session.rollback()
        return None
    item = dict(row)
    if item.get("brand_id"):
        brand_row = (
            (
                await session.execute(
                    text("SELECT name FROM brands WHERE id = :id"),
                    {"id": item["brand_id"]},
                )
            )
            .mappings()
            .first()
        )
        item["brand_name"] = (dict(brand_row) if brand_row else {}).get("name")
    else:
        item["brand_name"] = None
    item["effective_from"] = _isoformat(item.get("effective_from"))
    item["effective_until"] = _isoformat(item.get("effective_until"))
    item["created_at"] = _isoformat(item.get("created_at"))
    item["updated_at"] = _isoformat(item.get("updated_at"))
    await session.commit()
    return item


async def delete_hot_topic(session: AsyncSession, hot_id: int) -> tuple[bool, int]:
    """Set ``prompts.hotspot_id = NULL`` (defensive — admin_console
    line 6404), then DELETE the row. Returns ``(deleted, unlinked)``."""
    if not await _table_exists(session, "hot_topics"):
        return False, 0
    unlinked = 0
    if await _table_exists(session, "prompts"):
        result = await session.execute(
            text("UPDATE prompts SET hotspot_id = NULL WHERE hotspot_id = :id"),
            {"id": hot_id},
        )
        unlinked = int(getattr(result, "rowcount", 0) or 0)
    delete_result = await session.execute(
        text("DELETE FROM hot_topics WHERE id = :id"),
        {"id": hot_id},
    )
    if (getattr(delete_result, "rowcount", 0) or 0) == 0:
        await session.rollback()
        return False, 0
    await session.commit()
    return True, unlinked


async def archive_expired(session: AsyncSession) -> int:
    """Flip active rows whose ``effective_until <= NOW()`` to expired.
    Idempotent. Returns the number of rows updated."""
    if not await _table_exists(session, "hot_topics"):
        return 0
    result = await session.execute(
        text(
            "UPDATE hot_topics SET status = 'expired', updated_at = NOW() "
            "WHERE status = 'active' AND effective_until <= NOW()"
        )
    )
    n = int(getattr(result, "rowcount", 0) or 0)
    await session.commit()
    return n


async def batch_update_hot_topics(
    session: AsyncSession,
    *,
    ids: list[int],
    action: str,
    status: str | None = None,
    industry: str | None = None,
    brand_id: int | None = None,
) -> dict[str, int]:
    """Bulk operation for the SPA's multi-select toolbar. Returns a dict
    with one of:
    - ``{"updated": n}`` for status / industry / brand
    - ``{"deleted": n, "unlinked_prompts": k}`` for delete
    """
    if not await _table_exists(session, "hot_topics") or not ids:
        return {"updated": 0}
    if action == "delete":
        unlinked = 0
        if await _table_exists(session, "prompts"):
            result = await session.execute(
                text("UPDATE prompts SET hotspot_id = NULL WHERE hotspot_id = ANY(:ids)"),
                {"ids": ids},
            )
            unlinked = int(getattr(result, "rowcount", 0) or 0)
        delete_result = await session.execute(
            text("DELETE FROM hot_topics WHERE id = ANY(:ids)"),
            {"ids": ids},
        )
        deleted = int(getattr(delete_result, "rowcount", 0) or 0)
        await session.commit()
        return {"deleted": deleted, "unlinked_prompts": unlinked}

    if action == "status":
        result = await session.execute(
            text("UPDATE hot_topics SET status = :v, updated_at = NOW() WHERE id = ANY(:ids)"),
            {"v": status, "ids": ids},
        )
    elif action == "industry":
        result = await session.execute(
            text("UPDATE hot_topics SET industry = :v, updated_at = NOW() WHERE id = ANY(:ids)"),
            {"v": industry, "ids": ids},
        )
    elif action == "brand":
        result = await session.execute(
            text("UPDATE hot_topics SET brand_id = :v, updated_at = NOW() WHERE id = ANY(:ids)"),
            {"v": brand_id, "ids": ids},
        )
    else:
        return {"updated": 0}
    updated = int(getattr(result, "rowcount", 0) or 0)
    await session.commit()
    return {"updated": updated}


__all__ = [
    "archive_expired",
    "batch_update_hot_topics",
    "create_hot_topic",
    "delete_hot_topic",
    "get_hot_topic",
    "list_hot_topics",
    "update_hot_topic",
]
