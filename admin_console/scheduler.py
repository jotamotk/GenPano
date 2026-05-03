"""Scheduling + execution-tracking helpers for the GenPano Admin console.

This module owns three concerns that the admin console previously stubbed in
the prototype HTML:

1. **Schedule config** — when (and whether) the daily auto-collection runs,
   plus per-LLM caps and the optional manual override count.
2. **Profile-account routing** — which LLM accounts each Profile is routed to
   per LLM (chatgpt / doubao / deepseek / etc). The scheduler picks accounts
   with capacity from each profile's binding list when dispatching.
3. **Schedule run history** — every auto or manual collection produces a row
   in ``schedule_runs`` so the UI can render a per-day execution timeline.

The HTTP routes and the daily auto-trigger thread live in ``app.py`` and call
into this module so the Flask file stays slim and the logic is unit-testable
without spinning up the full Flask app.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

# ── Constants ─────────────────────────────────────────────────────────────────
APPROVED_LLMS = ("chatgpt", "doubao", "deepseek")
DEFAULT_RUN_TIME = "03:00"  # UTC; admins can override per-deployment
DEFAULT_DAILY_CAP_PER_LLM = 200
SCHEDULE_CONFIG_ID = 1  # singleton row


# ── Migration ────────────────────────────────────────────────────────────────
def ensure_schedule_tables(get_db_conn):
    """Idempotently create scheduler tables and seed the singleton config row.

    ``get_db_conn`` is the project's ``get_db`` callable; we accept it as a
    parameter so this module doesn't need to import from app.py at import
    time (and the tests can swap in a fake).
    """
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schedule_config (
                    id INTEGER PRIMARY KEY,
                    paused BOOLEAN NOT NULL DEFAULT FALSE,
                    auto_run_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    daily_run_time VARCHAR(5) NOT NULL DEFAULT '03:00',
                    timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
                    daily_caps_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                    per_profile_cap INTEGER NOT NULL DEFAULT 5,
                    last_modified_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    last_modified_by VARCHAR(64)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schedule_runs (
                    id SERIAL PRIMARY KEY,
                    run_uid VARCHAR(64) UNIQUE,
                    trigger_type VARCHAR(16) NOT NULL,
                    status VARCHAR(16) NOT NULL,
                    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    finished_at TIMESTAMP,
                    planned_count INTEGER NOT NULL DEFAULT 0,
                    dispatched_count INTEGER NOT NULL DEFAULT 0,
                    skipped_count INTEGER NOT NULL DEFAULT 0,
                    config_snapshot_json JSONB,
                    per_llm_breakdown_json JSONB,
                    note TEXT,
                    triggered_by VARCHAR(64)
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS ix_schedule_runs_started_at "
                "ON schedule_runs(started_at DESC)"
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS profile_account_bindings (
                    id SERIAL PRIMARY KEY,
                    profile_id INTEGER NOT NULL,
                    llm_name VARCHAR(32) NOT NULL,
                    account_id INTEGER NOT NULL,
                    weight INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_profile_llm_account
                        UNIQUE (profile_id, llm_name, account_id)
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS ix_profile_bindings_profile "
                "ON profile_account_bindings(profile_id)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS ix_profile_bindings_llm "
                "ON profile_account_bindings(llm_name)"
            )

            # Seed singleton config.
            default_caps = {llm: DEFAULT_DAILY_CAP_PER_LLM for llm in APPROVED_LLMS}
            cur.execute(
                """
                INSERT INTO schedule_config
                    (id, paused, auto_run_enabled, daily_run_time, timezone,
                     daily_caps_json, per_profile_cap)
                VALUES (%s, FALSE, TRUE, %s, 'UTC', %s::jsonb, 5)
                ON CONFLICT (id) DO NOTHING
                """,
                (SCHEDULE_CONFIG_ID, DEFAULT_RUN_TIME, json.dumps(default_caps)),
            )
        conn.commit()
    finally:
        conn.close()


# ── Config helpers ────────────────────────────────────────────────────────────
def fetch_config(cur) -> dict:
    """Read the singleton schedule config row, returning safe defaults if missing."""
    cur.execute(
        """
        SELECT paused, auto_run_enabled, daily_run_time, timezone,
               daily_caps_json, per_profile_cap,
               last_modified_at, last_modified_by
        FROM schedule_config WHERE id = %s
        """,
        (SCHEDULE_CONFIG_ID,),
    )
    row = cur.fetchone()
    if not row:
        return {
            "paused": False,
            "auto_run_enabled": True,
            "daily_run_time": DEFAULT_RUN_TIME,
            "timezone": "UTC",
            "daily_caps": {llm: DEFAULT_DAILY_CAP_PER_LLM for llm in APPROVED_LLMS},
            "per_profile_cap": 5,
            "last_modified_at": None,
            "last_modified_by": None,
        }
    if isinstance(row, dict):
        paused = row.get("paused")
        auto_enabled = row.get("auto_run_enabled")
        run_time = row.get("daily_run_time")
        tz = row.get("timezone")
        caps_json = row.get("daily_caps_json")
        per_profile = row.get("per_profile_cap")
        modified_at = row.get("last_modified_at")
        modified_by = row.get("last_modified_by")
    else:
        paused, auto_enabled, run_time, tz, caps_json, per_profile, modified_at, modified_by = row
    caps = caps_json if isinstance(caps_json, dict) else (json.loads(caps_json) if caps_json else {})
    # Backfill any missing LLM entries with the default cap so the UI always
    # shows the same set of inputs and ``apply_caps`` doesn't have to worry
    # about missing keys when computing remaining budget.
    for llm in APPROVED_LLMS:
        caps.setdefault(llm, DEFAULT_DAILY_CAP_PER_LLM)
    return {
        "paused": bool(paused),
        "auto_run_enabled": bool(auto_enabled),
        "daily_run_time": run_time or DEFAULT_RUN_TIME,
        "timezone": tz or "UTC",
        "daily_caps": caps,
        "per_profile_cap": int(per_profile or 5),
        "last_modified_at": modified_at.isoformat() if modified_at else None,
        "last_modified_by": modified_by,
    }


def update_config(cur, *, paused=None, auto_run_enabled=None, daily_run_time=None,
                  daily_caps=None, per_profile_cap=None, modified_by=None) -> dict:
    """Patch the singleton config. Pass ``None`` to leave a field unchanged."""
    sets = []
    params: list[Any] = []
    if paused is not None:
        sets.append("paused = %s")
        params.append(bool(paused))
    if auto_run_enabled is not None:
        sets.append("auto_run_enabled = %s")
        params.append(bool(auto_run_enabled))
    if daily_run_time is not None:
        # Accept "HH:MM" only — guard against arbitrary input since this gets
        # fed into the auto-trigger thread's clock comparisons.
        if not isinstance(daily_run_time, str) or len(daily_run_time) != 5 or daily_run_time[2] != ":":
            raise ValueError("daily_run_time must be 'HH:MM'")
        hh, mm = daily_run_time.split(":")
        if not (hh.isdigit() and mm.isdigit() and 0 <= int(hh) < 24 and 0 <= int(mm) < 60):
            raise ValueError("daily_run_time must be 'HH:MM'")
        sets.append("daily_run_time = %s")
        params.append(daily_run_time)
    if daily_caps is not None:
        if not isinstance(daily_caps, dict):
            raise ValueError("daily_caps must be a dict")
        cleaned = {}
        for llm, value in daily_caps.items():
            llm_norm = str(llm).strip().lower()
            if llm_norm not in APPROVED_LLMS:
                continue
            try:
                cap = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"daily_caps[{llm}] must be an integer")
            if cap < 0:
                raise ValueError(f"daily_caps[{llm}] must be >= 0")
            cleaned[llm_norm] = cap
        sets.append("daily_caps_json = %s::jsonb")
        params.append(json.dumps(cleaned))
    if per_profile_cap is not None:
        try:
            cap = int(per_profile_cap)
        except (TypeError, ValueError):
            raise ValueError("per_profile_cap must be an integer")
        if cap < 0:
            raise ValueError("per_profile_cap must be >= 0")
        sets.append("per_profile_cap = %s")
        params.append(cap)
    if not sets:
        return fetch_config(cur)
    sets.append("last_modified_at = NOW()")
    sets.append("last_modified_by = %s")
    params.append(modified_by)
    params.append(SCHEDULE_CONFIG_ID)
    cur.execute(
        f"UPDATE schedule_config SET {', '.join(sets)} WHERE id = %s",
        params,
    )
    return fetch_config(cur)


# ── Profile-account routing ──────────────────────────────────────────────────
def list_profile_bindings(cur, *, profile_id: int | None = None) -> list[dict]:
    """Return rows joined with profile + account display info.

    Used both by the GET routing endpoint and by the scheduler when picking
    an account for a query.
    """
    where = []
    params: list[Any] = []
    if profile_id is not None:
        where.append("pab.profile_id = %s")
        params.append(int(profile_id))
    where_clause = ("WHERE " + " AND ".join(where)) if where else ""
    cur.execute(
        f"""
        SELECT pab.id, pab.profile_id, pab.llm_name, pab.account_id, pab.weight,
               p.name AS profile_name, p.location AS profile_location,
               la.phone_number AS account_label, la.status AS account_status,
               la.daily_limit, la.query_count_today
        FROM profile_account_bindings pab
        LEFT JOIN profiles p ON p.id = pab.profile_id
        LEFT JOIN llm_accounts la ON la.id = pab.account_id
        {where_clause}
        ORDER BY pab.profile_id, pab.llm_name, pab.weight DESC, pab.id
        """,
        params,
    )
    rows = cur.fetchall() or []
    out = []
    for row in rows:
        if isinstance(row, dict):
            out.append(dict(row))
        else:
            out.append({
                "id": row[0], "profile_id": row[1], "llm_name": row[2],
                "account_id": row[3], "weight": row[4],
                "profile_name": row[5], "profile_location": row[6],
                "account_label": row[7], "account_status": row[8],
                "daily_limit": row[9], "query_count_today": row[10],
            })
    return out


def replace_profile_bindings(cur, profile_id: int, bindings: Iterable[dict]) -> int:
    """Replace all bindings for ``profile_id`` with the supplied list.

    Each binding is ``{"llm_name": str, "account_id": int, "weight": int}``.
    Replacing rather than upserting keeps the UI's "edit and save" semantics
    simple — operators see exactly what's in the DB after a save.
    Returns the number of rows inserted.
    """
    cleaned = []
    for entry in bindings or []:
        llm = str(entry.get("llm_name", "")).strip().lower()
        if llm not in APPROVED_LLMS:
            continue
        try:
            account_id = int(entry.get("account_id"))
        except (TypeError, ValueError):
            continue
        try:
            weight = int(entry.get("weight", 1))
        except (TypeError, ValueError):
            weight = 1
        if weight < 0:
            weight = 0
        cleaned.append((profile_id, llm, account_id, weight))

    cur.execute(
        "DELETE FROM profile_account_bindings WHERE profile_id = %s",
        (profile_id,),
    )
    inserted = 0
    for row in cleaned:
        cur.execute(
            """
            INSERT INTO profile_account_bindings
                (profile_id, llm_name, account_id, weight)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (profile_id, llm_name, account_id) DO NOTHING
            """,
            row,
        )
        inserted += cur.rowcount or 0
    return inserted


def pick_account_for_profile(cur, profile_id: int, llm_name: str) -> int | None:
    """Return the highest-weight account binding for (profile, llm) that has
    spare daily capacity. Falls back to ``NULL`` so the worker's existing
    AccountPool keeps working when no binding is configured.
    """
    cur.execute(
        """
        SELECT pab.account_id, la.daily_limit, la.query_count_today, la.status
        FROM profile_account_bindings pab
        JOIN llm_accounts la ON la.id = pab.account_id
        WHERE pab.profile_id = %s
          AND pab.llm_name = %s
          AND la.status = 'active'
        ORDER BY pab.weight DESC, pab.id
        """,
        (profile_id, llm_name),
    )
    for row in cur.fetchall() or []:
        if isinstance(row, dict):
            account_id = row["account_id"]
            limit = row.get("daily_limit") or 0
            used = row.get("query_count_today") or 0
        else:
            account_id, limit, used, _status = row
            limit = limit or 0
            used = used or 0
        if limit == 0 or used < limit:
            return int(account_id)
    return None


# ── Run history ──────────────────────────────────────────────────────────────
def insert_run(cur, *, trigger_type: str, planned_count: int, config_snapshot: dict,
               triggered_by: str | None) -> dict:
    import uuid
    run_uid = uuid.uuid4().hex
    cur.execute(
        """
        INSERT INTO schedule_runs
            (run_uid, trigger_type, status, started_at,
             planned_count, config_snapshot_json, triggered_by)
        VALUES (%s, %s, 'running', NOW(), %s, %s::jsonb, %s)
        RETURNING id, run_uid, started_at
        """,
        (run_uid, trigger_type, planned_count,
         json.dumps(config_snapshot or {}), triggered_by),
    )
    row = cur.fetchone()
    if isinstance(row, dict):
        return {
            "id": row["id"], "run_uid": row["run_uid"],
            "started_at": row["started_at"].isoformat() if row.get("started_at") else None,
        }
    return {"id": row[0], "run_uid": row[1],
            "started_at": row[2].isoformat() if row[2] else None}


def finalize_run(cur, *, run_id: int, status: str, dispatched_count: int,
                 skipped_count: int, per_llm_breakdown: dict, note: str | None = None):
    cur.execute(
        """
        UPDATE schedule_runs
        SET status = %s,
            finished_at = NOW(),
            dispatched_count = %s,
            skipped_count = %s,
            per_llm_breakdown_json = %s::jsonb,
            note = COALESCE(%s, note)
        WHERE id = %s
        """,
        (status, dispatched_count, skipped_count,
         json.dumps(per_llm_breakdown or {}), note, run_id),
    )


def list_runs(cur, *, limit: int = 30) -> list[dict]:
    cur.execute(
        """
        SELECT id, run_uid, trigger_type, status, started_at, finished_at,
               planned_count, dispatched_count, skipped_count,
               per_llm_breakdown_json, triggered_by, note
        FROM schedule_runs
        ORDER BY started_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit), 200)),),
    )
    out = []
    for row in cur.fetchall() or []:
        if isinstance(row, dict):
            d = dict(row)
        else:
            d = {
                "id": row[0], "run_uid": row[1], "trigger_type": row[2],
                "status": row[3], "started_at": row[4], "finished_at": row[5],
                "planned_count": row[6], "dispatched_count": row[7],
                "skipped_count": row[8], "per_llm_breakdown_json": row[9],
                "triggered_by": row[10], "note": row[11],
            }
        if d.get("started_at"):
            d["started_at"] = d["started_at"].isoformat()
        if d.get("finished_at"):
            d["finished_at"] = d["finished_at"].isoformat()
        breakdown = d.pop("per_llm_breakdown_json", None)
        d["per_llm_breakdown"] = breakdown if isinstance(breakdown, dict) else (
            json.loads(breakdown) if breakdown else {}
        )
        out.append(d)
    return out


