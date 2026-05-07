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

import json as _json
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


def _dialect_name(session: AsyncSession) -> str | None:
    try:
        bind = getattr(session, "bind", None) or session.get_bind()
        return getattr(getattr(bind, "dialect", None), "name", None)
    except Exception:
        return None


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
    now = _now()
    await session.execute(
        text(
            """
            UPDATE profiles
            SET status = 'deleted',
                is_deleted = TRUE,
                deleted_at = :now,
                updated_by = :admin_id,
                updated_at = :now
            WHERE segment_id = :sid
              AND COALESCE(is_deleted, FALSE) = FALSE
            """
        ),
        {"sid": sid, "admin_id": admin_id, "now": now},
    )
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
        # Refresh brand info on associated profiles too, using raw SQL so
        # legacy integer profile ids don't flow through the string ORM model.
        await session.execute(
            text(
                """
                UPDATE profiles
                SET brand_id = :brand_id,
                    brand_name = :brand_name,
                    updated_by = :admin_id,
                    updated_at = :now
                WHERE segment_id = :sid
                  AND COALESCE(is_deleted, FALSE) = FALSE
                """
            ),
            {
                "sid": data["id"],
                "brand_id": data["brand_id"],
                "brand_name": data["brand_name"],
                "admin_id": admin_id,
                "now": _now(),
            },
        )
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


# ---------------------------------------------------------------------------
# Profile CRUD (Phase 6 slice 6b)
# ---------------------------------------------------------------------------


from app.admin.segments.lib import profile_payload, profile_row  # noqa: E402


async def _profiles_use_integer_id(session: AsyncSession) -> bool:
    if _dialect_name(session) not in {None, "postgresql"}:
        return False
    try:
        row = (
            (
                await session.execute(
                    text(
                        """
                        SELECT data_type, udt_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'profiles'
                          AND column_name = 'id'
                        LIMIT 1
                        """
                    )
                )
            )
            .mappings()
            .first()
        )
    except Exception as exc:
        logger.warning("profiles.id schema probe failed: %s", exc)
        return False
    info = dict(row or {})
    return info.get("data_type") in {"integer", "bigint", "smallint"} or info.get("udt_name") in {
        "int4",
        "int8",
        "int2",
    }


async def _sync_profiles_id_sequence(session: AsyncSession) -> bool:
    try:
        seq_row = (
            (
                await session.execute(
                    text("SELECT pg_get_serial_sequence('profiles', 'id') AS sequence_name")
                )
            )
            .mappings()
            .first()
        )
        sequence_name = (dict(seq_row or {}).get("sequence_name") or "").strip()
        if not sequence_name:
            return False
        max_row = (
            (await session.execute(text("SELECT COALESCE(MAX(id), 0) AS max_id FROM profiles")))
            .mappings()
            .first()
        )
        max_id = int(dict(max_row or {}).get("max_id") or 0)
        await session.execute(
            text("SELECT setval(to_regclass(:sequence_name), :next_value, :is_called)"),
            {
                "sequence_name": sequence_name,
                "next_value": max(max_id, 1),
                "is_called": max_id > 0,
            },
        )
        return True
    except Exception as exc:
        logger.warning("profiles.id sequence sync failed: %s", exc)
        return False


