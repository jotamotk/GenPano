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



