"""Manual scheduler trigger — Phase 8 slice 8c-bis.

Async port of admin_console's ``_run_manual_dispatch`` (lines 10125-10440
of admin_console/app.py). Reads scheduler_config (per-engine caps +
temp_global_cap), walks query_schedules + account_profile_map, and
inserts pending rows into the ``queries`` table. Returns a status dict
the SPA shows to the operator.

Design notes:
- Query rows are prepared in memory and inserted in one executemany call
  so large batch plans do not spend the whole proxy timeout in per-row DB
  round trips.
- Manual trigger SKIPS the "(B) per-(account,profile) random prompt fill"
  loop that the daily Beat tick runs — a single user reported 94k
  pending queries from repeated manual clicks. Schedules only.
- ``scheduler_runs`` row is inserted only when ``queries_created > 0``
  to keep the history table from filling with noise.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import column, insert, table, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.scheduler.lib import (
    is_query_engine,
    normalize_engine_caps,
    normalize_engine_name,
    normalize_paused_engines,
    schedule_item_target_llms,
)


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


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


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


async def _ensure_scheduler_config(session: AsyncSession) -> dict[str, Any]:
    """Read scheduler_config; seed a default row if the table is empty
    (admin_console parity, line 10144). Caller is inside a transaction."""
    row = (
        (
            await session.execute(
                text(
                    "SELECT id, mode, daily_time, timezone, temp_global_cap, "
                    "       engine_caps, retry_max, paused_engines "
                    "FROM scheduler_config ORDER BY id LIMIT 1"
                )
            )
        )
        .mappings()
        .first()
    )
    if row is not None:
        return dict(row)
    seeded = (
        (
            await session.execute(
                text(
                    "INSERT INTO scheduler_config "
                    "(mode, daily_time, timezone, temp_global_cap, engine_caps, "
                    " retry_max, paused_engines) "
                    "VALUES ('auto', '09:00', 'Asia/Shanghai', NULL, "
                    "        CAST('{}' AS jsonb), 3, CAST('[]' AS jsonb)) "
                    "RETURNING id, mode, daily_time, timezone, temp_global_cap, "
                    "          engine_caps, retry_max, paused_engines"
                )
            )
        )
        .mappings()
        .first()
    )
    if seeded is None:  # pragma: no cover — RETURNING should always emit
        return {
            "mode": "auto",
            "daily_time": "09:00",
            "timezone": "Asia/Shanghai",
            "temp_global_cap": None,
            "engine_caps": {},
            "retry_max": 3,
            "paused_engines": [],
        }
    return dict(seeded)


async def run_manual_dispatch(
    session: AsyncSession,
    *,
    cap_override: int | None = None,
    note: str = "manual via UI",
    brand_id: int | None = None,
    schedule_limit: int = 50,
) -> dict[str, Any]:
    """Inline copy of geo_tracker.tasks.scheduler.run_daily_dispatch
    (manual-trigger variant — schedules only, no random fill).

    Raises ``RuntimeError("scheduler_tables_unavailable")`` when the
    upstream tables aren't in the DB (sqlite test fixture). Router
    surfaces 503 with a stable error code.
    """
    if not (
        await _table_exists(session, "scheduler_config")
        and await _table_exists(session, "llm_accounts")
        and await _table_exists(session, "queries")
        and await _table_exists(session, "query_schedules")
    ):
        raise RuntimeError("scheduler_tables_unavailable")

    cfg = await _ensure_scheduler_config(session)
    paused_engines = normalize_paused_engines(cfg.get("paused_engines") or [])
    engine_caps = normalize_engine_caps(cfg.get("engine_caps") or {}, strict=False)

    # ── per-(account, profile) quota frame ───────────────────────────
    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT a.id           AS account_id,
                       a.llm_name     AS engine,
                       a.daily_limit  AS account_cap,
                       COALESCE(apm.profile_id, a.profile_id::text) AS profile_id,
                       COALESCE(apm.daily_quota, 1) AS quota
                FROM llm_accounts a
                LEFT JOIN account_profile_map apm ON apm.account_id = a.id
                WHERE a.status = 'active'
                  AND a.cookies_json IS NOT NULL
                  AND a.cookies_json != ''
                """
                )
            )
        )
        .mappings()
        .all()
    )
    quotas: list[dict[str, Any]] = [
        dict(r)
        for r in rows
        if r.get("profile_id") is not None and is_query_engine(r.get("engine"))
    ]

    paused_set = {str(e).lower() for e in paused_engines}
    quotas = [q for q in quotas if normalize_engine_name(q.get("engine")) not in paused_set]

    # Per-account daily_limit cap (binding rows may over-allocate).
    by_account: dict[Any, list[dict[str, Any]]] = {}
    for q in quotas:
        by_account.setdefault(q["account_id"], []).append(q)
    for items in by_account.values():
        cap_v = int(items[0].get("account_cap") or 0)
        total = sum(int(i.get("quota") or 0) for i in items)
        if cap_v > 0 and total > cap_v and total > 0:
            scale = cap_v / total
            for item in items:
                item["quota"] = max(1, round(int(item.get("quota") or 0) * scale))

    # Per-engine caps from the UI's 当日产出 card.
    if engine_caps:
        by_engine: dict[str, list[dict[str, Any]]] = {}
        for q in quotas:
            by_engine.setdefault(normalize_engine_name(q.get("engine")), []).append(q)
        for engine, items in by_engine.items():
            raw_cap = engine_caps.get(engine)
            if raw_cap is None or raw_cap == 0:
                continue
            try:
                ec = int(raw_cap)
            except (TypeError, ValueError):
                continue
            total = sum(int(i.get("quota") or 0) for i in items)
            if ec <= 0 or total <= ec or total == 0:
                continue
            scale = ec / total
            for item in items:
                item["quota"] = max(1, round(int(item.get("quota") or 0) * scale))

    # Optional global cap (manual override or temp_global_cap).
    global_cap = cap_override if cap_override is not None else cfg.get("temp_global_cap")
    if global_cap and int(global_cap) > 0:
        gc = int(global_cap)
        total = sum(int(q.get("quota") or 0) for q in quotas)
        if total > gc and total > 0:
            scale = gc / total
            for q in quotas:
                q["quota"] = max(1, round(int(q.get("quota") or 0) * scale))

    schedule_cols = await _table_columns(session, "query_schedules")
    has_batch_cols = {
        "plan_kind",
        "target_llms_json",
        "query_items_json",
        "item_count",
    }.issubset(schedule_cols)
    plan_cols = (
        "plan_kind, target_llms_json, query_items_json, item_count"
        if has_batch_cols
        else "'single' AS plan_kind, '[]' AS target_llms_json, "
        "'[]' AS query_items_json, 1 AS item_count"
    )
    schedule_params: dict[str, Any] = {}
    schedule_where_parts = ["qs.enabled = TRUE"]
    brand_filter = await _schedule_brand_filter(
        session,
        alias="qs",
        has_batch_cols=has_batch_cols,
        brand_id=brand_id,
        params=schedule_params,
    )
    if brand_filter:
        schedule_where_parts.append(brand_filter)
    schedule_where = " AND ".join(schedule_where_parts)

    # ── total enabled schedules (independent of paused filter) ───────
    schedules_enabled_row = (
        (
            await session.execute(
                text(f"SELECT COUNT(*) AS n FROM query_schedules qs WHERE {schedule_where}"),
                schedule_params,
            )
        )
        .mappings()
        .first()
    )
    schedules_enabled_total = int(
        (dict(schedules_enabled_row) if schedules_enabled_row else {}).get("n") or 0
    )

    # Fetch enabled schedules (ignore next_run_at — manual trigger fires
    # everything). LIMIT 50 keeps work bounded against proxy timeouts.
    schedule_limit = min(5000, max(1, int(schedule_limit or 50)))
    due_params = dict(schedule_params)
    due_params["limit"] = schedule_limit
    due_rows = (
        (
            await session.execute(
                text(
                    f"""
                SELECT id, query_text, profile_id, target_llm, cadence_days,
                       brand_id, prompt_id, {plan_cols}
                FROM query_schedules qs
                WHERE {schedule_where}
                ORDER BY next_run_at ASC, id ASC
                LIMIT :limit
                """
                ),
                due_params,
            )
        )
        .mappings()
        .all()
    )
    due_schedules: list[dict[str, Any]] = []
    for raw in due_rows:
        row = dict(raw)
        target_llms = [
            str(v)
            for v in _json_list(row.get("target_llms_json"))
            if is_query_engine(v) and str(v).lower() not in paused_engines
        ]
        if not target_llms:
            fallback_llm = normalize_engine_name(row.get("target_llm"))
            if is_query_engine(fallback_llm) and fallback_llm not in paused_engines:
                target_llms = [fallback_llm]
        if row.get("plan_kind") == "batch":
            for item in _json_list(row.get("query_items_json")):
                if not isinstance(item, dict):
                    continue
                for target_llm in schedule_item_target_llms(item, target_llms):
                    if not is_query_engine(target_llm):
                        continue
                    due_schedules.append(
                        {
                            **row,
                            "query_text": item.get("query_text"),
                            "profile_id": item.get("profile_id"),
                            "brand_id": item.get("brand_id"),
                            "prompt_id": item.get("prompt_id"),
                            "target_llm": target_llm,
                        }
                    )
            continue
        target_llm = normalize_engine_name(row.get("target_llm"))
        target_allowed = schedule_item_target_llms(
            {"query_text": row.get("query_text")},
            [target_llm],
        )
        if (
            is_query_engine(row.get("target_llm"))
            and target_llm not in paused_engines
            and target_allowed
        ):
            due_schedules.append(row)

    # ── (A) consume due query_schedules ─────────────────────────────
    schedule_failures: list[str] = []
    account_by_engine: dict[str, Any] = {}
    account_by_engine_profile: dict[tuple[str, str], Any] = {}
    for quota_row in rows:
        quota = dict(quota_row)
        account_id = quota.get("account_id")
        engine = normalize_engine_name(quota.get("engine"))
        if not account_id or not is_query_engine(engine):
            continue
        account_by_engine.setdefault(engine, account_id)
        profile_id = quota.get("profile_id")
        if profile_id is not None:
            account_by_engine_profile.setdefault((engine, str(profile_id)), account_id)

    query_cols = await _table_columns(session, "queries")
    include_schedule_id = "schedule_id" in query_cols
    include_queued_at = "queued_at" in query_cols
    insert_cols = [
        "prompt_id",
        "profile_id",
        "brand_id",
        "account_id",
        "query_text",
        "target_llm",
        "status",
    ]
    if include_schedule_id:
        insert_cols.append("schedule_id")
    insert_cols.append("created_at")
    if include_queued_at:
        insert_cols.append("queued_at")
    queries_table = table("queries", column("id"), *(column(name) for name in insert_cols))

    insert_rows: list[dict[str, Any]] = []
    touched_schedule_ids: set[int] = set()
    now = _utcnow_naive()
    for sch in due_schedules:
        try:
            query_text = str(sch.get("query_text") or "").strip()
            target_llm = normalize_engine_name(sch.get("target_llm"))
            if not query_text:
                raise ValueError("query_text is required")
            if not is_query_engine(target_llm):
                raise ValueError("target_llm is not dispatchable")

            # queries.profile_id may be INTEGER (geo_tracker schema) — coerce
            # when possible, drop to NULL otherwise.
            pid_for_queries: Any = sch.get("profile_id")
            profile_key: str | None = None
            if pid_for_queries is not None:
                profile_key = str(pid_for_queries)
                try:
                    pid_for_queries = int(pid_for_queries)
                except (TypeError, ValueError):
                    pid_for_queries = None

            account_id = (
                account_by_engine_profile.get((target_llm, profile_key))
                if profile_key is not None
                else None
            )
            if account_id is None:
                account_id = account_by_engine.get(target_llm)

            row = {
                "prompt_id": sch.get("prompt_id"),
                "profile_id": pid_for_queries,
                "brand_id": sch.get("brand_id"),
                "account_id": account_id,
                "query_text": query_text,
                "target_llm": target_llm,
                "status": "pending",
                "created_at": now,
            }
            if include_schedule_id:
                row["schedule_id"] = sch.get("id")
            if include_queued_at:
                row["queued_at"] = now
            insert_rows.append(row)
            touched_schedule_ids.add(int(sch["id"]))
        except Exception as exc:
            schedule_failures.append(f"#{sch.get('id')}: {exc}")

    created = 0
    query_ids: list[int] = []
    if insert_rows:
        inserted = await session.execute(
            insert(queries_table).returning(queries_table.c.id),
            insert_rows,
        )
        query_ids = [int(row["id"]) for row in inserted.mappings().all()]
        await session.execute(
            text(
                """
                UPDATE query_schedules
                   SET last_run_at = NOW(),
                       next_run_at = NOW() + (cadence_days || ' days')::interval,
                       updated_at = NOW()
                 WHERE id = ANY(:ids)
                """
            ),
            {"ids": sorted(touched_schedule_ids)},
        )
        created = len(insert_rows)

    # Manual trigger skips the (B) random-fill loop on purpose. The
    # Beat task (geo_tracker.tasks.scheduler) keeps the original
    # (A)+(B) behavior for the daily auto run.
    target_total = len(due_schedules)

    # Only record a scheduler_runs row when work happened (admin_console
    # line 10399 — "0 / 0" rows just clutter the history table).
    run_id: int | None = None
    if created > 0:
        run_row = (
            (
                await session.execute(
                    text(
                        "INSERT INTO scheduler_runs "
                        "(mode, target_total, queries_created, note, finished_at) "
                        "VALUES ('manual', :target_total, :created, :note, NOW()) "
                        "RETURNING id"
                    ),
                    {"target_total": target_total, "created": created, "note": note},
                )
            )
            .mappings()
            .first()
        )
        run_id = int((dict(run_row) if run_row else {}).get("id") or 0) or None

    await session.commit()

    # Reason taxonomy admin_console line 10408-10424.
    if created > 0:
        reason = "ok"
    elif schedules_enabled_total == 0 and not quotas:
        reason = "no_plans_or_bindings"
    elif schedules_enabled_total > 0 and len(due_schedules) == 0:
        reason = "all_engines_paused"
    elif schedules_enabled_total == 0 and quotas:
        reason = "no_schedules_only_bindings_no_prompts"
    else:
        reason = "unknown"

    return {
        "target_total": target_total,
        "queries_created": created,
        "query_ids": query_ids,
        "run_id": run_id,
        "reason": reason,
        "schedules_enabled": schedules_enabled_total,
        "schedules_dispatchable": len(due_schedules),
        "brand_id": brand_id,
        "schedule_limit": schedule_limit,
        "paused_engines": paused_engines,
        "quotas_total": sum(int(q.get("quota") or 0) for q in quotas),
        "schedule_failures": schedule_failures,
    }


__all__ = ["run_manual_dispatch"]
