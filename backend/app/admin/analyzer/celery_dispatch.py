"""Celery dispatch shim for the analyzer write paths (Phase 9 slice 9c).

Mirrors app.admin.queries.celery_dispatch — uses importlib so the
admin Docker image (without geo_tracker) gracefully reports celery as
unavailable rather than crashing the import.
"""

from __future__ import annotations

from typing import Any


def _load_celery_app() -> Any | None:
    try:
        import importlib

        importlib.import_module("celery")
        return importlib.import_module("geo_tracker.celery_app").celery_app
    except Exception:
        return None


def dispatch_run_daily_analysis(date_str: str, brand_id: int | None) -> str | None:
    """Send ``geo_tracker.tasks.celery_tasks.run_daily_analysis``. Returns
    the task id when dispatched; ``None`` when celery is unavailable
    OR the broker rejected the call."""
    celery_app = _load_celery_app()
    if celery_app is None:
        return None
    try:
        result = celery_app.send_task(
            "geo_tracker.tasks.celery_tasks.run_daily_analysis",
            kwargs={"date_str": date_str, "brand_id": brand_id},
            queue="analysis",
        )
    except Exception:
        return None
    return getattr(result, "id", None)


def dispatch_aggregate_daily_scores(date_str: str, brand_id: int | None) -> str | None:
    celery_app = _load_celery_app()
    if celery_app is None:
        return None
    try:
        result = celery_app.send_task(
            "geo_tracker.tasks.celery_tasks.aggregate_daily_scores",
            kwargs={"date_str": date_str, "brand_id": brand_id},
            queue="analysis",
        )
    except Exception:
        return None
    return getattr(result, "id", None)


def dispatch_analyze_response(response_id: int) -> str | None:
    celery_app = _load_celery_app()
    if celery_app is None:
        return None
    try:
        result = celery_app.send_task(
            "geo_tracker.tasks.celery_tasks.analyze_response",
            args=[int(response_id)],
            queue="analysis",
        )
    except Exception:
        return None
    return getattr(result, "id", None)


__all__ = [
    "dispatch_aggregate_daily_scores",
    "dispatch_analyze_response",
    "dispatch_run_daily_analysis",
]
