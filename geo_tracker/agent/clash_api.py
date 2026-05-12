"""
Clash/Mihomo REST API client used by overseas LLM proxy rotation.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

CLASH_API_URL = os.getenv("CLASH_API_URL", "http://host.docker.internal:9098")
_LAST_ERROR_REASON: str | None = None
GLOBAL_PROXY_GROUP = os.getenv("CLASH_GLOBAL_PROXY_GROUP", "GLOBAL")


@dataclass(frozen=True)
class ProxyRouteDiagnostic:
    ok: bool
    reason: str | None = None
    global_group: str = GLOBAL_PROXY_GROUP
    global_now: str | None = None
    source_group: str | None = None
    source_now: str | None = None
    selected_node: str | None = None
    changed: bool = False


def _set_last_error_reason(reason: str | None) -> None:
    global _LAST_ERROR_REASON
    _LAST_ERROR_REASON = reason


def get_last_error_reason() -> str | None:
    return _LAST_ERROR_REASON


def clear_last_error_reason() -> None:
    _set_last_error_reason(None)


def _api_headers() -> dict[str, str]:
    secret = os.getenv("CLASH_API_SECRET", "").strip()
    if not secret:
        return {}
    return {"Authorization": f"Bearer {secret}"}


async def get_proxy_group(api_url: str, group_name: str) -> Optional[dict]:
    """Return proxy group metadata including all nodes and selected node."""
    clear_last_error_reason()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{api_url}/proxies/{group_name}",
                headers=_api_headers(),
            )
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 401:
                _set_last_error_reason("proxy_api_unauthorized")
                logger.warning(
                    "Clash API unauthorized for proxy group %s; configure "
                    "CLASH_API_SECRET to match V-Ninja/Mihomo API secret",
                    group_name,
                )
                return None
            if resp.status_code == 404:
                _set_last_error_reason("proxy_group_not_found")
                logger.warning(
                    "Clash API proxy group %s not found; check CLASH_PROXY_GROUP",
                    group_name,
                )
                return None
            _set_last_error_reason(f"proxy_api_http_{resp.status_code}")
            logger.warning("Clash API proxy group fetch failed: %s", resp.status_code)
            return None
    except Exception as e:
        _set_last_error_reason("proxy_api_unreachable")
        logger.error("Clash API connection failed: %s", e)
        return None


async def get_current_node(api_url: str, group_name: str) -> Optional[str]:
    """Return the currently selected proxy node name."""
    group = await get_proxy_group(api_url, group_name)
    if group:
        return group.get("now")
    return None


async def get_all_nodes(api_url: str, group_name: str) -> list[str]:
    """Return selectable proxy nodes, excluding DIRECT and REJECT."""
    group = await get_proxy_group(api_url, group_name)
    if not group:
        return []
    excluded = {"DIRECT", "REJECT"}
    return [n for n in group.get("all", []) if n not in excluded]


async def switch_node(api_url: str, group_name: str, node_name: str) -> bool:
    """Switch a proxy group to a specific node."""
    clear_last_error_reason()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.put(
                f"{api_url}/proxies/{group_name}",
                json={"name": node_name},
                headers=_api_headers(),
            )
            if resp.status_code == 204:
                logger.info("Clash proxy switched to node: %s", node_name)
                return True
            if resp.status_code == 401:
                _set_last_error_reason("proxy_api_unauthorized")
                logger.warning(
                    "Clash API unauthorized while switching proxy group %s; "
                    "configure CLASH_API_SECRET",
                    group_name,
                )
                return False
            _set_last_error_reason(f"proxy_api_http_{resp.status_code}")
            logger.warning(
                "Clash proxy switch failed: %s %s",
                resp.status_code,
                resp.text[:300],
            )
            return False
    except Exception as e:
        _set_last_error_reason("proxy_api_unreachable")
        logger.error("Clash API switch failed: %s", e)
        return False


async def switch_to_next_node(
    api_url: str, group_name: str, exclude: set[str] | None = None
) -> Optional[str]:
    """Switch to the next available proxy node outside ``exclude``."""
    exclude = exclude or set()
    nodes = await get_all_nodes(api_url, group_name)
    current = await get_current_node(api_url, group_name)

    available = [n for n in nodes if n not in exclude and n != current]
    if not available:
        if not get_last_error_reason():
            _set_last_error_reason("proxy_no_available_nodes")
        logger.error("No available proxy nodes remain; excluded=%s", len(exclude))
        return None

    next_node = available[0]
    ok = await switch_node(api_url, group_name, next_node)
    return next_node if ok else None


def _select_global_candidate(
    global_group: dict,
    source_group: dict,
    source_group_name: str,
) -> str | None:
    global_nodes = [
        n for n in global_group.get("all", []) if n not in {"DIRECT", "REJECT"}
    ]
    if not global_nodes:
        return None

    if source_group_name in global_nodes:
        return source_group_name
    source_now = source_group.get("now")
    if source_now and source_now in global_nodes:
        return source_now
    return global_nodes[0]


async def ensure_global_proxy_route(
    api_url: str,
    source_group_name: str,
    *,
    global_group_name: str | None = None,
) -> ProxyRouteDiagnostic:
    """Ensure ChatGPT proxy traffic is not left on GLOBAL -> DIRECT."""
    global_group_name = global_group_name or GLOBAL_PROXY_GROUP
    global_group = await get_proxy_group(api_url, global_group_name)
    if not global_group:
        return ProxyRouteDiagnostic(
            ok=False,
            reason=get_last_error_reason() or "proxy_global_group_unavailable",
            global_group=global_group_name,
            source_group=source_group_name,
        )

    global_now = global_group.get("now")
    source_group = await get_proxy_group(api_url, source_group_name)
    if not source_group:
        return ProxyRouteDiagnostic(
            ok=False,
            reason=get_last_error_reason() or "proxy_source_group_unavailable",
            global_group=global_group_name,
            global_now=global_now,
            source_group=source_group_name,
        )

    candidate = _select_global_candidate(global_group, source_group, source_group_name)
    if not candidate:
        return ProxyRouteDiagnostic(
            ok=False,
            reason="proxy_global_no_candidate",
            global_group=global_group_name,
            global_now=global_now,
            source_group=source_group_name,
            source_now=source_group.get("now"),
        )

    if global_now == candidate:
        return ProxyRouteDiagnostic(
            ok=True,
            global_group=global_group_name,
            global_now=global_now,
            source_group=source_group_name,
            source_now=source_group.get("now"),
            selected_node=candidate,
        )

    if not await switch_node(api_url, global_group_name, candidate):
        return ProxyRouteDiagnostic(
            ok=False,
            reason=get_last_error_reason() or "proxy_global_switch_failed",
            global_group=global_group_name,
            global_now=global_now,
            source_group=source_group_name,
            source_now=source_group.get("now"),
            selected_node=candidate,
        )

    return ProxyRouteDiagnostic(
        ok=True,
        global_group=global_group_name,
        global_now=candidate,
        source_group=source_group_name,
        source_now=source_group.get("now"),
        selected_node=candidate,
        changed=True,
    )
