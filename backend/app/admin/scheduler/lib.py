"""Pure helpers for the admin/scheduler package (Phase 8 slice 8c).

Stateless validation + normalization for the scheduler API. No DB / no
celery. Tested in isolation by ``tests/test_phase_8c_admin_scheduler.py``.

Public:
- ``SCHEDULER_MODES`` / ``ALLOWED_LLM_ENGINES`` / ``LLM_DEFAULT_GEO`` —
  constants mirrored from admin_console.
- ``SchedulerValidationError`` — coded validation error.
- ``normalize_engine_name`` / ``is_query_engine`` / ``account_engine_geo``.
- ``parse_config_payload`` — PUT /scheduler/config validator.
- ``parse_schedule_payload`` — POST/PUT /scheduler/schedules validator.
- ``normalize_paused_engines`` / ``normalize_engine_caps`` —
  used by both the GET-config response and the PUT validator.
- ``DAILY_TIME_PATTERN`` — HH:MM regex used by config PUT.
"""

from __future__ import annotations

import re
from typing import Any

# Mirror admin_console constants byte-for-byte.
SCHEDULER_MODES = ("auto", "manual", "paused")
ALLOWED_LLM_ENGINES = frozenset({"doubao", "deepseek", "chatgpt", "gemini"})
SCHEDULER_EXCLUDED_ENGINE_SUFFIXES = ("_hots",)
LLM_DEFAULT_GEO: dict[str, str] = {
    "doubao": "CN",
    "deepseek": "CN",
    "chatgpt": "US",
    "gemini": "US",
}

DAILY_TIME_PATTERN = re.compile(r"^\d{1,2}:\d{2}$")


class SchedulerValidationError(Exception):
    """Coded validation error returned to the API layer (HTTP 400)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def normalize_engine_name(value: Any) -> str:
    return str(value or "").strip().lower()


def is_query_engine(value: Any) -> bool:
    engine = normalize_engine_name(value)
    return bool(engine) and not engine.endswith(SCHEDULER_EXCLUDED_ENGINE_SUFFIXES)


def account_engine_geo(value: Any) -> str | None:
    if not value:
        return None
    return LLM_DEFAULT_GEO.get(str(value).lower())


def normalize_paused_engines(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        engine = normalize_engine_name(value)
        if not is_query_engine(engine) or engine in seen:
            continue
        out.append(engine)
        seen.add(engine)
    return out


def normalize_engine_caps(engine_caps: Any, *, strict: bool = True) -> dict[str, int | None]:
    """Returns ``{engine: cap_or_none}``. Keys with non-engine names are
    dropped. ``cap_or_none`` is ``None`` (no cap) or a non-negative int.
    Raises ``SchedulerValidationError`` on negative / non-integer caps
    when ``strict`` is True; silently drops them otherwise (used for
    GET responses to defend against malformed db state)."""
    if engine_caps is None:
        return {}
    if not isinstance(engine_caps, dict):
        if strict:
            raise SchedulerValidationError("engine_caps_invalid", "engine_caps must be an object")
        return {}
    out: dict[str, int | None] = {}
    for raw_key, raw_value in engine_caps.items():
        key = normalize_engine_name(raw_key)
        if not is_query_engine(key):
            continue
        if raw_value in ("", None):
            out[key] = None
            continue
        try:
            iv = int(raw_value)
            if iv < 0:
                raise ValueError
        except Exception as error:
            if strict:
                raise SchedulerValidationError(
                    "engine_caps_invalid",
                    f"engine_caps['{key}'] must be a non-negative integer or null",
                ) from error
            continue
        out[key] = iv
    return out


def parse_config_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Validate PUT /api/scheduler/config body. Returns a sparse dict of
    the columns to set; empty dict ⇒ no-op (handler returns 200
    {success: True, updated: 0}).
    """
    payload = payload or {}
    out: dict[str, Any] = {}

    raw_mode = str(payload.get("mode") or "").strip().lower()
    if raw_mode:
        if raw_mode not in SCHEDULER_MODES:
            raise SchedulerValidationError(
                "mode_invalid", f"mode must be one of {sorted(SCHEDULER_MODES)}"
            )
        out["mode"] = raw_mode

    raw_daily = str(payload.get("daily_time") or "").strip()
    if raw_daily:
        if not DAILY_TIME_PATTERN.match(raw_daily):
            raise SchedulerValidationError("daily_time_invalid", "daily_time must be HH:MM")
        out["daily_time"] = raw_daily

    raw_tz = str(payload.get("timezone") or "").strip()
    if raw_tz:
        out["timezone"] = raw_tz

    if "temp_global_cap" in payload:
        cap = payload.get("temp_global_cap")
        if cap in ("", None):
            out["temp_global_cap"] = None
        else:
            try:
                iv = int(cap) if cap is not None else 0
                if iv < 0:
                    raise ValueError
            except Exception as error:
                raise SchedulerValidationError(
                    "temp_global_cap_invalid",
                    "temp_global_cap must be a non-negative integer or null",
                ) from error
            out["temp_global_cap"] = iv

    if "retry_max" in payload and payload.get("retry_max") is not None:
        retry_raw = payload.get("retry_max")
        try:
            iv2 = int(retry_raw) if retry_raw is not None else 0
            if iv2 < 0:
                raise ValueError
        except Exception as error:
            raise SchedulerValidationError(
                "retry_max_invalid", "retry_max must be a non-negative integer"
            ) from error
        out["retry_max"] = iv2

    if "paused_engines" in payload:
        raw_paused = payload.get("paused_engines")
        if raw_paused is not None and not isinstance(raw_paused, list):
            raise SchedulerValidationError(
                "paused_engines_invalid", "paused_engines must be a list"
            )
        out["paused_engines"] = normalize_paused_engines(raw_paused or [])

    if "engine_caps" in payload:
        raw_caps = payload.get("engine_caps")
        if raw_caps is not None and not isinstance(raw_caps, dict):
            raise SchedulerValidationError("engine_caps_invalid", "engine_caps must be an object")
        out["engine_caps"] = normalize_engine_caps(raw_caps or {}, strict=True)

    return out


