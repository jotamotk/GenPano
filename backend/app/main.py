"""FastAPI application factory + router registration.

Phase 0: 12 product API sub-routers registered at /api/v1/* alongside existing
auth router. All product endpoints currently return 501 stub; Phase 1+ fills
them in.
"""

from typing import Annotated

from fastapi import Depends, FastAPI, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._meta.router import router as meta_router
from app.api.v1.auth import router as user_auth_router
from app.api.v1.brands.router import router as brands_router
from app.api.v1.citations.router import router as citations_router
from app.api.v1.competitors.router import router as competitors_router
from app.api.v1.crawl.router import router as crawl_router
from app.api.v1.diagnostics.router import router as diagnostics_router
from app.api.v1.industries.router import router as industries_router
from app.api.v1.leads.router import router as leads_router
from app.api.v1.products.router import router as products_router
from app.api.v1.projects.router import router as projects_router
from app.api.v1.reports.router import router as reports_router
from app.api.v1.topics.router import router as topics_router
from app.db.session import get_db

app = FastAPI(
    title="GenPano API",
    version="0.1.0",
    description="GenPano App backend — Phase 0 skeleton (12 sub-routers + auth)",
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
app.include_router(reports_router, prefix=f"{V1_PREFIX}/projects/{{project_id}}/reports")
app.include_router(diagnostics_router, prefix=f"{V1_PREFIX}/projects/{{project_id}}/diagnostics")
app.include_router(leads_router, prefix=f"{V1_PREFIX}/leads")
app.include_router(crawl_router, prefix=f"{V1_PREFIX}/projects/{{project_id}}/crawl-requests")
app.include_router(meta_router, prefix=V1_PREFIX)

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
