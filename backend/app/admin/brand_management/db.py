"""DB operations for Brand Management — Phase 7 slice 7a.

Vendored from admin_console/app.py 12453-13222. ``brands`` is an
upstream stub in backend's ORM (ADR-002 — only ``id`` modeled), so all
queries use raw ``text()`` SQL with defensive
``_table_exists`` / column probing — exactly what admin_console did.

Public:
- ``coerce_brand_columns(session)`` — set of columns currently on
  ``public.brands``; empty on sqlite (no information_schema).
- ``select_brand_management_sql(cols)`` — builds a SELECT clause with
  NULL fallbacks for missing columns.
- ``brand_row_to_dict(row)`` — wire shape for SPA.
- ``fetch_industries(session)`` — distinct industries for the filter.
- ``fetch_brands(session, *, page, per_page, q, industry, source, status)``
- ``get_brand(session, brand_id)``
- ``persist_brand_draft(session, draft, *, admin_id, brand_id=None)`` —
  insert or update; returns the persisted brand_id.
- ``archive_brand(session, brand_id)`` — soft-delete via status.
"""

from __future__ import annotations

import json as _json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.brand_management.lib import normalize_brand_draft

logger = logging.getLogger(__name__)


async def _table_exists(session: AsyncSession, name: str) -> bool:
    """True iff ``public.<name>`` exists. False on sqlite."""
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
    """Return columns of ``public.<name>``. Empty on sqlite."""
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


async def coerce_brand_columns(session: AsyncSession) -> set[str]:
    if not await _table_exists(session, "brands"):
        return set()
    return await _table_columns(session, "brands")


def select_brand_management_sql(cols: set[str]) -> str:
    """Build a SELECT clause with NULL fallbacks for missing columns.

    admin_console's ``brands`` table has different column sets across
    deployments (some envs have ``positioning`` / ``founded_year`` /
    ``aliases``, some don't). Mirror admin_console's defensive
    fallbacks so the SPA gets a consistent wire shape regardless.
    """
    pieces: list[str] = ["id"]
    pieces.append("name" if "name" in cols else "('Brand #' || id::text) AS name")
    for col, default in (
        ("name_zh", "NULL"),
        ("name_en", "NULL"),
        ("industry", "''"),
        ("target_market", "''"),
        ("description", "''"),
        ("positioning", "''"),
        ("headquarters", "''"),
        ("founded_year", "NULL::int"),
        ("aliases", "NULL::jsonb"),
        ("official_domains", "NULL::jsonb"),
        ("tags", "NULL::jsonb"),
        ("status", "'active'"),
        ("source", "'manual'"),
        ("created_by", "NULL"),
        ("created_at", "NULL::timestamp"),
        ("updated_at", "NULL::timestamp"),
    ):
        if col in cols:
            pieces.append(col)
        else:
            pieces.append(f"{default} AS {col}")
    return ", ".join(pieces)


