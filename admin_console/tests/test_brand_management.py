import json
import sys
from types import SimpleNamespace

import pytest

import admin_console.app as app_mod
import admin_console.brand_management as brand_management


# ─── Service-level tests (no DB / no LLM) ────────────────────────────────────


def test_normalize_brand_draft_requires_name():
    with pytest.raises(brand_management.BrandManagementError) as info:
        brand_management.normalize_brand_draft({"industry": "Beauty"})
    assert info.value.code == "missing_brand_name"


def test_normalize_brand_draft_canonicalizes_fields():
    draft = brand_management.normalize_brand_draft(
        {
            "name": "  Lancôme  ",
            "中文名": "兰蔻",
            "english_name": "Lancome",
            "industry": "Beauty",
            "aliases": "lancome, LC, 兰蔻",
            "official_domains": ["lancome.com", "lancome.com.cn"],
            "competitors": [
                "Estée Lauder",
                {"name": "Dior Beauty", "type": "competitor"},
                {"name": "L'Oréal", "type": "same-group", "note": "parent group"},
            ],
            "founded_year": "1935",
            "status": "已启用",
            "source": "llm",
            "tags": "luxury, fragrance",
        }
    )
    assert draft["name"] == "Lancôme"
    assert draft["name_zh"] == "兰蔻"
    assert draft["name_en"] == "Lancome"
    assert draft["industry"] == "Beauty"
    assert draft["aliases"] == ["lancome", "LC", "兰蔻"]
    assert draft["official_domains"] == ["lancome.com", "lancome.com.cn"]
    assert {c["name"] for c in draft["competitors"]} == {"Estée Lauder", "Dior Beauty", "L'Oréal"}
    types_by_name = {c["name"]: c["type"] for c in draft["competitors"]}
    assert types_by_name["Dior Beauty"] == "COMPETES_WITH"
    assert types_by_name["L'Oréal"] == "SAME_GROUP"
    assert draft["founded_year"] == 1935
    assert draft["status"] == "active"
    assert draft["source"] == "llm"
    assert draft["tags"] == ["luxury", "fragrance"]


def test_validate_brand_candidates_dedupes_and_marks_source():
    items = [
        {"name": "Brand A", "industry": "EV"},
        {"name": "brand a", "industry": "EV"},  # duplicate by case
        {"industry": "EV"},  # missing name
        {"name": "Brand B"},
    ]
    drafts = brand_management.validate_brand_candidates(items, max_count=10)
    names = [d["name"] for d in drafts]
    assert names == ["Brand A", "Brand B"]
    assert all(d["source"] == "llm" for d in drafts)


def test_brand_to_kg_payload_uses_pending_for_drafts():
    draft = brand_management.normalize_brand_draft(
        {"name": "DraftCo", "industry": "Beauty", "status": "draft"}
    )
    payload = brand_management.brand_to_kg_payload(draft, brand_id=42)
    assert payload["brand_id"] == 42
    assert payload["primary_name"] == "DraftCo"
    assert payload["status"] == "pending"


def test_brand_to_kg_payload_uses_approved_for_active():
    draft = brand_management.normalize_brand_draft(
        {"name": "ActiveCo", "industry": "Beauty", "status": "active"}
    )
    payload = brand_management.brand_to_kg_payload(draft, brand_id=7)
    assert payload["status"] == "approved"


def test_generate_brands_uses_fallback_when_llm_unavailable(monkeypatch):
    service = brand_management.BrandManagementService(allow_fallback=True)

    def boom(**kwargs):
        raise brand_management.BrandManagementError("llm_call_failed", "LLM is offline")

    monkeypatch.setattr(service, "_call_llm_json", boom)
    result = service.generate_brands(industry="Beauty", count=4, region="china")
    assert len(result.items) == 4
    assert result.model == "fallback-brand-management-v1"
    assert all(item["industry"] == "Beauty" for item in result.items)