def parse_schedule_payload(
    payload: dict[str, Any] | None, *, partial: bool = False
) -> dict[str, Any]:
    """Validate POST/PUT /api/scheduler/schedules body. ``partial=False``
    requires the create-mandatory fields; ``partial=True`` is for PUT
    where missing keys mean "leave as-is"."""
    payload = payload or {}
    out: dict[str, Any] = {}

    if "query_text" in payload or not partial:
        qt = str(payload.get("query_text") or "").strip()
        if not qt:
            raise SchedulerValidationError("query_text_required", "query_text is required")
        out["query_text"] = qt

    if "target_llm" in payload or not partial:
        llm = normalize_engine_name(payload.get("target_llm"))
        if llm not in ALLOWED_LLM_ENGINES:
            raise SchedulerValidationError(
                "target_llm_invalid",
                f"target_llm must be one of {sorted(ALLOWED_LLM_ENGINES)}",
            )
        out["target_llm"] = llm

    if "profile_id" in payload:
        pid = payload.get("profile_id")
        out["profile_id"] = pid.strip() if isinstance(pid, str) and pid.strip() else None

    if "cadence_days" in payload or not partial:
        cd_raw = payload.get("cadence_days", 1)
        try:
            cd = int(cd_raw) if cd_raw is not None else 0
            if cd < 1:
                raise ValueError
        except (TypeError, ValueError) as error:
            raise SchedulerValidationError(
                "cadence_days_invalid", "cadence_days must be a positive integer"
            ) from error
        out["cadence_days"] = cd

    if "next_run_at" in payload:
        v = payload.get("next_run_at")
        out["next_run_at"] = None if v in ("", None) else str(v)

    if "enabled" in payload:
        out["enabled"] = bool(payload.get("enabled"))

    if "note" in payload:
        nv = payload.get("note")
        out["note"] = nv if isinstance(nv, str) else None

    if "brand_id" in payload:
        v_brand = payload.get("brand_id")
        try:
            out["brand_id"] = int(v_brand) if v_brand is not None and v_brand != "" else None
        except (TypeError, ValueError) as error:
            raise SchedulerValidationError(
                "brand_id_invalid", "brand_id must be an integer or null"
            ) from error

    if "prompt_id" in payload:
        v_prompt = payload.get("prompt_id")
        try:
            out["prompt_id"] = int(v_prompt) if v_prompt is not None and v_prompt != "" else None
        except (TypeError, ValueError) as error:
            raise SchedulerValidationError(
                "prompt_id_invalid", "prompt_id must be an integer or null"
            ) from error

    return out


__all__ = [
    "ALLOWED_LLM_ENGINES",
    "DAILY_TIME_PATTERN",
    "LLM_DEFAULT_GEO",
    "SCHEDULER_EXCLUDED_ENGINE_SUFFIXES",
    "SCHEDULER_MODES",
    "SchedulerValidationError",
    "account_engine_geo",
    "is_query_engine",
    "normalize_engine_caps",
    "normalize_engine_name",
    "normalize_paused_engines",
    "parse_config_payload",
    "parse_schedule_payload",
]
