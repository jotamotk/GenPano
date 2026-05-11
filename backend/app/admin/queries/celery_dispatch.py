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

TASK_NAME = "geo_tracker.tasks.celery_tasks.execute_query"
ENGINE_QUEUES = {
    "chatgpt": "llm_chatgpt",
    "doubao": "llm_doubao",
    "deepseek": "llm_deepseek",
}
DEFAULT_QUEUE = "celery"


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


def queue_for_target(target_llm: Any | None) -> str:
    return ENGINE_QUEUES.get(str(target_llm or "").strip().lower(), DEFAULT_QUEUE)


def _normalize_dispatch_item(item: Any) -> tuple[int, Any | None]:
    if isinstance(item, dict):
        raw_id: Any = item.get("id")
        if raw_id is None:
            raw_id = item.get("query_id")
        if raw_id is None:
            raise ValueError("dispatch item missing query id")
        return int(raw_id), item.get("target_llm") or item.get("engine") or item.get("llm")
    if isinstance(item, (tuple, list)) and item:
        return int(item[0]), item[1] if len(item) > 1 else None
    return int(item), None


def dispatch_execute_query(query_id: int, target_llm: Any | None = None) -> bool:
    """Send a ``geo_tracker.tasks.celery_tasks.execute_query`` task. Returns
    True when the dispatch succeeded; False when celery is unavailable
    OR the broker rejected the call (admin_console ignored both)."""
    celery_app = _load_celery_app()
    if celery_app is None:
        return False
    queue = queue_for_target(target_llm)
    try:
        celery_app.send_task(
            TASK_NAME,
            args=[int(query_id)],
            queue=queue,
        )
    except Exception:
        return False
    return True


def dispatch_many(ids: list[Any]) -> tuple[int, int]:
    """Bulk dispatch. Returns ``(dispatched, dispatch_failed)``."""
    if not ids:
        return 0, 0
    celery_app = _load_celery_app()
    if celery_app is None:
        return 0, len(ids)
    dispatched = 0
    failed = 0
    for item in ids:
        try:
            qid, target_llm = _normalize_dispatch_item(item)
            celery_app.send_task(
                TASK_NAME,
                args=[qid],
                queue=queue_for_target(target_llm),
            )
            dispatched += 1
        except Exception:
            failed += 1
    return dispatched, failed


__all__ = ["dispatch_execute_query", "dispatch_many", "queue_for_target"]
