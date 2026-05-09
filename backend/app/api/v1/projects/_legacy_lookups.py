"""Helpers to resolve legacy `brands` / `topics` table values.

The `brands` and `topics` tables predate the genpano_models ORM (they live in
the upstream Tracker schema). They are referenced by FK from `geo_score_daily`,
`brand_mentions`, `topic_score_daily`, `project_topic_pins`, etc. but have no
SQLAlchemy model in this repo. These helpers centralize the raw-SQL lookups so
service modules don't have to repeat them.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def resolve_brand_name(session: AsyncSession, brand_id: int) -> str | None:
    """Return the best display name for a brand_id, or None if not found."""
    try:
        row = await session.execute(
            text(
                "SELECT COALESCE(NULLIF(name_zh, ''), NULLIF(name_en, ''), name) "
                "FROM brands WHERE id = :id"
            ),
            {"id": brand_id},
        )
        return row.scalar_one_or_none()
    except Exception:
        # Table missing on dev / SQLite — caller should tolerate None.
        return None


async def resolve_brand_names(
    session: AsyncSession, brand_ids: list[int]
) -> dict[int, str]:
    """Bulk lookup; returns {brand_id: display_name}. Missing rows omitted."""
    if not brand_ids:
        return {}
    try:
        result = await session.execute(
            text(
                "SELECT id, COALESCE(NULLIF(name_zh, ''), NULLIF(name_en, ''), name) "
                "FROM brands WHERE id = ANY(:ids)"
            ),
            {"ids": list(brand_ids)},
        )
        return {int(r[0]): r[1] for r in result.all() if r[1]}
    except Exception:
        # Fallback: try IN-clause for SQLite (no array support).
        try:
            placeholders = ",".join(f":id{i}" for i in range(len(brand_ids)))
            params = {f"id{i}": v for i, v in enumerate(brand_ids)}
            result = await session.execute(
                text(
                    "SELECT id, COALESCE(NULLIF(name_zh, ''), NULLIF(name_en, ''), name) "
                    f"FROM brands WHERE id IN ({placeholders})"
                ),
                params,
            )
            return {int(r[0]): r[1] for r in result.all() if r[1]}
        except Exception:
            return {}


async def resolve_brand_industry(
    session: AsyncSession, brand_id: int
) -> str | None:
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


async def resolve_topic_names(
    session: AsyncSession, topic_ids: list[int]
) -> dict[int, str]:
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
    """Return the brand's top topics (by recent mention_count) with names.

    Reads `topic_score_daily` over the most recent 30 days and joins to the
    legacy `topics` table for the display string.
    """
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
