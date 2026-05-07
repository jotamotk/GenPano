"""DB operations for segments — Phase 6 slice 6a + 6a-bis.

Vendored from admin_console/app.py 9254-9528 (CRUD) and 8990-9061 +
9515-9528 + 9754-9778 (import / brand resolution / generation log).
Uses the ORM ``Segment`` + ``Profile`` models for the writes
(sqlite-friendly) and raw SQL for the read-side aggregations
(``profile_count`` JOIN, summary stats, brand lookup) — same numbers
the SPA was getting from admin_console.

Public:
- CRUD: ``fetch_segments``, ``get_segment``, ``create_segment``,
  ``update_segment``, ``soft_delete_segment``
- Bulk: ``upsert_segment``, ``import_segments_bulk``
- Brand selection: ``BrandSelectionAmbiguous``, ``resolve_admin_brand_selection``
- Generation log: ``write_segment_generation_log``
"""

from __future__ import annotations

import logging
import uuid as _uuid
from datetime import UTC, datetime
from typing import Any

from genpano_models import Profile, Segment
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.segments.lib import segment_payload, segment_row

logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# Bulk import (Phase 6 slice 6a-bis)
# ---------------------------------------------------------------------------


async def upsert_segment(
    session: AsyncSession, payload: dict[str, Any], admin_id: str
) -> tuple[str, dict[str, Any]]:
    """Insert-or-update a single segment.

    Returns ``("added", row)`` or ``("updated", row)``. On id collision
    with a soft-deleted row the row gets undeleted (mirrors admin_console
    so a re-import resurrects past names instead of silently failing).
    """
    data = segment_payload(payload)
    existing = (
        await session.execute(select(Segment).where(Segment.id == data["id"]))
    ).scalar_one_or_none()
    if existing is not None:
        existing.code = data["code"]
        existing.brand_id = data["brand_id"]
        existing.brand_name = data["brand_name"]
        existing.name = data["name"]
        existing.industry_id = data["industry_id"]
        existing.industry = data["industry"]
        existing.status = data["status"]
        existing.weight = data["weight"]
        existing.age_range = data["age_range"]
        existing.income = data["income"]
        existing.regions = data["regions"]
        existing.sampling_rate = data["sampling_rate"]
        existing.note = data["note"]
        existing.is_deleted = False
        existing.deleted_at = None
        existing.updated_by = admin_id
        existing.updated_at = _now()
        # Refresh brand info on associated profiles too — admin_console does
        # this so a brand rename via the import sheet propagates immediately.
        children = list(
            (
                await session.execute(
                    select(Profile).where(
                        Profile.segment_id == data["id"],
                        Profile.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )
        for prof in children:
            prof.brand_id = data["brand_id"]
            prof.brand_name = data["brand_name"]
            prof.updated_by = admin_id
            prof.updated_at = _now()
        await session.commit()
        out = await get_segment(session, data["id"])
        if out is None:
            raise RuntimeError("segment vanished post-upsert")
        return "updated", out
    out = await create_segment(session, payload, admin_id)
    return "added", out


async def import_segments_bulk(
    session: AsyncSession,
    rows: list[Any] | None,
    admin_id: str,
) -> dict[str, Any]:
    """Apply ``upsert_segment`` to each input row, summarising counts.

    Per-row failures (validation errors raised by ``segment_payload``)
    are counted as ``skipped`` rather than aborting the batch — matches
    admin_console's "best-effort import" behaviour.
    """
    added = 0
    updated = 0
    skipped = 0
    output: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            skipped += 1
            continue
        try:
            outcome, segment = await upsert_segment(session, row, admin_id)
        except ValueError:
            skipped += 1
            continue
        if outcome == "added":
            added += 1
        else:
            updated += 1
        output.append(segment)
    return {"added": added, "updated": updated, "skipped": skipped, "rows": output}


# ---------------------------------------------------------------------------
# Brand resolution (Phase 6 slice 6a-bis)
# ---------------------------------------------------------------------------


class BrandSelectionAmbiguous(ValueError):
    """Raised when ``resolve_admin_brand_selection`` finds >1 brand
    matching the operator-supplied name without an explicit brand_id.
    """

    def __init__(self, candidates: list[dict[str, Any]]):
        super().__init__("ambiguous_brand")
        self.candidates = candidates


def _brand_option_from_row(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row or {})
    raw_id = item.get("id")
    try:
        brand_id: int | str = int(raw_id)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        brand_id = str(raw_id or "").strip()
    return {
        "id": brand_id,
        "name": str(item.get("name") or "").strip(),
        "industry": str(item.get("industry") or item.get("industry_name") or "").strip(),
        "target_market": str(item.get("target_market") or item.get("targetMarket") or "").strip(),
    }


async def _brand_table_columns(session: AsyncSession) -> set[str]:
    """information_schema lookup of public.brands columns. Empty set on
    sqlite (no information_schema) → caller treats it as "no brand
    table available" and degrades to passing the name through."""
    try:
        result = await session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'brands'"
            )
        )
    except Exception:
        return set()
    return {row[0] for row in result.all()}


async def resolve_admin_brand_selection(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Resolve operator-supplied ``brand_id`` / ``brand_name`` against
    the production ``brands`` table.

    Returns ``{brand_id, brand_name}``. Raises
    ``BrandSelectionAmbiguous`` when only a name was supplied AND >1
    matching row exists. Falls back to passthrough when the brands
    table isn't in the schema (sqlite tests).
    """
    from app.admin.segments.lib import brand_id_value, brand_name_value

    bid = brand_id_value(payload)
    bname = brand_name_value(payload)
    if bid and bname:
        return {"brand_id": bid, "brand_name": bname}
    cols = await _brand_table_columns(session)
    if not {"id", "name"}.issubset(cols):
        return {"brand_id": bid, "brand_name": bname}
    industry_select = "industry" if "industry" in cols else "NULL::text AS industry"
    target_market_select = (
        "target_market" if "target_market" in cols else "NULL::text AS target_market"
    )
    if bid:
        sql = text(
            f"""
            SELECT id, name, {industry_select}, {target_market_select}
            FROM brands
            WHERE CAST(id AS TEXT) = :bid
            LIMIT 1
            """
        )
        row = (await session.execute(sql, {"bid": str(bid)})).mappings().first()
        if row:
            option = _brand_option_from_row(dict(row))
            return {
                "brand_id": str(option["id"]),
                "brand_name": option["name"] or bname,
            }
        return {"brand_id": bid, "brand_name": bname}

    if not bname:
        return {"brand_id": None, "brand_name": ""}

    sql = text(
        f"""
        SELECT id, name, {industry_select}, {target_market_select}
        FROM brands
        WHERE LOWER(name) = LOWER(:bname)
        ORDER BY id
        LIMIT 20
        """
    )
    matches_raw = (await session.execute(sql, {"bname": bname})).mappings().all()
    matches = [_brand_option_from_row(dict(r)) for r in matches_raw]
    matches = [m for m in matches if m.get("id") and m.get("name")]
    if len(matches) > 1:
        raise BrandSelectionAmbiguous(matches)
    if len(matches) == 1:
        option = matches[0]
        return {"brand_id": str(option["id"]), "brand_name": option["name"]}
    return {"brand_id": None, "brand_name": bname}


# ---------------------------------------------------------------------------
# Generation log (Phase 6 slice 6a-bis)
# ---------------------------------------------------------------------------


async def write_segment_generation_log(
    session: AsyncSession,
    *,
    admin_id: str,
    payload: dict[str, Any],
    model: str,
    prompt: str,
    items: list[dict[str, Any]],
    usage: dict[str, Any],
    estimated_cost: float | None,
) -> None:
    """Best-effort INSERT into ``segment_generation_logs``.

    Table is admin_console-only — not registered with the backend ORM
    (ADR-002 upstream-stub policy). On sqlite tests / fresh deployments
    where the table doesn't exist, swallow the error instead of aborting
    the whole /generate request, since the actual drafts have already
    been validated and returned.
    """
    import json as _json

    try:
        await session.execute(
            text(
                """
                INSERT INTO segment_generation_logs
                    (id, brand_id, brand_name, industry_id, llm_model, prompt_used,
                     input_params, output_json, segments_generated, segments_skipped,
                     tokens_used, estimated_cost, created_by, created_at)
                VALUES
                    (:id, :brand_id, :brand_name, :industry_id, :llm_model,
                     :prompt_used, CAST(:input_params AS jsonb),
                     CAST(:output_json AS jsonb), :segments_generated,
                     :segments_skipped, :tokens_used, :estimated_cost,
                     :created_by, NOW())
                """
            ),
            {
                "id": str(_uuid.uuid4()),
                "brand_id": payload.get("brand_id"),
                "brand_name": payload.get("brand_name") or payload.get("brand"),
                "industry_id": payload.get("industry_id"),
                "llm_model": model,
                "prompt_used": prompt,
                "input_params": _json.dumps(payload, default=str),
                "output_json": _json.dumps(items, default=str),
                "segments_generated": len(items),
                "segments_skipped": 0,
                "tokens_used": int((usage or {}).get("total_tokens") or 0),
                "estimated_cost": estimated_cost,
                "created_by": admin_id,
            },
        )
        await session.commit()
    except Exception as exc:
        # Roll back the failed log INSERT so the next statement on this
        # session isn't poisoned by the aborted transaction.
        try:
            await session.rollback()
        except Exception:
            pass
        logger.warning("segment_generation_logs INSERT failed (table missing?): %s", exc)
