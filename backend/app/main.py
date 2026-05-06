"""FastAPI application factory + router registration.

Phase 0: 12 product API sub-routers registered at /api/v1/* alongside existing
auth router. All product endpoints currently return 501 stub; Phase 1+ fills
them in.
"""

import logging
import os
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

from app.api.admin import router as admin_router
from app.api.admin.auth import router as admin_auth_router
from app.api.v1._meta.router import router as meta_router
from app.api.v1.alerts.router import prefs_router as notifications_router
from app.api.v1.alerts.router import router as alerts_router
from app.api.v1.api_keys.router import mcp_router
from app.api.v1.api_keys.router import router as api_keys_router
from app.api.v1.auth import router as user_auth_router
from app.api.v1.brands.router import router as brands_router
from app.api.v1.citations.router import router as citations_router
from app.api.v1.competitors.router import router as competitors_router
from app.api.v1.crawl.router import router as crawl_router
from app.api.v1.diagnostics.router import router as diagnostics_router
from app.api.v1.exports.router import router as exports_router
from app.api.v1.exports.router import submission_router as brand_submissions_router
from app.api.v1.industries.router import router as industries_router
from app.api.v1.leads.router import router as leads_router
from app.api.v1.products.router import router as products_router
from app.api.v1.projects.router import router as projects_router
from app.api.v1.reports.router import public_router as reports_public_router
from app.api.v1.reports.router import router as reports_router
from app.api.v1.topics.router import router as topics_router
from app.core.rate_limit import setup_rate_limit
from app.core.request_id import (
    REQUEST_ID_HEADER,
    RequestIDMiddleware,
    current_request_id,
    install_logging_filter,
)
from app.db.session import get_db

logger = logging.getLogger("app")
install_logging_filter()

app = FastAPI(
    title="GenPano API",
    version="0.1.0",
    description="GenPano App backend — Phase 0 skeleton (12 sub-routers + auth)",
)

# Phase 5 hardening — CORS + rate limit
_default_origins = "http://localhost:5173,http://localhost:3000"
_origins = [
    o.strip()
    for o in os.environ.get("GENPANO_CORS_ORIGINS", _default_origins).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept-Language"],
    expose_headers=["X-Request-ID"],
    max_age=3600,
)
app.add_middleware(RequestIDMiddleware)
setup_rate_limit(app)

# Cookie-based session for admin operator auth (Phase 2 of admin → backend
# consolidation). The same secret protects every signed cookie this app sets.
# Falls back to USER_JWT_SECRET (already required to be ≥32 bytes) so a
# minimum-config dev setup needs no extra env var.
_session_secret = (
    os.environ.get("ADMIN_SESSION_SECRET")
    or os.environ.get("USER_JWT_SECRET")
    or "dev-session-secret-change-in-production-32-bytes-minimum"
)


def _admin_cookie_secure() -> bool:
    """Whether the admin session cookie should carry the ``Secure`` flag.

    Reads ``ADMIN_COOKIE_SECURE`` first (explicit, accepts ``1/0/true/false``).
    If unset, falls back to ``GENPANO_ENVIRONMENT == "production"`` for
    backwards compatibility with the original Phase 2 wiring.

    Why this lives in its own function: the original code gated ``Secure``
    purely on ``GENPANO_ENVIRONMENT="production"``. On a HTTP-only deploy
    that still flagged itself ``production`` (e.g. an internal IP behind
    nginx without TLS), every Set-Cookie carried ``Secure`` and the browser
    silently dropped it — so login appeared to succeed but the cookie was
    never stored, every subsequent admin request 401-ed with
    ``admin_session_required``, and previous hotfixes (#347 / #353 / #355)
    looked at the wrong layer of the stack. Splitting the flag out lets a
    HTTP deploy set ``ADMIN_COOKIE_SECURE=0`` without touching
    ``GENPANO_ENVIRONMENT`` (which other code paths may key off), and lets
    a HTTPS deploy that *doesn't* set ``GENPANO_ENVIRONMENT=production``
    still mark the cookie ``Secure`` via ``ADMIN_COOKIE_SECURE=1``.
    """
    explicit = os.environ.get("ADMIN_COOKIE_SECURE")
    if explicit is not None:
        return explicit.strip().lower() in ("1", "true", "yes", "on")
    return os.environ.get("GENPANO_ENVIRONMENT") == "production"


_ADMIN_COOKIE_SECURE = _admin_cookie_secure()

app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret,
    session_cookie="genpano_admin_session",
    # ci_check.py rule D10 enforces SameSite=Strict for every auth cookie;
    # in production both admin.html (Flask, port 5000) and the FastAPI auth
    # endpoints sit behind the same nginx origin, so Strict does not block
    # the cross-service cookie bridge.
    same_site="strict",
    https_only=_ADMIN_COOKIE_SECURE,
    max_age=60 * 60 * 24 * 7,  # 7 days
)