# ── Query selection ──────────────────────────────────────────────────────────
def select_pending_queries(cur, *, caps: dict[str, int],
                           per_profile_cap: int,
                           override_total: int | None = None) -> list[dict]:
    """Return pending queries to dispatch, grouped by LLM, capped per LLM and
    per profile. Ordered oldest-first so the queue drains FIFO.

    ``override_total`` (when provided) replaces the sum-of-caps for manual
    runs where the operator entered an explicit total. We still honor the
    per-profile cap so a single profile can't dominate the run.
    """
    selected: list[dict] = []
    per_llm_remaining = {llm: int(cap) for llm, cap in caps.items() if int(cap) > 0}
    total_budget = override_total if override_total is not None else sum(per_llm_remaining.values())
    if total_budget <= 0:
        return []

    cur.execute(
        """
        SELECT id, target_llm, profile_id, brand_id, query_text,
               COALESCE(retry_count, 0) AS retry_count
        FROM queries
        WHERE LOWER(status) IN ('pending','failed')
          AND target_llm IS NOT NULL
        ORDER BY id ASC
        LIMIT %s
        """,
        (max(total_budget * 4, 200),),  # over-fetch then filter for caps
    )

    profile_counter: dict[int, int] = {}
    for row in cur.fetchall() or []:
        if isinstance(row, dict):
            qid = row["id"]; llm = (row.get("target_llm") or "").lower()
            profile_id = row.get("profile_id")
        else:
            qid, llm, profile_id, _brand, _qtext, _retry = row
            llm = (llm or "").lower()
        if llm not in per_llm_remaining or per_llm_remaining[llm] <= 0:
            continue
        if profile_id is not None:
            seen = profile_counter.get(profile_id, 0)
            if seen >= per_profile_cap:
                continue
            profile_counter[profile_id] = seen + 1
        per_llm_remaining[llm] -= 1
        total_budget -= 1
        selected.append({
            "id": int(qid),
            "target_llm": llm,
            "profile_id": profile_id,
        })
        if total_budget <= 0:
            break
    return selected


