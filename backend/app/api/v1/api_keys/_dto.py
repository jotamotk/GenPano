"""DTOs for /v1/users/me/api-keys + /mcp/v1 (Phase M)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiKeyIn(BaseModel):
    name: str | None = Field(None, max_length=64)
    rate_limit_per_minute: int = Field(60, ge=1, le=600)
    expires_at: datetime | None = None
    scope: dict[str, Any] | None = None


class ApiKeyCreated(BaseModel):
    """First-time response includes the cleartext token (shown ONCE)."""

    id: str
    prefix: str
    secret: str  # only returned at creation
    name: str | None
    rate_limit_per_minute: int
    created_at: datetime
    expires_at: datetime | None


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str | None
    prefix: str
    scope: dict[str, Any] | None
    rate_limit_per_minute: int
    usage_count: int
    last_used_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    revoked_at: datetime | None


class ApiKeyListOut(BaseModel):
    items: list[ApiKeyOut]
    total: int


class UsageStatsOut(BaseModel):
    api_key_id: str
    total_calls: int
    by_tool: list[dict[str, Any]]
    by_day: list[dict[str, Any]]


# ── MCP JSON-RPC ─────────────────────────────────────────────────


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] | None = None


class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