async def fetch_profiles(
    session: AsyncSession,
    segment_id: str,
    *,
    page: int = 1,
    per_page: int = 100,
    q: str | None = None,
    status: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Page + filter profiles for a single segment.

    Wire shape: ``(rows, total)`` — paginated rows are wire-shape via
    ``profile_row``; ``total`` is the unpaged count under the same
    filters. Joins ``segments s`` so blank-on-profile brand_*
    inherits from the parent.
    """
    page = max(int(page or 1), 1)
    per_page = max(1, min(int(per_page or 100), 100000))
    offset = (page - 1) * per_page
    sid = str(segment_id).strip().upper()
    where: list[str] = [
        "p.segment_id = :sid",
        "COALESCE(p.is_deleted, FALSE) = FALSE",
        "COALESCE(p.status, 'draft') <> 'deleted'",
    ]
    params: dict[str, Any] = {"sid": sid}
    qq = (q or "").strip()
    if qq:
        params["like"] = f"%{qq}%"
        where.append(
            "(COALESCE(p.code, '') ILIKE :like OR CAST(p.id AS TEXT) ILIKE :like "
            "OR p.name ILIKE :like OR COALESCE(p.brand_name, '') ILIKE :like "
            "OR COALESCE(p.demographic, '') ILIKE :like "
            "OR COALESCE(p.need, '') ILIKE :like "
            "OR COALESCE(p.status, '') ILIKE :like)"
        )
    p_status = (status or "").strip().lower()
    if p_status and p_status != "all":
        where.append("p.status = :status")
        params["status"] = p_status
    where_clause = " AND ".join(where)
    total_row = (
        (
            await session.execute(
                text(f"SELECT COUNT(*) AS cnt FROM profiles p WHERE {where_clause}"),
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
        SELECT p.*,
               COALESCE(p.code, CAST(p.id AS TEXT)) AS api_id,
               COALESCE(NULLIF(p.brand_id, ''), s.brand_id) AS brand_id,
               COALESCE(NULLIF(p.brand_name, ''), s.brand_name, '') AS brand_name
        FROM profiles p
        LEFT JOIN segments s ON s.id = p.segment_id
        WHERE {where_clause}
        ORDER BY p.updated_at DESC NULLS LAST,
                 p.created_at DESC NULLS LAST,
                 p.id
        LIMIT :limit OFFSET :offset
        """
    )
    raw = (await session.execute(list_sql, page_params)).mappings().all()
    return [profile_row(dict(r)) for r in raw], total


async def get_profile(
    session: AsyncSession, segment_id: str, profile_id: str
) -> dict[str, Any] | None:
    """Detail row by (segment_id, code-or-id). None when missing /
    soft-deleted."""
    sid = str(segment_id).strip().upper()
    pid_upper = str(profile_id).strip().upper()
    pid_raw = str(profile_id).strip()
    sql = text(
        """
        SELECT p.*,
               COALESCE(p.code, CAST(p.id AS TEXT)) AS api_id,
               COALESCE(NULLIF(p.brand_id, ''), s.brand_id) AS brand_id,
               COALESCE(NULLIF(p.brand_name, ''), s.brand_name, '') AS brand_name
        FROM profiles p
        LEFT JOIN segments s ON s.id = p.segment_id
        WHERE p.segment_id = :sid
          AND (p.code = :pid_upper OR CAST(p.id AS TEXT) = :pid_raw)
          AND COALESCE(p.is_deleted, FALSE) = FALSE
          AND COALESCE(p.status, 'draft') <> 'deleted'
        """
    )
    row = (
        (await session.execute(sql, {"sid": sid, "pid_upper": pid_upper, "pid_raw": pid_raw}))
        .mappings()
        .first()
    )
    return profile_row(dict(row)) if row else None


async def create_profile(
    session: AsyncSession,
    segment_id: str,
    payload: dict[str, Any],
    admin_id: str,
) -> dict[str, Any]:
    """Insert a new profile under ``segment_id``.

    Raises ``segment_not_found`` if parent missing,
    ``profile_id_exists`` on collision with a non-deleted row.
    """
    seg = await get_segment(session, segment_id)
    if not seg:
        raise ValueError("segment_not_found")
    data = profile_payload(payload, segment_id, segment=seg)
    existing = (
        await session.execute(
            text(
                """
                SELECT 1 FROM profiles
                WHERE segment_id = :sid
                  AND (code = :code OR CAST(id AS TEXT) = :pid)
                  AND COALESCE(is_deleted, FALSE) = FALSE
                """
            ),
            {"sid": data["segment_id"], "code": data["code"], "pid": data["id"]},
        )
    ).first()
    if existing:
        raise ValueError("profile_id_exists")
    if await _profiles_use_integer_id(session):
        await _sync_profiles_id_sequence(session)
        now = _now()
        result = await session.execute(
            text(
                """
                INSERT INTO profiles (
                    code, segment_id, brand_id, brand_name, name, demographic,
                    need, weight, status, persona_json, is_deleted,
                    created_by, updated_by, created_at, updated_at
                )
                VALUES (
                    :code, :segment_id, :brand_id, :brand_name, :name, :demographic,
                    :need, :weight, :status, CAST(:persona_json AS jsonb), FALSE,
                    :created_by, :updated_by, :created_at, :updated_at
                )
                RETURNING *, COALESCE(code, CAST(id AS TEXT)) AS api_id
                """
            ),
            {
                "code": data["code"],
                "segment_id": data["segment_id"],
                "brand_id": data["brand_id"],
                "brand_name": data["brand_name"],
                "name": data["name"],
                "demographic": data["demographic"],
                "need": data["need"],
                "weight": data["weight"],
                "status": data["status"],
                "persona_json": _json.dumps(data["persona_json"], default=str),
                "created_by": admin_id,
                "updated_by": admin_id,
                "created_at": now,
                "updated_at": now,
            },
        )
        inserted = result.mappings().first()
        await session.commit()
        if inserted:
            return profile_row(dict(inserted))
        out = await get_profile(session, data["segment_id"], data["code"])
        if out is None:
            raise RuntimeError("profile vanished post-insert")
        return out
    prof = Profile(
        id=data["id"],
        code=data["code"],
        segment_id=data["segment_id"],
        brand_id=data["brand_id"],
        brand_name=data["brand_name"],
        name=data["name"],
        demographic=data["demographic"],
        need=data["need"],
        weight=data["weight"],
        status=data["status"],
        persona_json=data["persona_json"],
        is_deleted=False,
        created_by=admin_id,
        updated_by=admin_id,
        created_at=_now(),
        updated_at=_now(),
    )
    session.add(prof)
    await session.commit()
    out = await get_profile(session, data["segment_id"], data["code"])
    if out is None:
        raise RuntimeError("profile vanished post-insert")
    return out


