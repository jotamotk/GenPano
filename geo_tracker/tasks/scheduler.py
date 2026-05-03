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
        SELECT id, mode, daily_time, timezone, temp_global_cap, retry_max,
               paused_engines
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
            (mode, daily_time, timezone, temp_global_cap, retry_max, paused_engines)
        VALUES ('auto', '09:00', 'Asia/Shanghai', NULL, 3, '[]'::jsonb)
        RETURNING id, mode, daily_time, timezone, temp_global_cap, retry_max,
                  paused_engines
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

    # Drop entries whose engine is paused right now.
    paused = set((paused_engines or []))
    rows = [r for r in rows if r["engine"] not in paused]

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
