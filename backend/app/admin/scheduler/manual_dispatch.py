"""Manual scheduler trigger — Phase 8 slice 8c-bis.

Async port of admin_console's ``_run_manual_dispatch`` (lines 10125-10440
of admin_console/app.py). Reads scheduler_config (per-engine caps +
temp_global_cap), walks query_schedules + account_profile_map, and
inserts pending rows into the ``queries`` table. Returns a status dict
the SPA shows to the operator.

Design notes:
- SAVEPOINTs (``session.begin_nested``) wrap each schedule INSERT so a
  single bad row (profile_id type mismatch / queries.schedule_id column
  missing on legacy DB) doesn't poison the whole dispatch.
- Manual trigger SKIPS the "(B) per-(account,profile) random prompt fill"
  loop that the daily Beat tick runs — a single user reported 94k
  pending queries from repeated manual clicks. Schedules only.
- ``scheduler_runs`` row is inserted only when ``queries_created > 0``
  to keep the history table from filling with noise.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.scheduler.lib import (
    is_query_engine,
    normalize_engine_caps,
    normalize_engine_name,
    normalize_paused_engines,
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
    session: AsyncSession, *, cap_override: int | None = None, note: str = "manual via UI"
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

    # ── total enabled schedules (independent of paused filter) ───────
    schedules_enabled_row = (
        (
            await session.execute(
                text("SELECT COUNT(*) AS n FROM query_schedules WHERE enabled = TRUE")
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
    paused_json = json.dumps([str(e).lower() for e in paused_engines])
    due_rows = (
        (
            await session.execute(
                text(
                    """
                SELECT id, query_text, profile_id, target_llm, cadence_days,
                       brand_id, prompt_id
                FROM query_schedules
                WHERE enabled = TRUE
                  AND target_llm NOT IN (
                      SELECT jsonb_array_elements_text(CAST(:paused AS jsonb))
                  )
                ORDER BY next_run_at ASC, id ASC
                LIMIT 50
                """
                ),
                {"paused": paused_json},
            )
        )
        .mappings()
        .all()
    )
    due_schedules = [dict(r) for r in due_rows if is_query_engine(r.get("target_llm"))]

    # ── (A) consume due query_schedules ─────────────────────────────
    schedule_failures: list[str] = []
    created = 0
    for sch in due_schedules:
        # SAVEPOINT per schedule so a single broken row doesn't poison
        # the whole dispatch (mirrors admin_console line 10283).
        savepoint = await session.begin_nested()
        try:
            account_row = (
                (
                    await session.execute(
                        text(
                            """
                        SELECT a.id
                        FROM llm_accounts a
                        LEFT JOIN account_profile_map apm
                               ON apm.account_id = a.id
                              AND apm.profile_id = :pid
                        WHERE a.llm_name = :engine
                          AND a.status = 'active'
                          AND a.cookies_json IS NOT NULL
                          AND a.cookies_json != ''
                          AND (:pid_null IS NULL
                               OR apm.profile_id IS NOT NULL
                               OR a.profile_id::text = :pid)
                        ORDER BY (apm.profile_id IS NOT NULL) DESC,
                                 a.last_used_at NULLS FIRST,
                                 a.id
                        LIMIT 1
                        """
                        ),
                        {
                            "pid": sch.get("profile_id"),
                            "engine": sch.get("target_llm"),
                            "pid_null": sch.get("profile_id"),
                        },
                    )
                )
                .mappings()
                .first()
            )
            account_id = (dict(account_row) if account_row else {}).get("id")

            # queries.profile_id may be INTEGER (geo_tracker schema) — coerce
            # when possible, drop to NULL otherwise.
            pid_for_queries: Any = sch.get("profile_id")
            if pid_for_queries is not None:
                try:
                    pid_for_queries = int(pid_for_queries)
                except (TypeError, ValueError):
                    pid_for_queries = None

            try:
                await session.execute(
                    text(
                        """
                        INSERT INTO queries
                            (prompt_id, profile_id, brand_id, account_id,
                             query_text, target_llm, status, schedule_id,
                             created_at)
                        VALUES (:prompt_id, :profile_id, :brand_id, :account_id,
                                :query_text, :target_llm, 'pending',
                                :schedule_id, NOW())
                        """
                    ),
                    {
                        "prompt_id": sch.get("prompt_id"),
                        "profile_id": pid_for_queries,
                        "brand_id": sch.get("brand_id"),
                        "account_id": account_id,
                        "query_text": sch["query_text"],
                        "target_llm": sch["target_llm"],
                        "schedule_id": sch["id"],
                    },
                )
            except Exception:
                # schedule_id column missing OR profile_id type mismatch we
                # couldn't coerce. Roll back the savepoint, then INSERT
                # without schedule_id + with profile_id=NULL (safest).
                await savepoint.rollback()
                savepoint = await session.begin_nested()
                await session.execute(
                    text(
                        """
                        INSERT INTO queries
                            (prompt_id, profile_id, brand_id, account_id,
                             query_text, target_llm, status, created_at)
                        VALUES (:prompt_id, NULL, :brand_id, :account_id,
                                :query_text, :target_llm, 'pending', NOW())
                        """
                    ),
                    {
                        "prompt_id": sch.get("prompt_id"),
                        "brand_id": sch.get("brand_id"),
                        "account_id": account_id,
                        "query_text": sch["query_text"],
                        "target_llm": sch["target_llm"],
                    },
                )

            await session.execute(
                text(
                    """
                    UPDATE query_schedules
                       SET last_run_at = NOW(),
                           next_run_at = NOW() + (cadence_days || ' days')::interval,
                           updated_at = NOW()
                     WHERE id = :id
                    """
                ),
                {"id": sch["id"]},
            )
            await savepoint.commit()
            created += 1
        except Exception as exc:
            try:
                await savepoint.rollback()
            except Exception:
                pass
            schedule_failures.append(f"#{sch.get('id')}: {exc}")
            continue

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
        "run_id": run_id,
        "reason": reason,
        "schedules_enabled": schedules_enabled_total,
        "schedules_dispatchable": len(due_schedules),
        "paused_engines": paused_engines,
        "quotas_total": sum(int(q.get("quota") or 0) for q in quotas),
        "schedule_failures": schedule_failures,
    }


__all__ = ["run_manual_dispatch"]