def brand_row_to_dict(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convert a raw brands row into the SPA wire shape.

    Coerces JSONB columns (aliases / official_domains / tags) that may
    arrive as strings on some psycopg setups; defaults to empty lists
    on parse error.
    """
    if not row:
        return None
    aliases = row.get("aliases")
    if isinstance(aliases, str):
        try:
            aliases = _json.loads(aliases)
        except Exception:
            aliases = [aliases]
    domains = row.get("official_domains")
    if isinstance(domains, str):
        try:
            domains = _json.loads(domains)
        except Exception:
            domains = []
    tags = row.get("tags")
    if isinstance(tags, str):
        try:
            tags = _json.loads(tags)
        except Exception:
            tags = []
    raw_id = row.get("id")
    try:
        brand_id = int(raw_id) if raw_id is not None else None
    except (TypeError, ValueError):
        brand_id = None

    def _isoformat(value: Any) -> str | None:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return str(value.isoformat())
        return str(value)

    return {
        "id": brand_id,
        "name": row.get("name") or "",
        "name_zh": row.get("name_zh") or "",
        "name_en": row.get("name_en") or "",
        "industry": row.get("industry") or "",
        "target_market": row.get("target_market") or "",
        "description": row.get("description") or "",
        "positioning": row.get("positioning") or "",
        "headquarters": row.get("headquarters") or "",
        "founded_year": row.get("founded_year"),
        "aliases": aliases if isinstance(aliases, list) else [],
        "official_domains": domains if isinstance(domains, list) else [],
        "tags": tags if isinstance(tags, list) else [],
        "status": row.get("status") or "active",
        "source": row.get("source") or "manual",
        "created_by": row.get("created_by"),
        "created_at": _isoformat(row.get("created_at")),
        "updated_at": _isoformat(row.get("updated_at")),
    }


async def fetch_industries(session: AsyncSession) -> list[dict[str, Any]]:
    """Distinct industries currently present in ``brands``.

    Returns ``[]`` when the table doesn't exist (sqlite tests / fresh
    deploys) or when the ``industry`` column isn't on the table.
    """
    if not await _table_exists(session, "brands"):
        return []
    cols = await coerce_brand_columns(session)
    if "industry" not in cols:
        return []
    sql = text(
        """
        SELECT industry, COUNT(*)::int AS brand_count
        FROM brands
        WHERE industry IS NOT NULL AND industry <> ''
        GROUP BY industry
        ORDER BY brand_count DESC, industry ASC
        LIMIT 200
        """
    )
    rows = (await session.execute(sql)).mappings().all()
    return [{"industry": r["industry"], "brand_count": int(r["brand_count"] or 0)} for r in rows]


async def fetch_brands(
    session: AsyncSession,
    *,
    page: int = 1,
    per_page: int = 25,
    q: str | None = None,
    industry: str | None = None,
    source: str | None = None,
    status: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Paginated brand list with industry / source / status / search filters.

    Returns ``(rows, total)``. Empty list + 0 if the table doesn't exist.
    """
    from app.admin.brand_management.lib import (
        ALLOWED_BRAND_SOURCES,
        ALLOWED_BRAND_STATUSES,
    )

    page = max(1, int(page or 1))
    per_page = max(1, min(int(per_page or 25), 200))
    offset = (page - 1) * per_page

    if not await _table_exists(session, "brands"):
        return [], 0
    cols = await coerce_brand_columns(session)
    select_clause = select_brand_management_sql(cols)
    where: list[str] = ["TRUE"]
    params: dict[str, Any] = {}
    if industry and "industry" in cols:
        where.append("industry = :industry")
        params["industry"] = industry
    src = (source or "").strip().lower()
    if src and src in ALLOWED_BRAND_SOURCES and "source" in cols:
        where.append("source = :source")
        params["source"] = src
    sts = (status or "").strip().lower()
    if sts and sts in ALLOWED_BRAND_STATUSES and "status" in cols:
        where.append("status = :status")
        params["status"] = sts
    qq = (q or "").strip()
    if qq:
        params["like"] = "%" + qq.lower() + "%"
        like_clauses = ["LOWER(name) LIKE :like"]
        if "name_zh" in cols:
            like_clauses.append("LOWER(COALESCE(name_zh, '')) LIKE :like")
        if "name_en" in cols:
            like_clauses.append("LOWER(COALESCE(name_en, '')) LIKE :like")
        if "description" in cols:
            like_clauses.append("LOWER(COALESCE(description, '')) LIKE :like")
        where.append("(" + " OR ".join(like_clauses) + ")")
    where_sql = " AND ".join(where)

    total_row = (
        (
            await session.execute(
                text(f"SELECT COUNT(*) AS c FROM brands WHERE {where_sql}"),
                params,
            )
        )
        .mappings()
        .first()
    )
    total = int((dict(total_row) if total_row else {}).get("c") or 0)

    order_col = "updated_at" if "updated_at" in cols else "id"
    page_params = dict(params)
    page_params["limit"] = per_page
    page_params["offset"] = offset
    sql = text(
        f"""
        SELECT {select_clause}
        FROM brands
        WHERE {where_sql}
        ORDER BY {order_col} DESC NULLS LAST, id DESC
        LIMIT :limit OFFSET :offset
        """
    )
    rows_raw = (await session.execute(sql, page_params)).mappings().all()
    rows: list[dict[str, Any]] = []
    for r in rows_raw:
        wire = brand_row_to_dict(dict(r))
        if wire is not None:
            rows.append(wire)
    return rows, total


async def get_brand(session: AsyncSession, brand_id: int) -> dict[str, Any] | None:
    """Detail row by id. None when missing / table absent."""
    if not await _table_exists(session, "brands"):
        return None
    cols = await coerce_brand_columns(session)
    select_clause = select_brand_management_sql(cols)
    sql = text(f"SELECT {select_clause} FROM brands WHERE id = :id")
    row = (await session.execute(sql, {"id": brand_id})).mappings().first()
    return brand_row_to_dict(dict(row)) if row else None


