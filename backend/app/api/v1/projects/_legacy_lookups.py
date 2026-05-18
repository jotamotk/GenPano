"""Helpers to resolve legacy `brands` / `topics` table values.

The `brands` and `topics` tables predate the genpano_models ORM. They are
referenced by FK from rollup tables but have no SQLAlchemy model here.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

BRAND_NAME_COLUMNS = ("name_zh", "name_en", "name", "primary_name")


async def brand_table_columns(session: AsyncSession) -> set[str]:
    """Return available columns on legacy `brands`, portable across DBs."""
    try:
        rows = (
            await session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'brands'"
                )
            )
        ).all()
        cols = {str(r[0]) for r in rows}
        if cols:
            return cols
    except Exception:
        pass

    try:
        rows = (await session.execute(text("PRAGMA table_info(brands)"))).all()
        return {str(r[1]) for r in rows}
    except Exception:
        return set()


def brand_display_expr(cols: set[str]) -> str | None:
    """SQL expression for best-effort brand display name."""
    name_cols = [c for c in BRAND_NAME_COLUMNS if c in cols]
    if not name_cols:
        return None
    parts = [f"NULLIF({c}, '')" for c in name_cols]
    return f"COALESCE({', '.join(parts)}, 'brand-' || CAST(id AS TEXT))"


async def resolve_brand_name(session: AsyncSession, brand_id: int) -> str | None:
    """Return the best display name for a brand_id, or None if not found."""
    names = await resolve_brand_names(session, [brand_id])
    return names.get(int(brand_id))


async def resolve_brand_names(session: AsyncSession, brand_ids: list[int]) -> dict[int, str]:
    """Bulk lookup; returns {brand_id: display_name}. Missing rows omitted."""
    if not brand_ids:
        return {}

    cols = await brand_table_columns(session)
    display = brand_display_expr(cols)
    if display is None:
        return {}

    try:
        placeholders = ",".join(f":id{i}" for i in range(len(brand_ids)))
        params = {f"id{i}": v for i, v in enumerate(brand_ids)}
        result = await session.execute(
            text(f"SELECT id, {display} FROM brands WHERE id IN ({placeholders})"),
            params,
        )
        return {int(r[0]): r[1] for r in result.all() if r[1]}
    except Exception:
        return {}


async def resolve_brand_industry(session: AsyncSession, brand_id: int) -> str | None:
    """Return the legacy `brands.industry` text for filtering benchmarks."""
    try:
        row = await session.execute(
            text("SELECT industry FROM brands WHERE id = :id"),
            {"id": brand_id},
        )
        return row.scalar_one_or_none()
    except Exception:
        return None


async def resolve_brand_industry_by_name(
    session: AsyncSession, brand_name: str | None
) -> str | None:
    """Resolve a free-form brand mention to ``brands.industry`` (or None).

    Issue #1192 / #1185 — competitor leak fix: name-only mention buckets
    (``brand_mentions.brand_id IS NULL``) need an industry attribution
    before the unified industry filter can keep or drop them. This
    helper does the forward lookup that ``brand_mention_names`` does in
    reverse (id -> set of names).

    Match strategy (case-insensitive, trimmed) - first hit wins:
      1. Any of the legacy display columns (``name_zh``, ``name_en``,
         ``name``, ``primary_name``).
      2. The ``aliases`` JSONB array if present.

    Returns ``None`` when no match resolves OR when the resolved row's
    ``industry`` is empty - callers treat ``None`` as 'cannot scope -
    drop'.
    """
    if brand_name is None:
        return None
    cleaned = str(brand_name).strip()
    if not cleaned:
        return None
    cleaned_lower = cleaned.casefold()

    cols = await brand_table_columns(session)
    name_cols = [c for c in BRAND_NAME_COLUMNS if c in cols]
    if not name_cols and "aliases" not in cols:
        return None

    # Step 1: direct name-column match. Build a portable case-insensitive
    # comparison across both Postgres and SQLite.
    if name_cols:
        or_parts = [f"LOWER(TRIM({c})) = :n" for c in name_cols]
        sql = f"SELECT industry FROM brands WHERE {' OR '.join(or_parts)} LIMIT 1"  # noqa: S608
        try:
            row = (
                await session.execute(text(sql), {"n": cleaned_lower})
            ).one_or_none()
            if row is not None and row[0]:
                return str(row[0])
        except Exception:
            pass

    # Step 2: scan aliases JSONB. Use Postgres jsonb_array_elements_text
    # when available; fall back to a Python scan for SQLite tests where
    # aliases is stored as JSON text.
    if "aliases" in cols:
        try:
            alias_rows = (
                await session.execute(
                    text(
                        """
                        SELECT industry
                        FROM brands b,
                             LATERAL jsonb_array_elements_text(
                               CASE WHEN jsonb_typeof(b.aliases) = 'array'
                                    THEN b.aliases ELSE '[]'::jsonb END
                             ) AS a(alias)
                        WHERE LOWER(TRIM(a.alias)) = :n
                        LIMIT 1
                        """
                    ),
                    {"n": cleaned_lower},
                )
            ).one_or_none()
            if alias_rows is not None and alias_rows[0]:
                return str(alias_rows[0])
        except Exception:
            # SQLite fallback: scan all rows and JSON-parse the aliases
            # column in Python.
            try:
                import json

                rows = (
                    await session.execute(
                        text("SELECT industry, aliases FROM brands WHERE aliases IS NOT NULL")
                    )
                ).all()
                for industry, aliases_val in rows:
                    if not aliases_val or not industry:
                        continue
                    try:
                        aliases = (
                            json.loads(aliases_val)
                            if isinstance(aliases_val, str)
                            else aliases_val
                        )
                    except Exception:
                        continue
                    if not isinstance(aliases, list):
                        continue
                    for entry in aliases:
                        if entry is None:
                            continue
                        if str(entry).strip().casefold() == cleaned_lower:
                            return str(industry)
            except Exception:
                pass

    return None


async def resolve_topic_name(session: AsyncSession, topic_id: int) -> str | None:
    """Return the legacy `topics.text` (the human-readable topic title)."""
    try:
        row = await session.execute(
            text("SELECT text FROM topics WHERE id = :id"),
            {"id": topic_id},
        )
        return row.scalar_one_or_none()
    except Exception:
        return None


async def resolve_topic_names(session: AsyncSession, topic_ids: list[int]) -> dict[int, str]:
    """Bulk lookup of topic display names."""
    if not topic_ids:
        return {}
    try:
        result = await session.execute(
            text("SELECT id, text FROM topics WHERE id = ANY(:ids)"),
            {"ids": list(topic_ids)},
        )
        return {int(r[0]): r[1] for r in result.all() if r[1]}
    except Exception:
        try:
            placeholders = ",".join(f":id{i}" for i in range(len(topic_ids)))
            params = {f"id{i}": v for i, v in enumerate(topic_ids)}
            result = await session.execute(
                text(f"SELECT id, text FROM topics WHERE id IN ({placeholders})"),
                params,
            )
            return {int(r[0]): r[1] for r in result.all() if r[1]}
        except Exception:
            return {}


async def resolve_top_topics_for_brand(
    session: AsyncSession, brand_id: int, limit: int = 20
) -> list[tuple[int, str | None]]:
    """Return the brand's top topics by recent mention_count with names."""
    try:
        result = await session.execute(
            text(
                """
                SELECT tsd.topic_id, t.text
                FROM topic_score_daily tsd
                LEFT JOIN topics t ON t.id = tsd.topic_id
                WHERE tsd.brand_id = :bid
                  AND tsd.date >= NOW() - INTERVAL '30 days'
                GROUP BY tsd.topic_id, t.text
                ORDER BY SUM(COALESCE(tsd.mention_count, 0)) DESC
                LIMIT :lim
                """
            ),
            {"bid": brand_id, "lim": limit},
        )
        return [(int(r[0]), r[1]) for r in result.all()]
    except Exception:
        return []
