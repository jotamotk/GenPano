"""Pure helpers for the analyzer API (Phase 9 slice 9c).

Stateless validators for the trigger / rerun write paths. No DB.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

ANALYZER_TRIGGER_ACTIONS = ("analyze", "aggregate", "reanalyze")
BATCH_ANALYZE_MODES = (
    "missing_or_failed_only",
    "reanalyze_current",
    "reanalyze_failed",
    "reanalyze_all",
)
SINGLE_ANALYZE_MODES = ("missing_or_failed_only", "reanalyze_current")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ATTEMPT_STATUSES = {"done", "failed", "pending", "running", "queued", "unqueued"}
ANALYSIS_STATUSES = {
    "missing",
    "pending",
    "queued",
    "running",
    "done",
    "partial",
    "failed",
    "stale",
    "not_eligible",
}


class AnalyzerValidationError(Exception):
    """Coded validation error returned to the API layer (HTTP 400)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class BatchPreviewRows(list[dict[str, Any]]):
    """Candidate rows plus DB-scope truncation metadata."""

    def __init__(
        self,
        rows: list[dict[str, Any]],
        *,
        query_truncated: bool = False,
        query_limit: int | None = None,
    ):
        super().__init__(rows)
        self.query_truncated = query_truncated
        self.query_limit = query_limit