async def update_profile(
    session: AsyncSession,
    segment_id: str,
    profile_id: str,
    payload: dict[str, Any],
    admin_id: str,
) -> dict[str, Any] | None:
    """Update a profile. Returns None if missing; raises ``ValueError``
    on payload validation."""
    seg = await get_segment(session, segment_id)
    if not seg:
        raise ValueError("segment_not_found")
    existing = await get_profile(session, segment_id, profile_id)
    if not existing:
        return None
    data = profile_payload(payload, segment_id, existing_id=profile_id, segment=seg)
    sid = data["segment_id"]
    pid_upper = str(profile_id).strip().upper()
    pid_raw = str(profile_id).strip()
    if await _profiles_use_integer_id(session):
        await session.execute(
            text(
                """
                UPDATE profiles
                SET code = :code,
                    brand_id = :brand_id,
                    brand_name = :brand_name,
                    name = :name,
                    demographic = :demographic,
                    need = :need,
                    weight = :weight,
                    status = :status,
                    persona_json = CAST(:persona_json AS jsonb),
                    updated_by = :admin_id,
                    updated_at = :updated_at
                WHERE segment_id = :sid
                  AND (code = :pid_upper OR CAST(id AS TEXT) = :pid_raw)
                  AND COALESCE(is_deleted, FALSE) = FALSE
                """
            ),
            {
                "sid": sid,
                "pid_upper": pid_upper,
                "pid_raw": pid_raw,
                "code": data["code"],
                "brand_id": data["brand_id"],
                "brand_name": data["brand_name"],
                "name": data["name"],
                "demographic": data["demographic"],
                "need": data["need"],
                "weight": data["weight"],
                "status": data["status"],
                "persona_json": _json.dumps(data["persona_json"], default=str),
                "admin_id": admin_id,
                "updated_at": _now(),
            },
        )
        await session.commit()
        return await get_profile(session, segment_id, data["code"])
    prof = (
        await session.execute(
            select(Profile).where(
                Profile.segment_id == sid,
                Profile.is_deleted.is_(False),
                (Profile.code == pid_upper) | (Profile.id == pid_raw),
            )
        )
    ).scalar_one_or_none()
    if prof is None:
        return None
    prof.code = data["code"]
    prof.brand_id = data["brand_id"]
    prof.brand_name = data["brand_name"]
    prof.name = data["name"]
    prof.demographic = data["demographic"]
    prof.need = data["need"]
    prof.weight = data["weight"]
    prof.status = data["status"]
    prof.persona_json = data["persona_json"]
    prof.updated_by = admin_id
    prof.updated_at = _now()
    await session.commit()
    return await get_profile(session, segment_id, data["code"])


