"""Pin the periodic stale-running sweep wired into celery beat.

Two assertions:

1. ``repair_stale_running_periodic`` is registered on Celery beat —
   without this the helper (which has lived in
   ``geo_tracker/tasks/stale_running_repair.py`` since the bestcoffer
   batch work) is unreachable from a running production worker because
   ``dispatch_batch`` (its only other caller) is itself not on beat.

2. Running the periodic task end-to-end against a database seeded with
   the actual broken-surface rows captured from production on
   2026-05-19 (workflow run 26073366807) does sweep them.

The fixture rows are not synthetic — query ids, target_llm, status,
account_id, retry_count, retry_reason, queued_at and started_at all
come from the live ``queries`` table readback. AGENTS.md Hard Rule 4
("test passing != bug fixed") requires at least one fixture tied to a
real captured value; this test ties three.
"""
from __future__ import annotations

import asyncio
import sys
import types
from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from geo_tracker.db.models import Base, Query, QueryStatus


def _install_fake_playwright(monkeypatch: pytest.MonkeyPatch) -> None:
    playwright_pkg = types.ModuleType("playwright")
    playwright_async = types.ModuleType("playwright.async_api")
    playwright_async.async_playwright = object
    playwright_async.BrowserContext = object
    playwright_async.ElementHandle = object
    playwright_async.Page = object
    playwright_async.TimeoutError = TimeoutError
    monkeypatch.setitem(sys.modules, "playwright", playwright_pkg)
    monkeypatch.setitem(sys.modules, "playwright.async_api", playwright_async)


class _TaskSessionContext:
    def __init__(self, maker):
        self.maker = maker
        self.session = None

    async def __aenter__(self):
        self.session = self.maker()
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        await self.session.close()
        return False


# Live production readback, workflow run 26073366807 step
# "queries rows for reported IDs":
#
#   id     | target_llm | status  | retry_count | retry_reason            | account_id | queued_at                  | started_at                 | finished_at                | latency_ms
#   185664 | chatgpt    | running | 5           | manual retry from admin | 17         | 2026-05-18 08:44:10.113858 | 2026-05-18 08:44:10.565495 |                            |
#   185661 | chatgpt    | running | 2           | manual retry from admin | 17         | 2026-05-18 08:44:13.881163 | 2026-05-18 08:44:14.030157 |                            |
#   185658 | chatgpt    | failed  | 2           | account_all_expired     | 17         | 2026-05-18 13:58:35.086046 | 2026-05-18 13:58:35.123052 | 2026-05-18 13:58:35.135707 | 12
#
# Probe timestamp 2026-05-19 02:57:12 UTC (sec_since_queued 65549 / 65545 / 46684).
LIVE_PROBE_NOW = datetime(2026, 5, 19, 2, 57, 12)
LIVE_Q_185664_QUEUED_AT = datetime(2026, 5, 18, 8, 44, 10, 113858)
LIVE_Q_185664_STARTED_AT = datetime(2026, 5, 18, 8, 44, 10, 565495)
LIVE_Q_185661_QUEUED_AT = datetime(2026, 5, 18, 8, 44, 13, 881163)
LIVE_Q_185661_STARTED_AT = datetime(2026, 5, 18, 8, 44, 14, 30157)
LIVE_Q_185658_QUEUED_AT = datetime(2026, 5, 18, 13, 58, 35, 86046)
LIVE_Q_185658_STARTED_AT = datetime(2026, 5, 18, 13, 58, 35, 123052)
LIVE_Q_185658_FINISHED_AT = datetime(2026, 5, 18, 13, 58, 35, 135707)


