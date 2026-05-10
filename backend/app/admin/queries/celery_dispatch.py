"""Celery dispatch shim for the queries write paths (Phase 9 slice 9b).

admin_console invoked celery directly via ``celery_app.send_task(...)``;
the FastAPI port keeps the same ``geo_tracker.tasks.celery_tasks.execute_query``
target name. When celery isn't on the path (admin Docker image without
geo_tracker), the dispatch is a graceful no-op — the queries row is
still created/reset, the SPA shows ``dispatched=0``.
"""

from __future__ import annotations

import importlib
from typing import Any


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


def dispatch_execute_query(query_id: int) -> bool:
    """Send a ``geo_tracker.tasks.celery_tasks.execute_query`` task. Returns
    True when the dispatch succeeded; False when celery is unavailable
    OR the broker rejected the call (admin_console ignored both)."""
    celery_app = _load_celery_app()
    if celery_app is None:
        return False
    try:
        celery_app.send_task(
            "geo_tracker.tasks.celery_tasks.execute_query",
            args=[int(query_id)],
            queue="celery",
        )
    except Exception:
        return False
    return True


def dispatch_many(ids: list[int]) -> tuple[int, int]:
    """Bulk dispatch. Returns ``(dispatched, dispatch_failed)``."""
    if not ids:
        return 0, 0
    celery_app = _load_celery_app()
    if celery_app is None:
        return 0, len(ids)
    dispatched = 0
    failed = 0
    for qid in ids:
        try:
            celery_app.send_task(
                "geo_tracker.tasks.celery_tasks.execute_query",
                args=[int(qid)],
                queue="celery",
            )
            dispatched += 1
        except Exception:
            failed += 1
    return dispatched, failed


__all__ = ["dispatch_execute_query", "dispatch_many"]
