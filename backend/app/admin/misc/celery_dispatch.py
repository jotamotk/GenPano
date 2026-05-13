"""Celery dispatch shim for misc routes (Phase 9 slice 9f)."""

from __future__ import annotations

import importlib
from typing import Any

SMS_REGISTER_TASK_NAME = "geo_tracker.tasks.celery_tasks.auto_login"
SMS_REGISTER_QUEUE = "account_login"


def _load_celery_app() -> Any | None:
    try:
        importlib.import_module("celery")
    except Exception:
        return None
    for module_name in ("geo_tracker.celery_app", "app.celery_app"):
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        celery_app = getattr(module, "celery_app", None)
        if celery_app is not None:
            return celery_app
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
            SMS_REGISTER_TASK_NAME,
            kwargs={"platform": platform, "new_account": True},
            queue=SMS_REGISTER_QUEUE,
        )
        task_id = getattr(result, "id", None)
        if not str(task_id or "").strip():
            return None, "Celery task id missing"
        return str(task_id), None
    except Exception:
        return None, "Celery dispatch failed"


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
