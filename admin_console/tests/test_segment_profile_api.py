import json
import sys
from types import SimpleNamespace

import pytest

import admin_console.app as app_mod
import admin_console.segment_profiles as segment_profiles


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rows = []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        compact = " ".join(str(sql).split())
        self.conn.statements.append((compact, params))
        self.rows = []

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self):
        self.statements = []
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


def fake_db(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)
    return conn


def test_segment_list_pagination_and_search(client, monkeypatch):
    login(monkeypatch)
    fake_db(monkeypatch)

    def fake_fetch(cur, *, page=1, per_page=50, q=None, status=None, industry_id=None):
        assert page == 2
        assert per_page == 10
        assert q == "luxury"
        assert status == "active"
        assert industry_id == "beauty"
        return (
            [{"id": "SEG-001", "name": "Luxury buyers", "status": "active", "profile_count": 3}],
            21,
            {"segment_count": 21, "profile_count": 88, "active_weight_sum": 0.4},
        )

    monkeypatch.setattr(app_mod, "_fetch_segments", fake_fetch)
    response = client.get("/api/segments?page=2&per_page=10&q=luxury&status=active&industry_id=beauty")
    body = response.get_json()
    assert response.status_code == 200
    assert body["rows"][0]["id"] == "SEG-001"
    assert body["pagination"] == {"page": 2, "per_page": 10, "total": 21, "total_pages": 3}
    assert body["summary"]["active_weight_sum"] == 0.4


def test_segment_create_update_and_soft_delete_write_audit(client, monkeypatch):
    login(monkeypatch)
    conn = fake_db(monkeypatch)
    segment_before = {"id": "SEG-001", "name": "Old", "status": "draft"}
    segment_after = {"id": "SEG-001", "name": "New", "status": "active"}

    monkeypatch.setattr(app_mod, "_create_segment", lambda cur, payload, admin_id: segment_after)
    response = client.post("/api/segments", json={"id": "SEG-001", "name": "New", "status": "active"})
    assert response.status_code == 201
    assert any("INSERT INTO admin_audit_log" in sql for sql, _ in conn.statements)

    conn.statements.clear()
    monkeypatch.setattr(app_mod, "_get_segment", lambda cur, segment_id: segment_before)
    monkeypatch.setattr(app_mod, "_update_segment", lambda cur, segment_id, payload, admin_id: segment_after)
    response = client.put("/api/segments/SEG-001", json={"id": "SEG-001", "name": "New", "status": "active"})
    assert response.status_code == 200
    assert any("update_segment" in str(params) for _sql, params in conn.statements)

    conn.statements.clear()
    monkeypatch.setattr(app_mod, "_soft_delete_segment", lambda cur, segment_id, admin_id: segment_after)
    response = client.delete("/api/segments/SEG-001", json={"reason": "cleanup"})
    assert response.status_code == 200
    assert any("delete_segment" in str(params) for _sql, params in conn.statements)


def test_segment_import(client, monkeypatch):
    login(monkeypatch)
    conn = fake_db(monkeypatch)
    monkeypatch.setattr(
        app_mod,
        "_import_segments",
        lambda cur, rows, admin_id: {"added": 1, "updated": 1, "skipped": 0, "rows": rows},
    )
    response = client.post(
        "/api/segments/import",
        json={"rows": [{"id": "SEG-001", "name": "A"}, {"id": "SEG-002", "name": "B"}]},
    )
    body = response.get_json()
    assert response.status_code == 200
    assert body["added"] == 1
    assert body["updated"] == 1
    assert any("import_segments" in str(params) for _sql, params in conn.statements)


def test_llm_segment_generation_service_boundary(client, monkeypatch):
    login(monkeypatch)
    conn = fake_db(monkeypatch)
    calls = []

    class FakeService:
        def __init__(self, model=None):
            self.model = model

        def generate_segments(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                items=[{"id": "SEG-DRAFT-001", "name": "Draft", "status": "draft", "weight": 0.2}],
                model=self.model or "fake-model",
                prompt="structured json prompt",
                usage={"total_tokens": 12},
                estimated_cost=0.01,
            )

    monkeypatch.setattr(app_mod, "SegmentProfileGenerationService", FakeService)
    response = client.post(
        "/api/segments/generate",
        json={"brand_name": "CHANEL", "industry": "beauty", "count": 1, "status": "draft"},
    )
    body = response.get_json()
    assert response.status_code == 200
    assert body["drafts"][0]["id"] == "SEG-DRAFT-001"
    assert calls[0]["brand_name"] == "CHANEL"
    assert any("INSERT INTO segment_generation_logs" in sql for sql, _ in conn.statements)
    assert any("generate_segments" in str(params) for _sql, params in conn.statements)


