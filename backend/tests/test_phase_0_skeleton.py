"""Phase 0 — verify product API skeleton wired correctly."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoints() -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/healthz").status_code == 200


def test_meta_routes_lists_v1_routes() -> None:
    """/api/v1/_meta/routes lists at least the 12 sub-routers + auth."""
    resp = client.get("/api/v1/_meta/routes")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "count" in data
    paths = {item["path"] for item in data["items"]}
    # All product API paths should be registered
    expected_path_substrings = [
        "/api/v1/projects",
        "/api/v1/brands",
        "/api/v1/industries",
        "/api/v1/projects/{project_id}/topics",
        "/api/v1/projects/{project_id}/citations",
        "/api/v1/projects/{project_id}/products",
        "/api/v1/projects/{project_id}/competitors",
        "/api/v1/projects/{project_id}/reports",
        "/api/v1/projects/{project_id}/diagnostics",
        "/api/v1/leads",
        "/api/v1/projects/{project_id}/crawl-requests",
    ]
    for sub in expected_path_substrings:
        assert any(sub in p for p in paths), f"missing route prefix: {sub}"


def test_phase_0_stub_returns_501() -> None:
    """A still-stubbed Phase 0 endpoint returns 501 + phase_0_stub body.

    `/v1/projects/` was wired in Phase 1; pick a still-stubbed one:
    `/v1/brands/` (Phase 1 doesn't implement brand search).
    """
    resp = client.get("/api/v1/brands/")
    assert resp.status_code == 501
    body = resp.json()
    assert body.get("state") == "phase_0_stub"


def test_v1_meta_route_count_at_least_phase_0() -> None:
    """At least 13 routes (12 stubs + 1 _meta itself)."""
    resp = client.get("/api/v1/_meta/routes")
    data = resp.json()
    # At Phase 0, we have 12 stubs (each 1 GET /) + auth (~14 endpoints) +
    # _meta (1) + health (3). Sanity bound: 13+.
    assert data["count"] >= 13
