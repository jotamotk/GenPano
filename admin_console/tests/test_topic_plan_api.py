import pytest
from datetime import datetime, timedelta, timezone

import admin_console.app as app_mod


class FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self):
        self.closed = False

    def cursor(self, *args, **kwargs):
        return FakeCursor()

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


def test_topic_plan_candidates_can_filter_to_generation_run(client, monkeypatch):
    login(monkeypatch)
    monkeypatch.setattr(app_mod, "get_db", lambda: FakeConnection())
    monkeypatch.setattr(
        app_mod,
        "_topic_plan_pending_summary",
        lambda cur, brand_ids, run_id=None: {"pending": 1, "low_confidence": 0},
    )

    def fake_fetch(cur, status="pending", brand_ids=None, query=None, limit=100, run_id=None):
        assert run_id == "run-1"
        return [{"id": "candidate-1", "run_id": run_id, "status": status}]

    monkeypatch.setattr(app_mod, "_fetch_topic_plan_candidates", fake_fetch)

    response = client.get("/api/admin/topic-plan/candidates?status=pending&run_id=run-1&brand_ids=13")
    body = response.get_json()

    assert response.status_code == 200
    assert body["rows"] == [{"id": "candidate-1", "run_id": "run-1", "status": "pending"}]


def test_topic_plan_candidates_run_filter_takes_precedence_over_brand_filter(client, monkeypatch):
    login(monkeypatch)
    monkeypatch.setattr(app_mod, "get_db", lambda: FakeConnection())

    def fake_pending_summary(cur, brand_ids, run_id=None):
        assert brand_ids is None
        assert run_id == "run-1"
        return {"pending": 1, "low_confidence": 0}

    def fake_fetch(cur, status="pending", brand_ids=None, query=None, limit=100, run_id=None):
        assert run_id == "run-1"
        assert brand_ids is None
        return [{"id": "candidate-1", "run_id": run_id, "status": status}]

    monkeypatch.setattr(app_mod, "_topic_plan_pending_summary", fake_pending_summary)
    monkeypatch.setattr(app_mod, "_fetch_topic_plan_candidates", fake_fetch)

    response = client.get("/api/admin/topic-plan/candidates?status=pending&run_id=run-1&brand_ids=999")
    body = response.get_json()

    assert response.status_code == 200
    assert body["rows"] == [{"id": "candidate-1", "run_id": "run-1", "status": "pending"}]
    assert body["summary"] == {"pending_candidates": 1, "low_confidence": 0}


def test_topic_plan_generation_batches_skip_brands_without_gaps(monkeypatch):
    monkeypatch.setenv("TOPIC_PLAN_LLM_BRANDS_PER_REQUEST", "1")
    brands = [
        {"id": 1, "name": "Complete Brand"},
        {"id": 2, "name": "Gap Brand A"},
        {"id": 3, "name": "Gap Brand B"},
    ]
    gaps = [
        {"brand_id": 2, "type": "product", "count": 2},
        {"brand_id": 3, "type": "scenario", "count": 1},
    ]

    batches = list(app_mod._topic_plan_brand_batches(brands, gaps, max_topics=10, max_per_brand=5))

    assert [[brand["id"] for brand in batch_brands] for batch_brands, _, _ in batches] == [[2], [3]]
    assert [[gap["brand_id"] for gap in batch_gaps] for _, batch_gaps, _ in batches] == [[2], [3]]


def test_topic_plan_generation_batches_do_not_call_llm_without_gaps(monkeypatch):
    monkeypatch.setenv("TOPIC_PLAN_LLM_BRANDS_PER_REQUEST", "1")

    batches = list(
        app_mod._topic_plan_brand_batches(
            [{"id": 1, "name": "Complete Brand"}],
            [],
            max_topics=10,
            max_per_brand=5,
        )
    )

    assert batches == []


def test_brand_options_do_not_require_topic_created_at(monkeypatch):
    class BrandCursor:
        def __init__(self):
            self.rows = []

        def execute(self, sql, params=None):
            compact = " ".join(str(sql).split())
            if "created_at" in compact:
                raise AssertionError("brand options should not require topics.created_at")
            if "FROM brands" in compact:
                self.rows = [
                    {
                        "id": 13,
                        "name": "NIKE",
                        "industry": "Sports",
                        "target_market": "",
                        "description": "",
                        "aliases": [],
                    }
                ]
            elif "COUNT(*) AS topic_count" in compact:
                self.rows = [{"brand_id": 13, "topic_count": 2}]
            elif "SELECT DISTINCT ON (brand_id)" in compact:
                self.rows = [{"brand_id": 13, "category": "running"}]

        def fetchall(self):
            return self.rows

    monkeypatch.setattr(app_mod, "_table_exists", lambda cur, table: table in {"brands", "topics"})
    monkeypatch.setattr(
        app_mod,
        "_table_columns",
        lambda cur, table: (
            {"id", "name", "industry", "target_market", "description", "aliases"}
            if table == "brands"
            else {"id", "brand_id", "text", "category"}
        ),
    )

    rows = app_mod._fetch_topic_plan_brands(BrandCursor())

    assert rows[0]["id"] == 13
    assert rows[0]["category_id"] == "running"


def test_stale_topic_plan_run_is_marked_failed(monkeypatch):
    monkeypatch.setenv("TOPIC_PLAN_RUN_TIMEOUT_SECONDS", "300")
    now = datetime(2026, 5, 6, 8, 0, tzinfo=timezone.utc)
    row = {
        "id": "run-1",
        "status": "running",
        "request_config": {"max_topics": 3},
        "updated_at": now - timedelta(seconds=301),
    }

    class StaleCursor:
        def __init__(self):
            self.updated = False

        def execute(self, query, params=None):
            self.updated = "UPDATE topic_plan_runs" in query
            assert params == ("run-1",)

        def fetchone(self):
            return {
                **row,
                "status": "failed",
                "llm_error": "topic_plan_run_timeout",
                "completed_at": now,
                "elapsed_seconds": 301,
            }

    cur = StaleCursor()

    updated, changed = app_mod._mark_stale_topic_plan_run(cur, row, now=now)

    assert changed is True
    assert cur.updated is True
    assert updated["status"] == "failed"
    assert updated["llm_error"] == "topic_plan_run_timeout"
