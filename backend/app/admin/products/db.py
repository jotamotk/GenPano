"""DB operations for the admin/products package (Phase 8 slice 8a).

The ``products`` table is created by Alembic migration
``20260504_phase0_app`` (Phase 0 product tables). Defensive
``_table_exists`` / ``_table_columns`` probes mirror the brand_management
pattern so sqlite tests degrade to "no data" rather than blowing up.

Public:
- ``list_products(session, *, brand_id, status, q, limit, offset)`` —
  paginated list with COUNT(*) total + topic_count subquery.
- ``get_product(session, product_id)`` — detail row for the audit
  before/after.
- ``create_product(session, *, brand_id, payload)`` — INSERT, raises
  ``ProductDBError`` for unique-violation / brand-not-found.
- ``update_product(session, *, product_id, fields)`` — UPDATE with the
  sparse mapping returned by ``lib.parse_update_payload``.
- ``delete_product(session, product_id)`` — soft cascade: sets
  ``topics.product_id = NULL`` then DELETEs the row. Returns
  ``(deleted, unlinked_count)``.
- ``brand_exists(session, brand_id)`` / ``fetch_brand_context(session, brand_id)``
  — used by router + LLM discovery.
- ``existing_product_names_for_brand(session, brand_id)`` — used by
  LLM discovery to dedupe before INSERT.
- ``bulk_insert_discovered_products(session, *, brand_id, brand_name,
  candidates)`` — INSERT each row with ``ON CONFLICT (brand_id, name)
  DO NOTHING`` and return ``(created, skipped)``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ProductDBError(Exception):
    """Stable code returned to the router; mapped to 4xx / 5xx there."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


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


