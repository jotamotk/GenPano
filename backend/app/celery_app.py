"""Celery application factory for the GENPANO Pipeline workers.

Defines the canonical 6-queue topology for background workers.
§4 Session 0' Step 7 (lines 82 and 362, both enumerate exactly the same
6 names -- treated as a closed enumeration).

Queue topology:
    llm_chatgpt    -- ChatGPT adapter execute() workload
    llm_doubao     -- Doubao adapter execute() workload
    llm_deepseek   -- DeepSeek-CN adapter execute() workload
    analysis       -- brand_detector + sentiment + citation_extractor pipeline
    account_login  -- Camoufox + Luban SMS auto-register + cookie injection
    beat           -- Celery Beat scheduler tick + heartbeat probe + cron tasks

Step 7 declares topology only. No worker is started here; that lands in
docker-compose.preview.yml during Step 11 (`verify-session-0prime.sh`).

Path B routing decision (Step 7 arbitration, 2026-04-27):
    The `heartbeat` health-check task routes to the `beat` queue rather
    than introducing a 7th catch-all `default` queue. This honors REPLAN's
    closed 6-queue enumeration; Celery Beat's scheduler semantics naturally
    contain heartbeat / cron-style ticks.
"""

from celery import Celery
from celery.schedules import crontab
from kombu import Queue

from app.core.config import get_settings


def _build_celery_app() -> Celery:
    settings = get_settings()
    app = Celery(
        "genpano",
        broker=settings.redis_url,
        backend=settings.redis_url,
        include=["app.tasks.health", "geo_tracker.tasks.scheduler"],
    )

    app.conf.task_queues = (
        Queue("llm_chatgpt", routing_key="llm_chatgpt"),
        Queue("llm_doubao", routing_key="llm_doubao"),
        Queue("llm_deepseek", routing_key="llm_deepseek"),
        Queue("analysis", routing_key="analysis"),
        Queue("account_login", routing_key="account_login"),
        Queue("beat", routing_key="beat"),
    )

    app.conf.task_routes = {
        "app.tasks.health.heartbeat": {"queue": "beat", "routing_key": "beat"},
        "geo_tracker.tasks.scheduler.run_daily_dispatch": {
            "queue": "beat", "routing_key": "beat"
        },
    }

    app.conf.task_default_queue = "beat"
    app.conf.task_default_routing_key = "beat"
    app.conf.task_acks_late = True
    app.conf.worker_prefetch_multiplier = 1
    app.conf.timezone = "UTC"

    # Daily dispatch tick at 01:00 UTC = 09:00 Asia/Shanghai (the default
    # config.daily_time). The task itself re-reads scheduler_config and
    # short-circuits when mode is 'paused' or when the configured
    # daily_time has already been processed today, so a coarser cron is fine.
    app.conf.beat_schedule = {
        "scheduler-daily-dispatch": {
            "task": "geo_tracker.tasks.scheduler.run_daily_dispatch",
            "schedule": crontab(minute=0, hour=1),
            "options": {"queue": "beat", "routing_key": "beat"},
        },
    }

    return app


celery_app = _build_celery_app()