async def persist_brand_draft(
    session: AsyncSession,
    draft: dict[str, Any],
    *,
    admin_id: str,
    brand_id: int | None = None,
) -> int:
    """Insert (when ``brand_id`` is None) or update a brands row.

    Returns the brand_id. Re-runs ``normalize_brand_draft`` on the
    incoming draft to defend against callers that bypass the route
    handler's normalization.
    """
    cols = await coerce_brand_columns(session)
    payload = normalize_brand_draft(draft)
    fields: list[str] = []
    placeholders: list[str] = []
    params: dict[str, Any] = {}

    def add(col: str, value: Any) -> None:
        if col not in cols:
            return
        fields.append(col)
        if isinstance(value, (list, dict)):
            placeholders.append(f"CAST(:{col} AS jsonb)")
            params[col] = _json.dumps(value, ensure_ascii=False)
        else:
            placeholders.append(f":{col}")
            params[col] = value

    add("name", payload["name"])
    add("name_zh", payload["name_zh"])
    add("name_en", payload["name_en"])
    add("industry", payload["industry"] or None)
    add("target_market", payload["target_market"] or None)
    add("description", payload["description"] or None)
    add("positioning", payload["positioning"] or None)
    add("headquarters", payload["headquarters"] or None)
    add("founded_year", payload["founded_year"])
    add("aliases", payload["aliases"])
    add("official_domains", payload["official_domains"])
    add("tags", payload["tags"])
    add("status", payload["status"])
    add("source", payload["source"])

    if brand_id is None:
        if "created_by" in cols:
            add("created_by", admin_id)
        sql = text(
            f"INSERT INTO brands ({', '.join(fields)}) "
            f"VALUES ({', '.join(placeholders)}) RETURNING id"
        )
        row = (await session.execute(sql, params)).mappings().first()
        await session.commit()
        if not row:
            raise RuntimeError("brand insert returned no row")
        return int(row["id"])

    set_pieces = [f"{f} = {p}" for f, p in zip(fields, placeholders, strict=False)]
    if "updated_at" in cols:
        set_pieces.append("updated_at = NOW()")
    if not set_pieces:
        return brand_id
    params["id"] = brand_id
    sql = text(f"UPDATE brands SET {', '.join(set_pieces)} WHERE id = :id")
    await session.execute(sql, params)
    await session.commit()
    return brand_id


async def archive_brand(session: AsyncSession, brand_id: int) -> bool:
    """Soft-delete a brand by flipping ``status='archived'``.

    Also archives the matching ``kg_brands`` row if that table exists
    (best-effort — not all envs run KG ingest). Returns ``True`` if a
    brand row matched, ``False`` if the brand_id is unknown.
    """
    if not await _table_exists(session, "brands"):
        return False
    row = (
        await session.execute(text("SELECT id FROM brands WHERE id = :id"), {"id": brand_id})
    ).first()
    if not row:
        return False
    cols = await coerce_brand_columns(session)
    if "status" in cols:
        await session.execute(
            text("UPDATE brands SET status = 'archived' WHERE id = :id"),
            {"id": brand_id},
        )
    if await _table_exists(session, "kg_brands"):
        try:
            await session.execute(
                text(
                    "UPDATE kg_brands SET status = 'archived', updated_at = NOW() "
                    "WHERE brand_id = :id"
                ),
                {"id": brand_id},
            )
        except Exception as exc:
            logger.warning("kg_brands archive mirror failed: %s", exc)
    await session.commit()
    return True


async def brand_name_exists(
    session: AsyncSession, name: str, *, exclude_id: int | None = None
) -> bool:
    """Returns True iff a non-archived brand with this name (case-folded)
    already exists. Used to map admin_console's psycopg2.UniqueViolation
    to a 409 ``duplicate_brand_name`` response.
    """
    if not await _table_exists(session, "brands"):
        return False
    cols = await coerce_brand_columns(session)
    if "name" not in cols:
        return False
    sql = "SELECT id FROM brands WHERE LOWER(name) = LOWER(:name)"
    params: dict[str, Any] = {"name": name}
    if exclude_id is not None:
        sql += " AND id <> :exclude_id"
        params["exclude_id"] = exclude_id
    sql += " LIMIT 1"
    row = (await session.execute(text(sql), params)).first()
    return row is not None


# ---------------------------------------------------------------------------
# Phase 7 slice 7a-bis — generate / enrich / import support
# ---------------------------------------------------------------------------


import uuid as _uuid  # noqa: E402


async def fetch_industry_seeds(
    session: AsyncSession, industry: str, *, limit: int = 200
) -> list[str]:
    """Existing brand names in ``industry`` — used as ``exclude_brands``
    when calling the LLM so generate doesn't re-suggest known players.
    """
    if not await _table_exists(session, "brands"):
        return []
    cols = await coerce_brand_columns(session)
    if "industry" not in cols or "name" not in cols:
        return []
    sql = text("SELECT name FROM brands WHERE industry = :industry ORDER BY id LIMIT :limit")
    rows = (await session.execute(sql, {"industry": industry, "limit": limit})).mappings().all()
    return [str(r["name"]) for r in rows if r.get("name")]


