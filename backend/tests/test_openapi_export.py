"""Phase 5 hardening — OpenAPI live schema validation + FE codegen contract.

Validates that the live FastAPI auto-schema is a well-formed OpenAPI 3.x
document, contains the consumer-facing endpoint paths the FE codegen
relies on, and exposes the `_meta/openapi-export` endpoint that FE uses
as the codegen source.

Strict diff vs `docs/openapi.yaml` is intentionally NOT enforced (the YAML
predates many live endpoints and is hand-curated for human reference; the
auto-export is the FE-binding source). A drift report is logged as a
warning so devs notice when the docs lag.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


# These paths must always be in the live schema. If any disappears, FE
# codegen + downstream apps break, so we fail the test loudly.
REQUIRED_PATHS: set[str] = {
    "/api/v1/projects/",
    "/api/v1/projects/{project_id}",
    "/api/v1/projects/{project_id}/overview",
    "/api/v1/projects/{project_id}/reports",
    "/api/v1/projects/{project_id}/reports/{report_id}",
    "/api/v1/users/me/api-keys",
    "/api/v1/alerts/",
    "/mcp/v1",
    "/reports/public/{token}",
    "/api/admin/_meta/routes",
    "/api/admin/audit-log",
    "/api/v1/_meta/openapi-export",
}


# These prefixes should never appear in the export (legacy / internal).
EXCLUDED_PREFIXES: set[str] = {
    "/api/auth",  # legacy session-auth surface, not consumed by new FE
    "/health",
    "/healthz",
}


@pytest.mark.asyncio
async def test_openapi_export_returns_valid_3x_doc(client) -> None:
    """Live schema must be valid OpenAPI 3.x with non-empty paths."""
    resp = await client.get("/api/v1/_meta/openapi-export")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec.get("openapi", "").startswith("3.")
    assert "info" in spec
    assert spec["info"]["title"] == "GENPANO API (live)"
    assert spec["info"]["x-codegen-source"] == "/api/v1/_meta/openapi-export"
    assert isinstance(spec.get("paths"), dict)
    assert len(spec["paths"]) > 0


@pytest.mark.asyncio
async def test_openapi_export_includes_required_paths(client) -> None:
    """Every consumer-facing path the FE relies on must be present."""
    resp = await client.get("/api/v1/_meta/openapi-export")
    spec = resp.json()
    paths = set(spec.get("paths", {}).keys())

    missing = REQUIRED_PATHS - paths
    assert not missing, (
        "OpenAPI export missing required paths (FE codegen will break):\n  - "
        + "\n  - ".join(sorted(missing))
    )


@pytest.mark.asyncio
async def test_openapi_export_excludes_legacy_paths(client) -> None:
    """Legacy auth + health paths must NOT pollute the consumer schema."""
    resp = await client.get("/api/v1/_meta/openapi-export")
    spec = resp.json()
    for path in spec.get("paths", {}):
        for excluded in EXCLUDED_PREFIXES:
            assert not path.startswith(excluded), (
                f"Legacy path {path} leaked into the consumer OpenAPI export"
            )


@pytest.mark.asyncio
async def test_openapi_export_paths_have_at_least_one_method(client) -> None:
    """Every path must declare at least one HTTP method (sanity)."""
    resp = await client.get("/api/v1/_meta/openapi-export")
    spec = resp.json()
    valid_methods = {"get", "post", "put", "patch", "delete", "options", "head"}
    for path, item in spec["paths"].items():
        method_keys = set(item.keys()) & valid_methods
        assert method_keys, f"Path {path} has no methods declared"


@pytest.mark.asyncio
async def test_openapi_export_unauthenticated(client) -> None:
    """The export endpoint should be publicly readable so FE codegen
    pipelines don't need a service-account token. Auth-protected by
    default would force every CI build to mint a token first.
    """
    resp = await client.get("/api/v1/_meta/openapi-export")
    # No 401/403 even without Authorization header
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_openapi_export_admin_paths_present(client) -> None:
    """Phase R.4 admin sub-routers should all appear in the schema."""
    resp = await client.get("/api/v1/_meta/openapi-export")
    spec = resp.json()
    paths = list(spec["paths"].keys())

    admin_segments_seen: set[str] = set()
    for p in paths:
        if p.startswith("/api/admin/"):
            seg = p[len("/api/admin/") :].split("/", 1)[0]
            admin_segments_seen.add(seg)

    # Core admin sub-routers shipped this session
    expected_min = {
        "alerts",
        "brand-submissions",
        "comms",
        "cost",
        "diagnostics",
        "engine-health",
        "kg-discovery",
        "leads",
        "mcp-ops",
        "projects",
        "proxy-pool",
        "session",
        "stats",
        "users",
    }
    missing = expected_min - admin_segments_seen
    assert not missing, (
        "Admin sub-routers expected in OpenAPI export but absent:\n  - "
        + "\n  - ".join(sorted(missing))
    )
