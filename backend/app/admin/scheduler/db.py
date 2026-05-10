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


async def _table_columns(session: AsyncSession, name: str) -> set[str]:
    try:
        rows = (
            await session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = :n"
                ),
                {"n": name},
            )
        ).all()
    except Exception:
        return set()
    return {str(row[0]) for row in rows}


async def _schedule_brand_filter(
    session: AsyncSession,
    *,
    alias: str,
    has_batch_cols: bool,
    brand_id: int | None,
    params: dict[str, Any],
) -> str | None:
    if brand_id is None:
        return None
    params["brand_id"] = int(brand_id)
    parts = [f"{alias}.brand_id = :brand_id"]
    if has_batch_cols:
        params["brand_item_json"] = json.dumps([{"brand_id": int(brand_id)}])
        parts.append(f"{alias}.query_items_json @> CAST(:brand_item_json AS jsonb)")
    prompt_cols = await _table_columns(session, "prompts")
    topic_cols = await _table_columns(session, "topics")
    if (
        {"id", "topic_id"}.issubset(prompt_cols)
        and {"id", "brand_id"}.issubset(topic_cols)
        and await _table_exists(session, "prompts")
        and await _table_exists(session, "topics")
    ):
        parts.append(
            "EXISTS ("
            "SELECT 1 FROM prompts pr_brand "
            "JOIN topics t_brand ON t_brand.id = pr_brand.topic_id "
            f"WHERE CAST(pr_brand.id AS TEXT) = CAST({alias}.prompt_id AS TEXT) "
            "AND CAST(t_brand.brand_id AS TEXT) = CAST(:brand_id AS TEXT)"
            ")"
        )
    return "(" + " OR ".join(parts) + ")"


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


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
    target_llms = _json_list(row.get("target_llms_json") or row.get("target_llms"))
    query_items = _json_list(row.get("query_items_json") or row.get("query_items"))
    target_llms = [str(v) for v in target_llms if str(v or "").strip()]
    item_count = row.get("item_count")
    if item_count is None:
        item_count = len(query_items) if query_items else 1
    return {
        "id": row.get("id"),
        "query_text": row.get("query_text"),
        "profile_id": row.get("profile_id"),
        "target_llm": row.get("target_llm"),
        "target_llms": target_llms or ([row.get("target_llm")] if row.get("target_llm") else []),
        "plan_kind": row.get("plan_kind") or "single",
        "query_items": query_items,
        "item_count": int(item_count or 0),
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
    session: AsyncSession,
    *,
    enabled_only: bool = False,
    brand_id: int | None = None,
    page: int | None = None,
    per_page: int | None = None,
) -> list[dict[str, Any]] | dict[str, Any]:
    if not await _table_exists(session, "query_schedules"):
        if page is not None or per_page is not None:
            return {"rows": [], "total": 0, "page": int(page or 1), "per_page": int(per_page or 50)}
        return []
    cols = await _table_columns(session, "query_schedules")
    has_batch_cols = {"plan_kind", "target_llms_json", "query_items_json", "item_count"}.issubset(
        cols
    )
    plan_cols = (
        "plan_kind, target_llms_json, query_items_json, item_count"
        if has_batch_cols
        else "'single' AS plan_kind, '[]' AS target_llms_json, "
        "'[]' AS query_items_json, 1 AS item_count"
    )
    params: dict[str, Any] = {}
    where_parts: list[str] = []
    if enabled_only:
        where_parts.append("qs.enabled = TRUE")
    brand_filter = await _schedule_brand_filter(
        session,
        alias="qs",
        has_batch_cols=has_batch_cols,
        brand_id=brand_id,
        params=params,
    )
    if brand_filter:
        where_parts.append(brand_filter)
    where = "WHERE " + " AND ".join(where_parts) if where_parts else ""
    limit_clause = ""
    is_paginated = page is not None or per_page is not None
    page_number = max(1, int(page or 1))
    per_page_number = min(200, max(1, int(per_page or 50)))
    if is_paginated:
        params["limit"] = per_page_number
        params["offset"] = (page_number - 1) * per_page_number
        limit_clause = "LIMIT :limit OFFSET :offset"
    sql = text(
        f"""
        SELECT id, query_text, profile_id, target_llm, cadence_days,
               next_run_at, last_run_at, enabled, note, brand_id,
               prompt_id, created_at, updated_at, {plan_cols}
        FROM query_schedules qs
        {where}
        ORDER BY enabled DESC, next_run_at ASC, id DESC
        {limit_clause}
        """
    )
    rows = [
        _row_to_schedule(dict(r)) for r in (await session.execute(sql, params)).mappings().all()
    ]
    if not is_paginated:
        return rows
    total = int(
        (
            await session.execute(
                text(f"SELECT COUNT(*) AS n FROM query_schedules qs {where}"), params
            )
        ).scalar()
        or 0
    )
    return {"rows": rows, "total": total, "page": page_number, "per_page": per_page_number}


