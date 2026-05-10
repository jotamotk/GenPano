"""Service layer for Brands."""

from __future__ import annotations

from genpano_models import Project
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.brands._dto import BrandSearchHit


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

    # Aliases is a JSONB array of alternate names (Chinese / English / typos).
    # Probe schema once so the query stays portable across SQLite (test bind,
    # no JSONB) and Postgres (prod). Falls back to name-only matching on
    # SQLite or when the column is absent.
    has_aliases = False
    try:
        col_row = (
            await session.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'brands' "
                    "AND column_name = 'aliases' LIMIT 1"
                )
            )
        ).first()
        has_aliases = col_row is not None
    except Exception:
        has_aliases = False

    aliases_clause = (
        " OR EXISTS (SELECT 1 FROM jsonb_array_elements_text(COALESCE(aliases, '[]'::jsonb)) AS a "
        "WHERE LOWER(a) LIKE :pattern)"
        if has_aliases
        else ""
    )

    try:
        result = await session.execute(
            text(
                f"""
                SELECT
                    id,
                    COALESCE(NULLIF(name_zh, ''), NULLIF(name_en, ''), name) AS display_name,
                    industry
                FROM brands
                WHERE
                    LOWER(COALESCE(name_zh, '')) LIKE :pattern
                    OR LOWER(COALESCE(name_en, '')) LIKE :pattern
                    OR LOWER(COALESCE(name, '')) LIKE :pattern
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
