"""
Scheduler — Daily Query Dispatch
================================

Replaces the conceptual "采集调度" pipeline with a concrete, browser-use-only
daily dispatcher. Reads ``scheduler_config`` for the global mode/throttle, then
walks ``account_profile_map`` to compute per-(account, profile, llm) quotas
and inserts rows into ``queries``.

Physical capacity ceiling: ``Σ active_accounts.daily_limit`` — there is no
"budget" abstraction above that, since every query goes through a real
browser session via the queue worker.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

# LLM → default geo (per product spec: 豆包/DS = CN, ChatGPT = US/NA)
LLM_DEFAULT_GEO = {
    "doubao": "CN",
    "deepseek": "CN",
    "chatgpt": "US",
    "gemini": "US",
}

SCHEDULER_EXCLUDED_ENGINE_SUFFIXES = ("_hots",)


def _normalize_scheduler_engine_name(llm_name: Any) -> str:
    return str(llm_name or "").strip().lower()


def _is_scheduler_query_engine(llm_name: Any) -> bool:
    engine = _normalize_scheduler_engine_name(llm_name)
    return bool(engine) and not engine.endswith(SCHEDULER_EXCLUDED_ENGINE_SUFFIXES)


def _db_url() -> str:
    url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    # psycopg2 wants 'postgresql://' not 'postgresql+asyncpg://'
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _connect():
    return psycopg2.connect(_db_url())


def _load_config(cur) -> Dict[str, Any]:
    cur.execute(
        """
        SELECT id, mode, daily_time, timezone, temp_global_cap, engine_caps,
               retry_max, paused_engines
        FROM scheduler_config
        ORDER BY id ASC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if row:
        return dict(row)
    # Lazy-create default config row on first run
    cur.execute(
        """
        INSERT INTO scheduler_config
            (mode, daily_time, timezone, temp_global_cap, engine_caps,
             retry_max, paused_engines)
        VALUES ('auto', '09:00', 'Asia/Shanghai', NULL, '{}'::jsonb,
                3, '[]'::jsonb)
        RETURNING id, mode, daily_time, timezone, temp_global_cap, engine_caps,
                  retry_max, paused_engines
        """
    )
    return dict(cur.fetchone())


