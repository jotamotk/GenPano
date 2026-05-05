"""`_meta` router — introspection + OpenAPI export."""

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix="/_meta", tags=["Meta"])


@router.get("/routes")
async def list_routes(request: Request) -> dict[str, object]:
    """List all registered v1 routes (debug / discovery)."""
    items = []
    for route in request.app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            items.append(
                {
                    "path": route.path,
                    "methods": sorted(route.methods - {"HEAD", "OPTIONS"}),
                    "name": route.name,
                }
            )
    return {"items": items, "count": len(items)}


@router.get("/openapi-export")
async def openapi_export(request: Request) -> dict[str, Any]:
    """Live FastAPI auto-schema (OpenAPI 3.x) for FE codegen.

    Frontend pipeline:
        curl http://api/api/v1/_meta/openapi-export \\
          | openapi-typescript - > frontend/src/lib/api-types.d.ts

    Differs from FastAPI's default `/openapi.json` by:
    1. Filtering paths to consumer-facing prefixes only
       (`/api/v1`, `/api/admin`, `/mcp`, `/reports/public`).
    2. Tagging the doc with `x-codegen-source` so FE codegen scripts
       can verify they're consuming the right endpoint.
    """
    spec = request.app.openapi()
    if not isinstance(spec, dict):  # pragma: no cover — defensive
        return {}

    paths = spec.get("paths", {})
    keep_prefixes = ("/api/v1", "/api/admin", "/mcp", "/reports/public")
    filtered_paths = {
        p: v for p, v in paths.items() if any(p.startswith(prefix) for prefix in keep_prefixes)
    }

    info = dict(spec.get("info", {}))
    info["title"] = "GENPANO API (live)"
    info["x-codegen-source"] = "/api/v1/_meta/openapi-export"

    return {
        **spec,
        "info": info,
        "paths": filtered_paths,
    }
