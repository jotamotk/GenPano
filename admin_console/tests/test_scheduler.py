"""Unit tests for admin_console.scheduler.

These cover the pure-logic helpers that don't need a live Postgres — config
validation, query selection caps, and routing replacement bookkeeping. The
HTTP routes themselves are covered by exercising the test client through
admin_console.app once it has loaded the module.
"""
from __future__ import annotations

import json

import pytest

from admin_console import scheduler as sched


# ── In-memory fake cursor / connection ────────────────────────────────────────
class FakeCursor:
    """Minimal psycopg2-style cursor that returns scripted responses.

    Each ``set_result`` call queues one row-set; ``execute`` records the call
    and pops the next queued result so ``fetchone`` / ``fetchall`` return it.
    """

    def __init__(self):
        self.calls: list[tuple[str, object]] = []
        self._results: list[list[tuple]] = []
        self._pending: list[tuple] = []
        self.rowcount = 0

    def queue(self, rows):
        self._results.append(list(rows))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.calls.append((" ".join(str(sql).split()), params))
        self._pending = self._results.pop(0) if self._results else []
        self.rowcount = len(self._pending)

    def fetchone(self):
        return self._pending[0] if self._pending else None

    def fetchall(self):
        rows = self._pending
        self._pending = []
        return rows


def test_fetch_config_returns_defaults_for_missing_row():
    cur = FakeCursor()
    cur.queue([])  # no row
    cfg = sched.fetch_config(cur)
    assert cfg["paused"] is False
    assert cfg["auto_run_enabled"] is True
    assert cfg["daily_run_time"] == sched.DEFAULT_RUN_TIME
    # All approved LLMs should appear in caps even when row is empty.
    for llm in sched.APPROVED_LLMS:
        assert llm in cfg["daily_caps"]


def test_fetch_config_backfills_missing_llm_caps():
    cur = FakeCursor()
    # Row missing 'deepseek' in caps; helper should fill it.
    cur.queue([(False, True, "04:00", "UTC", {"chatgpt": 50}, 4, None, "ops@x")])
    cfg = sched.fetch_config(cur)
    assert cfg["daily_caps"]["chatgpt"] == 50
    assert cfg["daily_caps"]["deepseek"] == sched.DEFAULT_DAILY_CAP_PER_LLM
    assert cfg["per_profile_cap"] == 4


def test_update_config_rejects_bad_run_time():
    cur = FakeCursor()
    with pytest.raises(ValueError):
        sched.update_config(cur, daily_run_time="3am")
    with pytest.raises(ValueError):
        sched.update_config(cur, daily_run_time="25:00")
    with pytest.raises(ValueError):
        sched.update_config(cur, daily_run_time="03:60")


def test_update_config_rejects_negative_caps():
    cur = FakeCursor()
    with pytest.raises(ValueError):
        sched.update_config(cur, daily_caps={"chatgpt": -1})
    with pytest.raises(ValueError):
        sched.update_config(cur, per_profile_cap=-2)


def test_update_config_only_writes_supplied_fields():
    cur = FakeCursor()
    # First the UPDATE writes one row, then fetch_config reads it back.
    cur.queue([])  # the UPDATE result is unused
    cur.queue([(True, True, "05:30", "UTC",
                {llm: 10 for llm in sched.APPROVED_LLMS}, 7, None, "admin")])
    out = sched.update_config(cur, paused=True, modified_by="admin")
    assert out["paused"] is True
    assert out["last_modified_by"] == "admin"
    # First call should be the partial UPDATE — only paused and the modified
    # bookkeeping cols.
    update_sql, update_params = cur.calls[0]
    assert update_sql.startswith("UPDATE schedule_config SET paused")
    assert "last_modified_at" in update_sql
    assert update_params[0] is True
    assert update_params[1] == "admin"


