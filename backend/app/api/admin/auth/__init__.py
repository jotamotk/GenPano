"""Admin operator auth — login / logout / current-session.

Mounted at ``/api/admin/auth/*``. Uses Starlette ``SessionMiddleware`` cookie
sessions (signed, server-side stateless). Replaces the legacy
``admin_console`` Flask routes ``POST /api/admin/login``,
``POST /api/admin/logout``, ``GET /api/admin/session``.
"""

from app.api.admin.auth.router import router

__all__ = ["router"]
