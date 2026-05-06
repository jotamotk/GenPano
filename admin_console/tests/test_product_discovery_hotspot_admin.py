import json

import admin_console.app as app_mod


def login(monkeypatch):
    monkeypatch.setattr(
        app_mod,
        "_current_admin",
        lambda: {"id": "admin-1", "email": "admin@example.com", "role": "admin", "status": "active"},
    )


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

        if "information_schema.columns" in compact:
            self.rows = [
                {"column_name": name}
                for name in ("id", "name", "industry", "target_market", "description", "aliases")
            ]
        elif "FROM brands WHERE id = %s" in compact:
            brand = self.conn.brands.get(int(params[0]))
            self.rows = [dict(brand)] if brand else []
        elif "FROM products WHERE brand_id = %s" in compact:
            self.rows = [
                {"name": name, "sku": None, "category": None}
                for name in self.conn.existing_products.get(int(params[0]), [])
            ]
        elif "INSERT INTO products" in compact and "RETURNING" in compact:
            row = {
                "id": self.conn.next_product_id,
                "brand_id": params[0],
                "name": params[1],
                "sku": params[2],
                "category": params[3],
                "description": params[4],
                "aliases": json.loads(params[5]),
                "status": params[6],
                "created_at": None,
                "updated_at": None,
                "brand_name": self.conn.brands[int(params[0])]["name"],
                "topic_count": 0,
            }
            self.conn.next_product_id += 1
            self.conn.inserted_products.append(row)
            self.rows = [row]
        elif compact.startswith("UPDATE hot_topics SET status = %s"):
            self.conn.hotspot_updates.append(("status", params))
            self.rows = []
        elif compact.startswith("UPDATE hot_topics SET industry = %s"):
            self.conn.hotspot_updates.append(("industry", params))
            self.rows = []
        elif compact.startswith("UPDATE hot_topics SET brand_id = %s"):
            self.conn.hotspot_updates.append(("brand", params))
            self.rows = []
        elif compact.startswith("UPDATE prompts SET hotspot_id = NULL WHERE hotspot_id = ANY"):
            self.conn.unlinked_prompts = 4
            self.rows = []
        elif compact.startswith("DELETE FROM hot_topics WHERE id = ANY"):
            self.conn.deleted_hotspots = list(params[0])
            self.rows = []
        else:
            self.rows = []

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows

    @property
    def rowcount(self):
        if self.conn.deleted_hotspots:
            return len(self.conn.deleted_hotspots)
        if self.conn.hotspot_updates:
            return len(self.conn.hotspot_updates[-1][1][-1])
        return self.conn.unlinked_prompts


class FakeConnection:
    def __init__(self):
        self.brands = {
            7: {
                "id": 7,
                "name": "Acme Beauty",
                "industry": "beauty",
                "target_market": "sensitive skin",
                "description": "premium skincare",
                "aliases": ["Acme"],
            }
        }
        self.existing_products = {7: {"Barrier Serum"}}
        self.inserted_products = []
        self.hotspot_updates = []
        self.deleted_hotspots = []
        self.unlinked_prompts = 0
        self.next_product_id = 100
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


def test_product_discovery_endpoint_creates_new_llm_products(monkeypatch):
    app_mod.app.config.update(TESTING=True, SECRET_KEY="test-secret")
    client = app_mod.app.test_client()
    login(monkeypatch)
    conn = FakeConnection()
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)

    def fake_discover(brand, *, query, limit):
        assert brand["name"] == "Acme Beauty"
        assert brand["industry"] == "beauty"
        assert query == "hero products"
        assert limit == 3
        return [
            {"name": "Barrier Serum", "sku": "AC-BS", "category": "serum"},
            {"name": "Cloud Cream", "sku": "AC-CC", "category": "cream", "aliases": ["Cloud Repair"]},
        ], {"model": "fake-product-llm", "usage": {"total_tokens": 12}}

    monkeypatch.setattr(app_mod, "_discover_brand_products_llm", fake_discover)

    response = client.post(
        "/api/admin/brands/7/products/discover",
        json={"query": "hero products", "limit": 3},
    )

    body = response.get_json()
    assert response.status_code == 200
    assert body["success"] is True
    assert body["created_count"] == 1
    assert body["skipped_count"] == 1
    assert body["llm_model"] == "fake-product-llm"
    assert conn.inserted_products[0]["name"] == "Cloud Cream"
    assert conn.inserted_products[0]["aliases"] == ["Cloud Repair"]


def test_hotspot_batch_status_update(monkeypatch):
    app_mod.app.config.update(TESTING=True, SECRET_KEY="test-secret")
    client = app_mod.app.test_client()
    login(monkeypatch)
    conn = FakeConnection()
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)

    response = client.post("/api/admin/hot-topics/batch", json={"ids": [1, 2, 3], "action": "status", "status": "active"})

    body = response.get_json()
    assert response.status_code == 200
    assert body["success"] is True
    assert body["updated"] == 3
    assert conn.hotspot_updates == [("status", ("active", [1, 2, 3]))]


def test_hotspot_collect_uses_brand_industry_context(monkeypatch):
    app_mod.app.config.update(TESTING=True, SECRET_KEY="test-secret")
    client = app_mod.app.test_client()
    login(monkeypatch)
    conn = FakeConnection()
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)
    captured = {}

    def fake_run_collection_cycle(**kwargs):
        captured.update(kwargs)
        return {"collected": 2, "inserted": 2, "by_source": {"llm_search": 2}, "errors": {}}

    import admin_console.hotspot_collectors as hc

    monkeypatch.setattr(hc, "run_collection_cycle", fake_run_collection_cycle)

    response = client.post(
        "/api/admin/hot-topics/collect",
        json={"brand_id": 7, "sources": ["llm_search"]},
    )

    body = response.get_json()
    assert response.status_code == 200
    assert body["success"] is True
    assert captured["industry_filter"] == "beauty"
    assert captured["brand_context"]["id"] == 7
    assert captured["brand_context"]["name"] == "Acme Beauty"