def test_profile_list_under_segment(client, monkeypatch):
    login(monkeypatch)
    fake_db(monkeypatch)
    monkeypatch.setattr(app_mod, "_get_segment", lambda cur, segment_id: {"id": segment_id, "name": "Segment"})

    def fake_fetch(cur, segment_id, *, page=1, per_page=100, q=None, status=None):
        assert segment_id == "SEG-001"
        assert page == 3
        assert per_page == 25
        assert q == "gift"
        assert status == "active"
        return ([{"id": "P-1", "name": "Gift buyer", "status": "active"}], 51)

    monkeypatch.setattr(app_mod, "_fetch_profiles", fake_fetch)
    response = client.get("/api/segments/SEG-001/profiles?page=3&per_page=25&q=gift&status=active")
    body = response.get_json()
    assert response.status_code == 200
    assert body["rows"][0]["id"] == "P-1"
    assert body["pagination"]["total_pages"] == 3


def test_profile_create_update_soft_delete_import_export(client, monkeypatch):
    login(monkeypatch)
    conn = fake_db(monkeypatch)
    segment = {"id": "SEG-001", "name": "Segment"}
    profile_before = {"id": "P-1", "name": "Old", "status": "draft"}
    profile_after = {
        "id": "P-1",
        "segment_id": "SEG-001",
        "name": "New",
        "demographic": "25-34",
        "need": "compare gifts",
        "weight": 1.0,
        "status": "active",
    }
    monkeypatch.setattr(app_mod, "_get_segment", lambda cur, segment_id: segment)
    monkeypatch.setattr(app_mod, "_create_profile", lambda cur, segment_id, payload, admin_id: profile_after)
    response = client.post("/api/segments/SEG-001/profiles", json={"id": "P-1", "name": "New"})
    assert response.status_code == 201
    assert any("create_profile" in str(params) for _sql, params in conn.statements)

    conn.statements.clear()
    monkeypatch.setattr(app_mod, "_get_profile", lambda cur, segment_id, profile_id: profile_before)
    monkeypatch.setattr(app_mod, "_update_profile", lambda cur, segment_id, profile_id, payload, admin_id: profile_after)
    response = client.put("/api/segments/SEG-001/profiles/P-1", json={"id": "P-1", "name": "New"})
    assert response.status_code == 200
    assert any("update_profile" in str(params) for _sql, params in conn.statements)

    conn.statements.clear()
    monkeypatch.setattr(app_mod, "_soft_delete_profile", lambda cur, segment_id, profile_id, admin_id: profile_after)
    response = client.delete("/api/segments/SEG-001/profiles/P-1", json={"reason": "cleanup"})
    assert response.status_code == 200
    assert any("delete_profile" in str(params) for _sql, params in conn.statements)

    conn.statements.clear()
    monkeypatch.setattr(
        app_mod,
        "_import_profiles",
        lambda cur, segment_id, rows, admin_id: {"added": 1, "updated": 0, "skipped": 0, "rows": rows},
    )
    response = client.post("/api/segments/SEG-001/profiles/import", json={"rows": [{"id": "P-2", "name": "Imported"}]})
    assert response.status_code == 200
    assert response.get_json()["added"] == 1

    monkeypatch.setattr(app_mod, "_fetch_profiles", lambda cur, segment_id, page=1, per_page=100000, q=None, status=None: ([profile_after], 1))
    response = client.get("/api/segments/SEG-001/profiles/export")
    assert response.status_code == 200
    csv_text = response.get_data(as_text=True)
    assert "id,segment_id,name,demographic,need,weight,status" in csv_text
    assert "P-1,SEG-001,New" in csv_text


