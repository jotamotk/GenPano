"""Pure helpers for the legacy profile API (Phase 9 slice 9d).

Stateless validators for the geo_tracker-flavor /api/profiles routes.
The admin.html attempt-tracker UI uses these; segment-attached
profiles (with code / segment_id) live in app.admin.segments and are
handled by slice 6b.
"""

from __future__ import annotations

from typing import Any


class ProfileValidationError(Exception):
    """Coded validation error returned to the API layer (HTTP 400)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _coerce_traits(value: Any) -> dict[str, Any]:
    """Accept dict, JSON-string, or anything else (return ``{}``)."""
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        import json

        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}


def parse_profile_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Validate POST/PUT /api/profiles body. ``name`` is required;
    everything else has admin_console-compatible defaults."""
    payload = payload or {}
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ProfileValidationError("name_required", "Name is required")
    return {
        "name": name[:256],
        "age_range": str(payload.get("age_range") or ""),
        "location": str(payload.get("location") or ""),
        "country_code": str(payload.get("country_code") or ""),
        "profession": str(payload.get("profession") or ""),
        "language": str(payload.get("language") or "zh") or "zh",
        "device_type": str(payload.get("device_type") or "desktop") or "desktop",
        "persona_traits": _coerce_traits(payload.get("persona_traits") or {}),
    }


__all__ = ["ProfileValidationError", "parse_profile_payload"]
