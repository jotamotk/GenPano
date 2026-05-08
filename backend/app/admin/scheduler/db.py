"""DB operations for the admin/scheduler package (Phase 8 slice 8c).

Tables touched:
- ``scheduler_config`` (singleton row, GET + PUT /scheduler/config)
- ``scheduler_runs`` (history rows, GET + DELETE /scheduler/runs)
- ``query_schedules`` (recurring plans, /scheduler/schedules CRUD)
- ``queries`` (read-only for /scheduler/today)
- ``llm_accounts`` (read-only for capacity breakdown)

All queries use raw ``text()`` because most of these tables are
admin_console-era schemas (ADR-002) and not in genpano_models. Defensive
``_table_exists`` probes degrade gracefully on sqlite test fixtures.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.scheduler.lib import (
    account_engine_geo,
    is_query_engine,
    normalize_engine_caps,
    normalize_engine_name,
    normalize_paused_engines,
)

logger = logging.getLogger(__name__)


def _isoformat(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


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


# ── scheduler_config ────────────────────────────────────────


async def fetch_scheduler_config(session: AsyncSession) -> dict[str, Any] | None:
    """Read the singleton scheduler_config row + capacity breakdown.
    Returns ``None`` when the table is missing OR no row exists."""
    if not await _table_exists(session, "scheduler_config"):
        return None
    row = (
        (
            await session.execute(
                text(
                    "SELECT id, mode, daily_time, timezone, temp_global_cap, "
                    "       engine_caps, retry_max, paused_engines, updated_at "
                    "FROM scheduler_config ORDER BY id LIMIT 1"
                )
            )
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    cfg = dict(row)
    cfg["updated_at"] = _isoformat(cfg.get("updated_at"))
    cfg["paused_engines"] = normalize_paused_engines(cfg.get("paused_engines") or [])
    cfg["engine_caps"] = normalize_engine_caps(cfg.get("engine_caps") or {}, strict=False)
    cap = await account_capacity_breakdown(session)
    cfg["capacity"] = cap
    cfg["capacity_total"] = sum(int(c.get("daily_capacity") or 0) for c in cap)
    return cfg


async def update_scheduler_config(session: AsyncSession, *, fields: dict[str, Any]) -> int:
    """Sparse UPDATE on the singleton row. Returns the rowcount.

    Caller is responsible for json.dumps() on list/dict values; this
    helper accepts python-native values and serializes JSONB columns."""
    if not await _table_exists(session, "scheduler_config") or not fields:
        return 0
    set_pieces: list[str] = []
    params: dict[str, Any] = {}
    for key, value in fields.items():
        if key in ("paused_engines", "engine_caps"):
            set_pieces.append(f"{key} = CAST(:{key} AS jsonb)")
            params[key] = json.dumps(value, ensure_ascii=False)
        else:
            set_pieces.append(f"{key} = :{key}")
            params[key] = value
    set_pieces.append("updated_at = NOW()")
    sql = text(
        f"""
        UPDATE scheduler_config SET {", ".join(set_pieces)}
        WHERE id = (SELECT id FROM scheduler_config ORDER BY id LIMIT 1)
        """
    )
    result = await session.execute(sql, params)
    rowcount = int(getattr(result, "rowcount", 0) or 0)
    await session.commit()
    return rowcount


async def account_capacity_breakdown(session: AsyncSession) -> list[dict[str, Any]]:
    """Σ active_account.daily_limit grouped by engine. Returns ``[]``
    when ``llm_accounts`` is missing (sqlite tests / fresh DB)."""
    if not await _table_exists(session, "llm_accounts"):
        return []
    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT llm_name AS engine,
                       COUNT(*) AS account_total,
                       COUNT(*) FILTER (WHERE status='active'
                                        AND cookies_json IS NOT NULL
                                        AND cookies_json != '') AS account_active,
                       COALESCE(SUM(daily_limit) FILTER (
                           WHERE status='active'
                             AND cookies_json IS NOT NULL
                             AND cookies_json != ''
                       ), 0) AS daily_capacity
                FROM llm_accounts
                GROUP BY llm_name
                ORDER BY llm_name
                """
                )
            )
        )
        .mappings()
        .all()
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        engine = normalize_engine_name(r.get("engine"))
        if not is_query_engine(engine):
            continue
        out.append(
            {
                "engine": engine,
                "accounts_total": int(r.get("account_total") or 0),
                "accounts_active": int(r.get("account_active") or 0),
                "daily_capacity": int(r.get("daily_capacity") or 0),
                "expected_geo": account_engine_geo(engine),
            }
        )
    return out