def test_generate_brands_propagates_when_fallback_disabled(monkeypatch):
    service = brand_management.BrandManagementService(allow_fallback=False)

    def boom(**kwargs):
        raise brand_management.BrandManagementError("llm_call_failed", "LLM is offline")

    monkeypatch.setattr(service, "_call_llm_json", boom)
    with pytest.raises(brand_management.BrandManagementError) as info:
        service.generate_brands(industry="Beauty", count=2)
    assert info.value.code == "llm_call_failed"


def test_generate_brands_rejects_blank_industry():
    service = brand_management.BrandManagementService(allow_fallback=True)
    with pytest.raises(brand_management.BrandManagementError) as info:
        service.generate_brands(industry="   ", count=3)
    assert info.value.code == "missing_industry"


# ─── API-level tests with fake DB ────────────────────────────────────────────


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._next_rows = []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        compact = " ".join(str(sql).split())
        self.conn.statements.append((compact, params))
        self._next_rows = self.conn._next_for(compact, params)

    def fetchone(self):
        return self._next_rows[0] if self._next_rows else None

    def fetchall(self):
        return list(self._next_rows)


class FakeConnection:
    def __init__(self):
        self.statements = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self._scripted: list[tuple[str, list]] = []

    def script(self, fragment: str, rows: list):
        self._scripted.append((fragment, rows))

    def _next_for(self, sql, params):
        for index, (fragment, rows) in enumerate(self._scripted):
            if fragment in sql:
                self._scripted.pop(index)
                return rows
        return []

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
    app_mod.app.config.update(TESTING=True, SECRET_KEY="brand-mgmt-test")
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


def test_admin_audit_log_insert_populates_legacy_resource_columns():
    class AuditCursor:
        def __init__(self):
            self.rows = []
            self.insert_sql = ""
            self.insert_params = None

        def execute(self, sql, params=None):
            compact = " ".join(str(sql).split())
            if "information_schema.columns" in compact:
                self.rows = [
                    {"column_name": name}
                    for name in (
                        "id",
                        "operator_id",
                        "action",
                        "resource_type",
                        "resource_id",
                        "target_type",
                        "target_id",
                        "diff_json",
                        "reason",
                        "ip",
                        "ua",
                        "created_at",
                    )
                ]
                return
            self.insert_sql = compact
            self.insert_params = params

        def fetchall(self):
            return list(self.rows)

    cur = AuditCursor()

    app_mod._insert_admin_audit_log(
        cur,
        operator_id="admin-1",
        action="enrich_brand",
        target_type="brand",
        target_id=None,
        diff={"name": "Best Coffer"},
        reason=None,
    )

    assert "resource_type" in cur.insert_sql
    assert "resource_id" in cur.insert_sql
    assert "target_type" in cur.insert_sql
    assert cur.insert_params[3] == "brand"
    assert cur.insert_params[5] == "brand"


def test_brand_management_migration_alters_brands_and_creates_logs(monkeypatch):
    conn = fake_db(monkeypatch)
    monkeypatch.setattr(app_mod, "_table_exists", lambda cur, name: name == "brands")

    app_mod._ensure_brand_management_tables()

    statements = "\n".join(sql for sql, _params in conn.statements)
    for column in (
        "name_zh",
        "name_en",
        "official_domains",
        "positioning",
        "headquarters",
        "founded_year",
        "tags",
        "status",
        "source",
        "created_at",
        "updated_at",
    ):
        assert f"ALTER TABLE brands ADD COLUMN IF NOT EXISTS {column}" in statements
    assert "CREATE TABLE IF NOT EXISTS brand_generation_logs" in statements
    assert "CREATE INDEX IF NOT EXISTS idx_brands_industry_status" in statements


