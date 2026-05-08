"""Celery dispatch shim for misc routes (Phase 9 slice 9f)."""

from __future__ import annotations

from typing import Any


def _load_celery_app() -> Any | None:
    try:
        import importlib

        importlib.import_module("celery")
        return importlib.import_module("geo_tracker.celery_app").celery_app
    except Exception:
        return None


def trigger_sms_register(platform: str) -> tuple[str | None, str | None]:
    """Returns ``(task_id, error_msg)``. Mirrors admin_console line
    7253 — celery is optional, returns 503 with a stable error code
    when unavailable."""
    celery_app = _load_celery_app()
    if celery_app is None:
        return None, "Celery not available"
    try:
        result = celery_app.send_task(
            "geo_tracker.tasks.celery_tasks.auto_login",
            kwargs={"platform": platform, "new_account": True},
            queue="account_login",
        )
        return getattr(result, "id", None), None
    except Exception as error:
        return None, str(error)


def fetch_task_status(task_id: str) -> dict[str, Any]:
    """Returns ``{state, task_id, result?, error?}``. Mirrors
    admin_console line 7271."""
    celery_app = _load_celery_app()
    if celery_app is None:
        return {"state": "UNKNOWN", "error": "Celery not available"}
    try:
        result = celery_app.AsyncResult(task_id)
        response: dict[str, Any] = {"state": result.state, "task_id": task_id}
        if result.state == "SUCCESS":
            response["result"] = result.result
        elif result.state == "FAILURE":
            response["error"] = str(result.result)
        return response
    except Exception as error:
        return {"state": "ERROR", "error": str(error)}


__all__ = ["fetch_task_status", "trigger_sms_register"]