def test_llm_profile_generation_service_boundary(client, monkeypatch):
    login(monkeypatch)
    conn = fake_db(monkeypatch)
    monkeypatch.setattr(app_mod, "_get_segment", lambda cur, segment_id: {"id": segment_id, "name": "Segment"})
    calls = []

    class FakeService:
        def __init__(self, model=None):
            self.model = model

        def generate_profiles(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                items=[{"id": "P-DRAFT-01", "name": "Draft profile", "status": "draft", "weight": 1.0}],
                model=self.model or "fake-model",
                prompt="structured json prompt",
                usage={"total_tokens": 10},
                estimated_cost=0.01,
            )

    monkeypatch.setattr(app_mod, "SegmentProfileGenerationService", FakeService)
    response = client.post(
        "/api/segments/SEG-001/profiles/generate",
        json={"brand_name": "CHANEL", "count": 1, "goal": "cover gift buyers"},
    )
    body = response.get_json()
    assert response.status_code == 200
    assert body["drafts"][0]["id"] == "P-DRAFT-01"
    assert calls[0]["segment"]["id"] == "SEG-001"
    assert any("INSERT INTO profile_generation_logs" in sql for sql, _ in conn.statements)


def test_segment_generation_service_uses_openai_compatible_llm(monkeypatch):
    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps(
                                {
                                    "segments": [
                                        {
                                            "id": "SEG-LLM-001",
                                            "name": "LLM Segment",
                                            "industry": "Beauty",
                                            "status": "draft",
                                            "weight": 0.2,
                                            "age_range": "25-34",
                                            "income": "mid-high",
                                            "regions": "tier 1",
                                            "sampling_rate": "20%",
                                            "note": "Generated by model",
                                        }
                                    ]
                                }
                            )
                        )
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setattr(
        segment_profiles,
        "load_doubao_config",
        lambda: SimpleNamespace(api_key="key", base_url="https://ark.example", model="doubao-test"),
    )

    result = segment_profiles.SegmentProfileGenerationService().generate_segments(
        brand_name="CHANEL",
        industry="Beauty",
        count=1,
        status="draft",
        positioning="Premium beauty",
        goal="Cover core buyers",
        constraints="No duplicates",
    )

    assert result.model == "doubao-test"
    assert result.items[0]["id"] == "SEG-LLM-001"
    assert result.usage["total_tokens"] == 30
    assert calls[0]["model"] == "doubao-test"


def test_profile_generation_service_uses_openai_compatible_llm(monkeypatch):
    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps(
                                {
                                    "profiles": [
                                        {
                                            "id": "P-LLM-01",
                                            "name": "Proof seeker",
                                            "demographic": "25-34 / mid-high / tier 1",
                                            "need": "Needs expert proof before buying.",
                                            "weight": 1.0,
                                            "status": "draft",
                                            "persona_json": {"archetype": "proof"},
                                        }
                                    ]
                                }
                            )
                        )
                    )
                ],
                usage={"total_tokens": 24},
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setattr(
        segment_profiles,
        "load_doubao_config",
        lambda: SimpleNamespace(api_key="key", base_url="https://ark.example", model="doubao-test"),
    )

    result = segment_profiles.SegmentProfileGenerationService().generate_profiles(
        segment={"id": "SEG-001", "name": "Core buyers", "industry": "Beauty"},
        brand_name="CHANEL",
        count=1,
        goal="Generate profiles",
        constraints="No queries",
    )

    assert result.model == "doubao-test"
    assert result.items[0]["id"] == "P-LLM-01"
    assert result.items[0]["persona_json"] == {"archetype": "proof"}


def test_generation_service_rejects_incomplete_llm_output(monkeypatch):
    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"segments":[{"name":"Incomplete"}]}'))],
                usage={},
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setattr(
        segment_profiles,
        "load_doubao_config",
        lambda: SimpleNamespace(api_key="key", base_url="https://ark.example", model="doubao-test"),
    )

    with pytest.raises(segment_profiles.SegmentProfileGenerationError) as exc:
        segment_profiles.SegmentProfileGenerationService().generate_segments(
            brand_name="CHANEL",
            industry="Beauty",
            count=1,
            status="draft",
            positioning="",
            goal="",
            constraints="",
        )

    assert exc.value.code == "missing_llm_field"


def test_mutations_require_admin(client):
    response = client.post("/api/segments", json={"id": "SEG-001", "name": "Nope"})
    assert response.status_code == 401
    assert response.get_json()["error"] == "admin_session_required"

    response = client.post("/api/segments/SEG-001/profiles", json={"id": "P-1", "name": "Nope"})
    assert response.status_code == 401
    assert response.get_json()["error"] == "admin_session_required"