# ── scheduler_runs ──────────────────────────────────────────


async def list_scheduler_runs(
    session: AsyncSession, *, limit: int, offset: int = 0, paginated: bool = False
) -> tuple[list[dict[str, Any]], int | None]:
    """List rows by started_at DESC. When ``paginated`` is True the
    second tuple value is the COUNT(*); otherwise it's None
    (admin_console emits the bare list in non-paginated mode)."""
    if not await _table_exists(session, "scheduler_runs"):
        return [], (0 if paginated else None)
    total: int | None = None
    if paginated:
        count_row = (
            (await session.execute(text("SELECT COUNT(*) AS n FROM scheduler_runs")))
            .mappings()
            .first()
        )
        total = int((dict(count_row) if count_row else {}).get("n") or 0)
    sql = text(
        """
        SELECT id, started_at, finished_at, mode,
               target_total, queries_created, note
        FROM scheduler_runs
        ORDER BY started_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    rows = (await session.execute(sql, {"limit": limit, "offset": offset})).mappings().all()
    out = [
        {
            "id": r.get("id"),
            "started_at": _isoformat(r.get("started_at")),
            "finished_at": _isoformat(r.get("finished_at")),
            "mode": r.get("mode"),
            "target_total": int(r.get("target_total") or 0),
            "queries_created": int(r.get("queries_created") or 0),
            "note": r.get("note"),
        }
        for r in rows
    ]
    return out, total


async def delete_scheduler_run(session: AsyncSession, run_id: int) -> bool:
    if not await _table_exists(session, "scheduler_runs"):
        return False
    result = await session.execute(
        text("DELETE FROM scheduler_runs WHERE id = :id"), {"id": run_id}
    )
    if (getattr(result, "rowcount", 0) or 0) == 0:
        await session.rollback()
        return False
    await session.commit()
    return True


async def bulk_delete_scheduler_runs(
    session: AsyncSession,
    *,
    ids: list[int] | None = None,
    delete_empty: bool = False,
    delete_all: bool = False,
) -> int:
    if not await _table_exists(session, "scheduler_runs"):
        return 0
    if delete_all:
        result = await session.execute(text("DELETE FROM scheduler_runs"))
    elif delete_empty:
        result = await session.execute(
            text("DELETE FROM scheduler_runs WHERE COALESCE(queries_created, 0) = 0")
        )
    else:
        if not ids:
            return 0
        result = await session.execute(
            text("DELETE FROM scheduler_runs WHERE id = ANY(:ids)"), {"ids": ids}
        )
    n = int(getattr(result, "rowcount", 0) or 0)
    await session.commit()
    return n


# ── /scheduler/today ─────────────────────────────────────────


async def fetch_today_dispatch(session: AsyncSession) -> dict[str, Any]:
    """Live progress for today's dispatch grouped by engine."""
    if not await _table_exists(session, "queries"):
        return {
            "engines": [],
            "total": {"target": 0, "done": 0, "failed": 0, "running": 0, "pending": 0},
        }
    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT target_llm AS engine,
                       LOWER(status) AS status,
                       COUNT(*) AS cnt
                FROM queries
                WHERE created_at::date = CURRENT_DATE
                GROUP BY target_llm, LOWER(status)
                """
                )
            )
        )
        .mappings()
        .all()
    )
    cap = await account_capacity_breakdown(session)
    engine_buckets: dict[str, dict[str, Any]] = {}
    for r in rows:
        eng = normalize_engine_name(r.get("engine")) or "unknown"
        b = engine_buckets.setdefault(
            eng,
            {
                "engine": eng,
                "done": 0,
                "failed": 0,
                "running": 0,
                "pending": 0,
            },
        )
        st = str(r.get("status") or "unknown")
        if st in b:
            b[st] = int(r.get("cnt") or 0)
    for c in cap:
        b = engine_buckets.setdefault(
            c["engine"],
            {
                "engine": c["engine"],
                "done": 0,
                "failed": 0,
                "running": 0,
                "pending": 0,
            },
        )
        b["target"] = int(c.get("daily_capacity") or 0)
        b["accounts_active"] = int(c.get("accounts_active") or 0)
        b["expected_geo"] = c.get("expected_geo")
    engines = list(engine_buckets.values())
    for b in engines:
        b.setdefault("target", 0)
        b.setdefault("accounts_active", 0)
        b.setdefault("expected_geo", None)
    total = {
        "target": sum(int(b.get("target") or 0) for b in engines),
        "done": sum(int(b.get("done") or 0) for b in engines),
        "failed": sum(int(b.get("failed") or 0) for b in engines),
        "running": sum(int(b.get("running") or 0) for b in engines),
        "pending": sum(int(b.get("pending") or 0) for b in engines),
    }
    return {"engines": engines, "total": total}


# ── query_schedules ─────────────────────────────────────────


def _row_to_schedule(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "query_text": row.get("query_text"),
        "profile_id": row.get("profile_id"),
        "target_llm": row.get("target_llm"),
        "cadence_days": int(row.get("cadence_days") or 1),
        "next_run_at": _isoformat(row.get("next_run_at")),
        "last_run_at": _isoformat(row.get("last_run_at")),
        "enabled": bool(row.get("enabled")),
        "note": row.get("note"),
        "brand_id": row.get("brand_id"),
        "prompt_id": row.get("prompt_id"),
        "created_at": _isoformat(row.get("created_at")),
        "updated_at": _isoformat(row.get("updated_at")),
    }


async def list_query_schedules(
    session: AsyncSession, *, enabled_only: bool = False
) -> list[dict[str, Any]]:
    if not await _table_exists(session, "query_schedules"):
        return []
    where = "WHERE enabled = TRUE" if enabled_only else ""
    sql = text(
        f"""
        SELECT id, query_text, profile_id, target_llm, cadence_days,
               next_run_at, last_run_at, enabled, note, brand_id,
               prompt_id, created_at, updated_at
        FROM query_schedules
        {where}
        ORDER BY enabled DESC, next_run_at ASC, id DESC
        """
    )
    rows = (await session.execute(sql)).mappings().all()
    return [_row_to_schedule(dict(r)) for r in rows]


async def get_query_schedule(session: AsyncSession, schedule_id: int) -> dict[str, Any] | None:
    if not await _table_exists(session, "query_schedules"):
        return None
    sql = text(
        """
        SELECT id, query_text, profile_id, target_llm, cadence_days,
               next_run_at, last_run_at, enabled, note, brand_id,
               prompt_id, created_at, updated_at
        FROM query_schedules WHERE id = :id
        """
    )
    row = (await session.execute(sql, {"id": schedule_id})).mappings().first()
    if not row:
        return None
    return _row_to_schedule(dict(row))


async def create_query_schedule(
    session: AsyncSession, *, payload: dict[str, Any]
) -> dict[str, Any] | None:
    if not await _table_exists(session, "query_schedules"):
        return None
    next_run = payload.get("next_run_at")
    if next_run is None:
        next_run = dt.datetime.utcnow().isoformat()
    sql = text(
        """
        INSERT INTO query_schedules
            (query_text, profile_id, target_llm, cadence_days,
             next_run_at, enabled, note, brand_id, prompt_id)
        VALUES (:query_text, :profile_id, :target_llm, :cadence_days,
                :next_run_at, :enabled, :note, :brand_id, :prompt_id)
        RETURNING id, query_text, profile_id, target_llm, cadence_days,
                  next_run_at, last_run_at, enabled, note, brand_id,
                  prompt_id, created_at, updated_at
        """
    )
    row = (
        (
            await session.execute(
                sql,
                {
                    "query_text": payload["query_text"],
                    "profile_id": payload.get("profile_id"),
                    "target_llm": payload["target_llm"],
                    "cadence_days": payload.get("cadence_days", 1),
                    "next_run_at": next_run,
                    "enabled": payload.get("enabled", True),
                    "note": payload.get("note"),
                    "brand_id": payload.get("brand_id"),
                    "prompt_id": payload.get("prompt_id"),
                },
            )
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    out = _row_to_schedule(dict(row))
    await session.commit()
    return out


async def update_query_schedule(
    session: AsyncSession, *, schedule_id: int, fields: dict[str, Any]
) -> dict[str, Any] | None:
    """Sparse UPDATE. Returns ``None`` when the row doesn't exist OR when
    no fields are passed (caller surfaces 200 success/updated:0)."""
    if not await _table_exists(session, "query_schedules") or not fields:
        return None
    set_pieces: list[str] = []
    params: dict[str, Any] = {"id": schedule_id}
    for col in (
        "query_text",
        "profile_id",
        "target_llm",
        "cadence_days",
        "next_run_at",
        "enabled",
        "note",
        "brand_id",
        "prompt_id",
    ):
        if col in fields:
            set_pieces.append(f"{col} = :{col}")
            params[col] = fields[col]
    if not set_pieces:
        return None
    set_pieces.append("updated_at = NOW()")
    sql = text(
        f"""
        UPDATE query_schedules SET {", ".join(set_pieces)}
        WHERE id = :id
        RETURNING id, query_text, profile_id, target_llm, cadence_days,
                  next_run_at, last_run_at, enabled, note, brand_id,
                  prompt_id, created_at, updated_at
        """
    )
    row = (await session.execute(sql, params)).mappings().first()
    if not row:
        await session.rollback()
        return None
    out = _row_to_schedule(dict(row))
    await session.commit()
    return out


async def delete_query_schedule(session: AsyncSession, schedule_id: int) -> bool:
    if not await _table_exists(session, "query_schedules"):
        return False
    result = await session.execute(
        text("DELETE FROM query_schedules WHERE id = :id"), {"id": schedule_id}
    )
    if (getattr(result, "rowcount", 0) or 0) == 0:
        await session.rollback()
        return False
    await session.commit()
    return True


async def upcoming_schedule_fires(
    session: AsyncSession, *, days: int
) -> dict[str, list[dict[str, Any]]]:
    """Project enabled schedules forward by their cadence_days through
    the requested window. Returns ``{date_iso: [fires...]}``.

    The actual roll-forward math runs in Python rather than SQL because
    cadence_days varies per row and Postgres doesn't have a clean
    generate_series equivalent that handles per-row intervals."""
    if not await _table_exists(session, "query_schedules"):
        return {}
    sql = text(
        """
        SELECT id, query_text, profile_id, target_llm, cadence_days,
               next_run_at, last_run_at, enabled, note
        FROM query_schedules
        WHERE enabled = TRUE
        ORDER BY next_run_at ASC
        """
    )
    rows = (await session.execute(sql)).mappings().all()
    now = dt.datetime.utcnow()
    horizon = now + dt.timedelta(days=int(days))
    by_date: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        cadence = max(1, int(r.get("cadence_days") or 1))
        next_run_dt = r.get("next_run_at")
        if next_run_dt is None:
            continue
        # Drop tzinfo to align with admin_console's naive comparisons.
        if hasattr(next_run_dt, "tzinfo") and next_run_dt.tzinfo is not None:
            next_run_dt = next_run_dt.replace(tzinfo=None)
        cursor = next_run_dt
        # Roll forward until we hit the horizon.
        while cursor < now:
            cursor = cursor + dt.timedelta(days=cadence)
        while cursor <= horizon:
            day = cursor.date().isoformat()
            by_date.setdefault(day, []).append(
                {
                    "id": r.get("id"),
                    "query_text": r.get("query_text"),
                    "profile_id": r.get("profile_id"),
                    "target_llm": r.get("target_llm"),
                    "cadence_days": cadence,
                    "fires_at": cursor.isoformat(),
                }
            )
            cursor = cursor + dt.timedelta(days=cadence)
    return by_date


__all__ = [
    "account_capacity_breakdown",
    "bulk_delete_scheduler_runs",
    "create_query_schedule",
    "delete_query_schedule",
    "delete_scheduler_run",
    "fetch_scheduler_config",
    "fetch_today_dispatch",
    "get_query_schedule",
    "list_query_schedules",
    "list_scheduler_runs",
    "upcoming_schedule_fires",
    "update_query_schedule",
    "update_scheduler_config",
]