def test_select_pending_queries_respects_per_llm_cap():
    cur = FakeCursor()
    # 4 chatgpt + 2 doubao pending; cap chatgpt=2, doubao=10.
    cur.queue([
        (101, "chatgpt", 1, 10, "q1", 0),
        (102, "chatgpt", 2, 10, "q2", 0),
        (103, "chatgpt", 3, 10, "q3", 0),
        (104, "chatgpt", 4, 10, "q4", 0),
        (201, "doubao",  5, 10, "q5", 0),
        (202, "doubao",  6, 10, "q6", 0),
    ])
    selected = sched.select_pending_queries(
        cur,
        caps={"chatgpt": 2, "doubao": 10, "deepseek": 0},
        per_profile_cap=10,
    )
    by_llm: dict[str, int] = {}
    for q in selected:
        by_llm[q["target_llm"]] = by_llm.get(q["target_llm"], 0) + 1
    assert by_llm.get("chatgpt") == 2  # capped
    assert by_llm.get("doubao") == 2   # below cap, all included
    assert by_llm.get("deepseek", 0) == 0


def test_select_pending_queries_respects_per_profile_cap():
    cur = FakeCursor()
    # 3 queries from same profile id=42 — should cap at 2.
    cur.queue([
        (101, "chatgpt", 42, 10, "q1", 0),
        (102, "chatgpt", 42, 10, "q2", 0),
        (103, "chatgpt", 42, 10, "q3", 0),
        (104, "chatgpt",  7, 10, "q4", 0),
    ])
    selected = sched.select_pending_queries(
        cur,
        caps={"chatgpt": 10, "doubao": 0, "deepseek": 0},
        per_profile_cap=2,
    )
    profile_42 = [q for q in selected if q["profile_id"] == 42]
    assert len(profile_42) == 2
    profile_7 = [q for q in selected if q["profile_id"] == 7]
    assert len(profile_7) == 1


def test_select_pending_queries_override_total_caps_total():
    cur = FakeCursor()
    cur.queue([
        (101, "chatgpt", 1, 10, "q1", 0),
        (102, "chatgpt", 2, 10, "q2", 0),
        (201, "doubao",  3, 10, "q3", 0),
        (202, "doubao",  4, 10, "q4", 0),
    ])
    selected = sched.select_pending_queries(
        cur,
        caps={"chatgpt": 10, "doubao": 10, "deepseek": 0},
        per_profile_cap=10,
        override_total=2,
    )
    # Override caps total at 2 regardless of per-LLM caps.
    assert len(selected) == 2


def test_select_pending_queries_skips_unapproved_llm():
    cur = FakeCursor()
    cur.queue([
        (101, "kimi", 1, 10, "q1", 0),  # not in caps → skipped
        (102, "chatgpt", 2, 10, "q2", 0),
    ])
    selected = sched.select_pending_queries(
        cur,
        caps={"chatgpt": 10, "doubao": 0, "deepseek": 0},
        per_profile_cap=10,
    )
    assert len(selected) == 1
    assert selected[0]["target_llm"] == "chatgpt"


def test_replace_profile_bindings_filters_invalid_entries():
    cur = FakeCursor()
    bindings = [
        {"llm_name": "chatgpt", "account_id": 5, "weight": 3},
        {"llm_name": "INVALID", "account_id": 9, "weight": 1},   # dropped
        {"llm_name": "doubao", "account_id": "not-int", "weight": 1},  # dropped
        {"llm_name": "deepseek", "account_id": 11, "weight": -2},  # weight clamped
    ]
    inserted = sched.replace_profile_bindings(cur, profile_id=42, bindings=bindings)
    # First call is the DELETE; remainder are INSERTs (valid rows only).
    assert cur.calls[0][0].startswith("DELETE FROM profile_account_bindings")
    insert_calls = [c for c in cur.calls if c[0].startswith("INSERT INTO profile_account_bindings")]
    # Two valid entries (chatgpt + deepseek with weight clamped to 0).
    assert len(insert_calls) == 2
    # Weight on the deepseek row was clamped to 0 (not negative).
    deepseek_params = [c[1] for c in insert_calls if c[1][1] == "deepseek"][0]
    assert deepseek_params[3] == 0