# ── Daily tracking aggregation ───────────────────────────────────────────────
def daily_tracking_summary(cur, *, days: int = 30) -> list[dict]:
    """Return per-(date, target_llm) aggregates over the last N days.

    Each row reports counts of responses, citations, and screenshots that the
    UI's "每日响应" tab uses to render its timeline cards.
    """
    cur.execute(
        """
        SELECT
            (lr.collected_at AT TIME ZONE 'UTC')::date AS day,
            q.target_llm,
            COUNT(DISTINCT lr.id) AS response_count,
            COUNT(DISTINCT cs.id) AS citation_count,
            COUNT(DISTINCT q.id) FILTER (WHERE LOWER(q.status) = 'done') AS done_count,
            COUNT(DISTINCT q.id) FILTER (WHERE LOWER(q.status) = 'failed') AS failed_count
        FROM llm_responses lr
        JOIN queries q ON q.id = lr.query_id
        LEFT JOIN citation_sources cs ON cs.response_id = lr.id
        WHERE lr.collected_at >= NOW() - %s::interval
        GROUP BY day, q.target_llm
        ORDER BY day DESC, q.target_llm
        """,
        (f"{max(1, min(int(days), 90))} days",),
    )
    out = []
    for row in cur.fetchall() or []:
        if isinstance(row, dict):
            d = dict(row)
        else:
            d = {
                "day": row[0], "target_llm": row[1],
                "response_count": row[2], "citation_count": row[3],
                "done_count": row[4], "failed_count": row[5],
            }
        if d.get("day"):
            d["day"] = d["day"].isoformat() if hasattr(d["day"], "isoformat") else str(d["day"])
        out.append(d)
    return out


