"""DB operations for segments — Phase 6 slice 6a.

Vendored from admin_console/app.py 9254-9468. Uses the ORM ``Segment``
+ ``Profile`` models for the writes (sqlite-friendly) and raw SQL for
the read-side aggregations (``profile_count`` JOIN, summary stats —
identical to admin_console so the SPA gets the same numbers).

Public:
- ``fetch_segments(session, *, page, per_page, q, status, industry_id, brand_id)``
- ``get_segment(session, segment_id)``
- ``create_segment(session, payload, admin_id)``
- ``update_segment(session, segment_id, payload, admin_id)``
- ``soft_delete_segment(session, segment_id, admin_id)``
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from genpano_models import Profile, Segment
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.segments.lib import segment_payload, segment_row


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# READ
# ---------------------------------------------------------------------------


async def fetch_segments(
    session: AsyncSession,
    *,
    page: int = 1,
    per_page: int = 50,
    q: str | None = None,
    status: str | None = None,
    industry_id: str | None = None,
    brand_id: str | None = None,
) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    """Page + filter + summarise segments.

    Returns ``(rows, total, summary)`` where ``rows`` are wire-shape
    dicts, ``total`` is the unpaged count under the same filters, and
    ``summary`` carries the dashboard-counter fields admin_console
    surfaces (``segment_count`` / ``active_segment_count`` /
    ``profile_count`` / ``active_profile_count`` / ``active_weight_sum``).
    """
    page = max(int(page or 1), 1)
    per_page = max(1, min(int(per_page or 50), 200))
    offset = (page - 1) * per_page
    where: list[str] = [
        "COALESCE(s.is_deleted, FALSE) = FALSE",
        "COALESCE(s.status, 'draft') <> 'deleted'",
    ]
    params: dict[str, Any] = {}
    qq = (q or "").strip()
    if qq:
        params["like"] = f"%{qq}%"
        where.append(
            "(s.id ILIKE :like OR COALESCE(s.code, '') ILIKE :like "
            "OR s.name ILIKE :like OR COALESCE(s.brand_name, '') ILIKE :like "
            "OR COALESCE(s.industry, '') ILIKE :like "
            "OR COALESCE(s.status, '') ILIKE :like "
            "OR COALESCE(s.note, '') ILIKE :like)"
        )
    s_status = (status or "").strip().lower()
    if s_status and s_status != "all":
        where.append("s.status = :status")
        params["status"] = s_status
    s_industry = (industry_id or "").strip()
    if s_industry:
        where.append(
            "(COALESCE(s.industry_id, '') = :industry OR COALESCE(s.industry, '') = :industry)"
        )
        params["industry"] = s_industry
    s_brand = (brand_id or "").strip()
    if s_brand:
        where.append("COALESCE(s.brand_id, '') = :brand_id")
        params["brand_id"] = s_brand
    where_clause = " AND ".join(where)

    total_row = (
        (
            await session.execute(
                text(f"SELECT COUNT(*) AS cnt FROM segments s WHERE {where_clause}"),
                params,
            )
        )
        .mappings()
        .first()
    )
    total = int((dict(total_row) if total_row else {}).get("cnt") or 0)

    page_params = dict(params)
    page_params["limit"] = per_page
    page_params["offset"] = offset
    list_sql = text(
        f"""
        SELECT s.*,
               COALESCE(pc.profile_count, 0) AS profile_count,
               COALESCE(pc.active_profile_count, 0) AS active_profile_count
        FROM segments s
        LEFT JOIN (
            SELECT segment_id,
                   COUNT(*) AS profile_count,
                   COUNT(*) FILTER (WHERE status = 'active') AS active_profile_count
            FROM profiles
            WHERE COALESCE(is_deleted, FALSE) = FALSE
            GROUP BY segment_id
        ) pc ON pc.segment_id = s.id
        WHERE {where_clause}
        ORDER BY s.updated_at DESC NULLS LAST,
                 s.created_at DESC NULLS LAST,
                 s.id
        LIMIT :limit OFFSET :offset
        """
    )
    raw_rows = (await session.execute(list_sql, page_params)).mappings().all()
    rows = [segment_row(dict(r)) for r in raw_rows]

    summary_row = (
        (
            await session.execute(
                text(
                    """
                SELECT
                    COUNT(*) AS segment_count,
                    COUNT(*) FILTER (WHERE status = 'active') AS active_segment_count,
                    COALESCE(SUM(weight) FILTER (WHERE status = 'active'), 0)
                        AS active_weight_sum
                FROM segments
                WHERE COALESCE(is_deleted, FALSE) = FALSE
                  AND COALESCE(status, 'draft') <> 'deleted'
                """
                )
            )
        )
        .mappings()
        .first()
    )
    summary: dict[str, Any] = dict(summary_row or {})
    profile_summary_row = (
        (
            await session.execute(
                text(
                    """
                SELECT
                    COUNT(*) AS profile_count,
                    COUNT(*) FILTER (WHERE p.status = 'active')
                        AS active_profile_count
                FROM profiles p
                WHERE COALESCE(p.is_deleted, FALSE) = FALSE
                  AND p.segment_id IN (
                      SELECT s.id FROM segments s
                      WHERE COALESCE(s.is_deleted, FALSE) = FALSE
                        AND COALESCE(s.status, 'draft') <> 'deleted'
                  )
                """
                )
            )
        )
        .mappings()
        .first()
    )
    summary.update(dict(profile_summary_row or {}))
    summary["active_weight_sum"] = float(summary.get("active_weight_sum") or 0)
    return rows, total, summary


async def get_segment(session: AsyncSession, segment_id: str) -> dict[str, Any] | None:
    """Detail row + profile counters; None when soft-deleted / missing."""
    sid = str(segment_id).strip().upper()
    sql = text(
        """
        SELECT s.*,
               COALESCE(pc.profile_count, 0) AS profile_count,
               COALESCE(pc.active_profile_count, 0) AS active_profile_count
        FROM segments s
        LEFT JOIN (
            SELECT segment_id,
                   COUNT(*) AS profile_count,
                   COUNT(*) FILTER (WHERE status = 'active') AS active_profile_count
            FROM profiles
            WHERE COALESCE(is_deleted, FALSE) = FALSE
            GROUP BY segment_id
        ) pc ON pc.segment_id = s.id
        WHERE s.id = :id
          AND COALESCE(s.is_deleted, FALSE) = FALSE
          AND COALESCE(s.status, 'draft') <> 'deleted'
        """
    )
    row = (await session.execute(sql, {"id": sid})).mappings().first()
    return segment_row(dict(row)) if row else None


# ---------------------------------------------------------------------------
# WRITE
# ---------------------------------------------------------------------------


async def create_segment(
    session: AsyncSession, payload: dict[str, Any], admin_id: str
) -> dict[str, Any]:
    """Insert + return the wire row. ``segment_id_exists`` if id collides
    with a non-deleted row."""
    data = segment_payload(payload)
    existing = (
        await session.execute(
            text("SELECT 1 FROM segments WHERE id = :id AND COALESCE(is_deleted, FALSE) = FALSE"),
            {"id": data["id"]},
        )
    ).first()
    if existing:
        raise ValueError("segment_id_exists")
    seg = Segment(
        id=data["id"],
        code=data["code"],
        brand_id=data["brand_id"],
        brand_name=data["brand_name"],
        name=data["name"],
        industry_id=data["industry_id"],
        industry=data["industry"],
        status=data["status"],
        weight=data["weight"],
        age_range=data["age_range"],
        income=data["income"],
        regions=data["regions"],
        sampling_rate=data["sampling_rate"],
        note=data["note"],
        is_deleted=False,
        created_by=admin_id,
        updated_by=admin_id,
        created_at=_now(),
        updated_at=_now(),
    )
    session.add(seg)
    await session.commit()
    out = await get_segment(session, data["id"])
    if out is None:
        # Should be impossible right after insert; raise to surface.
        raise RuntimeError("segment vanished post-insert")
    return out


async def update_segment(
    session: AsyncSession,
    segment_id: str,
    payload: dict[str, Any],
    admin_id: str,
) -> dict[str, Any]:
    """Update mutable fields. Caller checks existence beforehand and
    raises ``segment_not_found`` if missing.
    """
    data = segment_payload(payload, existing_id=segment_id)
    data["id"] = str(segment_id).strip().upper()
    seg = (
        await session.execute(select(Segment).where(Segment.id == data["id"]))
    ).scalar_one_or_none()
    if seg is None or seg.is_deleted:
        raise ValueError("segment_not_found")
    seg.code = data["code"]
    seg.brand_id = data["brand_id"]
    seg.brand_name = data["brand_name"]
    seg.name = data["name"]
    seg.industry_id = data["industry_id"]
    seg.industry = data["industry"]
    seg.status = data["status"]
    seg.weight = data["weight"]
    seg.age_range = data["age_range"]
    seg.income = data["income"]
    seg.regions = data["regions"]
    seg.sampling_rate = data["sampling_rate"]
    seg.note = data["note"]
    seg.updated_by = admin_id
    seg.updated_at = _now()
    await session.commit()
    out = await get_segment(session, data["id"])
    if out is None:
        raise RuntimeError("segment vanished post-update")
    return out


async def soft_delete_segment(
    session: AsyncSession, segment_id: str, admin_id: str
) -> dict[str, Any] | None:
    """Mark segment ``deleted`` + cascade to its profiles. Returns the
    pre-delete row (so the caller can audit a before-snapshot), or None
    if missing/already deleted.
    """
    sid = str(segment_id).strip().upper()
    before = await get_segment(session, sid)
    if not before:
        return None
    seg = (await session.execute(select(Segment).where(Segment.id == sid))).scalar_one_or_none()
    if seg is None or seg.is_deleted:
        return None
    seg.status = "deleted"
    seg.is_deleted = True
    seg.deleted_at = _now()
    seg.updated_by = admin_id
    seg.updated_at = _now()
    # Cascade-soft-delete child profiles (same as admin_console).
    children = list(
        (
            await session.execute(
                select(Profile).where(
                    Profile.segment_id == sid,
                    Profile.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    for prof in children:
        prof.status = "deleted"
        prof.is_deleted = True
        prof.deleted_at = _now()
        prof.updated_by = admin_id
        prof.updated_at = _now()
    await session.commit()
    return before
