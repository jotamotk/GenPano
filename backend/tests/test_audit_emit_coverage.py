"""Phase O.2 — CI gate: every admin write route must call ``emit_audit``.

Per ADR-014, all mutating endpoints under ``/api/admin/*`` are required to
record an entry in ``admin_audit_log`` so operator actions are traceable.

This test walks the live FastAPI app, filters to admin write routes
(POST/PUT/PATCH/DELETE), reads each handler's source code, and asserts
``emit_audit`` is invoked. It runs in CI on every PR — the moment a new
admin mutation lands without audit emit, the gate fires.

Exempt paths (read-only mutations or scaffolding hooks that legitimately
do not emit audit) live in ``EXEMPT_PATHS`` below — keep the list narrow
and require justification in PR description before adding entries.
"""

from __future__ import annotations

import inspect

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.main import app as _app

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Paths exempt from emit_audit requirement. Each entry must be justified.
# Add only when migrating an admin route that legitimately cannot or should
# not call emit_audit (e.g., session login). Keep the list narrow.
EXEMPT_PATHS: dict[str, str] = {
    # Login + logout audit themselves through admin_login_attempts (every
    # probe, success or failure). Calling emit_audit() would either fail
    # (no operator yet on a failed login) or duplicate the trail. The
    # existing audit-log dashboard already surfaces login_attempts.
    "/api/admin/auth/login": "writes admin_login_attempts directly (login probe)",
    "/api/admin/auth/logout": "session clear has no security-relevant state to log",
}


def _list_admin_write_routes(app: FastAPI) -> list[APIRoute]:
    out: list[APIRoute] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/api/admin"):
            continue
        if not (route.methods & WRITE_METHODS):
            continue
        out.append(route)
    return out


def test_admin_write_routes_call_emit_audit() -> None:
    """Every admin write route's handler source must contain ``emit_audit``."""
    app = _app
    routes = _list_admin_write_routes(app)
    assert routes, "no admin write routes found — Phase R.4 scaffold regressed?"

    failures: list[str] = []
    for route in routes:
        if route.path in EXEMPT_PATHS:
            continue
        handler = route.endpoint
        try:
            src = inspect.getsource(handler)
        except (OSError, TypeError) as exc:  # pragma: no cover
            failures.append(f"{route.path}: cannot read source ({exc})")
            continue
        if "emit_audit" not in src:
            methods = sorted(route.methods & WRITE_METHODS)
            failures.append(
                f"{methods} {route.path} ({handler.__qualname__}): "
                "handler does not call emit_audit() — required by ADR-014"
            )

    if failures:
        pytest.fail("ADR-014 audit emit coverage gate failed:\n  - " + "\n  - ".join(failures))


def test_exempt_paths_are_real_routes() -> None:
    """EXEMPT_PATHS entries must correspond to actual registered routes.

    This prevents stale exemptions from masking new violations as routes
    rename or disappear.
    """
    app = _app
    all_admin = {
        r.path for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/api/admin")
    }
    for path in EXEMPT_PATHS:
        assert path in all_admin, (
            f"EXEMPT_PATHS contains '{path}' but no such route is registered — "
            "remove it or fix the typo"
        )


def test_demo_mutation_is_covered() -> None:
    """Sanity: the Phase R.4 demo mutation calls emit_audit (positive baseline).

    If this fails, the test infrastructure is broken — the production gate
    would also be unreliable.
    """
    app = _app
    routes = _list_admin_write_routes(app)
    demo = [r for r in routes if r.path == "/api/admin/_demo/test-mutation"]
    assert len(demo) == 1
    src = inspect.getsource(demo[0].endpoint)
    assert "emit_audit" in src
