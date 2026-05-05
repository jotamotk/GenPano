"""Phase M router: /v1/users/me/api-keys + /mcp/v1 JSON-RPC endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, status
from genpano_models import User
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.api_keys._dto import (
    ApiKeyCreated,
    ApiKeyIn,
    ApiKeyListOut,
    ApiKeyOut,
    JsonRpcRequest,
    JsonRpcResponse,
    UsageStatsOut,
)
from app.api.v1.api_keys.service import (
    authenticate_mcp_token,
    create_key,
    dispatch_mcp_request,
    get_usage_stats,
    list_user_keys,
    revoke_key,
)
from app.core.errors import mcp_auth_required
from app.core.security import _DependsDb, current_user

router = APIRouter(tags=["API Keys"])


@router.get("/api-keys", response_model=ApiKeyListOut)
async def list_my_keys(
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> ApiKeyListOut:
    rows = await list_user_keys(session, user=user)
    items = [ApiKeyOut.model_validate(r) for r in rows]
    return ApiKeyListOut(items=items, total=len(items))


@router.post(
    "/api-keys",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_my_key(
    payload: ApiKeyIn,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> ApiKeyCreated:
    """Generate a new API key. Plaintext is returned **only once**."""
    key, secret = await create_key(
        session,
        user=user,
        name=payload.name,
        rate_limit_per_minute=payload.rate_limit_per_minute,
        expires_at=payload.expires_at,
        scope=payload.scope,
    )
    return ApiKeyCreated(
        id=key.id,
        prefix=key.prefix,
        secret=secret,
        name=key.name,
        rate_limit_per_minute=key.rate_limit_per_minute,
        created_at=key.created_at,
        expires_at=key.expires_at,
    )


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_my_key(
    key_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> None:
    await revoke_key(session, user=user, key_id=key_id)


@router.get("/api-keys/{key_id}/usage", response_model=UsageStatsOut)
async def usage_stats(
    key_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> UsageStatsOut:
    return UsageStatsOut(**(await get_usage_stats(session, user=user, key_id=key_id)))


# ── MCP JSON-RPC ─────────────────────────────────────────────────


mcp_router = APIRouter(tags=["MCP"])


@mcp_router.post("/v1", response_model=JsonRpcResponse)
async def mcp_jsonrpc(
    payload: JsonRpcRequest,
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = _DependsDb,
) -> JsonRpcResponse:
    """JSON-RPC entrypoint. Auth: Bearer gp_sk_xxx (PRD §4.5.2.1, ADR-006).

    Every successful auth records an `mcp_call_log` row (Phase O.2.3
    observability). Auth failures are NOT logged here — they raise
    `mcp_auth_required` before we have a session+key context.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise mcp_auth_required("missing Bearer token")
    token = authorization[len("bearer ") :].strip()
    key = await authenticate_mcp_token(session, token=token)
    if key is None:
        raise mcp_auth_required("invalid or revoked token")

    # Resolve the principal user for tool dispatch (multi-tenant enforcement)
    from genpano_models import User as UserModel
    from sqlalchemy import select as _select

    user_row = (
        await session.execute(_select(UserModel).where(UserModel.id == key.user_id))
    ).scalar_one_or_none()

    # Pull tool name from JSON-RPC params for observability — only present
    # for tools/call. Other methods (initialize / tools/list / resources/list)
    # log with tool=None.
    tool_name: str | None = None
    if payload.method == "tools/call" and isinstance(payload.params, dict):
        tool_name = payload.params.get("name")

    from app.api.v1.api_keys.call_log import measure_mcp_call

    async with measure_mcp_call(
        session,
        api_key_id=key.id,
        user_id=key.user_id,
        method=payload.method,
        tool=tool_name,
    ) as ctx:
        result = await dispatch_mcp_request(
            payload.method, payload.params, session=session, user=user_row
        )
        # If dispatch returned a JSON-RPC error envelope, record the code
        if "error" in result and isinstance(result["error"], dict):
            ctx["error_code"] = result["error"].get("message") or "rpc_error"

    if "error" in result:
        return JsonRpcResponse(id=payload.id, error=result["error"])
    return JsonRpcResponse(id=payload.id, result=result)