def test_brand_generate_endpoint_requires_industry(monkeypatch, client):
    login(monkeypatch)
    fake_db(monkeypatch)

    response = client.post(
        "/api/admin/brand-management/generate",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "industry_required"


def test_brand_generate_endpoint_records_log_and_returns_drafts(monkeypatch, client):
    login(monkeypatch)
    conn = fake_db(monkeypatch)
    monkeypatch.setattr(app_mod, "_table_exists", lambda cur, name: name == "brands")
    monkeypatch.setattr(app_mod, "_table_columns", lambda cur, name: ["id", "name", "industry"])

    conn.script("FROM brands WHERE industry =", [{"name": "Existing"}])
    captured = {}

    class FakeService:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)

        def generate_brands(self, **kwargs):
            assert kwargs["industry"] == "Beauty"
            assert kwargs["seed_brands"] == ["Existing"]
            return brand_management.BrandGenerationResult(
                items=[
                    brand_management.normalize_brand_draft(
                        {"name": "FakeBrand", "industry": "Beauty"}
                    )
                ],
                model="fake-model",
                prompt="prompt-body",
                usage={"total_tokens": 12},
                estimated_cost=0.0,
            )

    monkeypatch.setattr(app_mod, "BrandManagementService", FakeService)

    response = client.post(
        "/api/admin/brand-management/generate",
        data=json.dumps({"industry": "Beauty", "count": 2}),
        content_type="application/json",
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["industry"] == "Beauty"
    assert body["model"] == "fake-model"
    assert len(body["drafts"]) == 1
    assert captured["allow_fallback"] is False
    statements = "\n".join(sql for sql, _params in conn.statements)
    assert "INSERT INTO brand_generation_logs" in statements
    assert "INSERT INTO admin_audit_log" in statements
    assert conn.commits == 1


def test_brand_create_endpoint_persists_and_logs(monkeypatch, client):
    login(monkeypatch)
    conn = fake_db(monkeypatch)
    monkeypatch.setattr(app_mod, "_table_exists", lambda cur, name: name == "brands")
    monkeypatch.setattr(
        app_mod,
        "_table_columns",
        lambda cur, name: [
            "id",
            "name",
            "name_zh",
            "name_en",
            "industry",
            "target_market",
            "description",
            "positioning",
            "headquarters",
            "founded_year",
            "aliases",
            "official_domains",
            "tags",
            "status",
            "source",
            "created_by",
            "created_at",
            "updated_at",
        ],
    )

    conn.script("INSERT INTO brands", [{"id": 999}])
    conn.script("FROM brands WHERE id =", [
        {
            "id": 999,
            "name": "Future Beauty",
            "name_zh": None,
            "name_en": "Future Beauty",
            "industry": "Beauty",
            "target_market": "global",
            "description": "auto-generated test fixture",
            "positioning": "",
            "headquarters": "",
            "founded_year": None,
            "aliases": ["FB"],
            "official_domains": ["fb.com"],
            "tags": [],
            "status": "active",
            "source": "manual",
            "created_by": "admin-1",
            "created_at": None,
            "updated_at": None,
        }
    ])

    response = client.post(
        "/api/admin/brand-management",
        data=json.dumps(
            {
                "name": "Future Beauty",
                "industry": "Beauty",
                "target_market": "global",
                "description": "auto-generated test fixture",
                "aliases": ["FB"],
                "official_domains": ["fb.com"],
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["brand"]["id"] == 999
    statements = "\n".join(sql for sql, _params in conn.statements)
    assert "INSERT INTO brands" in statements
    assert "INSERT INTO admin_audit_log" in statements
    assert conn.commits == 1


def test_enrich_brand_uses_fallback_when_llm_unavailable(monkeypatch):
    service = brand_management.BrandManagementService(allow_fallback=True)

    def boom(**kwargs):
        raise brand_management.BrandManagementError("llm_call_failed", "offline")

    monkeypatch.setattr(service, "_call_llm_json", boom)
    result = service.enrich_brand_by_name(name="兰蔻 Lancôme")
    assert len(result.items) == 1
    assert result.items[0]["name"] == "兰蔻 Lancôme"
    assert result.model == "fallback-brand-management-v1"


def test_enrich_brand_rejects_blank_name():
    service = brand_management.BrandManagementService(allow_fallback=True)
    with pytest.raises(brand_management.BrandManagementError) as info:
        service.enrich_brand_by_name(name="   ")
    assert info.value.code == "missing_brand_name"


def test_enrich_brand_returns_canonicalized_draft(monkeypatch):
    service = brand_management.BrandManagementService(allow_fallback=False)

    def fake_call(**kwargs):
        return (
            [
                {
                    "name": "Lancôme",
                    "name_zh": "兰蔻",
                    "name_en": "Lancome",
                    "industry": "Beauty",
                    "target_market": "global",
                    "description": "Premier French luxury beauty house under L'Oréal.",
                    "positioning": "Premium skincare and fragrance",
                    "headquarters": "Paris, France",
                    "founded_year": 1935,
                    "aliases": ["LC"],
                    "official_domains": ["lancome.com"],
                    "competitors": [
                        {"name": "Estée Lauder", "type": "COMPETES_WITH"},
                        {"name": "L'Oréal Paris", "type": "SAME_GROUP"},
                    ],
                    "status": "active",
                    "tags": ["luxury"],
                }
            ],
            "fake-model",
            {"total_tokens": 42},
        )

    monkeypatch.setattr(service, "_call_llm_json", fake_call)
    result = service.enrich_brand_by_name(name="Lancôme")
    assert result.model == "fake-model"
    draft = result.items[0]
    assert draft["name"] == "Lancôme"
    assert draft["industry"] == "Beauty"
    assert draft["founded_year"] == 1935
    assert {c["name"] for c in draft["competitors"]} == {"Estée Lauder", "L'Oréal Paris"}
    types_by_name = {c["name"]: c["type"] for c in draft["competitors"]}
    assert types_by_name["L'Oréal Paris"] == "SAME_GROUP"


def test_enrich_brand_uses_timeout_override(monkeypatch):
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured["create_timeout"] = kwargs.get("timeout")
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps(
                                {
                                    "brands": [
                                        {
                                            "name": "Lancome",
                                            "industry": "Beauty",
                                        }
                                    ]
                                }
                            )
                        )
                    )
                ],
                usage=None,
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client_timeout"] = kwargs.get("timeout")
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    service = brand_management.BrandManagementService(
        config=SimpleNamespace(api_key="key", base_url="https://example.test", model="fake-model"),
        timeout_seconds=12,
    )

    result = service.enrich_brand_by_name(name="Lancome")

    assert result.items[0]["name"] == "Lancome"
    assert captured["client_timeout"] == 12
    assert captured["create_timeout"] == 12


def test_enrich_brand_accepts_singular_brand_object(monkeypatch):
    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps(
                                {
                                    "brand": {
                                        "name": "Lancome",
                                        "industry": "Beauty",
                                    }
                                }
                            )
                        )
                    )
                ],
                usage=None,
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    service = brand_management.BrandManagementService(
        config=SimpleNamespace(api_key="key", base_url="https://example.test", model="fake-model"),
        timeout_seconds=12,
    )

    result = service.enrich_brand_by_name(name="Lancome")

    assert result.items[0]["name"] == "Lancome"
    assert result.items[0]["industry"] == "Beauty"


