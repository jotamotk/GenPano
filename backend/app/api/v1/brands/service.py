"""Service layer for Brands."""

from __future__ import annotations

import logging

from genpano_models import Project
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.brands._dto import BrandSearchHit
from app.api.v1.projects._legacy_lookups import brand_display_expr, brand_table_columns

logger = logging.getLogger(__name__)


async def search_brands(
    session: AsyncSession,
    *,
    q: str,
    limit: int = 10,
    user_id: str | None = None,
) -> list[BrandSearchHit]:
    """Fuzzy search the legacy `brands` table by name (zh / en / canonical).

    Returns up to `limit` hits, ranked alphabetically by display name. Each
    hit carries `is_already_monitoring=True` when the calling user already
    has a non-deleted Project whose primary_brand_id equals that brand.

    The `brands` table predates this app's ORM (see `_legacy_lookups.py`),
    so we use raw SQL with a `LOWER(...) LIKE` clause that works on both
    SQLite and Postgres. Errors (table missing on dev / fresh deployment)
    return an empty list — same fallback contract as `_legacy_lookups`.
    """
    q_norm = q.strip()
    if not q_norm:
        return []
    pattern = f"%{q_norm.lower()}%"
    capped = max(1, min(limit, 50))

    cols = await brand_table_columns(session)
    display_expr = brand_display_expr(cols)
    if display_expr is None:
        return []

    name_clauses = [
        f"LOWER(COALESCE({col}, '')) LIKE :pattern"
        for col in ("name_zh", "name_en", "name", "primary_name")
        if col in cols
    ]
    if not name_clauses:
        return []

    dialect_name = ""
    try:
        dialect_name = session.get_bind().dialect.name
    except Exception:
        dialect_name = ""

    # Aliases is JSONB in production Postgres; skip it on SQLite test binds.
    has_aliases = "aliases" in cols and dialect_name == "postgresql"
    industry_expr = "industry" if "industry" in cols else "NULL"

    rows = await _query_brands(
        session,
        pattern=pattern,
        lim=capped,
        display_expr=display_expr,
        industry_expr=industry_expr,
        name_clauses=name_clauses,
        with_aliases=has_aliases,
    )

    monitored: set[int] = set()
    if user_id:
        stmt = select(Project.primary_brand_id).where(
            Project.user_id == user_id,
            Project.deleted_at.is_(None),
            Project.primary_brand_id.is_not(None),
        )
        for row in (await session.execute(stmt)).all():
            if row[0] is not None:
                monitored.add(int(row[0]))

    hits: list[BrandSearchHit] = []
    for r in rows:
        brand_id = int(r[0])
        display = r[1] or f"brand-{brand_id}"
        hits.append(
            BrandSearchHit(
                brand_id=brand_id,
                brand_name=display,
                industry=r[2],
                is_already_monitoring=brand_id in monitored,
            )
        )
    return hits


async def _query_brands(
    session: AsyncSession,
    *,
    pattern: str,
    lim: int,
    display_expr: str,
    industry_expr: str,
    name_clauses: list[str],
    with_aliases: bool,
) -> list[tuple[int, str, str | None]]:
    """Run the brand-search SELECT, falling back to name-only when the
    aliases JSONB sub-clause errors out (e.g. some row has a non-array
    aliases value, which would fail jsonb_array_elements_text). All
    failures are logged so the silent-empty-result mode that bit us in
    PR #438 is observable in prod logs.
    """
    aliases_clause = (
        " OR EXISTS (SELECT 1 FROM jsonb_array_elements_text("
        "COALESCE(aliases, '[]'::jsonb)) AS a WHERE LOWER(a) LIKE :pattern)"
        if with_aliases
        else ""
    )
    name_only_select = f"""
        SELECT
            id,
            {display_expr} AS display_name,
            {industry_expr} AS industry
        FROM brands
        WHERE
            {" OR ".join(name_clauses)}
    """
    sql = text(f"{name_only_select} {aliases_clause} ORDER BY display_name LIMIT :lim")
    try:
        rows = (await session.execute(sql, {"pattern": pattern, "lim": lim})).all()
        return [(int(r[0]), str(r[1]) if r[1] is not None else "", r[2]) for r in rows]
    except Exception:
        logger.exception(
            "search_brands: primary query failed (with_aliases=%s); will retry without aliases",
            with_aliases,
        )
    if not with_aliases:
        return []
    try:
        rows = (
            await session.execute(
                text(f"{name_only_select} ORDER BY display_name LIMIT :lim"),
                {"pattern": pattern, "lim": lim},
            )
        ).all()
        return [(int(r[0]), str(r[1]) if r[1] is not None else "", r[2]) for r in rows]
    except Exception:
        logger.exception("search_brands: name-only fallback also failed; returning []")
        return []