def daily_tracking_responses(cur, *, day: str, target_llm: str | None,
                             brand_id: int | None,
                             limit: int = 100, offset: int = 0) -> dict:
    """List responses collected on ``day`` (YYYY-MM-DD UTC) with their query +
    citation counts. The drill-down UI then issues a per-response screenshot
    fetch via the existing ``/api/html_files`` endpoint.
    """
    where = ["(lr.collected_at AT TIME ZONE 'UTC')::date = %s"]
    params: list[Any] = [day]
    if target_llm:
        where.append("q.target_llm = %s")
        params.append(target_llm)
    if brand_id is not None:
        where.append("q.brand_id = %s")
        params.append(int(brand_id))

    where_clause = " AND ".join(where)
    cur.execute(
        f"""
        SELECT COUNT(*) FROM llm_responses lr
        JOIN queries q ON q.id = lr.query_id
        WHERE {where_clause}
        """,
        params,
    )
    row = cur.fetchone()
    total = row[0] if not isinstance(row, dict) else row.get("count", row.get("count(*)"))
    if total is None and isinstance(row, dict):
        total = next(iter(row.values()))

    cur.execute(
        f"""
        SELECT lr.id AS response_id, lr.collected_at,
               lr.analysis_status,
               LEFT(COALESCE(lr.raw_text, ''), 600) AS preview,
               q.id AS query_id, q.target_llm, q.query_text,
               q.profile_id, q.account_id,
               b.name AS brand_name,
               p.name AS profile_name, p.country_code AS profile_country,
               la.phone_number AS account_label,
               (SELECT COUNT(*) FROM citation_sources cs WHERE cs.response_id = lr.id) AS citation_count
        FROM llm_responses lr
        JOIN queries q ON q.id = lr.query_id
        LEFT JOIN brands b ON b.id = q.brand_id
        LEFT JOIN profiles p ON p.id = q.profile_id
        LEFT JOIN llm_accounts la ON la.id = q.account_id
        WHERE {where_clause}
        ORDER BY lr.collected_at DESC, lr.id DESC
        LIMIT %s OFFSET %s
        """,
        params + [max(1, min(int(limit), 200)), max(0, int(offset))],
    )
    rows = []
    for r in cur.fetchall() or []:
        d = dict(r) if isinstance(r, dict) else {
            "response_id": r[0], "collected_at": r[1], "analysis_status": r[2],
            "preview": r[3], "query_id": r[4], "target_llm": r[5],
            "query_text": r[6], "profile_id": r[7], "account_id": r[8],
            "brand_name": r[9], "profile_name": r[10], "profile_country": r[11],
            "account_label": r[12], "citation_count": r[13],
        }
        if d.get("collected_at"):
            d["collected_at"] = d["collected_at"].isoformat()
        rows.append(d)
    return {"total": int(total or 0), "rows": rows}


