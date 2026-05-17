"""Queries + stats API package — Phase 9 slice 9a (read-only)."""

from app.api.queries.retry_via_vm import router as _retry_via_vm_router
from app.api.queries.router import router

# Refs Epic #1110 / Issue #1144: include the quick "Retry via VM" admin
# endpoint on the same router so it picks up both ``/api/*`` and
# ``/admin/api/*`` mounts wired in app/main.py without changing main.py
# or modifying the existing ``POST /api/queries/{id}/retry`` handler.
router.include_router(_retry_via_vm_router)

__all__ = ["router"]