def test_pick_account_for_profile_skips_account_at_limit():
    cur = FakeCursor()
    # First binding is at limit; second has spare capacity.
    cur.queue([
        (10, 100, 100, "active"),   # used == limit → skip
        (11, 100,  20, "active"),
    ])
    pick = sched.pick_account_for_profile(cur, profile_id=1, llm_name="chatgpt")
    assert pick == 11


def test_pick_account_for_profile_returns_none_when_all_full():
    cur = FakeCursor()
    cur.queue([
        (10, 100, 100, "active"),
        (11,  50,  50, "active"),
    ])
    pick = sched.pick_account_for_profile(cur, profile_id=1, llm_name="chatgpt")
    assert pick is None


def test_pick_account_for_profile_zero_limit_treated_as_unlimited():
    cur = FakeCursor()
    cur.queue([
        (42, 0, 999, "active"),
    ])
    # daily_limit=0 means no limit, so even with high usage it should return.
    pick = sched.pick_account_for_profile(cur, profile_id=1, llm_name="chatgpt")
    assert pick == 42


def test_insert_run_returns_run_uid_and_id():
    cur = FakeCursor()
    from datetime import datetime
    cur.queue([(7, "abcd1234", datetime(2026, 5, 3, 3, 0, 0))])
    out = sched.insert_run(
        cur,
        trigger_type="manual",
        planned_count=10,
        config_snapshot={"daily_caps": {"chatgpt": 50}},
        triggered_by="admin@x",
    )
    assert out["id"] == 7
    assert out["run_uid"] == "abcd1234"
    insert_call = cur.calls[0]
    assert "INSERT INTO schedule_runs" in insert_call[0]
    assert insert_call[1][1] == "manual"  # trigger_type


def test_list_runs_serializes_timestamps_and_breakdown():
    cur = FakeCursor()
    from datetime import datetime
    cur.queue([
        (
            1, "uid1", "manual", "completed",
            datetime(2026, 5, 3, 2, 0), datetime(2026, 5, 3, 2, 5),
            10, 9, 1,
            json.dumps({"chatgpt": 5, "doubao": 4}),
            "admin@x", "ok"
        ),
    ])
    runs = sched.list_runs(cur, limit=5)
    assert len(runs) == 1
    r = runs[0]
    assert r["started_at"].startswith("2026-05-03")
    assert r["finished_at"].startswith("2026-05-03")
    # JSON string in mock should be parsed back into a dict by the helper.
    assert isinstance(r["per_llm_breakdown"], dict)
    assert r["per_llm_breakdown"]["chatgpt"] == 5


def test_daily_tracking_summary_serializes_dates():
    cur = FakeCursor()
    from datetime import date
    cur.queue([
        (date(2026, 5, 2), "chatgpt", 12, 30, 11, 1),
        (date(2026, 5, 1), "doubao",   8, 15,  8, 0),
    ])
    rows = sched.daily_tracking_summary(cur, days=14)
    assert len(rows) == 2
    assert rows[0]["day"] == "2026-05-02"
    assert rows[0]["target_llm"] == "chatgpt"
    assert rows[0]["response_count"] == 12
    assert rows[0]["citation_count"] == 30


# ── HTTP-level smoke tests ────────────────────────────────────────────────────
# Exercise the routes through Flask's test client with the DB monkey-patched
# to a fake connection that returns scripted rows.
import admin_console.app as app_mod  # noqa: E402


class FakeRealDictCursor(FakeCursor):
    """Same as FakeCursor but ``fetchone`` / ``fetchall`` return dicts.

    The route handlers ask for RealDictCursor; mirror that contract so the
    handlers can reach the JSON-serialization branch that expects dicts.
    """
    field_names: tuple[str, ...] = ()

    def fetchone(self):
        if not self._pending:
            return None
        row = self._pending[0]
        if isinstance(row, dict):
            return row
        return dict(zip(self.field_names, row)) if self.field_names else row

    def fetchall(self):
        rows = self._pending
        self._pending = []
        if rows and isinstance(rows[0], tuple) and self.field_names:
            return [dict(zip(self.field_names, r)) for r in rows]
        return rows


