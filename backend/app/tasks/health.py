"""Health-check Celery tasks.

heartbeat() is a no-op task used to verify Celery routing and broker
connectivity. Per Step 7 Path B (2026-04-27), it routes to the `beat`
queue rather than introducing a 7th catch-all `default` queue, honoring
REPLAN §4 Session 0' lines 82 and 362 (6-queue closed enumeration).
"""

from app.celery_app import celery_app


@celery_app.task(name="app.tasks.health.heartbeat")  # type: ignore[untyped-decorator]
def heartbeat() -> dict[str, str]:
    return {"status": "ok"}
