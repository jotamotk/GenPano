"""Pure helpers for the admin/products package (Phase 8 slice 8a).

Stateless validation + normalization. No DB / no httpx. Tested in
isolation by ``tests/test_phase_8a_admin_products.py``.

Public:
- ``PRODUCT_STATUSES`` — allowed status values.
- ``ProductValidationError`` — coded validation error.
- ``coerce_product_aliases(value)`` — admin_console-compat alias parsing
  (list / JSON string / comma-separated).
- ``parse_create_payload(payload)`` — validate POST body for the
  ``brands/{id}/products`` create route.
- ``parse_update_payload(payload)`` — return (set_clause_pieces, params,
  changed_fields) for the PUT route, or raise ``ProductValidationError``.
- ``parse_discover_payload(payload)`` — extract / clamp ``query`` + ``limit``.
- ``product_row_to_dict(row)`` — wire shape mirror of admin_console.
"""

from __future__ import annotations

import json
from typing import Any

PRODUCT_STATUSES = ("active", "archived")


class ProductValidationError(Exception):
    """Coded validation error returned to the API layer (HTTP 400)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def coerce_product_aliases(value: Any) -> list[str]:
    """Accept list / JSON-string / comma-separated string. Empty values
    return ``[]``. Mirrors admin_console line 5933 byte-for-byte so
    operators copy-pasting old payloads keep working."""
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            pass
        return [piece.strip() for piece in value.replace("\n", ",").split(",") if piece.strip()]
    return []


def _normalize_status(value: Any, *, default: str = "active") -> str:
    text = str(value or "").strip().lower()
    if text in PRODUCT_STATUSES:
        return text
    return default


def parse_create_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Validate the body of POST ``/api/admin/brands/{brand_id}/products``.

    Raises ``ProductValidationError`` with a stable code on missing /
    invalid input (caller maps to HTTP 400).
    """
    payload = payload or {}
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ProductValidationError("name_required", "Product name is required")
    status = _normalize_status(payload.get("status"), default="active")
    return {
        "name": name[:256],
        "sku": (str(payload.get("sku") or "").strip() or None),
        "category": (str(payload.get("category") or "").strip() or None),
        "description": (str(payload.get("description") or "").strip() or None),
        "aliases": coerce_product_aliases(payload.get("aliases")),
        "status": status,
    }


def parse_update_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Return a sparse ``{column: value}`` mapping of fields the operator
    asked to change. Empty mapping → caller raises ``no_fields`` 400.

    Raises ``ProductValidationError`` for invalid status / empty name.
    """
    payload = payload or {}
    fields: dict[str, Any] = {}
    if "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ProductValidationError("name_required", "Product name is required")
        fields["name"] = name[:256]
    if "sku" in payload:
        fields["sku"] = str(payload.get("sku") or "").strip() or None
    if "category" in payload:
        fields["category"] = str(payload.get("category") or "").strip() or None
    if "description" in payload:
        fields["description"] = str(payload.get("description") or "").strip() or None
    if "aliases" in payload:
        fields["aliases"] = coerce_product_aliases(payload.get("aliases"))
    if "status" in payload:
        raw = str(payload.get("status") or "").strip().lower()
        if raw not in PRODUCT_STATUSES:
            raise ProductValidationError(
                "invalid_status",
                f"status must be one of {sorted(PRODUCT_STATUSES)}",
            )
        fields["status"] = raw
    return fields


def parse_discover_payload(payload: dict[str, Any] | None) -> tuple[str, int]:
    """Extract ``query`` (operator hint) and ``limit`` (clamped to 1-20).
    admin_console accepts both ``query`` and legacy ``hint``."""
    payload = payload or {}
    query = str(payload.get("query") or payload.get("hint") or "").strip()
    raw_limit = payload.get("limit", 8)
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        limit = 8
    limit = max(1, min(limit, 20))
    return query, limit


def product_row_to_dict(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Wire shape for the SPA, mirroring admin_console ``_product_row``.
    JSONB ``aliases`` may arrive as str on some psycopg setups; coerce.
    """
    if not row:
        return None
    aliases_raw: Any = row.get("aliases")
    if aliases_raw is None:
        aliases: list[Any] = []
    elif isinstance(aliases_raw, str):
        try:
            parsed = json.loads(aliases_raw)
            aliases = parsed if isinstance(parsed, list) else []
        except Exception:
            aliases = []
    elif isinstance(aliases_raw, list):
        aliases = aliases_raw
    else:
        aliases = []
    created_at = row.get("created_at")
    updated_at = row.get("updated_at")
    return {
        "id": row.get("id"),
        "brand_id": row.get("brand_id"),
        "brand_name": row.get("brand_name"),
        "name": row.get("name"),
        "sku": row.get("sku") or "",
        "category": row.get("category") or "",
        "description": row.get("description") or "",
        "aliases": [str(x) for x in aliases if str(x).strip()],
        "status": row.get("status") or "active",
        "topic_count": int(row.get("topic_count") or 0),
        "created_at": (
            created_at.isoformat()
            if created_at is not None and hasattr(created_at, "isoformat")
            else None
        ),
        "updated_at": (
            updated_at.isoformat()
            if updated_at is not None and hasattr(updated_at, "isoformat")
            else None
        ),
    }


__all__ = [
    "PRODUCT_STATUSES",
    "ProductValidationError",
    "coerce_product_aliases",
    "parse_create_payload",
    "parse_discover_payload",
    "parse_update_payload",
    "product_row_to_dict",
]