class FakeConn:
    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor
        self.commits = 0
        self.rolled_back = 0
        self.closed = False

    def cursor(self, *args, **kwargs):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rolled_back += 1

    def close(self):
        self.closed = True


@pytest.fixture
def client():
    app_mod.app.config.update(TESTING=True, SECRET_KEY="test-secret")
    return app_mod.app.test_client()


def _login(monkeypatch):
    monkeypatch.setattr(
        app_mod, "_current_admin",
        lambda: {"id": "admin-1", "email": "ops@x.com", "role": "admin", "status": "active"},
    )


def test_admin_schedule_config_get_returns_default_when_row_missing(client, monkeypatch):
    _login(monkeypatch)
    cur = FakeRealDictCursor()
    cur.queue([])  # fetch_config sees no row
    monkeypatch.setattr(app_mod, "get_db", lambda: FakeConn(cur))

    res = client.get("/api/admin/schedule/config")
    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    assert body["config"]["paused"] is False
    assert "approved_llms" in body
    assert "chatgpt" in body["approved_llms"]


def test_admin_schedule_pause_toggles_flag(client, monkeypatch):
    _login(monkeypatch)
    cur = FakeRealDictCursor()
    # update_config: first the UPDATE (no result), then fetch_config reads back.
    cur.queue([])
    cur.queue([{
        "paused": True, "auto_run_enabled": True,
        "daily_run_time": "03:00", "timezone": "UTC",
        "daily_caps_json": {"chatgpt": 200, "doubao": 200, "deepseek": 200},
        "per_profile_cap": 5,
        "last_modified_at": None, "last_modified_by": "ops@x.com",
    }])
    monkeypatch.setattr(app_mod, "get_db", lambda: FakeConn(cur))

    res = client.post("/api/admin/schedule/pause", json={"paused": True})
    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    assert body["paused"] is True


def test_admin_schedule_run_now_rejects_negative_override(client, monkeypatch):
    _login(monkeypatch)
    res = client.post("/api/admin/schedule/run-now", json={"override_total": -1})
    assert res.status_code == 400
    assert res.get_json()["success"] is False


def test_admin_schedule_runs_returns_history(client, monkeypatch):
    _login(monkeypatch)
    from datetime import datetime
    cur = FakeRealDictCursor()
    cur.queue([{
        "id": 1, "run_uid": "u1", "trigger_type": "manual",
        "status": "completed",
        "started_at": datetime(2026, 5, 3, 2, 0),
        "finished_at": datetime(2026, 5, 3, 2, 5),
        "planned_count": 10, "dispatched_count": 9, "skipped_count": 1,
        "per_llm_breakdown_json": {"chatgpt": 5, "doubao": 4},
        "triggered_by": "ops@x.com", "note": None,
    }])
    monkeypatch.setattr(app_mod, "get_db", lambda: FakeConn(cur))

    res = client.get("/api/admin/schedule/runs")
    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    assert len(body["runs"]) == 1
    assert body["runs"][0]["run_uid"] == "u1"
    assert body["runs"][0]["per_llm_breakdown"] == {"chatgpt": 5, "doubao": 4}


def test_admin_tracking_daily_summary_passes_through(client, monkeypatch):
    _login(monkeypatch)
    from datetime import date
    cur = FakeRealDictCursor()
    cur.queue([{
        "day": date(2026, 5, 2), "target_llm": "chatgpt",
        "response_count": 12, "citation_count": 30,
        "done_count": 11, "failed_count": 1,
    }])
    monkeypatch.setattr(app_mod, "get_db", lambda: FakeConn(cur))

    res = client.get("/api/admin/tracking/daily?days=7")
    assert res.status_code == 200
    body = res.get_json()
    assert body["days"] == 7
    assert body["summary"][0]["day"] == "2026-05-02"
    assert body["summary"][0]["target_llm"] == "chatgpt"


def test_admin_profile_routing_update_requires_profile_id(client, monkeypatch):
    _login(monkeypatch)
    res = client.post("/api/admin/schedule/profile-routing", json={"bindings": []})
    assert res.status_code == 400
    assert res.get_json()["success"] is False
