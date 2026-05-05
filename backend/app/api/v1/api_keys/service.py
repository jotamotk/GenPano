"""Phase M services: API keys + MCP request handling."""

from __future__ import annotations

import hashlib
import secrets
import string
import uuid
from datetime import UTC, datetime
from typing import Any

import bcrypt
from genpano_models import User, UserApiKey
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import not_found

KEY_PREFIX = "gp_sk_"
KEY_RANDOM_LEN = 32  # base62 chars after prefix


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _generate_secret() -> tuple[str, str, str]:
    """Generate (plaintext, prefix_for_display, bcrypt_hash)."""
    alphabet = string.ascii_letters + string.digits
    rand = "".join(secrets.choice(alphabet) for _ in range(KEY_RANDOM_LEN))
    plaintext = f"{KEY_PREFIX}{rand}"
    # Use first 12 chars after gp_sk_ as searchable prefix (display + lookup)
    prefix = plaintext[: len(KEY_PREFIX) + 6]  # gp_sk_XXXXXX
    hashed = bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt(rounds=12)).decode()
    return plaintext, prefix, hashed


def _sha_lookup(plaintext: str) -> str:
    """SHA-256 of token used for hint matching (NOT for auth — auth uses bcrypt verify)."""
    return hashlib.sha256(plaintext.encode()).hexdigest()


# ── CRUD ─────────────────────────────────────────────────────────


async def list_user_keys(session: AsyncSession, *, user: User) -> list[UserApiKey]:
    stmt = (
        select(UserApiKey)
        .where(and_(UserApiKey.user_id == user.id, UserApiKey.revoked_at.is_(None)))
        .order_by(UserApiKey.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def create_key(
    session: AsyncSession,
    *,
    user: User,
    name: str | None,
    rate_limit_per_minute: int,
    expires_at: datetime | None,
    scope: dict[str, Any] | None,
) -> tuple[UserApiKey, str]:
    plaintext, prefix, hashed = _generate_secret()
    key = UserApiKey(
        id=_new_id(),
        user_id=user.id,
        name=name,
        hash=hashed,
        prefix=prefix,
        scope=scope,
        rate_limit_per_minute=rate_limit_per_minute,
        expires_at=expires_at,
    )
    session.add(key)
    await session.commit()
    await session.refresh(key)
    return key, plaintext


async def revoke_key(session: AsyncSession, *, user: User, key_id: str) -> None:
    stmt = select(UserApiKey).where(and_(UserApiKey.id == key_id, UserApiKey.user_id == user.id))
    key = (await session.execute(stmt)).scalar_one_or_none()
    if key is None:
        raise not_found("api key not found")
    key.revoked_at = _now()
    await session.commit()


async def get_usage_stats(
    session: AsyncSession,
    *,
    user: User,
    key_id: str,
) -> dict[str, Any]:
    """Phase M stub — Phase O.2.3 wires real `mcp_call_log` aggregation."""
    stmt = select(UserApiKey).where(and_(UserApiKey.id == key_id, UserApiKey.user_id == user.id))
    key = (await session.execute(stmt)).scalar_one_or_none()
    if key is None:
        raise not_found("api key not found")
    return {
        "api_key_id": key_id,
        "total_calls": key.usage_count,
        "by_tool": [],
        "by_day": [],
    }


# ── MCP JSON-RPC dispatcher ──────────────────────────────────────


MCP_TOOLS = [
    "genpano_get_brand_visibility",
    "genpano_compare_brands",
    "genpano_get_industry_trends",
    "genpano_get_product_ranking",
    "genpano_generate_report",
    "genpano_get_optimization_insights",
    "genpano_get_citations",
    "genpano_list_pr_targets",
    "genpano_simulate_authority_boost",
]
MCP_RESOURCES = [
    "genpano://projects/{id}/dashboard",
    "genpano://brands/{id}/report",
    "genpano://industry/{name}/benchmark",
]


async def authenticate_mcp_token(session: AsyncSession, *, token: str) -> UserApiKey:
    """Verify Bearer API key + return UserApiKey row.

    Performance note: in production, prefix lookup narrows to ~1 row, then
    bcrypt.checkpw verifies. For Phase M we do a linear scan since fresh DB
    has few keys.
    """
    if not token.startswith(KEY_PREFIX):
        return None  # type: ignore[return-value]

    # Match by prefix
    prefix = token[: len(KEY_PREFIX) + 6]
    stmt = select(UserApiKey).where(
        and_(
            UserApiKey.prefix == prefix,
            UserApiKey.revoked_at.is_(None),
        )
    )
    candidates = list((await session.execute(stmt)).scalars().all())
    for key in candidates:
        if bcrypt.checkpw(token.encode(), key.hash.encode()):
            if key.expires_at and key.expires_at < _now():
                return None  # type: ignore[return-value]
            return key
    return None  # type: ignore[return-value]


async def dispatch_mcp_request(
    method: str,
    params: dict[str, Any] | None,
    *,
    session: AsyncSession | None = None,
    user: User | None = None,
) -> dict[str, Any]:
    """JSON-RPC dispatcher (PRD §4.5.2.1).

    `initialize` / `tools/list` / `resources/list` are pure metadata and don't
    need session+user. `tools/call` invokes Phase M.2 real implementations
    via `dispatch_tool_call` and requires both.
    """
    from app.api.v1.api_keys.mcp_tools import TOOLS, dispatch_tool_call

    if method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "genpano-mcp", "version": "0.1.0"},
            "capabilities": {"tools": {}, "resources": {}},
        }
    if method == "tools/list":
        return {
            "tools": [
                {
                    "name": name,
                    "description": f"GenPano tool: {name}",
                    "inputSchema": {"type": "object"},
                }
                for name in TOOLS
            ]
        }
    if method == "resources/list":
        return {
            "resources": [
                {"uri": uri, "name": uri, "mimeType": "application/json"} for uri in MCP_RESOURCES
            ]
        }
    if method == "tools/call":
        tool_name = (params or {}).get("name") or ""
        arguments = (params or {}).get("arguments") or {}
        if session is None or user is None:
            return {
                "content": [{"type": "text", "text": "session/user not propagated"}],
                "isError": True,
            }
        return await dispatch_tool_call(
            session, user=user, tool_name=tool_name, arguments=arguments
        )
    return {"error": {"code": -32601, "message": f"Method not found: {method}"}}