async def _seed_live_chatgpt_pipeline_state(db_url: str) -> None:
    engine = create_async_engine(db_url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        session.add_all(
            [
                Query(
                    id=185664,
                    target_llm="chatgpt",
                    query_text="非结构化数据AI脱敏准确率测评参考",
                    status=QueryStatus.RUNNING.value,
                    retry_count=5,
                    retry_reason="manual retry from admin",
                    account_id=17,
                    queued_at=LIVE_Q_185664_QUEUED_AT,
                    started_at=LIVE_Q_185664_STARTED_AT,
                ),
                Query(
                    id=185661,
                    target_llm="chatgpt",
                    query_text="非结构化数据AI脱敏准确率测评参考",
                    status=QueryStatus.RUNNING.value,
                    retry_count=2,
                    retry_reason="manual retry from admin",
                    account_id=17,
                    queued_at=LIVE_Q_185661_QUEUED_AT,
                    started_at=LIVE_Q_185661_STARTED_AT,
                ),
                Query(
                    id=185658,
                    target_llm="chatgpt",
                    query_text="非结构化数据AI脱敏准确率测评参考",
                    status=QueryStatus.FAILED.value,
                    retry_count=2,
                    retry_reason="account_all_expired",
                    account_id=17,
                    queued_at=LIVE_Q_185658_QUEUED_AT,
                    started_at=LIVE_Q_185658_STARTED_AT,
                    finished_at=LIVE_Q_185658_FINISHED_AT,
                    latency_ms=12,
                ),
            ]
        )
        await session.commit()
    await engine.dispose()


def test_repair_stale_running_periodic_is_on_beat_schedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_playwright(monkeypatch)
    from geo_tracker.tasks import celery_tasks

    schedule = celery_tasks.app.conf.get("beat_schedule") or {}
    entry = schedule.get("repair-stale-running")
    assert entry is not None, (
        "repair_stale_running_periodic must be on beat_schedule — otherwise "
        "the only caller of repair_stale_running_queries is dispatch_batch, "
        "which is itself unscheduled, so the sweep never runs in production."
    )
    assert entry["task"] == (
        "geo_tracker.tasks.celery_tasks.repair_stale_running_periodic"
    )


def test_periodic_sweep_clears_live_q185664_and_q185661_zombies(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _install_fake_playwright(monkeypatch)
    from geo_tracker.tasks import celery_tasks
    from geo_tracker.tasks import stale_running_repair as srr

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'chatgpt-pipeline-live.db'}"
    asyncio.run(_seed_live_chatgpt_pipeline_state(db_url))

    def create_engine():
        return create_async_engine(db_url, future=True)

    def get_session(engine):
        return _TaskSessionContext(async_sessionmaker(engine, expire_on_commit=False))

    monkeypatch.setattr(celery_tasks, "create_task_engine", create_engine)
    monkeypatch.setattr(celery_tasks, "get_task_async_session", get_session)
    # Pin "now" to the live probe timestamp so 18-hour-old rows are stale
    # under the default 3600s TTL and the 12ms-old failed row is untouched.
    monkeypatch.setattr(srr, "_utcnow_naive", lambda: LIVE_PROBE_NOW)

    result = celery_tasks.repair_stale_running_periodic.run()

    assert result["repaired"] == 2
    assert sorted(result["query_ids"]) == [185661, 185664]
    assert result["by_engine"] == {"chatgpt": 2}
    assert result["reason"] == "stale_running_timeout"
    assert result["dry_run"] is False

    async def _verify_rows() -> None:
        engine = create_async_engine(db_url, future=True)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            rows = (
                (await session.execute(select(Query).order_by(Query.id)))
                .scalars()
                .all()
            )
            by_id = {row.id: row for row in rows}

            assert by_id[185664].status == QueryStatus.FAILED.value
            assert by_id[185664].retry_reason == "stale_running_timeout"
            assert by_id[185664].finished_at == LIVE_PROBE_NOW
            # Latency must be wall-clock from started_at, not zero —
            # otherwise the sweep would look like a sub-second completion
            # in dashboards.
            expected_185664_latency = int(
                (LIVE_PROBE_NOW - LIVE_Q_185664_STARTED_AT).total_seconds() * 1000
            )
            assert by_id[185664].latency_ms == expected_185664_latency

            assert by_id[185661].status == QueryStatus.FAILED.value
            assert by_id[185661].retry_reason == "stale_running_timeout"
            assert by_id[185661].finished_at == LIVE_PROBE_NOW

            # The genuinely-failed row stays as captured — the sweep must
            # not touch terminal rows.
            assert by_id[185658].status == QueryStatus.FAILED.value
            assert by_id[185658].retry_reason == "account_all_expired"
            assert by_id[185658].finished_at == LIVE_Q_185658_FINISHED_AT
            assert by_id[185658].latency_ms == 12
        await engine.dispose()

    asyncio.run(_verify_rows())
