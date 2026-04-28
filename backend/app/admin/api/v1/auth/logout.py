"""POST /admin/api/v1/auth/logout — revoke session + clear cookies.

Always returns 200 + clears both cookies, even if the inbound refresh
cookie is missing or already revoked. The 6-step logout contract from
decision #24 (PRD §4.1.1e) is driven from the frontend; this endpoint
only handles the server side.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.api.v1.auth._dto import OkResponse
from app.admin.auth.constants import REFRESH_TOKEN_COOKIE
from app.admin.auth.cookies import clear_auth_cookies
from app.admin.auth.refresh_token import hash_refresh_token
from app.admin.auth.session_repo import find_active_by_refresh_token, revoke_session
from app.db.session import get_db

router = APIRouter()


@router.post("/logout", response_model=OkResponse)
async def logout(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    refresh_cookie: Annotated[str | None, Cookie(alias=REFRESH_TOKEN_COOKIE)] = None,
) -> OkResponse:
    if refresh_cookie:
        digest = hash_refresh_token(refresh_cookie)
        row = await find_active_by_refresh_token(db, digest)
        if row is not None:
            await revoke_session(db, session_row=row)
            await db.commit()

    clear_auth_cookies(response)
    return OkResponse()