# Auth router is self-prefixed with /api/auth (legacy)
app.include_router(user_auth_router)

# Phase 0 product API routers — mounted under /api/v1/...
V1_PREFIX = "/api/v1"
app.include_router(projects_router, prefix=f"{V1_PREFIX}/projects")
app.include_router(brands_router, prefix=f"{V1_PREFIX}/brands")
app.include_router(industries_router, prefix=f"{V1_PREFIX}/industries")
app.include_router(topics_router, prefix=f"{V1_PREFIX}/projects/{{project_id}}/topics")
app.include_router(citations_router, prefix=f"{V1_PREFIX}/projects/{{project_id}}/citations")
app.include_router(products_router, prefix=f"{V1_PREFIX}/projects/{{project_id}}/products")
app.include_router(competitors_router, prefix=f"{V1_PREFIX}/projects/{{project_id}}/competitors")
app.include_router(reports_router, prefix=f"{V1_PREFIX}/projects")
app.include_router(diagnostics_router, prefix=f"{V1_PREFIX}/projects/{{project_id}}/diagnostics")
app.include_router(leads_router, prefix=f"{V1_PREFIX}/leads")
app.include_router(crawl_router, prefix=f"{V1_PREFIX}/projects")
app.include_router(exports_router, prefix=f"{V1_PREFIX}/projects")
app.include_router(brand_submissions_router, prefix=f"{V1_PREFIX}/brands")
app.include_router(alerts_router, prefix=f"{V1_PREFIX}/alerts")
app.include_router(notifications_router, prefix=f"{V1_PREFIX}/users/me")
app.include_router(api_keys_router, prefix=f"{V1_PREFIX}/users/me")
app.include_router(mcp_router, prefix="/mcp")
app.include_router(meta_router, prefix=V1_PREFIX)
app.include_router(reports_public_router, prefix="/reports/public")
app.include_router(admin_router, prefix="/api/admin")
app.include_router(admin_auth_router, prefix="/api/admin/auth")

# Legacy alias for the Query Pool sub-router. admin_console served the
# same Query Pool endpoints both at /api/admin/query-pool/* and at the
# longer /admin/api/v1/pipeline/query-pool/* path; the SPA still calls
# the latter from a few places (cursor lists, etc.). Mount the same
# FastAPI router at the alias prefix so we don't break those callers
# during the Phase 5 migration. The alias goes away in Phase X when
# admin.html JS is fully cleaned up.
from app.api.admin.query_pool import router as _query_pool_router  # noqa: E402

app.include_router(_query_pool_router, prefix="/admin/api/v1/pipeline/query-pool")

# Legacy alias for the Segments router. admin_console served Segments at
# the un-prefixed /api/segments/* path; admin.html still calls the same.
# Phase 6 slice 6a mounts the canonical FastAPI router at /api/admin/segments
# and re-mounts it at /api/segments to keep the SPA working until the JS
# is updated and admin_console is fully retired (Phase X).
from app.api.admin.segments import router as _segments_router  # noqa: E402

app.include_router(_segments_router, prefix="/api/segments")

# Legacy alias for the Accounts router (Phase 7 slice 7b — HIGHEST
# sensitivity). admin_console served these at /api/accounts/* WITHOUT
# admin auth; the FastAPI port keeps the same path AND adds
# Depends(current_admin) on every handler. The cookie bridge gives us
# the operator session, so admin.html keeps working unchanged while
# direct curl calls now correctly 401.
from app.api.admin.accounts import router as _accounts_router  # noqa: E402

app.include_router(_accounts_router, prefix="/api/accounts")

# Legacy alias for the Scheduler routes (Phase 8 slice 8c). admin.html
# uses ``/api/scheduler/*`` directly. The router file's paths are
# ``/scheduler/...`` so mounting at the empty prefix here gives us the
# legacy paths; the same router is also included under
# ``/api/admin`` (via app/api/admin/router.py) for the canonical mount.
from app.api.admin.scheduler import router as _scheduler_router  # noqa: E402

app.include_router(_scheduler_router, prefix="/api")

# Topics + Prompts read-only pickers (Phase 8 slice 8d). admin_console
# served /api/topics and /api/prompts without auth; the FastAPI port adds
# Depends(current_admin) (security hardening). admin.html's attempt
# tracker dropdowns hit these directly.
from app.api.picker import router as _picker_router  # noqa: E402

app.include_router(_picker_router, prefix="/api")