def _quotas(cur, paused_engines: List[str]) -> List[Dict[str, Any]]:
    """Return per-(account, profile, engine) quotas to dispatch today.

    Source of truth: ``account_profile_map``. Falls back to the legacy
    ``llm_accounts.profile_id`` for accounts that have no explicit binding
    rows yet, so we don't silently drop them on rollout.
    """
    cur.execute(
        """
        WITH bindings AS (
            SELECT
                a.id           AS account_id,
                a.llm_name     AS engine,
                a.daily_limit  AS account_cap,
                COALESCE(apm.profile_id, a.profile_id::text) AS profile_id,
                COALESCE(apm.daily_quota, 1) AS quota
            FROM llm_accounts a
            LEFT JOIN account_profile_map apm ON apm.account_id = a.id
            WHERE a.status = 'active'
              AND a.cookies_json IS NOT NULL
              AND a.cookies_json != ''
        )
        SELECT account_id, engine, account_cap, profile_id, quota
        FROM bindings
        WHERE profile_id IS NOT NULL
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    rows = [r for r in rows if _is_scheduler_query_engine(r.get("engine"))]

    # Drop entries whose engine is paused right now.
    paused = {
        _normalize_scheduler_engine_name(engine)
        for engine in (paused_engines or [])
        if _is_scheduler_query_engine(engine)
    }
    rows = [
        r for r in rows
        if _normalize_scheduler_engine_name(r.get("engine")) not in paused
    ]

    # Cap the total quota per account at its daily_limit (binding rows may
    # over-allocate; we shrink proportionally if so).
    by_account: Dict[int, List[Dict[str, Any]]] = {}
    for r in rows:
        by_account.setdefault(r["account_id"], []).append(r)
    capped: List[Dict[str, Any]] = []
    for account_id, items in by_account.items():
        cap = items[0]["account_cap"] or 0
        total = sum(int(i["quota"] or 0) for i in items)
        if cap > 0 and total > cap and total > 0:
            scale = cap / total
            for i in items:
                i["quota"] = max(1, int(round(int(i["quota"] or 0) * scale)))
        capped.extend(items)
    return capped


def _apply_global_cap(quotas: List[Dict[str, Any]], cap: Optional[int]) -> List[Dict[str, Any]]:
    if not cap or cap <= 0:
        return quotas
    total = sum(int(q["quota"] or 0) for q in quotas)
    if total <= cap or total == 0:
        return quotas
    scale = cap / total
    for q in quotas:
        q["quota"] = max(1, int(round(int(q["quota"] or 0) * scale)))
    return quotas


def _apply_engine_caps(
    quotas: List[Dict[str, Any]],
    engine_caps: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Apply per-engine ceilings.

    ``engine_caps`` shape: ``{"doubao": 100, "deepseek": null}``. A null or
    missing entry means "no cap, use account capacity for that engine"; 0 also
    means "no cap" (UI sends 0 for empty inputs in some cases). Negatives are
    rejected at the API layer, so we don't re-validate here.
    """
    if not engine_caps:
        return quotas
    by_engine: Dict[str, List[Dict[str, Any]]] = {}
    for q in quotas:
        by_engine.setdefault((q.get("engine") or "").lower(), []).append(q)
    for engine, items in by_engine.items():
        cap = engine_caps.get(engine)
        if cap in (None, 0):
            continue
        try:
            cap_i = int(cap)
        except Exception:
            continue
        total = sum(int(i["quota"] or 0) for i in items)
        if cap_i <= 0 or total <= cap_i or total == 0:
            continue
        scale = cap_i / total
        for i in items:
            i["quota"] = max(1, int(round(int(i["quota"] or 0) * scale)))
    return quotas


def _pick_query_text(cur, profile_id: str, engine: str) -> Optional[Dict[str, Any]]:
    """Pick one prompt to enqueue for this (profile, engine) pair.

    Strategy: prefer prompts that have not yet been queried for this
    (profile, engine) today, ordered by lowest historical attempt count.
    Returns ``None`` if no candidate prompt exists.
    """
    cur.execute(
        """
        SELECT pr.id   AS prompt_id,
               pr.text AS query_text,
               t.brand_id
        FROM prompts pr
        JOIN topics  t  ON t.id = pr.topic_id
        WHERE NOT EXISTS (
            SELECT 1 FROM queries q
            WHERE q.prompt_id = pr.id
              AND q.profile_id::text = %s
              AND q.target_llm = %s
              AND DATE(q.created_at) = CURRENT_DATE
        )
        ORDER BY (
            SELECT COUNT(*) FROM queries q2
            WHERE q2.prompt_id = pr.id AND q2.target_llm = %s
        ) ASC,
        random()
        LIMIT 1
        """,
        (str(profile_id), engine, engine),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def run_daily_dispatch(
    *,
    mode_override: Optional[str] = None,
    cap_override: Optional[int] = None,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """Entry point for both Beat (no kwargs) and the manual-trigger button.

    Returns: ``{"target_total": N, "queries_created": M, "run_id": K}``.
    Raises if DB is unreachable or the mode is "paused".
    """
    conn = _connect()
    conn.autocommit = False
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cfg = _load_config(cur)
            effective_mode = (mode_override or cfg["mode"] or "auto").lower()
            if effective_mode == "paused":
                logger.info("Scheduler paused; skipping dispatch")
                return {"target_total": 0, "queries_created": 0, "run_id": None,
                        "skipped": "paused"}

            paused_engines = cfg.get("paused_engines") or []
            quotas = _quotas(cur, paused_engines)
            # Order matters: per-engine caps shrink first (so the global cap
            # then applies to a number that already respects engine ceilings),
            # then the optional global cap.
            quotas = _apply_engine_caps(quotas, cfg.get("engine_caps") or {})
            cap = cap_override if cap_override is not None else cfg.get("temp_global_cap")
            quotas = _apply_global_cap(quotas, cap)

            target_total = sum(int(q["quota"] or 0) for q in quotas)

            # Open a run row up front so partial failures still leave a record
            cur.execute(
                """
                INSERT INTO scheduler_runs (mode, target_total, queries_created, note)
                VALUES (%s, %s, 0, %s)
                RETURNING id
                """,
                (effective_mode, target_total, note),
            )
            run_id = cur.fetchone()["id"]

            created = 0

            # ── Consume due query_schedules first (recurring user-defined plans) ──
            paused_lower = [str(e).lower() for e in (paused_engines or [])]
            cur.execute(
                """
                SELECT id, query_text, profile_id, target_llm, cadence_days,
                       brand_id, prompt_id
                FROM query_schedules
                WHERE enabled = TRUE
                  AND next_run_at <= NOW()
                  AND target_llm NOT IN (
                      SELECT jsonb_array_elements_text(%s::jsonb)
                  )
                ORDER BY next_run_at ASC, id ASC
                """,
                (json.dumps(paused_lower),),
            )
            due_schedules = [dict(r) for r in cur.fetchall()]
            due_schedules = [
                sch for sch in due_schedules
                if _is_scheduler_query_engine(sch.get("target_llm"))
            ]
            for sch in due_schedules:
                # SAVEPOINT per row so a single bad schedule (profile_id type
                # mismatch, missing schedule_id column) doesn't poison the
                # batch.
                cur.execute("SAVEPOINT sp_sched")
                try:
                    cur.execute(
                        """
                        SELECT a.id
                        FROM llm_accounts a
                        LEFT JOIN account_profile_map apm
                               ON apm.account_id = a.id
                              AND apm.profile_id = %s
                        WHERE a.llm_name = %s
                          AND a.status = 'active'
                          AND a.cookies_json IS NOT NULL
                          AND a.cookies_json != ''
                          AND (%s IS NULL
                               OR apm.profile_id IS NOT NULL
                               OR a.profile_id::text = %s)
                        ORDER BY (apm.profile_id IS NOT NULL) DESC,
                                 a.last_used_at NULLS FIRST,
                                 a.id
                        LIMIT 1
                        """,
                        (sch["profile_id"], sch["target_llm"],
                         sch["profile_id"], sch["profile_id"]),
                    )
                    acct = cur.fetchone()
                    account_id = acct["id"] if acct else None
                    pid_for_queries = sch.get("profile_id")
                    if pid_for_queries is not None:
                        try:
                            pid_for_queries = int(pid_for_queries)
                        except (TypeError, ValueError):
                            # Non-numeric (e.g. "pf_xxx") — drop to NULL if
                            # queries.profile_id is INTEGER. The retry path
                            # below catches the type error and re-tries with
                            # NULL.
                            pass
                    try:
                        cur.execute(
                            """
                            INSERT INTO queries
                                (prompt_id, profile_id, brand_id, account_id,
                                 query_text, target_llm, status, schedule_id,
                                 created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s,
                                    NOW())
                            """,
                            (
                                sch.get("prompt_id"),
                                pid_for_queries,
                                sch.get("brand_id"),
                                account_id,
                                sch["query_text"],
                                sch["target_llm"],
                                sch["id"],
                            ),
                        )
                    except Exception:
                        cur.execute("ROLLBACK TO SAVEPOINT sp_sched")
                        cur.execute(
                            """
                            INSERT INTO queries
                                (prompt_id, profile_id, brand_id, account_id,
                                 query_text, target_llm, status, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, 'pending', NOW())
                            """,
                            (
                                sch.get("prompt_id"),
                                None,
                                sch.get("brand_id"),
                                account_id,
                                sch["query_text"],
                                sch["target_llm"],
                            ),
                        )
                    cur.execute(
                        """
                        UPDATE query_schedules
                           SET last_run_at = NOW(),
                               next_run_at = NOW() + (cadence_days || ' days')::interval,
                               updated_at = NOW()
                         WHERE id = %s
                        """,
                        (sch["id"],),
                    )
                    cur.execute("RELEASE SAVEPOINT sp_sched")
                    created += 1
                except Exception as e:
                    cur.execute("ROLLBACK TO SAVEPOINT sp_sched")
                    logger.warning(
                        "Skipping schedule #%s due to error: %s", sch["id"], e
                    )
                    continue

            # ── Random prompt fill against per-(account, profile) quotas ──
            for q in quotas:
                for _ in range(int(q["quota"] or 0)):
                    pick = _pick_query_text(cur, q["profile_id"], q["engine"])
                    if not pick:
                        # No fresh prompt available for this pair today; skip
                        continue
                    cur.execute(
                        """
                        INSERT INTO queries
                            (prompt_id, profile_id, brand_id, account_id,
                             query_text, target_llm, status, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, 'pending', NOW())
                        """,
                        (
                            pick["prompt_id"],
                            q["profile_id"],
                            pick.get("brand_id"),
                            q["account_id"],
                            pick["query_text"],
                            q["engine"],
                        ),
                    )
                    created += 1

            cur.execute(
                """
                UPDATE scheduler_runs
                   SET queries_created = %s, finished_at = NOW()
                 WHERE id = %s
                """,
                (created, run_id),
            )
            conn.commit()

            logger.info(
                "Scheduler dispatch complete: mode=%s target=%d created=%d run_id=%d",
                effective_mode, target_total, created, run_id,
            )
            return {
                "target_total": target_total,
                "queries_created": created,
                "run_id": run_id,
            }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─── Celery task wrapper ─────────────────────────────────────────────────────
try:
    from app.celery_app import celery_app  # backend service

    @celery_app.task(name="geo_tracker.tasks.scheduler.run_daily_dispatch")
    def run_daily_dispatch_task() -> Dict[str, Any]:
        return run_daily_dispatch()
except Exception:  # backend Celery not importable in this env — runtime-only
    pass
