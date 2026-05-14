from __future__ import annotations

import pytest


class _FakeResult:
    def __init__(self, rows=None, rowcount: int = 0):
        self._rows = list(rows or [])
        self.rowcount = rowcount

    def first(self):
        return self._rows[0] if self._rows else None

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeTrackerReconcileSession:
    def __init__(self):
        self.sql: list[str] = []
        self.commits = 0

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.sql.append(sql)
        if "information_schema.tables" in sql:
            return _FakeResult([(1,)])
        if "LOWER(status) = 'running'" in sql:
            return _FakeResult([{"id": 184974}])
        if "LOWER(status) = 'pending'" in sql:
            return _FakeResult([{"id": 184975}, {"id": 184976}])
        raise AssertionError(f"unexpected SQL: {sql}")

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_tracker_reconciliation_marks_stale_running_and_queued_pending() -> None:
    from app.admin.queries import db as queries_db

    session = _FakeTrackerReconcileSession()

    report = await queries_db.reconcile_stale_tracker_query_states(
        session,
        running_max_age_seconds=660,
        pending_max_age_seconds=660,
    )

    joined_sql = "\n".join(session.sql)
    assert report == {
        "running": 1,
        "pending": 2,
        "total": 3,
    }
    assert "retry_reason = 'stale_running_timeout'" in joined_sql
    assert "retry_reason = 'pending_dispatch_timeout'" in joined_sql
    assert "LOWER(status) = 'running'" in joined_sql
    assert "LOWER(status) = 'pending'" in joined_sql
    assert "queued_at IS NOT NULL" in joined_sql
    assert "NOT EXISTS" in joined_sql
    assert session.commits == 1
