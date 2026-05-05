"""MCP call log ingest helper.

Wraps `mcp_call_log` writes used by the JSON-RPC dispatcher in
`router.mcp_jsonrpc`. Admin MCP Ops view (`/api/admin/mcp-ops/*`)
queries the same table — this module closes the loop by populating it.

Per PRD §4.4.6, every MCP call records:
  - api_key_id, user_id (auth principal)
  - tool / resource_uri (what was requested)
  - status ('ok' | 'error') + http_status + error_code
  - latency_ms
  - cost_estimate_cny (sum of LLM token spend if tool used LLM)

Failures here MUST NOT break the request; this is observability, not
critical path.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from genpano_models import McpCallLog
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _http_status_for(method: str, error_code: str | None) -> int:
    """Map JSON-RPC outcome to a sensible http_status proxy."""
    if error_code is None:
        return 200
    if error_code in {"MCP_AUTH_REQUIRED", "unauthorized"}:
        return 401
    if error_code == "rate_limited":
        return 429
    if error_code in {"PARAMS_INVALID", "validation_error"}:
        return 422
    return 500


async def record_mcp_call(
    session: AsyncSession,
    *,
    api_key_id: str | None,
    user_id: str | None,
    method: str,
    tool: str | None = None,
    resource_uri: str | None = None,
    status: str = "ok",
    error_code: str | None = None,
    latency_ms: int | None = None,
    cost_estimate_cny: float | None = None,
) -> McpCallLog | None:
    """Insert one mcp_call_log row. Returns None on persistence failure."""
    row = McpCallLog(
        api_key_id=api_key_id,
        user_id=user_id,
        tool=tool,
        resource_uri=resource_uri,
        status=status,
        http_status=_http_status_for(method, error_code),
        error_code=error_code,
        latency_ms=latency_ms,
        cost_estimate_cny=cost_estimate_cny,
        occurred_at=_now(),
    )
    try:
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row
    except Exception as exc:  # pragma: no cover — defensive
        log.warning("record_mcp_call failed: %s", exc)
        try:
            await session.rollback()
        except Exception:
            pass
        return None


@asynccontextmanager
async def measure_mcp_call(
    session: AsyncSession,
    *,
    api_key_id: str | None,
    user_id: str | None,
    method: str,
    tool: str | None = None,
    resource_uri: str | None = None,
) -> Any:
    """Context manager that records latency + outcome of an MCP call.

    Usage:
        async with measure_mcp_call(session, ...) as ctx:
            result = await dispatch(...)
            ctx["error_code"] = result.get("error", {}).get("code")
    """
    started = time.monotonic()
    ctx: dict[str, Any] = {
        "error_code": None,
        "cost_estimate_cny": None,
    }
    raised = False
    try:
        yield ctx
    except Exception:
        ctx["error_code"] = "internal_error"
        raised = True
        raise
    finally:
        latency_ms = int((time.monotonic() - started) * 1000)
        status = "error" if (raised or ctx.get("error_code")) else "ok"
        await record_mcp_call(
            session,
            api_key_id=api_key_id,
            user_id=user_id,
            method=method,
            tool=tool,
            resource_uri=resource_uri,
            status=status,
            error_code=ctx.get("error_code"),
            latency_ms=latency_ms,
            cost_estimate_cny=ctx.get("cost_estimate_cny"),
        )
