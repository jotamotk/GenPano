"""Service layer for Brands."""

from __future__ import annotations

from genpano_models import Project
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.brands._dto import BrandSearchHit
from app.api.v1.projects._legacy_lookups import brand_display_expr, brand_table_columns


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
    aliases_clause = (
        " OR EXISTS (SELECT 1 FROM jsonb_array_elements_text(COALESCE(aliases, '[]'::jsonb)) AS a "
        "WHERE LOWER(a) LIKE :pattern)"
        if "aliases" in cols and dialect_name == "postgresql"
        else ""
    )
    industry_expr = "industry" if "industry" in cols else "NULL"

    try:
        result = await session.execute(
            text(
                f"""
                SELECT
                    id,
                    {display_expr} AS display_name,
                    {industry_expr} AS industry
                FROM brands
                WHERE
                    {" OR ".join(name_clauses)}
                    {aliases_clause}
                ORDER BY display_name
                LIMIT :lim
                """
            ),
            {"pattern": pattern, "lim": capped},
        )
        rows = result.all()
    except Exception:
        return []

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
