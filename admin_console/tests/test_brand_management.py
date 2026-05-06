import json

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

    class FakeService:
        def __init__(self, *args, **kwargs):
            pass

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