async def soft_delete_profile(
    session: AsyncSession,
    segment_id: str,
    profile_id: str,
    admin_id: str,
) -> dict[str, Any] | None:
    """Soft-delete a profile. Returns the pre-delete row or None."""
    before = await get_profile(session, segment_id, profile_id)
    if not before:
        return None
    sid = str(segment_id).strip().upper()
    pid_upper = str(profile_id).strip().upper()
    pid_raw = str(profile_id).strip()
    if await _profiles_use_integer_id(session):
        now = _now()
        await session.execute(
            text(
                """
                UPDATE profiles
                SET status = 'deleted',
                    is_deleted = TRUE,
                    deleted_at = :now,
                    updated_by = :admin_id,
                    updated_at = :now
                WHERE segment_id = :sid
                  AND (code = :pid_upper OR CAST(id AS TEXT) = :pid_raw)
                  AND COALESCE(is_deleted, FALSE) = FALSE
                """
            ),
            {
                "sid": sid,
                "pid_upper": pid_upper,
                "pid_raw": pid_raw,
                "admin_id": admin_id,
                "now": now,
            },
        )
        await session.commit()
        return before
    prof = (
        await session.execute(
            select(Profile).where(
                Profile.segment_id == sid,
                Profile.is_deleted.is_(False),
                (Profile.code == pid_upper) | (Profile.id == pid_raw),
            )
        )
    ).scalar_one_or_none()
    if prof is None:
        return None
    prof.status = "deleted"
    prof.is_deleted = True
    prof.deleted_at = _now()
    prof.updated_by = admin_id
    prof.updated_at = _now()
    await session.commit()
    return before


async def import_profiles_bulk(
    session: AsyncSession,
    segment_id: str,
    rows: list[Any] | None,
    admin_id: str,
) -> dict[str, Any]:
    """Bulk-upsert profiles for one segment.

    Per-row failures (validation errors) counted as ``skipped`` with
    a structured ``skipped_rows`` list, matching admin_console.
    """
    seg = await get_segment(session, segment_id)
    if not seg:
        raise ValueError("segment_not_found")
    added = 0
    updated = 0
    skipped = 0
    output: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows or [], start=1):
        if not isinstance(row, dict):
            skipped += 1
            skipped_rows.append(
                {"index": index, "error": "profile_row_must_be_object", "id": None, "name": None}
            )
            continue
        try:
            existing = await get_profile(
                session, segment_id, row.get("id") or row.get("code") or ""
            )
            if existing:
                updated_row = await update_profile(
                    session, segment_id, existing["id"], row, admin_id
                )
                if updated_row is None:
                    raise ValueError("profile_update_failed")
                output.append(updated_row)
                updated += 1
            else:
                output.append(await create_profile(session, segment_id, row, admin_id))
                added += 1
        except ValueError as error:
            skipped += 1
            skipped_rows.append(
                {
                    "index": index,
                    "error": str(error) or error.__class__.__name__,
                    "id": row.get("id"),
                    "name": row.get("name"),
                }
            )
    return {
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "rows": output,
        "skipped_rows": skipped_rows,
    }


async def write_profile_generation_log(
    session: AsyncSession,
    *,
    admin_id: str,
    segment_id: str,
    payload: dict[str, Any],
    model: str,
    prompt: str,
    items: list[dict[str, Any]],
    usage: dict[str, Any],
    estimated_cost: float | None,
) -> None:
    """Best-effort INSERT into ``profile_generation_logs``.

    Uses a SAVEPOINT (begin_nested) so a failed INSERT doesn't poison
    the calling session — important for the async worker where the
    same session also writes the audit row right after this call.
    On sqlite tests / fresh deployments where the table doesn't exist,
    the savepoint releases cleanly and the warning is logged.
    """
    import json as _json

    nested = await session.begin_nested()
    try:
        await session.execute(
            text(
                """
                INSERT INTO profile_generation_logs
                    (id, segment_id, llm_model, prompt_used, input_params, output_json,
                     profiles_generated, profiles_skipped, tokens_used, estimated_cost,
                     created_by, created_at)
                VALUES
                    (:id, :segment_id, :llm_model, :prompt_used,
                     CAST(:input_params AS jsonb), CAST(:output_json AS jsonb),
                     :profiles_generated, :profiles_skipped, :tokens_used,
                     :estimated_cost, :created_by, NOW())
                """
            ),
            {
                "id": str(_uuid.uuid4()),
                "segment_id": str(segment_id).strip().upper(),
                "llm_model": model,
                "prompt_used": prompt,
                "input_params": _json.dumps(payload, default=str),
                "output_json": _json.dumps(items, default=str),
                "profiles_generated": len(items),
                "profiles_skipped": 0,
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
        logger.warning("profile_generation_logs INSERT failed (table missing?): %s", exc)
