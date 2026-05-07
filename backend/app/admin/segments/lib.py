"""Pure (no-DB) segment payload + row helpers — Phase 6 slice 6a.

Vendored from admin_console/app.py 8932-9221. Used by the segment CRUD
routes (and by 6a-bis import + generate when we ship them). Brand
helpers are duplicated from admin_console because the SPA's wire
shape uses both ``brand_id`` and ``brandId`` keys interchangeably.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

SEGMENT_STATUSES = {"active", "draft", "paused"}
PROFILE_STATUSES = {"active", "draft", "paused"}


def _admin_float(value: Any, default: float) -> float:
    try:
        return float(value) if value is not None and value != "" else float(default)
    except (TypeError, ValueError):
        return float(default)


def brand_id_value(data: dict[str, Any] | None) -> str | None:
    """Read ``brand_id`` (snake or camelCase). Returns None when blank."""
    value = (data or {}).get("brand_id")
    if value in (None, ""):
        value = (data or {}).get("brandId")
    text = str(value or "").strip()
    return text or None


def brand_name_value(data: dict[str, Any] | None) -> str:
    value = (
        (data or {}).get("brand_name")
        or (data or {}).get("brandName")
        or (data or {}).get("brand")
        or ""
    )
    return str(value).strip()


def _isoformat(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def segment_row(row: Any) -> dict[str, Any]:
    """Wire shape used by both list + detail responses.

    Includes both snake_case and camelCase aliases for the SPA — same as
    admin_console.app._segment_row so the existing JS can keep reading
    ``segment.brandName`` while we keep writing ``brand_name``.
    """
    item = dict(row or {})
    weight_raw = item.get("weight")
    try:
        weight = float(weight_raw or 0)
    except (TypeError, ValueError):
        weight = 0.0
    profile_count = int(item.get("profile_count") or 0)
    active_profile_count = int(item.get("active_profile_count") or 0)
    bid = brand_id_value(item)
    bname = brand_name_value(item)
    return {
        "id": item.get("id"),
        "code": item.get("code") or item.get("id"),
        "brand_id": bid,
        "brandId": bid,
        "brand_name": bname,
        "brandName": bname,
        "brand": bname,
        "name": item.get("name"),
        "industry_id": item.get("industry_id"),
        "industry": item.get("industry") or item.get("industry_id") or "",
        "status": item.get("status") or "draft",
        "weight": weight,
        "age_range": item.get("age_range") or "",
        "ageRange": item.get("age_range") or "",
        "income": item.get("income") or "",
        "regions": item.get("regions") or "",
        "sampling_rate": item.get("sampling_rate") or "",
        "samplingRate": item.get("sampling_rate") or "",
        "note": item.get("note") or "",
        "profile_count": profile_count,
        "profileCount": profile_count,
        "active_profile_count": active_profile_count,
        "activeProfileCount": active_profile_count,
        "created_at": _isoformat(item.get("created_at")),
        "updated_at": _isoformat(item.get("updated_at")),
    }


def segment_payload(
    data: dict[str, Any] | None, *, existing_id: str | None = None
) -> dict[str, Any]:
    """Validate + normalize a SPA-supplied segment dict.

    Raises ``ValueError`` with a stable code (``segment_name_required`` /
    ``invalid_segment_status``); generates a SEG-XXXXXXXX id when none
    supplied. Mirrors admin_console line-for-line so existing curl
    integrations keep working.
    """
    data = data or {}
    segment_id = str(data.get("id") or data.get("code") or existing_id or "").strip().upper()
    if not segment_id:
        segment_id = "SEG-" + str(uuid.uuid4())[:8].upper()
    name = str(data.get("name") or "").strip()
    if not name:
        raise ValueError("segment_name_required")
    status = str(data.get("status") or "draft").strip().lower()
    if status == "deleted":
        # admin_console treats explicit ``deleted`` writes as "soft-pause";
        # callers must use DELETE /api/admin/segments/{id} for hard delete.
        status = "paused"
    if status not in SEGMENT_STATUSES:
        raise ValueError("invalid_segment_status")
    return {
        "id": segment_id,
        "code": str(data.get("code") or segment_id).strip().upper(),
        "brand_id": brand_id_value(data),
        "brand_name": brand_name_value(data),
        "name": name,
        "industry_id": str(data.get("industry_id") or "").strip() or None,
        "industry": str(data.get("industry") or data.get("industry_name") or "").strip(),
        "status": status,
        "weight": _admin_float(data.get("weight"), 0.0),
        "age_range": str(data.get("age_range") or data.get("ageRange") or "").strip(),
        "income": str(data.get("income") or "").strip(),
        "regions": str(data.get("regions") or "").strip(),
        "sampling_rate": str(data.get("sampling_rate") or data.get("samplingRate") or "").strip(),
        "note": str(data.get("note") or "").strip(),
    }


# ---------------------------------------------------------------------------
# Profile helpers (Phase 6 slice 6b)
# ---------------------------------------------------------------------------


def _admin_json(value: Any, default: Any = None) -> Any:
    """Coerce JSONB-shaped value to a Python dict/list (or default)."""
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            import json

            parsed = json.loads(text)
            if isinstance(parsed, (dict, list)):
                return parsed
        except Exception:
            pass
        return default
    return default


def profile_row(row: Any) -> dict[str, Any]:
    """Wire shape used by profile list + CRUD responses.

    Mirrors admin_console.app._profile_row — same snake/camel duality
    + ``api_id`` (code or stringified int id) the SPA uses for URL
    routing.
    """
    item = dict(row or {})
    weight_raw = item.get("weight")
    try:
        weight = float(weight_raw or 0)
    except (TypeError, ValueError):
        weight = 0.0
    persona_json = _admin_json(item.get("persona_json"), {}) or {}
    api_id = item.get("api_id") or item.get("code") or item.get("id")
    bid = brand_id_value(item)
    bname = brand_name_value(item)
    return {
        "id": str(api_id),
        "code": item.get("code") or str(api_id),
        "segment_id": item.get("segment_id"),
        "brand_id": bid,
        "brandId": bid,
        "brand_name": bname,
        "brandName": bname,
        "brand": bname,
        "name": item.get("name"),
        "demographic": item.get("demographic") or "",
        "need": item.get("need") or "",
        "weight": weight,
        "status": item.get("status") or "draft",
        "persona_json": persona_json,
        "created_at": _isoformat(item.get("created_at")),
        "updated_at": _isoformat(item.get("updated_at")),
    }


def profile_payload(
    data: dict[str, Any] | None,
    segment_id: str,
    *,
    existing_id: str | None = None,
    segment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate + normalize a SPA-supplied profile dict.

    Inherits brand context from the parent segment when the operator
    didn't override it. Raises ``profile_name_required`` /
    ``invalid_profile_status``. Auto-generates a ``P-<seg>-XXXXXX``
    id when none supplied, matching admin_console.
    """
    import uuid as _uuid

    data = data or {}
    seg = segment or {}
    pid = (
        str(
            data.get("id")
            or data.get("code")
            or data.get("profile_id")
            or data.get("profileId")
            or existing_id
            or ""
        )
        .strip()
        .upper()
    )
    if not pid:
        suffix = str(segment_id or "SEG").replace("SEG-", "").replace(" ", "-")
        pid = f"P-{suffix}-{str(_uuid.uuid4())[:6].upper()}"
    name = str(
        data.get("name") or data.get("profile_name") or data.get("profileName") or ""
    ).strip()
    if not name:
        raise ValueError("profile_name_required")
    status = str(data.get("status") or "draft").strip().lower()
    if status == "deleted":
        status = "paused"
    if status not in PROFILE_STATUSES:
        raise ValueError("invalid_profile_status")
    demographic = (
        data.get("demographic")
        or data.get("persona")
        or data.get("profile")
        or data.get("description")
        or data.get("画像")
        or ""
    )
    need = (
        data.get("need")
        or data.get("needs")
        or data.get("demand")
        or data.get("pain_point")
        or data.get("需求")
        or ""
    )
    persona_source = data.get("persona_json")
    if persona_source is None:
        persona_source = data.get("personaJson")
    if persona_source is None and isinstance(data.get("persona"), (dict, list, str)):
        persona_source = data.get("persona")
    return {
        "id": pid,
        "code": str(data.get("code") or pid).strip().upper(),
        "segment_id": str(segment_id).strip().upper(),
        "brand_id": brand_id_value(seg) or brand_id_value(data),
        "brand_name": brand_name_value(seg) or brand_name_value(data),
        "name": name,
        "demographic": str(demographic or "").strip(),
        "need": str(need or "").strip(),
        "weight": _admin_float(data.get("weight"), 1.0),
        "status": status,
        "persona_json": _admin_json(persona_source, {}) or {},
    }