# Queries + stats read-only routes (Phase 9 slice 9a). admin_console
# served /api/stats and /api/queries without auth; FastAPI port adds
# Depends(current_admin). Write paths come in slice 9b.
from app.api.queries import router as _queries_router  # noqa: E402

app.include_router(_queries_router, prefix="/api")

# Analyzer routes (Phase 9 slice 9c). admin_console served
# /api/analyzer/* without auth; FastAPI port adds Depends(current_admin).
from app.api.analyzer import router as _analyzer_router  # noqa: E402

app.include_router(_analyzer_router, prefix="/api")

# Legacy profile routes (Phase 9 slice 9d). geo_tracker-flavor profiles
# table CRUD + lite picker + similar suggestions. admin_console served
# without auth; FastAPI port adds Depends(current_admin).
from app.api.profiles_legacy import router as _profiles_legacy_router  # noqa: E402

app.include_router(_profiles_legacy_router, prefix="/api")

# Misc legacy routes (Phase 9 slice 9f) — sms_register / task_status /
# html_files / html / screenshot / backfill_citations / queries/by-day.
from app.api.misc import router as _misc_router  # noqa: E402

app.include_router(_misc_router, prefix="/api")


# Self-heal handler for un-decryptable admin session cookies.
# See current_admin in app/api/admin/auth/router.py for the producer side.
# Why this isn't done by SessionMiddleware: Starlette's middleware silently
# swallows BadSignature into an empty session and treats it as anonymous,
# but never emits Set-Cookie to clear the bad cookie. So after
# ADMIN_SESSION_SECRET rotates (e.g. the env_file: .env hotfix in #347)
# every browser holding an old cookie 401s forever. This handler turns
# that ratchet off by emitting Max-Age=0 on the 401 response when
# current_admin tagged the request.
@app.exception_handler(HTTPException)
async def _admin_session_clear_on_bad_cookie(request: Request, exc: HTTPException) -> JSONResponse:
    response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    if getattr(request.state, "clear_admin_session_cookie", False):
        response.delete_cookie(
            "genpano_admin_session",
            path="/",
            samesite="strict",
            httponly=True,
            # Must match the SessionMiddleware ``Secure`` flag — otherwise
            # browsers will refuse to clear a Secure cookie via a non-Secure
            # Set-Cookie response, leaving the un-decryptable cookie in place.
            secure=_ADMIN_COOKIE_SECURE,
        )
    return response


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log full stack with request_id; return safe internal_error body.

    HTTPException continues to use the handler above (default
    ``{"detail": ...}`` envelope, plus the bad-cookie self-heal). This
    catch-all kicks in only for *unhandled* exceptions and must never leak
    the traceback to the client. ``app.core.errors._problem(...)`` already
    embeds ``request_id`` into structured detail dicts via the contextvar,
    so HTTPException bodies stay correlated; here we synthesise the same
    shape for the 500 path.
    """
    logger.exception("unhandled exception on %s %s", request.method, request.url.path)
    rid = current_request_id() or ""
    body = {
        "detail": {
            "type": "about:blank",
            "title": "Internal server error",
            "status": 500,
            "code": "internal_error",
            "request_id": rid,
            "instance": request.url.path,
        }
    }
    return JSONResponse(status_code=500, content=body, headers={REQUEST_ID_HEADER: rid})


DbSession = Annotated[AsyncSession, Depends(get_db)]


@app.get("/health")
@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/healthz/db")
async def healthz_db(response: Response, session: DbSession) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "db": exc.__class__.__name__}
    return {"status": "ok", "db": "ok"}


# ─── Admin SPA shell (Phase X-2) ─────────────────────────────────────
# Phase X-2 deletes the admin_console Flask service. The 17k-line admin.html
# now lives at backend/static/admin.html and is served directly by FastAPI.
# nginx routes /admin and /admin/<path> here.
import pathlib  # noqa: E402

from fastapi.responses import FileResponse  # noqa: E402

_ADMIN_HTML_PATH = pathlib.Path(__file__).resolve().parent.parent / "static" / "admin.html"


@app.get("/admin", include_in_schema=False)
@app.get("/admin/", include_in_schema=False)
async def serve_admin_root() -> FileResponse:
    """Serve the admin SPA shell. admin.html is a single-page app — its
    own client-side router handles every sub-path under /admin."""
    return FileResponse(_ADMIN_HTML_PATH, media_type="text/html; charset=utf-8")


@app.get("/admin/{path:path}", include_in_schema=False)
async def serve_admin_subpath(path: str) -> FileResponse:
    """Same SPA shell for any /admin/<path>. Real admin SPA routing is
    client-side via JavaScript — the server just returns the same HTML
    for every URL under the prefix."""
    return FileResponse(_ADMIN_HTML_PATH, media_type="text/html; charset=utf-8")
