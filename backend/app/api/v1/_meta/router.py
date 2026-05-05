"""`_meta` router — introspection (Phase 0)."""

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
