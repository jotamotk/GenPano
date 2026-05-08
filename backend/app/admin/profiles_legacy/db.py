"""DB operations for the legacy profile API (Phase 9 slice 9d).

The ``profiles`` table comes in two flavors across the production fleet:
- geo_tracker original (INTEGER id + name + age_range + location etc.)
- segments-based (VARCHAR id 'pf_xxx' + code + segment_id)

The CRUD endpoints in this slice target the geo_tracker flavor
(integer id, used by admin.html's profile management tab). The
``lite`` and ``similar`` endpoints probe ``information_schema`` so
they work on both flavors (mirroring admin_console exactly).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


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


async def list_profiles(session: AsyncSession) -> list[dict[str, Any]]:
    """List geo_tracker-flavor profiles + per-profile query_count.
    Returns ``[]`` when the table doesn't exist (sqlite test fixture)."""
    if not await _table_exists(session, "profiles"):
        return []
    sql = text(
        """
        SELECT p.id, p.name, p.age_range, p.location, p.country_code,
               p.profession, p.language, p.device_type, p.persona_traits,
               COALESCE(qc.cnt, 0) AS query_count
        FROM profiles p
        LEFT JOIN (
            SELECT profile_id, COUNT(*) AS cnt
            FROM queries
            GROUP BY profile_id
        ) qc ON p.id = qc.profile_id
        ORDER BY p.id
        """
    )
    rows = (await session.execute(sql)).mappings().all()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        traits = item.get("persona_traits")
        if isinstance(traits, str):
            try:
                item["persona_traits"] = json.loads(traits)
            except Exception:
                item["persona_traits"] = {}
        elif not traits:
            item["persona_traits"] = {}
        out.append(item)
    return out


