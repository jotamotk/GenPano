"""Phase M scope enforcement for MCP API keys.

`UserApiKey.scope` is a JSONB column shaped like:

    {
        "tools": ["*"] | ["genpano_get_brand_visibility", ...],
        "resources": ["*"] | ["genpano://industry/*"]
    }

Semantics:
    - `None` (no scope set) — full access (legacy keys, default behavior)
    - `["*"]` — full access for that capability
    - `[...]` — exact-match allowlist for tool names; pattern allowlist
      for resource URIs (each entry is a glob, currently `*` at the end
      treated as prefix wildcard; otherwise exact match).

Anything outside the allowlist is denied. Empty list `[]` denies all
in that capability.
"""

from __future__ import annotations

from typing import Any


def _normalize_list(raw: Any) -> list[str] | None:
    """Coerce the raw JSONB entry to a list[str] or None."""
    if raw is None:
        return None
    if isinstance(raw, list):
        return [str(v) for v in raw]
    return None


def _matches_resource(uri: str, pattern: str) -> bool:
    if pattern == "*":
        return True
    if pattern.endswith("/*"):
        prefix = pattern[:-1]  # keep trailing slash
        return uri.startswith(prefix)
    if pattern.endswith("*"):
        return uri.startswith(pattern[:-1])
    return uri == pattern


def is_tool_allowed(scope: dict[str, Any] | None, tool_name: str) -> bool:
    """Return True if the API key's scope permits invoking `tool_name`."""
    if scope is None:
        return True
    tools = _normalize_list(scope.get("tools")) if isinstance(scope, dict) else None
    if tools is None:
        return True
    if "*" in tools:
        return True
    return tool_name in tools


def is_resource_allowed(scope: dict[str, Any] | None, uri: str) -> bool:
    """Return True if the API key's scope permits reading `uri`."""
    if scope is None:
        return True
    resources = _normalize_list(scope.get("resources")) if isinstance(scope, dict) else None
    if resources is None:
        return True
    if "*" in resources:
        return True
    return any(_matches_resource(uri, p) for p in resources)