async def write_brand_generation_log(
    session: AsyncSession,
    *,
    admin_id: str,
    industry: str,
    seeds: list[str],
    model: str,
    prompt: str,
    payload: dict[str, Any],
    items: list[dict[str, Any]],
    usage: dict[str, Any],
    estimated_cost: float | None,
) -> None:
    """Best-effort INSERT into ``brand_generation_logs``.

    Uses ``begin_nested`` so a missing-table failure on sqlite tests
    doesn't poison the worker's session for the subsequent emit_audit.
    """
    nested = await session.begin_nested()
    try:
        await session.execute(
            text(
                """
                INSERT INTO brand_generation_logs
                    (id, industry, seed_brands, llm_model, prompt_used,
                     input_params, output_json, brands_generated,
                     tokens_used, estimated_cost, created_by, created_at)
                VALUES
                    (:id, :industry, CAST(:seed_brands AS jsonb), :llm_model,
                     :prompt_used, CAST(:input_params AS jsonb),
                     CAST(:output_json AS jsonb), :brands_generated,
                     :tokens_used, :estimated_cost, :created_by, NOW())
                """
            ),
            {
                "id": str(_uuid.uuid4()),
                "industry": industry,
                "seed_brands": _json.dumps(seeds, ensure_ascii=False),
                "llm_model": model,
                "prompt_used": prompt,
                "input_params": _json.dumps(payload, default=str, ensure_ascii=False),
                "output_json": _json.dumps(items, default=str, ensure_ascii=False),
                "brands_generated": len(items),
                "tokens_used": int((usage or {}).get("total_tokens") or 0),
                "estimated_cost": estimated_cost,
                "created_by": admin_id,
            },
        )
        await nested.commit()
    except Exception as exc:
        try:
            await nested.rollback()
        except Exception:
            pass
        logger.warning("brand_generation_logs INSERT failed (table missing?): %s", exc)


async def import_brands_bulk(
    session: AsyncSession,
    drafts: list[Any] | None,
    *,
    admin_id: str,
    default_industry: str = "",
) -> dict[str, Any]:
    """Bulk-upsert reviewed brand drafts.

    Per-row: normalize via ``normalize_brand_draft`` (skipped on error),
    then UPSERT keyed on ``LOWER(name)`` if the name already exists,
    else INSERT. The optional ``kg_brands`` mirror admin_console wrote
    on each row is intentionally NOT done here — Phase 7a-bis stays
    surgical; ``kg_discovery`` repopulates kg_brands periodically.
    Returns ``{added, updated, skipped, results}``.
    """
    from app.admin.brand_management.lib import (
        BrandManagementError,
        normalize_brand_draft,
    )

    if not await _table_exists(session, "brands"):
        raise BrandManagementError("brands_table_missing", "brands table is not available")
    cols = await coerce_brand_columns(session)
    if "name" not in cols:
        raise BrandManagementError("brands_table_missing", "brands.name column required")

    added = 0
    updated = 0
    skipped = 0
    results: list[dict[str, Any]] = []

    for raw in drafts or []:
        try:
            draft = normalize_brand_draft(raw, default_industry=default_industry)
        except BrandManagementError as error:
            skipped += 1
            results.append(
                {
                    "skipped": True,
                    "error": error.code,
                    "message": error.message,
                }
            )
            continue
        # match-by-name → update; else → insert.
        existing = (
            await session.execute(
                text("SELECT id FROM brands WHERE LOWER(name) = LOWER(:name) LIMIT 1"),
                {"name": draft["name"]},
            )
        ).first()
        try:
            if existing:
                brand_id = int(existing[0])
                await persist_brand_draft(session, draft, admin_id=admin_id, brand_id=brand_id)
                updated += 1
                results.append({"brand_id": brand_id, "name": draft["name"], "outcome": "updated"})
            else:
                brand_id = await persist_brand_draft(session, draft, admin_id=admin_id)
                added += 1
                results.append({"brand_id": brand_id, "name": draft["name"], "outcome": "added"})
        except Exception as exc:
            skipped += 1
            results.append(
                {
                    "skipped": True,
                    "name": draft.get("name"),
                    "error": "brand_persist_failed",
                    "message": str(exc)[:300],
                }
            )

    return {
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "results": results,
    }
