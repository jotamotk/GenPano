"""Auth dependencies for product API endpoints.

Per ADR-005 / Phase P §4.7.3 / multi-tenant contract:

- `current_user` — resolves Bearer JWT or API key principal to a `User`.
- `current_project(project_id)` — resolves project + verifies ownership;
  cross-tenant deny is **404** (not 403, to avoid leaking existence info).

Phase 0 ships stubs that delegate to existing user_auth.jwt for JWT path; API
key path returns 501 (Phase M will implement). `current_project` is a real
dependency factory that issues a 404 on miss / cross-tenant.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Header
from genpano_models import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import not_found, unauthorized
from app.db.session import get_db
from app.user_auth.jwt import UserJwtInvalidError, verify_user_access_token

_DependsDb = Depends(get_db)


async def current_user(
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = _DependsDb,
) -> User:
    """Dependency: extract Bearer token → verify → load User.

    Phase M will extend this to also accept Bearer API keys (`gp_sk_*`) by
    branching on prefix. Until then, only JWT-based session tokens are
    accepted.

    Raises 401 with `code=unauthorized` if missing/invalid.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise unauthorized("missing Bearer token")
    token = authorization[len("bearer ") :].strip()
    if not token:
        raise unauthorized("empty Bearer token")

    # MCP API key path (Phase M) — placeholder branching:
    # if token.startswith("gp_sk_"):
    #     return await _resolve_api_key_principal(token, session)

    try:
        user_id = verify_user_access_token(token)
    except UserJwtInvalidError as exc:
        raise unauthorized(str(exc)) from exc

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise unauthorized("user not found")
    return user


def current_project(
    project_id_param: str = "project_id",
) -> Callable[..., Coroutine[Any, Any, dict[str, str]]]:
    """Dependency factory: resolve project_id path param → verify user owns it.

    Cross-tenant or missing → 404 (not 403, per multi-tenant deny contract).

    Usage:

        @router.get("/v1/projects/{project_id}/overview")
        async def get_overview(
            project = Depends(current_project()),
        ):
            ...

    Phase 0 ships a stub that just verifies user is authenticated and the
    project_id path param is present. Phase 1 wires it to real `projects`
    table once the table exists. After Phase M, `org_id` membership replaces
    `user_id` ownership check (ADR-005).
    """

    async def _dep(
        project_id: str,
        user: Annotated[User, Depends(current_user)],
        session: Annotated[AsyncSession, Depends(get_db)],
    ) -> dict[str, str]:
        # Phase 0 stub — Phase 1 replaces with real Project ORM lookup.
        # The contract is established now so service layer can rely on it.
        if not project_id:
            raise not_found()
        # TODO Phase 1: from genpano_models import Project; verify project.user_id == user.id
        return {"id": project_id, "user_id": user.id}

    return _dep
