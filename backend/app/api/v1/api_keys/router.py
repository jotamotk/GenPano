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
    """JSON-RPC entrypoint. Auth: Bearer gp_sk_xxx (PRD §4.5.2.1, ADR-006)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise mcp_auth_required("missing Bearer token")
    token = authorization[len("bearer ") :].strip()
    key = await authenticate_mcp_token(session, token=token)
    if key is None:
        raise mcp_auth_required("invalid or revoked token")

    result = await dispatch_mcp_request(payload.method, payload.params)
    if "error" in result:
        return JsonRpcResponse(id=payload.id, error=result["error"])
    return JsonRpcResponse(id=payload.id, result=result)