def parse_trigger_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Validate POST /api/analyzer/trigger body. Required: ``date``
    (YYYY-MM-DD); ``action`` defaults to ``analyze``.
    """
    payload = payload or {}
    action = str(payload.get("action") or "analyze").strip().lower()
    if action not in ANALYZER_TRIGGER_ACTIONS:
        raise AnalyzerValidationError(
            "invalid_action",
            f"action must be one of {sorted(ANALYZER_TRIGGER_ACTIONS)}",
        )
    date_str = str(payload.get("date") or "").strip()
    if not date_str:
        raise AnalyzerValidationError("date_required", "date is required")
    if not DATE_PATTERN.match(date_str):
        raise AnalyzerValidationError("invalid_date", "date must be ISO YYYY-MM-DD")
    raw_brand = payload.get("brand_id")
    brand_id: int | None
    if raw_brand is None or raw_brand == "":
        brand_id = None
    else:
        try:
            brand_id = int(raw_brand)
        except (TypeError, ValueError) as error:
            raise AnalyzerValidationError(
                "invalid_brand_id", "brand_id must be an integer or null"
            ) from error
    return {"action": action, "date": date_str, "brand_id": brand_id}


def _parse_positive_int_list(value: Any, field: str) -> list[int]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AnalyzerValidationError(f"invalid_{field}", f"{field} must be an array")
    out: list[int] = []
    for raw in value:
        try:
            parsed = int(raw)
        except (TypeError, ValueError) as error:
            raise AnalyzerValidationError(
                f"invalid_{field}", f"{field} must contain integers"
            ) from error
        if parsed <= 0:
            raise AnalyzerValidationError(
                f"invalid_{field}", f"{field} must contain positive integers"
            )
        out.append(parsed)
    return out


def _optional_positive_int(value: Any, field: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise AnalyzerValidationError(f"invalid_{field}", f"{field} must be an integer") from error
    if parsed <= 0:
        raise AnalyzerValidationError(f"invalid_{field}", f"{field} must be positive")
    return parsed


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def _normalize_filters(raw_filters: Any) -> dict[str, Any]:
    if raw_filters is None:
        return {}
    if not isinstance(raw_filters, dict):
        raise AnalyzerValidationError("invalid_filters", "filters must be an object")

    filters: dict[str, Any] = {}
    for field in ("brand_id", "topic_id", "prompt_id"):
        parsed = _optional_positive_int(raw_filters.get(field), field)
        if parsed is not None:
            filters[field] = parsed

    llm = _string_or_none(raw_filters.get("llm"))
    if llm is not None:
        filters["llm"] = llm

    prompt_query = _string_or_none(raw_filters.get("q"))
    if prompt_query is not None:
        filters["q"] = prompt_query

    attempt_status = _string_or_none(raw_filters.get("attempt_status"))
    if attempt_status is not None:
        normalized = attempt_status.lower()
        if normalized not in ATTEMPT_STATUSES:
            raise AnalyzerValidationError(
                "invalid_attempt_status",
                f"attempt_status must be one of {sorted(ATTEMPT_STATUSES)}",
            )
        filters["attempt_status"] = normalized

    analysis_status = _string_or_none(raw_filters.get("analysis_status"))
    if analysis_status is not None:
        normalized = analysis_status.lower()
        if normalized not in ANALYSIS_STATUSES:
            raise AnalyzerValidationError(
                "invalid_analysis_status",
                f"analysis_status must be one of {sorted(ANALYSIS_STATUSES)}",
            )
        filters["analysis_status"] = normalized

    for field in ("date", "date_from", "date_to"):
        date_value = _string_or_none(raw_filters.get(field))
        if date_value is None:
            continue
        if not DATE_PATTERN.match(date_value):
            raise AnalyzerValidationError(f"invalid_{field}", f"{field} must be ISO YYYY-MM-DD")
        filters[field] = date_value

    return filters


def _parse_count(value: Any, field: str, *, default: int, max_value: int) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise AnalyzerValidationError(f"invalid_{field}", f"{field} must be an integer") from error
    if parsed < 1 or parsed > max_value:
        raise AnalyzerValidationError(
            f"invalid_{field}", f"{field} must be between 1 and {max_value}"
        )
    return parsed


def parse_batch_dry_run_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    if not isinstance(payload, dict):
        raise AnalyzerValidationError("invalid_payload", "payload must be an object")

    raw_scope = payload.get("scope") or {}
    if not isinstance(raw_scope, dict):
        raise AnalyzerValidationError("invalid_scope", "scope must be an object")

    response_ids = _parse_positive_int_list(raw_scope.get("response_ids"), "response_ids")
    query_ids = _parse_positive_int_list(raw_scope.get("query_ids"), "query_ids")
    filters = _normalize_filters(raw_scope.get("filters"))
    if not response_ids and not query_ids and not filters:
        raise AnalyzerValidationError(
            "empty_scope", "scope must include response_ids, query_ids, or filters"
        )

    mode = str(payload.get("mode") or "missing_or_failed_only").strip().lower()
    if mode not in BATCH_ANALYZE_MODES:
        raise AnalyzerValidationError(
            "invalid_mode", f"mode must be one of {sorted(BATCH_ANALYZE_MODES)}"
        )

    return {
        "scope": {
            "response_ids": response_ids,
            "query_ids": query_ids,
            "filters": filters,
        },
        "mode": mode,
        "max_count": _parse_count(
            payload.get("max_count"), "max_count", default=200, max_value=1000
        ),
        "sample_limit": _parse_count(
            payload.get("sample_limit"), "sample_limit", default=50, max_value=200
        ),
        "reason": _string_or_none(payload.get("reason")),
        "confirm": bool(payload.get("confirm") is True),
    }


def parse_single_analyze_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    if not isinstance(payload, dict):
        raise AnalyzerValidationError("invalid_payload", "payload must be an object")
    mode = str(payload.get("mode") or "missing_or_failed_only").strip().lower()
    if mode not in SINGLE_ANALYZE_MODES:
        raise AnalyzerValidationError(
            "invalid_mode", f"mode must be one of {sorted(SINGLE_ANALYZE_MODES)}"
        )
    return {
        "mode": mode,
        "reason": _string_or_none(payload.get("reason")),
        "idempotency_key": _string_or_none(payload.get("idempotency_key")),
    }


def _blank_skipped_counts() -> dict[str, int]:
    return {
        "no_response": 0,
        "empty_response": 0,
        "failed_attempt_without_response": 0,
        "already_done": 0,
        "already_queued_or_running": 0,
        "invalid_response_id": 0,
        "duplicate_response_id": 0,
        "missing_brand_context": 0,
    }


def _append_sample(
    samples: dict[str, list[dict[str, Any]]],
    reason: str,
    row: dict[str, Any],
    *,
    sample_limit: int,
    detail: dict[str, Any] | None = None,
) -> None:
    bucket = samples.setdefault(reason, [])
    if len(bucket) >= sample_limit:
        return
    sample = {
        "response_id": row.get("response_id"),
        "query_id": row.get("query_id"),
        "reason": reason,
    }
    if detail:
        sample.update(detail)
    bucket.append(sample)


def _is_done(row: dict[str, Any]) -> bool:
    return (
        str(row.get("analysis_status") or "").strip().lower() == "done"
        and row.get("analysis_id") is not None
    )


def _is_running_or_queued(row: dict[str, Any]) -> bool:
    return str(row.get("analysis_status") or "").strip().lower() in {"queued", "running"}


def _eligible_for_mode(row: dict[str, Any], mode: str) -> tuple[bool, str | None]:
    status = str(row.get("analysis_status") or "").strip().lower()
    if _is_running_or_queued(row):
        return False, "already_queued_or_running"
    if mode == "missing_or_failed_only":
        if _is_done(row):
            return False, "already_done"
        return True, None
    if mode == "reanalyze_failed":
        if status in {"failed", "stale", "partial"}:
            return True, None
        if _is_done(row):
            return False, "already_done"
        return False, "invalid_response_id"
    return True, None


def _selection_token(
    payload: dict[str, Any], eligible_ids: list[int], skipped_counts: dict[str, int]
) -> str:
    material = {
        "mode": payload["mode"],
        "scope": payload["scope"],
        "eligible_response_ids": eligible_ids,
        "skipped_counts": skipped_counts,
    }
    raw = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def build_batch_dry_run_result(
    payload: dict[str, Any],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    sample_limit = int(payload["sample_limit"])
    query_truncated = bool(getattr(rows, "query_truncated", False))
    raw_query_limit = getattr(rows, "query_limit", None)
    query_limit = int(raw_query_limit) if raw_query_limit is not None else None
    skipped_counts = _blank_skipped_counts()
    skipped_samples: dict[str, list[dict[str, Any]]] = {}
    response_ids = list(payload["scope"].get("response_ids") or [])

    seen_requested: set[int] = set()
    unique_requested: list[int] = []
    for response_id in response_ids:
        if response_id in seen_requested:
            skipped_counts["duplicate_response_id"] += 1
        else:
            seen_requested.add(response_id)
            unique_requested.append(response_id)

    row_by_response_id = {
        int(row["response_id"]): row for row in rows if row.get("response_id") is not None
    }
    for response_id in unique_requested:
        if response_id not in row_by_response_id:
            skipped_counts["invalid_response_id"] += 1
            _append_sample(
                skipped_samples,
                "invalid_response_id",
                {"response_id": response_id, "query_id": None},
                sample_limit=sample_limit,
            )

    eligible_rows: list[dict[str, Any]] = []
    processed_response_ids: set[int] = set()
    for row in rows:
        response_id = row.get("response_id")
        attempt_status = str(row.get("attempt_status") or "").strip().lower()
        raw_text = str(row.get("raw_text") or "").strip()

        if response_id is not None:
            parsed_response_id = int(response_id)
            if parsed_response_id in processed_response_ids:
                continue
            processed_response_ids.add(parsed_response_id)

        if response_id is None:
            reason = (
                "failed_attempt_without_response" if attempt_status == "failed" else "no_response"
            )
            skipped_counts[reason] += 1
            _append_sample(skipped_samples, reason, row, sample_limit=sample_limit)
            continue
        if not raw_text:
            reason = (
                "failed_attempt_without_response"
                if attempt_status == "failed"
                else "empty_response"
            )
            skipped_counts[reason] += 1
            _append_sample(skipped_samples, reason, row, sample_limit=sample_limit)
            continue

        eligible, skipped_reason = _eligible_for_mode(row, str(payload["mode"]))
        if not eligible:
            reason = skipped_reason or "invalid_response_id"
            skipped_counts[reason] += 1
            _append_sample(
                skipped_samples,
                reason,
                row,
                sample_limit=sample_limit,
                detail={"analysis_id": row.get("analysis_id")},
            )
            continue
        eligible_rows.append(row)

    if unique_requested:
        requested_order = {response_id: index for index, response_id in enumerate(unique_requested)}
        eligible_rows.sort(
            key=lambda row: (
                requested_order.get(int(row["response_id"]), len(requested_order)),
                int(row["response_id"]),
            )
        )

    cap_limit = int(payload["max_count"])
    eligible_ids = [int(row["response_id"]) for row in eligible_rows]
    capped_ids = eligible_ids[:cap_limit]
    cap_truncated = len(eligible_ids) > cap_limit
    candidate_responses = sum(1 for row in rows if row.get("response_id") is not None)
    requested_count = (
        len(response_ids) + len(payload["scope"].get("query_ids") or [])
        if response_ids or payload["scope"].get("query_ids")
        else len(rows)
    )
    dry_run_id = _selection_token(payload, [] if query_truncated else capped_ids, skipped_counts)

    if query_truncated:
        return {
            "success": False,
            "dry_run": True,
            "dry_run_id": dry_run_id,
            "mode": payload["mode"],
            "error": "dry_run_scope_too_large",
            "scope_too_large": True,
            "counts_complete": False,
            "query_truncated": True,
            "query_limit": query_limit,
            "requested_count": None,
            "matched_attempts": None,
            "matched_attempts_evaluated": len(rows),
            "candidate_responses": None,
            "candidate_responses_evaluated": candidate_responses,
            "eligible_count": None,
            "eligible_count_evaluated": len(eligible_ids),
            "already_done_count": None,
            "already_done_count_evaluated": skipped_counts["already_done"],
            "skipped_no_response_count": None,
            "skipped_no_response_count_evaluated": skipped_counts["no_response"]
            + skipped_counts["empty_response"],
            "skipped_invalid_count": None,
            "skipped_invalid_count_evaluated": skipped_counts["invalid_response_id"],
            "skipped_failed_attempt_without_response_count": None,
            "skipped_failed_attempt_without_response_count_evaluated": skipped_counts[
                "failed_attempt_without_response"
            ],
            "cap": cap_limit,
            "cap_limit": cap_limit,
            "cap_exceeded": False,
            "cap_truncated": False,
            "will_enqueue_count": 0,
            "eligible_response_ids_preview": [],
            "eligible_response_ids_sample": [],
            "skipped_counts": {},
            "skipped_counts_evaluated": skipped_counts,
            "skipped_reasons": {},
            "skipped_samples": {},
            "skipped_reasons_evaluated": skipped_samples,
            "skipped_samples_evaluated": skipped_samples,
            "requires_confirmation": False,
            "warnings": [
                {
                    "code": "dry_run_scope_too_large",
                    "message": (
                        "Dry-run scope exceeded the safe preview row limit; "
                        "narrow the filters before submitting analyzer work."
                    ),
                    "query_limit": query_limit,
                }
            ],
        }

    return {
        "success": True,
        "dry_run": True,
        "dry_run_id": dry_run_id,
        "mode": payload["mode"],
        "scope_too_large": False,
        "counts_complete": True,
        "query_truncated": False,
        "query_limit": query_limit,
        "requested_count": requested_count,
        "matched_attempts": len(rows),
        "candidate_responses": candidate_responses,
        "eligible_count": len(eligible_ids),
        "already_done_count": skipped_counts["already_done"],
        "skipped_no_response_count": skipped_counts["no_response"]
        + skipped_counts["empty_response"],
        "skipped_invalid_count": skipped_counts["invalid_response_id"],
        "skipped_failed_attempt_without_response_count": skipped_counts[
            "failed_attempt_without_response"
        ],
        "cap": cap_limit,
        "cap_limit": cap_limit,
        "cap_exceeded": cap_truncated,
        "cap_truncated": cap_truncated,
        "will_enqueue_count": len(capped_ids),
        "eligible_response_ids_preview": capped_ids[:sample_limit],
        "eligible_response_ids_sample": capped_ids[:sample_limit],
        "skipped_counts": skipped_counts,
        "skipped_reasons": skipped_samples,
        "skipped_samples": skipped_samples,
        "requires_confirmation": len(capped_ids) > 0,
        "warnings": [],
    }


__all__ = [
    "ANALYZER_TRIGGER_ACTIONS",
    "BATCH_ANALYZE_MODES",
    "SINGLE_ANALYZE_MODES",
    "AnalyzerValidationError",
    "BatchPreviewRows",
    "build_batch_dry_run_result",
    "parse_batch_dry_run_payload",
    "parse_single_analyze_payload",
    "parse_trigger_payload",
]
