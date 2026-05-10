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
