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


def test_segment_table_migration_backfills_legacy_columns(monkeypatch):
    conn = fake_db(monkeypatch)

    app_mod._ensure_segment_profile_tables()

    statements = "\n".join(sql for sql, _params in conn.statements)
    assert "ALTER TABLE segments ADD COLUMN IF NOT EXISTS name TEXT" in statements
    assert "ALTER TABLE segments ADD COLUMN IF NOT EXISTS status VARCHAR(16)" in statements
    assert "ALTER TABLE segments ADD COLUMN IF NOT EXISTS weight NUMERIC" in statements
    assert "ALTER TABLE segments ADD COLUMN IF NOT EXISTS age_range TEXT" in statements
    assert "ALTER TABLE segments ADD COLUMN IF NOT EXISTS income TEXT" in statements
    assert "ALTER TABLE segments ADD COLUMN IF NOT EXISTS regions TEXT" in statements
    assert "ALTER TABLE segments ADD COLUMN IF NOT EXISTS sampling_rate TEXT" in statements
    assert "ALTER TABLE segments ADD COLUMN IF NOT EXISTS note TEXT" in statements
    assert "ALTER TABLE segments ADD COLUMN IF NOT EXISTS brand_id VARCHAR(128)" in statements
    assert "ALTER TABLE segments ADD COLUMN IF NOT EXISTS brand_name TEXT" in statements


def test_profile_table_migration_backfills_legacy_columns(monkeypatch):
    conn = fake_db(monkeypatch)

    app_mod._ensure_segment_profile_tables()

    statements = "\n".join(sql for sql, _params in conn.statements)
    assert "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS name TEXT" in statements
    assert "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS brand_id VARCHAR(128)" in statements
    assert "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS brand_name TEXT" in statements


