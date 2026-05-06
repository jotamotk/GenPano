import pytest

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
        lambda cur, brand_ids: {"pending": 1, "low_confidence": 0},
    )

    def fake_fetch(cur, status="pending", brand_ids=None, query=None, limit=100, run_id=None):
        assert run_id == "run-1"
        return [{"id": "candidate-1", "run_id": run_id, "status": status}]

    monkeypatch.setattr(app_mod, "_fetch_topic_plan_candidates", fake_fetch)

    response = client.get("/api/admin/topic-plan/candidates?status=pending&run_id=run-1&brand_ids=13")
    body = response.get_json()

    assert response.status_code == 200
    assert body["rows"] == [{"id": "candidate-1", "run_id": "run-1", "status": "pending"}]
