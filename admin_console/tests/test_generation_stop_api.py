"""Tests for the generation stop endpoints (topic plan, prompt matrix, query pool)."""
import pytest

import admin_console.app as app_mod


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        compact = " ".join(str(sql).split())
        self.conn.statements.append((compact, params))
        params = params or []
        if "SELECT id, status FROM topic_plan_runs WHERE id = %s" in compact:
            row = self.conn.runs.get(params[0])
            self.rows = [dict(row)] if row else []
        elif "SELECT id, status FROM prompt_generation_runs WHERE id = %s" in compact:
            row = self.conn.runs.get(params[0])
            self.rows = [dict(row)] if row else []
        elif "SELECT id, status FROM query_generation_runs WHERE id = %s" in compact:
            row = self.conn.runs.get(params[0])
            self.rows = [dict(row)] if row else []
        elif compact.startswith("UPDATE topic_plan_runs SET status = 'cancelled'"):
            run_id = params[0]
            row = self.conn.runs.get(run_id)
            if row and row.get("status") not in {"completed", "failed", "cancelled"}:
                row["status"] = "cancelled"
                self.conn.runs[run_id] = row
        elif compact.startswith("UPDATE prompt_generation_runs SET status = 'cancelled'"):
            run_id = params[0]
            row = self.conn.runs.get(run_id)
            if row and row.get("status") not in {"completed", "failed", "cancelled"}:
                row["status"] = "cancelled"
                self.conn.runs[run_id] = row
        elif compact.startswith("UPDATE query_generation_runs SET status = 'cancelled'"):
            run_id = params[0]
            row = self.conn.runs.get(run_id)
            if row and row.get("status") not in {"completed", "failed", "cancelled"}:
                row["status"] = "cancelled"
                self.conn.runs[run_id] = row
        elif "SELECT * FROM query_generation_runs WHERE id = %s" in compact:
            row = self.conn.runs.get(params[0]) if params else None
            self.rows = [dict(row)] if row else []
        elif "FROM topic_plan_runs WHERE id = %s" in compact:
            row = self.conn.runs.get(params[0]) if params else None
            self.rows = [dict(row)] if row else []
        elif "FROM prompt_generation_runs WHERE id = %s" in compact:
            row = self.conn.runs.get(params[0]) if params else None
            self.rows = [dict(row)] if row else []
        elif "INSERT INTO admin_audit_logs" in compact:
            self.rows = []
        else:
            self.rows = []

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, runs=None):
        self.statements = []
        self.runs = runs or {}
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self, *args, **kwargs):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


@pytest.fixture
def client():
    app_mod.app.config.update(TESTING=True, SECRET_KEY="test-secret")
    return app_mod.app.test_client()


def login(monkeypatch):
    monkeypatch.setattr(
        app_mod,
        "_current_admin",
        lambda: {"id": "admin-1", "email": "admin@example.com", "role": "admin", "status": "active"},
    )


def test_topic_plan_stop_requires_admin(client):
    response = client.post("/api/admin/topic-plan/runs/run-1/stop")
    assert response.status_code == 401


def test_topic_plan_stop_marks_run_cancelled(client, monkeypatch):
    login(monkeypatch)
    conn = FakeConnection(runs={"run-1": {"id": "run-1", "status": "running"}})
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)
    monkeypatch.setattr(app_mod, "_table_exists", lambda cur, name: True)
    monkeypatch.setattr(app_mod, "_topic_plan_run_row", lambda row: dict(row) if row else None)
    monkeypatch.setattr(app_mod, "_insert_admin_audit_log", lambda *a, **kw: None)

    response = client.post("/api/admin/topic-plan/runs/run-1/stop")
    body = response.get_json()
    assert response.status_code == 200
    assert body["success"] is True
    assert conn.runs["run-1"]["status"] == "cancelled"