async def get_query_schedule(session: AsyncSession, schedule_id: int) -> dict[str, Any] | None:
    if not await _table_exists(session, "query_schedules"):
        return None
    cols = await _table_columns(session, "query_schedules")
    has_batch_cols = {"plan_kind", "target_llms_json", "query_items_json", "item_count"}.issubset(
        cols
    )
    plan_cols = (
        "plan_kind, target_llms_json, query_items_json, item_count"
        if has_batch_cols
        else "'single' AS plan_kind, '[]' AS target_llms_json, "
        "'[]' AS query_items_json, 1 AS item_count"
    )
    sql = text(
        f"""
        SELECT id, query_text, profile_id, target_llm, cadence_days,
               next_run_at, last_run_at, enabled, note, brand_id,
               prompt_id, created_at, updated_at, {plan_cols}
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
    cols = await _table_columns(session, "query_schedules")
    has_batch_cols = {"plan_kind", "target_llms_json", "query_items_json", "item_count"}.issubset(
        cols
    )
    if payload.get("plan_kind") == "batch" and not has_batch_cols:
        return None
    next_run = payload.get("next_run_at")
    if next_run is None:
        next_run = dt.datetime.utcnow().isoformat()
    insert_cols = [
        "query_text",
        "profile_id",
        "target_llm",
        "cadence_days",
        "next_run_at",
        "enabled",
        "note",
        "brand_id",
        "prompt_id",
    ]
    value_exprs = [
        ":query_text",
        ":profile_id",
        ":target_llm",
        ":cadence_days",
        ":next_run_at",
        ":enabled",
        ":note",
        ":brand_id",
        ":prompt_id",
    ]
    returning_cols = [
        "id",
        "query_text",
        "profile_id",
        "target_llm",
        "cadence_days",
        "next_run_at",
        "last_run_at",
        "enabled",
        "note",
        "brand_id",
        "prompt_id",
        "created_at",
        "updated_at",
    ]
    params = {
        "query_text": payload["query_text"],
        "profile_id": payload.get("profile_id"),
        "target_llm": payload["target_llm"],
        "cadence_days": payload.get("cadence_days", 1),
        "next_run_at": next_run,
        "enabled": payload.get("enabled", True),
        "note": payload.get("note"),
        "brand_id": payload.get("brand_id"),
        "prompt_id": payload.get("prompt_id"),
    }
    if has_batch_cols:
        insert_cols.extend(["plan_kind", "target_llms_json", "query_items_json", "item_count"])
        value_exprs.extend(
            [
                ":plan_kind",
                "CAST(:target_llms_json AS jsonb)",
                "CAST(:query_items_json AS jsonb)",
                ":item_count",
            ]
        )
        returning_cols.extend(["plan_kind", "target_llms_json", "query_items_json", "item_count"])
        params.update(
            {
                "plan_kind": payload.get("plan_kind") or "single",
                "target_llms_json": json.dumps(payload.get("target_llms") or []),
                "query_items_json": json.dumps(payload.get("query_items") or []),
                "item_count": payload.get("item_count") or 1,
            }
        )
    sql = text(
        f"""
        INSERT INTO query_schedules
            ({", ".join(insert_cols)})
        VALUES ({", ".join(value_exprs)})
        RETURNING {", ".join(returning_cols)}
        """
    )
    row = (await session.execute(sql, params)).mappings().first()
    if not row:
        return None
    out = _row_to_schedule(dict(row))
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
    cols = await _table_columns(session, "query_schedules")
    has_batch_cols = {"plan_kind", "target_llms_json", "query_items_json", "item_count"}.issubset(
        cols
    )
    plan_cols = (
        "plan_kind, target_llms_json, query_items_json, item_count"
        if has_batch_cols
        else "'single' AS plan_kind, '[]' AS target_llms_json, "
        "'[]' AS query_items_json, 1 AS item_count"
    )
    sql = text(
        f"""
        SELECT id, query_text, profile_id, target_llm, cadence_days,
               next_run_at, last_run_at, enabled, note, {plan_cols}
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
                    "target_llms": _json_list(r.get("target_llms_json")),
                    "plan_kind": r.get("plan_kind") or "single",
                    "item_count": int(r.get("item_count") or 1),
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