async def create_profile(session: AsyncSession, *, payload: dict[str, Any]) -> int | None:
    """INSERT and return the new id; ``None`` when the table is missing."""
    if not await _table_exists(session, "profiles"):
        return None
    sql = text(
        """
        INSERT INTO profiles
            (name, age_range, location, country_code,
             profession, language, device_type, persona_traits)
        VALUES (:name, :age_range, :location, :country_code,
                :profession, :language, :device_type,
                CAST(:persona_traits AS jsonb))
        RETURNING id
        """
    )
    row = (
        (
            await session.execute(
                sql,
                {
                    "name": payload["name"],
                    "age_range": payload.get("age_range", ""),
                    "location": payload.get("location", ""),
                    "country_code": payload.get("country_code", ""),
                    "profession": payload.get("profession", ""),
                    "language": payload.get("language", "zh"),
                    "device_type": payload.get("device_type", "desktop"),
                    "persona_traits": json.dumps(
                        payload.get("persona_traits", {}), ensure_ascii=False
                    ),
                },
            )
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    await session.commit()
    return int(dict(row)["id"])


async def update_profile(
    session: AsyncSession, *, profile_id: int, payload: dict[str, Any]
) -> bool:
    """Update a profile by id. Returns False when the row is missing."""
    if not await _table_exists(session, "profiles"):
        return False
    sql = text(
        """
        UPDATE profiles
        SET name = :name,
            age_range = :age_range,
            location = :location,
            country_code = :country_code,
            profession = :profession,
            language = :language,
            device_type = :device_type,
            persona_traits = CAST(:persona_traits AS jsonb)
        WHERE id = :id
        """
    )
    result = await session.execute(
        sql,
        {
            "id": profile_id,
            "name": payload["name"],
            "age_range": payload.get("age_range", ""),
            "location": payload.get("location", ""),
            "country_code": payload.get("country_code", ""),
            "profession": payload.get("profession", ""),
            "language": payload.get("language", "zh"),
            "device_type": payload.get("device_type", "desktop"),
            "persona_traits": json.dumps(payload.get("persona_traits", {}), ensure_ascii=False),
        },
    )
    if (getattr(result, "rowcount", 0) or 0) == 0:
        await session.rollback()
        return False
    await session.commit()
    return True


async def delete_profile(session: AsyncSession, profile_id: int) -> tuple[bool, int]:
    """Cascade-NULL queries.profile_id + llm_accounts.profile_id, then
    delete browser_profiles + the profile row. Returns ``(deleted,
    unlinked_query_count)``."""
    if not await _table_exists(session, "profiles"):
        return False, 0
    unlinked = 0
    if await _table_exists(session, "queries"):
        cnt_row = (
            (
                await session.execute(
                    text("SELECT COUNT(*) AS n FROM queries WHERE profile_id = :id"),
                    {"id": profile_id},
                )
            )
            .mappings()
            .first()
        )
        unlinked = int((dict(cnt_row) if cnt_row else {}).get("n") or 0)
        if unlinked > 0:
            await session.execute(
                text("UPDATE queries SET profile_id = NULL WHERE profile_id = :id"),
                {"id": profile_id},
            )
    if await _table_exists(session, "browser_profiles"):
        await session.execute(
            text("DELETE FROM browser_profiles WHERE profile_id = :id"),
            {"id": profile_id},
        )
    if await _table_exists(session, "llm_accounts"):
        await session.execute(
            text("UPDATE llm_accounts SET profile_id = NULL WHERE profile_id = :id"),
            {"id": profile_id},
        )
    result = await session.execute(text("DELETE FROM profiles WHERE id = :id"), {"id": profile_id})
    if (getattr(result, "rowcount", 0) or 0) == 0:
        await session.rollback()
        return False, 0
    await session.commit()
    return True, unlinked


async def list_profiles_lite(
    session: AsyncSession, *, q: str | None = None, limit: int = 200
) -> list[dict[str, Any]]:
    """Schema-aware lite picker. Returns ``[]`` when ``profiles`` is
    missing. Mirrors admin_console line 9290 — accepts both schema flavors."""
    if not await _table_exists(session, "profiles"):
        return []
    cols = await _table_columns(session, "profiles")
    select_parts = ["p.id::text AS id"]
    select_parts.append("COALESCE(p.code, '') AS code" if "code" in cols else "'' AS code")
    select_parts.append("p.name" if "name" in cols else "NULL AS name")
    select_parts.append("p.segment_id" if "segment_id" in cols else "NULL AS segment_id")
    select_parts.append(
        "p.brand_id::text AS brand_id" if "brand_id" in cols else "NULL AS brand_id"
    )

    where: list[str] = []
    params: dict[str, Any] = {"limit": int(limit)}
    if q:
        conds = ["p.id::text ILIKE :q"]
        if "code" in cols:
            conds.append("COALESCE(p.code,'') ILIKE :q")
        if "name" in cols:
            conds.append("COALESCE(p.name,'') ILIKE :q")
        where.append("(" + " OR ".join(conds) + ")")
        params["q"] = f"%{q}%"
    if "is_deleted" in cols:
        where.append("COALESCE(p.is_deleted, FALSE) = FALSE")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    sql = text(
        f"""
        SELECT {", ".join(select_parts)}
        FROM profiles p
        {where_sql}
        ORDER BY p.id::text
        LIMIT :limit
        """
    )
    rows = (await session.execute(sql, params)).mappings().all()
    return [dict(r) for r in rows]


async def find_similar_profiles(
    session: AsyncSession, *, profile_id: str, limit: int = 20
) -> dict[str, Any] | None:
    """Heuristic similarity:
    1. Same segment_id → ``strategy='same_segment'``
    2. Same brand_id → ``strategy='same_brand'``
    3. Else fallback (other rows by id proximity) → ``strategy='fallback'``

    Returns ``None`` when the seed profile doesn't exist, mirroring
    admin_console's 404 behaviour."""
    if not await _table_exists(session, "profiles"):
        return None
    cols = await _table_columns(session, "profiles")
    seed_select = [
        "p.id::text AS id",
        "p.segment_id" if "segment_id" in cols else "NULL AS segment_id",
        "p.brand_id" if "brand_id" in cols else "NULL AS brand_id",
        "p.name" if "name" in cols else "NULL AS name",
    ]
    seed_row = (
        (
            await session.execute(
                text(f"SELECT {', '.join(seed_select)} FROM profiles p WHERE p.id::text = :id"),
                {"id": str(profile_id)},
            )
        )
        .mappings()
        .first()
    )
    if not seed_row:
        return None
    seed = dict(seed_row)

    select_parts = [
        "p.id::text AS id",
        "p.code" if "code" in cols else "'' AS code",
        "p.name" if "name" in cols else "NULL AS name",
        "p.segment_id" if "segment_id" in cols else "NULL AS segment_id",
    ]
    deleted_clause = " AND COALESCE(p.is_deleted, FALSE) = FALSE" if "is_deleted" in cols else ""

    if "segment_id" in cols and seed.get("segment_id"):
        sql = text(
            f"""
            SELECT {", ".join(select_parts)}
            FROM profiles p
            WHERE p.segment_id = :segment_id
              AND p.id::text != :id{deleted_clause}
            ORDER BY p.id::text
            LIMIT :limit
            """
        )
        params = {
            "segment_id": seed["segment_id"],
            "id": str(profile_id),
            "limit": int(limit),
        }
        strategy = "same_segment"
    elif "brand_id" in cols and seed.get("brand_id"):
        sql = text(
            f"""
            SELECT {", ".join(select_parts)}
            FROM profiles p
            WHERE p.brand_id = :brand_id
              AND p.id::text != :id{deleted_clause}
            ORDER BY p.id::text
            LIMIT :limit
            """
        )
        params = {
            "brand_id": seed["brand_id"],
            "id": str(profile_id),
            "limit": int(limit),
        }
        strategy = "same_brand"
    else:
        sql = text(
            f"""
            SELECT {", ".join(select_parts)}
            FROM profiles p
            WHERE p.id::text != :id{deleted_clause}
            ORDER BY p.id::text
            LIMIT :limit
            """
        )
        params = {"id": str(profile_id), "limit": int(limit)}
        strategy = "fallback"

    rows = (await session.execute(sql, params)).mappings().all()
    return {
        "seed": seed,
        "strategy": strategy,
        "rows": [dict(r) for r in rows],
    }


__all__ = [
    "create_profile",
    "delete_profile",
    "find_similar_profiles",
    "list_profiles",
    "list_profiles_lite",
    "update_profile",
]