def test_topic_plan_stop_already_finalized(client, monkeypatch):
    login(monkeypatch)
    conn = FakeConnection(runs={"run-2": {"id": "run-2", "status": "completed"}})
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)
    monkeypatch.setattr(app_mod, "_table_exists", lambda cur, name: True)
    monkeypatch.setattr(app_mod, "_topic_plan_run_row", lambda row: dict(row) if row else None)

    response = client.post("/api/admin/topic-plan/runs/run-2/stop")
    body = response.get_json()
    assert response.status_code == 200
    assert body["success"] is True
    assert body.get("already_finalized") is True
    assert conn.runs["run-2"]["status"] == "completed"


def test_topic_plan_stop_unknown_run_returns_404(client, monkeypatch):
    login(monkeypatch)
    conn = FakeConnection(runs={})
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)
    monkeypatch.setattr(app_mod, "_table_exists", lambda cur, name: True)

    response = client.post("/api/admin/topic-plan/runs/missing/stop")
    body = response.get_json()
    assert response.status_code == 404
    assert body["success"] is False
    assert body["error"] == "run_not_found"


def test_prompt_matrix_stop_marks_run_cancelled(client, monkeypatch):
    login(monkeypatch)
    conn = FakeConnection(runs={"pm-1": {"id": "pm-1", "status": "running"}})
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)
    monkeypatch.setattr(app_mod, "_table_exists", lambda cur, name: True)
    monkeypatch.setattr(app_mod, "_prompt_matrix_run_row", lambda row: dict(row) if row else None)
    monkeypatch.setattr(app_mod, "_insert_admin_audit_log", lambda *a, **kw: None)

    response = client.post("/api/admin/prompt-matrix/runs/pm-1/stop")
    body = response.get_json()
    assert response.status_code == 200
    assert body["success"] is True
    assert conn.runs["pm-1"]["status"] == "cancelled"


def test_prompt_matrix_stop_already_finalized(client, monkeypatch):
    login(monkeypatch)
    conn = FakeConnection(runs={"pm-2": {"id": "pm-2", "status": "failed"}})
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)
    monkeypatch.setattr(app_mod, "_table_exists", lambda cur, name: True)
    monkeypatch.setattr(app_mod, "_prompt_matrix_run_row", lambda row: dict(row) if row else None)

    response = client.post("/api/admin/prompt-matrix/runs/pm-2/stop")
    body = response.get_json()
    assert response.status_code == 200
    assert body.get("already_finalized") is True
    assert conn.runs["pm-2"]["status"] == "failed"


def test_query_pool_stop_marks_run_cancelled(client, monkeypatch):
    login(monkeypatch)
    conn = FakeConnection(runs={"qp-1": {"id": "qp-1", "status": "running"}})
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)
    monkeypatch.setattr(app_mod, "_table_exists", lambda cur, name: True)
    monkeypatch.setattr(app_mod, "_get_query_pool_run", lambda cur, run_id: dict(conn.runs.get(run_id) or {}))
    monkeypatch.setattr(app_mod, "_insert_admin_audit_log", lambda *a, **kw: None)

    response = client.post("/api/admin/query-pool/runs/qp-1/stop")
    body = response.get_json()
    assert response.status_code == 200
    assert body["success"] is True
    assert conn.runs["qp-1"]["status"] == "cancelled"


def test_query_pool_stop_unknown_run_returns_404(client, monkeypatch):
    login(monkeypatch)
    conn = FakeConnection(runs={})
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)
    monkeypatch.setattr(app_mod, "_table_exists", lambda cur, name: True)

    response = client.post("/api/admin/query-pool/runs/missing/stop")
    body = response.get_json()
    assert response.status_code == 404
    assert body["error"] == "query_pool_run_not_found"


def test_query_pool_stop_already_finalized(client, monkeypatch):
    login(monkeypatch)
    conn = FakeConnection(runs={"qp-2": {"id": "qp-2", "status": "cancelled"}})
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)
    monkeypatch.setattr(app_mod, "_table_exists", lambda cur, name: True)
    monkeypatch.setattr(app_mod, "_get_query_pool_run", lambda cur, run_id: dict(conn.runs.get(run_id) or {}))

    response = client.post("/api/admin/query-pool/runs/qp-2/stop")
    body = response.get_json()
    assert response.status_code == 200
    assert body.get("already_finalized") is True
    assert conn.runs["qp-2"]["status"] == "cancelled"