def _isoformat(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


async def brand_exists(session: AsyncSession, *, brand_id: int) -> bool:
    if not await _table_exists(session, "brands"):
        return False
    row = (
        await session.execute(
            text("SELECT 1 FROM brands WHERE id = :id LIMIT 1"),
            {"id": brand_id},
        )
    ).first()
    return row is not None


async def fetch_brand_context(session: AsyncSession, *, brand_id: int) -> dict[str, Any] | None:
    """Return brand metadata used by the LLM discovery prompt.

    Defensively NULL-substitutes columns that may not exist on legacy
    DBs (admin_console line 6101). Returns ``None`` when the brand or
    table is missing.
    """
    if not await _table_exists(session, "brands"):
        return None
    cols = await _table_columns(session, "brands")
    name_expr = "name" if "name" in cols else "('Brand #' || id::text)"
    industry_expr = "COALESCE(NULLIF(industry, ''), '')" if "industry" in cols else "''"
    target_market_expr = (
        "COALESCE(NULLIF(target_market, ''), '')" if "target_market" in cols else "''"
    )
    description_expr = "COALESCE(description, '')" if "description" in cols else "''"
    aliases_expr = "aliases" if "aliases" in cols else "NULL::jsonb AS aliases"
    sql = text(
        f"""
        SELECT id, {name_expr} AS name, {industry_expr} AS industry,
               {target_market_expr} AS target_market,
               {description_expr} AS description,
               {aliases_expr}
        FROM brands WHERE id = :id
        """
    )
    row = (await session.execute(sql, {"id": brand_id})).mappings().first()
    if not row:
        return None
    item = dict(row)
    aliases = item.get("aliases") or []
    if isinstance(aliases, str):
        try:
            aliases = json.loads(aliases)
        except Exception:
            aliases = [aliases]
    item["aliases"] = aliases if isinstance(aliases, list) else []
    return item


async def list_products(
    session: AsyncSession,
    *,
    brand_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Paginated list with brand_name JOIN + topic_count subquery.

    Returns ``[]``, ``0`` when ``products`` doesn't exist (sqlite tests).
    """
    if not await _table_exists(session, "products"):
        return [], 0
    where: list[str] = []
    params: dict[str, Any] = {"limit": int(limit), "offset": int(offset)}
    if brand_id is not None:
        where.append("p.brand_id = :brand_id")
        params["brand_id"] = brand_id
    if status in ("active", "archived"):
        where.append("p.status = :status")
        params["status"] = status
    if q:
        where.append("(p.name ILIKE :q OR p.sku ILIKE :q OR p.category ILIKE :q)")
        params["q"] = f"%{q}%"
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    total_row = (
        (await session.execute(text(f"SELECT COUNT(*) AS c FROM products p {where_sql}"), params))
        .mappings()
        .first()
    )
    total = int((dict(total_row) if total_row else {}).get("c") or 0)

    sql = text(
        f"""
        SELECT p.id, p.brand_id, b.name AS brand_name,
               p.name, p.sku, p.category, p.description,
               p.aliases, p.status, p.created_at, p.updated_at,
               (SELECT COUNT(*) FROM topics t WHERE t.product_id = p.id) AS topic_count
        FROM products p
        LEFT JOIN brands b ON b.id = p.brand_id
        {where_sql}
        ORDER BY p.updated_at DESC, p.id DESC
        LIMIT :limit OFFSET :offset
        """
    )
    rows = (await session.execute(sql, params)).mappings().all()
    return [dict(r) for r in rows], total


async def get_product(session: AsyncSession, product_id: int) -> dict[str, Any] | None:
    if not await _table_exists(session, "products"):
        return None
    sql = text(
        """
        SELECT p.id, p.brand_id, b.name AS brand_name,
               p.name, p.sku, p.category, p.description,
               p.aliases, p.status, p.created_at, p.updated_at,
               (SELECT COUNT(*) FROM topics t WHERE t.product_id = p.id) AS topic_count
        FROM products p
        LEFT JOIN brands b ON b.id = p.brand_id
        WHERE p.id = :id
        """
    )
    row = (await session.execute(sql, {"id": product_id})).mappings().first()
    if not row:
        return None
    item = dict(row)
    item["created_at"] = _isoformat(item.get("created_at"))
    item["updated_at"] = _isoformat(item.get("updated_at"))
    return item


async def create_product(
    session: AsyncSession,
    *,
    brand_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """INSERT. Raises ``ProductDBError`` with code:
    - ``brand_not_found``  (brand FK missing)
    - ``products_table_missing``  (sqlite test path)
    - ``duplicate_product_name``  (UniqueViolation on (brand_id, name))
    """
    if not await _table_exists(session, "products"):
        raise ProductDBError("products_table_missing", "products table is not available")
    if not await brand_exists(session, brand_id=brand_id):
        raise ProductDBError("brand_not_found", "Brand not found")
    sql = text(
        """
        INSERT INTO products
            (brand_id, name, sku, category, description, aliases, status)
        VALUES
            (:brand_id, :name, :sku, :category, :description,
             CAST(:aliases AS jsonb), :status)
        RETURNING id, brand_id, name, sku, category, description,
                  aliases, status, created_at, updated_at
        """
    )
    try:
        row = (
            (
                await session.execute(
                    sql,
                    {
                        "brand_id": brand_id,
                        "name": payload["name"],
                        "sku": payload.get("sku"),
                        "category": payload.get("category"),
                        "description": payload.get("description"),
                        "aliases": json.dumps(payload.get("aliases") or [], ensure_ascii=False),
                        "status": payload.get("status") or "active",
                    },
                )
            )
            .mappings()
            .first()
        )
    except IntegrityError as error:
        await session.rollback()
        raise ProductDBError(
            "duplicate_product_name",
            "A product with this name already exists for the brand",
        ) from error
    if not row:
        raise ProductDBError("insert_failed", "Failed to insert product row")
    item = dict(row)
    # Attach brand_name for the wire response (caller will pass through).
    brand_row = (
        (await session.execute(text("SELECT name FROM brands WHERE id = :id"), {"id": brand_id}))
        .mappings()
        .first()
    )
    item["brand_name"] = (dict(brand_row) if brand_row else {}).get("name")
    item["topic_count"] = 0
    item["created_at"] = _isoformat(item.get("created_at"))
    item["updated_at"] = _isoformat(item.get("updated_at"))
    await session.commit()
    return item


async def update_product(
    session: AsyncSession,
    *,
    product_id: int,
    fields: dict[str, Any],
) -> dict[str, Any] | None:
    """UPDATE specified columns + ``updated_at = NOW()``. Returns the
    refreshed row dict (with ``brand_name`` + ``topic_count``) or
    ``None`` when the product isn't found. Raises ``ProductDBError`` on
    UniqueViolation.
    """
    if not await _table_exists(session, "products"):
        raise ProductDBError("products_table_missing", "products table is not available")
    if not fields:
        raise ProductDBError("no_fields", "No update fields supplied")

    set_pieces: list[str] = []
    params: dict[str, Any] = {"id": product_id}
    for key, value in fields.items():
        if key == "aliases":
            set_pieces.append(f"{key} = CAST(:{key} AS jsonb)")
            params[key] = json.dumps(value or [], ensure_ascii=False)
        else:
            set_pieces.append(f"{key} = :{key}")
            params[key] = value
    set_pieces.append("updated_at = NOW()")
    sql = text(
        f"""
        UPDATE products
        SET {", ".join(set_pieces)}
        WHERE id = :id
        RETURNING id, brand_id, name, sku, category, description,
                  aliases, status, created_at, updated_at
        """
    )
    try:
        row = (await session.execute(sql, params)).mappings().first()
    except IntegrityError as error:
        await session.rollback()
        raise ProductDBError(
            "duplicate_product_name",
            "A product with this name already exists for the brand",
        ) from error
    if not row:
        return None
    item = dict(row)
    brand_row = (
        (
            await session.execute(
                text("SELECT name FROM brands WHERE id = :id"), {"id": item["brand_id"]}
            )
        )
        .mappings()
        .first()
    )
    item["brand_name"] = (dict(brand_row) if brand_row else {}).get("name")
    topic_row = (
        (
            await session.execute(
                text("SELECT COUNT(*) AS c FROM topics WHERE product_id = :id"),
                {"id": product_id},
            )
        )
        .mappings()
        .first()
    )
    item["topic_count"] = int((dict(topic_row) if topic_row else {}).get("c") or 0)
    item["created_at"] = _isoformat(item.get("created_at"))
    item["updated_at"] = _isoformat(item.get("updated_at"))
    await session.commit()
    return item


async def delete_product(session: AsyncSession, product_id: int) -> tuple[bool, int]:
    """Set ``topics.product_id = NULL`` (defensive — admin_console
    line 6446) then DELETE the row. Returns ``(deleted, unlinked)``.
    """
    if not await _table_exists(session, "products"):
        return False, 0
    unlinked = 0
    if await _table_exists(session, "topics"):
        result = await session.execute(
            text("UPDATE topics SET product_id = NULL WHERE product_id = :id"),
            {"id": product_id},
        )
        unlinked = int(getattr(result, "rowcount", 0) or 0)
    delete_result = await session.execute(
        text("DELETE FROM products WHERE id = :id"), {"id": product_id}
    )
    if (getattr(delete_result, "rowcount", 0) or 0) == 0:
        await session.rollback()
        return False, 0
    await session.commit()
    return True, unlinked


async def existing_product_names_for_brand(session: AsyncSession, brand_id: int) -> set[str]:
    if not await _table_exists(session, "products"):
        return set()
    rows = (
        (
            await session.execute(
                text("SELECT name FROM products WHERE brand_id = :id"),
                {"id": brand_id},
            )
        )
        .mappings()
        .all()
    )
    return {str(row.get("name") or "").strip().casefold() for row in rows}


async def bulk_insert_discovered_products(
    session: AsyncSession,
    *,
    brand_id: int,
    brand_name: str | None,
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """INSERT with ``ON CONFLICT (brand_id, name) DO NOTHING``. Returns
    ``(created, skipped)`` where each ``created`` row is wire-shaped via
    ``product_row_to_dict`` upstream and each ``skipped`` is
    ``{"name": ..., "reason": "duplicate"}``."""
    if not await _table_exists(session, "products"):
        raise ProductDBError("products_table_missing", "products table is not available")
    existing = await existing_product_names_for_brand(session, brand_id)
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in candidates:
        key = str(item.get("name") or "").strip().casefold()
        if not key or key in existing:
            skipped.append({"name": item.get("name"), "reason": "duplicate"})
            continue
        sql = text(
            """
            INSERT INTO products
                (brand_id, name, sku, category, description, aliases, status)
            VALUES
                (:brand_id, :name, :sku, :category, :description,
                 CAST(:aliases AS jsonb), 'active')
            ON CONFLICT (brand_id, name) DO NOTHING
            RETURNING id, brand_id, name, sku, category, description,
                      aliases, status, created_at, updated_at
            """
        )
        row = (
            (
                await session.execute(
                    sql,
                    {
                        "brand_id": brand_id,
                        "name": item.get("name"),
                        "sku": item.get("sku") or None,
                        "category": item.get("category") or None,
                        "description": item.get("description") or None,
                        "aliases": json.dumps(item.get("aliases") or [], ensure_ascii=False),
                    },
                )
            )
            .mappings()
            .first()
        )
        if not row:
            skipped.append({"name": item.get("name"), "reason": "duplicate"})
            existing.add(key)
            continue
        created_item = dict(row)
        created_item["brand_name"] = brand_name
        created_item["topic_count"] = 0
        created_item["created_at"] = _isoformat(created_item.get("created_at"))
        created_item["updated_at"] = _isoformat(created_item.get("updated_at"))
        created.append(created_item)
        existing.add(key)
    await session.commit()
    return created, skipped


__all__ = [
    "ProductDBError",
    "brand_exists",
    "bulk_insert_discovered_products",
    "create_product",
    "delete_product",
    "existing_product_names_for_brand",
    "fetch_brand_context",
    "get_product",
    "list_products",
    "update_product",
]
