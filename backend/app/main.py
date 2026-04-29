from typing import Annotated

from fastapi import Depends, FastAPI, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.api.v1.auth import router as admin_auth_router
from app.api.v1.auth import router as user_auth_router
from app.db.session import get_db

app = FastAPI()
app.include_router(admin_auth_router)
app.include_router(user_auth_router)

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