def test_brand_enrich_endpoint_requires_name(monkeypatch, client):
    login(monkeypatch)
    fake_db(monkeypatch)

    response = client.post(
        "/api/admin/brand-management/enrich",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "name_required"


def test_brand_enrich_timeout_defaults_to_shared_llm_window(monkeypatch):
    monkeypatch.delenv("BRAND_MANAGEMENT_ENRICH_TIMEOUT_SECONDS", raising=False)

    assert app_mod._brand_management_enrich_timeout_seconds() == 90


def test_brand_enrich_endpoint_uses_long_timeout_without_fallback(monkeypatch, client):
    login(monkeypatch)
    fake_db(monkeypatch)
    monkeypatch.setenv("BRAND_MANAGEMENT_ENRICH_TIMEOUT_SECONDS", "120")
    captured = {}

    class FakeService:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)

        def enrich_brand_by_name(self, *, name):
            return brand_management.BrandGenerationResult(
                items=[brand_management.normalize_brand_draft({"name": name, "status": "draft"})],
                model="fallback-brand-management-v1",
                prompt="enrich-prompt",
                usage={"total_tokens": 0},
            )

    monkeypatch.setattr(app_mod, "BrandManagementService", FakeService)

    response = client.post(
        "/api/admin/brand-management/enrich",
        data=json.dumps({"name": "Lancome"}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert captured["allow_fallback"] is False
    assert captured["timeout_seconds"] == 120


def test_brand_enrich_endpoint_returns_draft_and_audits(monkeypatch, client):
    login(monkeypatch)
    conn = fake_db(monkeypatch)

    class FakeService:
        def __init__(self, *args, **kwargs):
            pass

        def enrich_brand_by_name(self, *, name):
            assert name == "Lancôme"
            return brand_management.BrandGenerationResult(
                items=[
                    brand_management.normalize_brand_draft(
                        {
                            "name": "Lancôme",
                            "name_zh": "兰蔻",
                            "industry": "Beauty",
                            "founded_year": 1935,
                        }
                    )
                ],
                model="fake-model",
                prompt="enrich-prompt",
                usage={"total_tokens": 7},
            )

    monkeypatch.setattr(app_mod, "BrandManagementService", FakeService)

    response = client.post(
        "/api/admin/brand-management/enrich",
        data=json.dumps({"name": "Lancôme"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["draft"]["name"] == "Lancôme"
    assert body["draft"]["name_zh"] == "兰蔻"
    assert body["model"] == "fake-model"
    statements = "\n".join(sql for sql, _params in conn.statements)
    assert "INSERT INTO admin_audit_log" in statements
    assert conn.commits == 1


def test_brand_enrich_endpoint_returns_async_job(monkeypatch, client):
    login(monkeypatch)
    with app_mod._brand_enrich_jobs_lock:
        app_mod._brand_enrich_jobs.clear()
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
        "/api/admin/brand-management/enrich",
        data=json.dumps({"name": "Lancome", "async": True}),
        content_type="application/json",
    )

    assert response.status_code == 202
    body = response.get_json()
    assert body["success"] is True
    assert body["pending"] is True
    assert body["job_id"]
    assert body["status"] == "queued"
    assert started["started"] is True
    assert started["daemon"] is True
    assert started["kwargs"]["name"] == "Lancome"
    job = app_mod._get_brand_enrich_job(body["job_id"])
    assert job["status"] == "queued"


def test_brand_enrich_job_poll_returns_choices(monkeypatch, client):
    login(monkeypatch)
    with app_mod._brand_enrich_jobs_lock:
        app_mod._brand_enrich_jobs.clear()
    drafts = [
        brand_management.normalize_brand_draft({"name": "Lancome", "industry": "Beauty"}),
        brand_management.normalize_brand_draft({"name": "Lancome Paris", "industry": "Beauty"}),
    ]
    app_mod._set_brand_enrich_job(
        "job-1",
        status="completed",
        drafts=drafts,
        model="fake-model",
        usage={"total_tokens": 7},
    )

    response = client.get("/api/admin/brand-management/enrich/job-1")

    assert response.status_code == 409
    body = response.get_json()
    assert body["success"] is False
    assert body["error"] == "ambiguous_brand"
    assert [choice["name"] for choice in body["choices"]] == ["Lancome", "Lancome Paris"]


def test_brand_enrich_job_poll_reports_llm_error_as_json(monkeypatch, client):
    login(monkeypatch)
    with app_mod._brand_enrich_jobs_lock:
        app_mod._brand_enrich_jobs.clear()
    app_mod._set_brand_enrich_job(
        "job-failed",
        status="failed",
        error="llm_schema_invalid",
        message="LLM JSON must contain a brands array",
        http_status=503,
    )

    response = client.get("/api/admin/brand-management/enrich/job-failed")

    assert response.status_code == 503
    body = response.get_json()
    assert body["success"] is False
    assert body["error"] == "llm_schema_invalid"
    assert body["message"] == "LLM JSON must contain a brands array"


def test_brand_enrich_background_job_completes_and_audits(monkeypatch, client):
    login(monkeypatch)
    conn = fake_db(monkeypatch)
    with app_mod._brand_enrich_jobs_lock:
        app_mod._brand_enrich_jobs.clear()

    class FakeService:
        def __init__(self, *args, **kwargs):
            pass

        def enrich_brand_by_name(self, *, name):
            return brand_management.BrandGenerationResult(
                items=[brand_management.normalize_brand_draft({"name": name, "industry": "Beauty"})],
                model="fake-model",
                prompt="enrich-prompt",
                usage={"total_tokens": 7},
            )

    monkeypatch.setattr(app_mod, "BrandManagementService", FakeService)

    app_mod._run_brand_enrich_job(
        "job-complete",
        admin_id="admin-1",
        name="Lancome",
        payload={},
    )

    response = client.get("/api/admin/brand-management/enrich/job-complete")

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["pending"] is False
    assert body["draft"]["name"] == "Lancome"
    assert body["model"] == "fake-model"
    assert conn.commits == 1
    statements = "\n".join(sql for sql, _params in conn.statements)
    assert "INSERT INTO admin_audit_log" in statements


def test_brand_delete_endpoint_archives_brand(monkeypatch, client):
    login(monkeypatch)
    conn = fake_db(monkeypatch)
    monkeypatch.setattr(app_mod, "_table_exists", lambda cur, name: name in {"brands", "kg_brands"})
    monkeypatch.setattr(app_mod, "_table_columns", lambda cur, name: ["id", "name", "status"])
    conn.script("SELECT id FROM brands WHERE id =", [{"id": 42}])

    response = client.delete("/api/admin/brand-management/42")
    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["status"] == "archived"
    statements = "\n".join(sql for sql, _params in conn.statements)
    assert "UPDATE brands SET status = 'archived'" in statements
    assert "UPDATE kg_brands SET status = 'archived'" in statements


def test_product_discovery_endpoint_reports_llm_failure(monkeypatch, client):
    login(monkeypatch)
    conn = fake_db(monkeypatch)

    def table_columns(_cur, name):
        if name == "brands":
            return ["id", "name", "industry", "target_market", "description", "aliases"]
        return []

    monkeypatch.setattr(app_mod, "_table_columns", table_columns)
    monkeypatch.setattr(
        app_mod,
        "_discover_brand_products_llm",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            app_mod.TopicPlanLLMError("llm_call_failed", "LLM timeout")
        ),
    )
    conn.script(
        "FROM brands WHERE id =",
        [
            {
                "id": 5,
                "name": "NIKE",
                "industry": "Sportswear",
                "target_market": "global",
                "description": "",
                "aliases": [],
            }
        ],
    )
    conn.script("FROM products WHERE brand_id =", [])
    conn.script(
        "INSERT INTO products",
        [
            {
                "id": 1001,
                "brand_id": 5,
                "name": "Nike Air Force 1",
                "sku": "",
                "category": "Shoes",
                "description": "Iconic Nike lifestyle sneaker.",
                "aliases": ["AF1"],
                "status": "active",
                "created_at": None,
                "updated_at": None,
            }
        ],
    )

    response = client.post(
        "/api/admin/brands/5/products/discover",
        data=json.dumps({"query": "热门鞋款", "limit": 1}),
        content_type="application/json",
    )

    assert response.status_code == 503
    body = response.get_json()
    assert body["success"] is False
    assert body["error"] == "llm_call_failed"
    assert body["message"] == "LLM timeout"
    assert conn.commits == 0