def test_admin_db_environment_defaults_to_local_admin_database(monkeypatch):
    for key in (
        "ADMIN_DATABASE_URL",
        "DATABASE_URL",
        "GENPANO_DATABASE_URL",
        "ADMIN_DB_USER",
        "ADMIN_DB_PASSWORD",
        "ADMIN_DB_HOST",
        "ADMIN_DB_PORT",
        "ADMIN_DB_NAME",
        "POSTGRES_PASSWORD",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("ADMIN_DB_USER", "genpano")
    monkeypatch.setenv("ADMIN_DB_PASSWORD", "local_dev_admin_pw")

    assert (
        app_mod._database_url_from_environment()
        == "postgresql://genpano:local_dev_admin_pw@localhost:5433/genpano_admin"
    )


def test_admin_db_environment_normalizes_asyncpg_url(monkeypatch):
    for key in ("ADMIN_DATABASE_URL", "DATABASE_URL", "GENPANO_DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://genpano:pw@postgres:5432/genpano")

    assert app_mod._database_url_from_environment() == "postgresql://genpano:pw@postgres:5432/genpano"


def test_admin_api_mount_alias_redirects_to_real_api(client):
    response = client.get("/admin/api/segments?page=2", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["Location"] == "/api/segments?page=2"


def test_segment_brand_fields_round_trip_payload_and_row():
    payload = app_mod._segment_payload(
        {"id": "SEG-001", "name": "Core buyers", "brand_id": "42", "brand_name": "CHANEL"}
    )
    assert payload["brand_id"] == "42"
    assert payload["brand_name"] == "CHANEL"

    row = app_mod._segment_row(
        {
            "id": "SEG-001",
            "name": "Core buyers",
            "brand_id": "42",
            "brand_name": "CHANEL",
            "weight": 0.5,
        }
    )
    assert row["brand_id"] == "42"
    assert row["brandId"] == "42"
    assert row["brand_name"] == "CHANEL"
    assert row["brandName"] == "CHANEL"


def test_profile_payload_inherits_segment_brand_context():
    payload = app_mod._profile_payload(
        {"id": "P-1", "name": "Proof seeker"},
        "SEG-001",
        segment={"brand_id": "42", "brand_name": "CHANEL"},
    )
    assert payload["brand_id"] == "42"
    assert payload["brand_name"] == "CHANEL"


def test_profile_payload_accepts_import_aliases():
    payload = app_mod._profile_payload(
        {
            "profile_id": "p-1",
            "profile_name": "Proof seeker",
            "persona": "25-34 urban buyer",
            "needs": "Needs ingredient proof",
            "personaJson": {"channel": "official store"},
        },
        "SEG-001",
    )

    assert payload["id"] == "P-1"
    assert payload["name"] == "Proof seeker"
    assert payload["demographic"] == "25-34 urban buyer"
    assert payload["need"] == "Needs ingredient proof"
    assert payload["persona_json"] == {"channel": "official store"}


def test_profile_import_skips_bad_rows_without_failing_batch(monkeypatch):
    conn = FakeConnection()
    cur = conn.cursor()
    created = []

    monkeypatch.setattr(
        app_mod,
        "_get_segment",
        lambda cur, segment_id: {"id": segment_id, "name": "Segment", "brand_id": "42", "brand_name": "CHANEL"},
    )
    monkeypatch.setattr(app_mod, "_get_profile", lambda cur, segment_id, profile_id: None)

    def fake_create(cur, segment_id, payload, admin_id):
        created.append(payload)
        return {"id": payload["id"], "name": payload["name"], "segment_id": segment_id}

    monkeypatch.setattr(app_mod, "_create_profile", fake_create)

    result = app_mod._import_profiles(
        cur,
        "SEG-001",
        [
            None,
            {"profile_id": "p-1", "profile_name": "Proof seeker", "persona": "demo", "needs": "need"},
        ],
        "admin-1",
    )

    assert result["added"] == 1
    assert result["skipped"] == 1
    assert result["skipped_rows"][0]["error"] == "profile_row_empty"
    assert created[0]["brand_id"] == "42"
    assert any("SAVEPOINT profile_import_row" in sql for sql, _params in conn.statements)
    assert any("ROLLBACK TO SAVEPOINT profile_import_row" in sql for sql, _params in conn.statements)


def test_segment_list_pagination_and_search(client, monkeypatch):
    login(monkeypatch)
    fake_db(monkeypatch)

    def fake_fetch(cur, *, page=1, per_page=50, q=None, status=None, industry_id=None, brand_id=None):
        assert page == 2
        assert per_page == 10
        assert q == "luxury"
        assert status == "active"
        assert industry_id == "beauty"
        assert brand_id == "42"
        return (
            [{"id": "SEG-001", "name": "Luxury buyers", "status": "active", "profile_count": 3}],
            21,
            {"segment_count": 21, "profile_count": 88, "active_weight_sum": 0.4},
        )

    monkeypatch.setattr(app_mod, "_fetch_segments", fake_fetch)
    response = client.get("/api/segments?page=2&per_page=10&q=luxury&status=active&industry_id=beauty&brand_id=42")
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


def test_segment_import_returns_json_error_on_unexpected_failure(client, monkeypatch):
    login(monkeypatch)
    conn = fake_db(monkeypatch)

    def broken_import(*_args, **_kwargs):
        raise RuntimeError("missing column")

    monkeypatch.setattr(app_mod, "_import_segments", broken_import)
    response = client.post("/api/segments/import", json={"rows": [{"id": "SEG-001", "name": "A"}]})
    body = response.get_json()

    assert response.status_code == 500
    assert body["error"] == "segment_import_failed"
    assert conn.rollbacks == 1


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
        json={"brand_id": "42", "brand_name": "CHANEL", "industry": "beauty", "count": 1, "status": "draft"},
    )
    body = response.get_json()
    assert response.status_code == 200
    assert body["drafts"][0]["id"] == "SEG-DRAFT-001"
    assert body["drafts"][0]["brand_id"] == "42"
    assert body["drafts"][0]["brand_name"] == "CHANEL"
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


def test_profile_import_returns_json_error_on_unexpected_failure(client, monkeypatch):
    login(monkeypatch)
    conn = fake_db(monkeypatch)

    def broken_import(*_args, **_kwargs):
        raise RuntimeError("missing column")

    monkeypatch.setattr(app_mod, "_import_profiles", broken_import)
    response = client.post("/api/segments/SEG-001/profiles/import", json={"rows": [{"id": "P-1", "name": "A"}]})
    body = response.get_json()

    assert response.status_code == 500
    assert body["error"] == "profile_import_failed"
    assert conn.rollbacks == 1


def test_profile_import_returns_400_when_all_rows_are_invalid(client, monkeypatch):
    login(monkeypatch)
    conn = fake_db(monkeypatch)

    monkeypatch.setattr(
        app_mod,
        "_import_profiles",
        lambda cur, segment_id, rows, admin_id: {
            "added": 0,
            "updated": 0,
            "skipped": 1,
            "skipped_rows": [{"index": 1, "error": "profile_name_required"}],
            "rows": [],
        },
    )

    response = client.post("/api/segments/SEG-001/profiles/import", json={"rows": [{"id": "P-1"}]})
    body = response.get_json()

    assert response.status_code == 400
    assert body["error"] == "profile_import_no_valid_rows"
    assert body["skipped_rows"][0]["error"] == "profile_name_required"
    assert conn.rollbacks == 1


def test_llm_profile_generation_service_boundary(client, monkeypatch):
    login(monkeypatch)
    conn = fake_db(monkeypatch)
    monkeypatch.setattr(
        app_mod,
        "_get_segment",
        lambda cur, segment_id: {"id": segment_id, "name": "Segment", "brand_id": "42", "brand_name": "CHANEL"},
    )
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
    assert body["drafts"][0]["brand_id"] == "42"
    assert body["drafts"][0]["brand_name"] == "CHANEL"
    assert calls[0]["segment"]["id"] == "SEG-001"
    assert any("INSERT INTO profile_generation_logs" in sql for sql, _ in conn.statements)


def test_async_profile_generation_returns_job(client, monkeypatch):
    login(monkeypatch)
    with app_mod._profile_generation_jobs_lock:
        app_mod._profile_generation_jobs.clear()
    started = {}

    class FakeThread:
        def __init__(self, target=None, kwargs=None, daemon=None):
            started["target"] = target
            started["kwargs"] = kwargs
            started["daemon"] = daemon

        def start(self):
            started["started"] = True

    monkeypatch.setattr(app_mod.threading, "Thread", FakeThread)

    response = client.post(
        "/api/segments/SEG-001/profiles/generate",
        json={"brand_name": "CHANEL", "count": 6, "async_generation": True},
    )
    body = response.get_json()

    assert response.status_code == 202
    assert body["pending"] is True
    assert body["job_id"]
    assert started["started"] is True
    assert started["daemon"] is True
    assert started["kwargs"]["segment_id"] == "SEG-001"
    job = app_mod._get_profile_generation_job(body["job_id"])
    assert job["status"] == "queued"
    assert job["segment_id"] == "SEG-001"

    with app_mod._profile_generation_jobs_lock:
        app_mod._profile_generation_jobs.clear()


def test_profile_generation_job_poll_returns_completed(client, monkeypatch):
    login(monkeypatch)
    with app_mod._profile_generation_jobs_lock:
        app_mod._profile_generation_jobs.clear()
    app_mod._set_profile_generation_job(
        "job-1",
        segment_id="SEG-001",
        status="completed",
        drafts=[{"id": "P-1", "name": "Draft"}],
        model="fake-model",
        usage={"total_tokens": 10},
    )

    response = client.get("/api/segments/SEG-001/profiles/generate/job-1")
    body = response.get_json()

    assert response.status_code == 200
    assert body["pending"] is False
    assert body["status"] == "completed"
    assert body["drafts"][0]["id"] == "P-1"

    with app_mod._profile_generation_jobs_lock:
        app_mod._profile_generation_jobs.clear()


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


def test_profile_generation_accepts_relative_weight_and_alias_fields():
    rows = segment_profiles.validate_profile_candidates(
        [
            {
                "profile_name": "Price optimizer",
                "persona": "25-34 urban beauty buyer",
                "needs": "Compares bundles, channels, and final price.",
                "weight": "1.3",
                "status": "已启用",
            }
        ],
        3,
    )

    assert rows[0]["id"] == "P-DRAFT-001"
    assert rows[0]["name"] == "Price optimizer"
    assert rows[0]["demographic"] == "25-34 urban beauty buyer"
    assert rows[0]["need"] == "Compares bundles, channels, and final price."
    assert rows[0]["weight"] == 1.3
    assert rows[0]["status"] == "active"
    assert rows[0]["persona_json"]["summary"] == "25-34 urban beauty buyer"


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
