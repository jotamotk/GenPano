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

import datetime as dt
import re
from typing import Any

# Mirror admin_console constants byte-for-byte.
SCHEDULER_MODES = ("auto", "manual", "paused")
ALLOWED_LLM_ENGINES = frozenset({"doubao", "deepseek", "chatgpt", "gemini"})
CN_QUERY_ENGINES = frozenset({"doubao", "deepseek"})
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


def _parse_next_run_at(value: Any) -> dt.datetime | None:
    if value in ("", None):
        return None
    if isinstance(value, dt.datetime):
        parsed = value
    elif isinstance(value, dt.date):
        parsed = dt.datetime.combine(value, dt.time.min)
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = dt.datetime.fromisoformat(raw)
        except ValueError as error:
            raise SchedulerValidationError(
                "next_run_at_invalid", "next_run_at must be an ISO datetime"
            ) from error
    else:
        raise SchedulerValidationError("next_run_at_invalid", "next_run_at must be an ISO datetime")
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(dt.UTC).replace(tzinfo=None)
    return parsed


def is_query_engine(value: Any) -> bool:
    engine = normalize_engine_name(value)
    return bool(engine) and not engine.endswith(SCHEDULER_EXCLUDED_ENGINE_SUFFIXES)


def account_engine_geo(value: Any) -> str | None:
    if not value:
        return None
    return LLM_DEFAULT_GEO.get(str(value).lower())


def detect_query_language(text: Any) -> str:
    value = str(text or "")
    if re.search(r"[\u4e00-\u9fff]", value):
        return "zh"
    if re.search(r"[A-Za-z]", value):
        return "en"
    return "unknown"


def _normalize_target_llms(values: Any) -> list[str]:
    raw_values = values if isinstance(values, list) else [values]
    out: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        engine = normalize_engine_name(value)
        if not engine:
            continue
        if engine not in ALLOWED_LLM_ENGINES:
            raise SchedulerValidationError(
                "target_llm_invalid",
                f"target_llm must be one of {sorted(ALLOWED_LLM_ENGINES)}",
            )
        if engine not in seen:
            out.append(engine)
            seen.add(engine)
    return out


def schedule_item_target_llms(item: dict[str, Any], target_llms: list[str]) -> list[str]:
    language = str(item.get("language") or detect_query_language(item.get("query_text"))).lower()
    if language.startswith("en"):
        return [engine for engine in target_llms if engine not in CN_QUERY_ENGINES]
    return list(target_llms)


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
    query_items_raw = payload.get("query_items")
    is_batch = isinstance(query_items_raw, list) and len(query_items_raw) > 0

    if is_batch:
        items: list[dict[str, Any]] = []
        for index, raw_item in enumerate(query_items_raw or []):
            if not isinstance(raw_item, dict):
                raise SchedulerValidationError(
                    "query_items_invalid", "query_items must contain objects"
                )
            query_text = str(raw_item.get("query_text") or "").strip()
            if not query_text:
                raise SchedulerValidationError(
                    "query_item_text_required",
                    f"query_items[{index}].query_text is required",
                )
            item: dict[str, Any] = {"query_text": query_text}
            profile_id = raw_item.get("profile_id")
            item["profile_id"] = (
                profile_id.strip() if isinstance(profile_id, str) and profile_id.strip() else None
            )
            for field in ("prompt_id", "brand_id"):
                value = raw_item.get(field)
                try:
                    item[field] = int(value) if value is not None and value != "" else None
                except (TypeError, ValueError) as error:
                    raise SchedulerValidationError(
                        f"{field}_invalid",
                        f"query_items[{index}].{field} must be an integer or null",
                    ) from error
            language = (
                str(raw_item.get("language") or detect_query_language(query_text)).strip().lower()
            )
            item["language"] = language or "unknown"
            candidate_id = raw_item.get("candidate_id")
            if candidate_id is not None and str(candidate_id).strip():
                item["candidate_id"] = str(candidate_id).strip()
            items.append(item)
        out["plan_kind"] = "batch"
        out["query_items"] = items
        out["item_count"] = len(items)
        target_llms = _normalize_target_llms(
            payload.get("target_llms") or payload.get("target_llm")
        )
        if not target_llms:
            raise SchedulerValidationError(
                "target_llm_invalid",
                f"target_llm must be one of {sorted(ALLOWED_LLM_ENGINES)}",
            )
        out["target_llms"] = target_llms
        out["target_llm"] = target_llms[0]
        out["query_text"] = str(payload.get("query_text") or "").strip() or (
            f"Query Pool batch ({len(items)} queries)"
        )
    elif "query_text" in payload or not partial:
        qt = str(payload.get("query_text") or "").strip()
        if not qt:
            raise SchedulerValidationError("query_text_required", "query_text is required")
        out["query_text"] = qt

    if not is_batch and ("target_llm" in payload or not partial):
        llms = _normalize_target_llms(payload.get("target_llm"))
        if not llms:
            raise SchedulerValidationError(
                "target_llm_invalid",
                f"target_llm must be one of {sorted(ALLOWED_LLM_ENGINES)}",
            )
        out["target_llm"] = llms[0]

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
        out["next_run_at"] = _parse_next_run_at(payload.get("next_run_at"))

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
    "CN_QUERY_ENGINES",
    "DAILY_TIME_PATTERN",
    "LLM_DEFAULT_GEO",
    "SCHEDULER_EXCLUDED_ENGINE_SUFFIXES",
    "SCHEDULER_MODES",
    "SchedulerValidationError",
    "account_engine_geo",
    "detect_query_language",
    "is_query_engine",
    "normalize_engine_caps",
    "normalize_engine_name",
    "normalize_paused_engines",
    "parse_config_payload",
    "parse_schedule_payload",
    "schedule_item_target_llms",
]