def response_citations(cur, response_id: int) -> list[dict]:
    cur.execute(
        """
        SELECT id, url, domain, title, citation_index, source_type
        FROM citation_sources
        WHERE response_id = %s
        ORDER BY citation_index NULLS LAST, id
        """,
        (int(response_id),),
    )
    out = []
    for r in cur.fetchall() or []:
        out.append(dict(r) if isinstance(r, dict) else {
            "id": r[0], "url": r[1], "domain": r[2], "title": r[3],
            "citation_index": r[4], "source_type": r[5],
        })
    return out


# ── Auto-trigger thread ──────────────────────────────────────────────────────
class DailyAutoTrigger:
    """Tiny wall-clock thread that fires the configured run at the configured
    time once per day. Intentionally simple — APScheduler would be overkill
    for "fire once at HH:MM UTC" and would add a runtime dep on top of
    Celery/Redis we already use for query dispatch.
    """

    def __init__(self, *, on_fire, get_config, sleep_seconds: int = 30):
        self._on_fire = on_fire
        self._get_config = get_config
        self._sleep = sleep_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_fire_date: str | None = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="genpano-scheduler", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            try:
                cfg = self._get_config()
            except Exception:
                cfg = None
            if cfg and cfg.get("auto_run_enabled") and not cfg.get("paused"):
                now = datetime.now(timezone.utc)
                target = cfg.get("daily_run_time", DEFAULT_RUN_TIME)
                today_key = now.date().isoformat()
                try:
                    hh, mm = (int(x) for x in target.split(":"))
                except Exception:
                    hh, mm = 3, 0
                # Fire when we're inside the target minute and we haven't fired today yet.
                if (now.hour, now.minute) == (hh, mm) and self._last_fire_date != today_key:
                    self._last_fire_date = today_key
                    try:
                        self._on_fire()
                    except Exception:
                        # Logged by the caller — swallowing here keeps the
                        # thread alive so tomorrow's run still happens.
                        pass
            self._stop.wait(self._sleep)


__all__ = [
    "APPROVED_LLMS", "DEFAULT_RUN_TIME", "DEFAULT_DAILY_CAP_PER_LLM",
    "ensure_schedule_tables",
    "fetch_config", "update_config",
    "list_profile_bindings", "replace_profile_bindings", "pick_account_for_profile",
    "insert_run", "finalize_run", "list_runs",
    "select_pending_queries",
    "daily_tracking_summary", "daily_tracking_responses", "response_citations",
    "DailyAutoTrigger",
]
