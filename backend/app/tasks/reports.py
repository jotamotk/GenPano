"""Phase RP.7 — Celery tasks for the report pipeline.

Three tasks are registered:

  - ``reports.generate(report_id)``
        Async wrapper around the existing report builder. Accepts a
        previously-queued ReportJob row id, calls the same service
        layer that the synchronous endpoint uses, marks the job
        ``done`` (or ``failed`` with error text). Idempotent: re-runs
        on a ``done`` job are no-ops.

  - ``reports.run_schedules()``
        Periodic dispatcher (Celery Beat). Scans
        ``report_schedules.next_run_at <= now()``, enqueues a
        ``reports.generate`` for each due schedule, and bumps
        ``next_run_at`` to the next cron tick.

  - ``reports.expire_share_tokens()``
        Daily housekeeping. Marks expired ``report_share_tokens`` rows
        with ``revoked_at = now()`` so public reads return 410 even if
        the row is still in the table.

All three tasks route to the ``beat`` queue (existing topology — see
``app/celery_app.py``). They reuse the existing service-layer functions
so business logic stays in one place.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update

from app.celery_app import celery_app
from app.core.config import get_settings


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _run_async(coro: Any) -> dict[str, Any]:  # pragma: no cover — thin wrapper
    """Run a coroutine from a sync Celery task body."""
    result: dict[str, Any] = asyncio.run(coro)
    return result


def _next_cron_tick(cron_expr: str | None, base: datetime) -> datetime:
    """Compute the next firing time for a cron expression after `base`.

    Falls back to base + 1 day when:
        - cron_expr is None / empty
        - the expression doesn't parse (malformed cron)

    The fallback keeps a misconfigured schedule visible (next run is
    tomorrow) instead of silently dropping it — operator can fix the
    cron string and the schedule resumes on its real cadence.
    """
    if not cron_expr:
        from datetime import timedelta as _td

        return base + _td(days=1)
    try:
        from croniter import croniter  # type: ignore[import-untyped]

        nxt: datetime = croniter(cron_expr, base).get_next(datetime)
        return nxt
    except Exception:
        from datetime import timedelta as _td

        return base + _td(days=1)


@celery_app.task(name="app.tasks.reports.generate", queue="beat")  # type: ignore[untyped-decorator]
def generate(report_id: str) -> dict[str, Any]:
    """Re-run the builder for an existing ReportJob row.

    Used by run_schedules() + by the upcoming admin re-trigger flow.
    The synchronous user-facing endpoint already inlines the build at
    creation time; this task path is used only for scheduled / manual
    re-builds.
    """

    async def _do() -> dict[str, Any]:
        from genpano_models import Project, ReportJob
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.api.v1.reports.service import _decode_scope
        from app.reports import build_report
        from app.reports.lead_diagnostic_builder import build_lead_diagnostic

        settings = get_settings()
        engine = create_async_engine(settings.database_url, future=True)
        sm = async_sessionmaker(engine, expire_on_commit=False)
        async with sm() as session:
            job = (
                await session.execute(select(ReportJob).where(ReportJob.id == report_id))
            ).scalar_one_or_none()
            if job is None:
                return {"status": "not_found", "report_id": report_id}
            if job.status == "done":
                return {"status": "already_done", "report_id": report_id}

            project = (
                await session.execute(select(Project).where(Project.id == job.project_id))
            ).scalar_one_or_none()
            if project is None:
                job.status = "failed"
                job.error = "underlying project missing"
                job.finished_at = _now()
                await session.commit()
                return {"status": "failed", "report_id": report_id}

            scope = _decode_scope(job.scope)
            rt = scope.get("report_type", "weekly")
            try:
                if rt == "lead_diagnostic":
                    await build_lead_diagnostic(
                        session, project=project, locale=scope.get("locale", "zh-CN")
                    )
                else:
                    await build_report(
                        session,
                        project=project,
                        report_type=rt,
                        locale=scope.get("locale", "zh-CN"),
                        reader_perspective=scope.get("reader_perspective", "manager"),
                    )
            except Exception as exc:  # pragma: no cover — defensive
                job.status = "failed"
                job.error = str(exc)[:500]
                job.finished_at = _now()
                await session.commit()
                return {"status": "failed", "report_id": report_id, "error": str(exc)}

            job.status = "done"
            job.finished_at = _now()
            await session.commit()
        await engine.dispose()
        return {"status": "done", "report_id": report_id}

    return _run_async(_do())


@celery_app.task(name="app.tasks.reports.run_schedules", queue="beat")  # type: ignore[untyped-decorator]
def run_schedules() -> dict[str, Any]:
    """Scan report_schedules and enqueue reports.generate for due rows."""

    async def _do() -> dict[str, Any]:
        from genpano_models import ReportJob, ReportSchedule
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        settings = get_settings()
        engine = create_async_engine(settings.database_url, future=True)
        sm = async_sessionmaker(engine, expire_on_commit=False)
        enqueued: list[str] = []
        async with sm() as session:
            now = _now()
            due = list(
                (
                    await session.execute(
                        select(ReportSchedule).where(
                            ReportSchedule.enabled.is_(True),
                            ReportSchedule.next_run_at <= now,
                        )
                    )
                )
                .scalars()
                .all()
            )
            for sched in due:
                # Create a queued ReportJob row pointing at this schedule.
                # generate() will pick it up from the queue.
                import uuid as _uuid

                job_id = str(_uuid.uuid4())
                session.add(
                    ReportJob(
                        id=job_id,
                        project_id=sched.project_id,
                        type="json",
                        scope=json.dumps(
                            {
                                "report_type": sched.report_type,
                                "locale": sched.locale or "zh-CN",
                                "reader_perspective": "manager",
                            }
                        ),
                        status="queued",
                        scheduled_cron=sched.cron,
                        created_by=None,
                    )
                )
                # Real cron evaluation via croniter. Falls back to
                # +1 day on parse error so a malformed cron doesn't
                # wedge the scheduler — operator sees the same row
                # next run + can fix the cron string.
                sched.next_run_at = _next_cron_tick(sched.cron, now)
                sched.last_run_at = now
                sched.last_run_id = job_id
                enqueued.append(job_id)
            await session.commit()

        for job_id in enqueued:
            generate.apply_async(args=[job_id], queue="beat")

        await engine.dispose()
        return {"enqueued": len(enqueued), "job_ids": enqueued}

    return _run_async(_do())


async def expire_share_tokens_in_session(session: Any) -> dict[str, Any]:
    """Sweep logic, factored out so tests can call it against the
    fixture-injected AsyncSession (audit #1044 B2-14). Marks every
    not-yet-revoked share token whose `expires_at` is in the past with
    `revoked_at = now()` and returns `{"expired_count": N}`.
    """
    from genpano_models import ReportShareToken

    now = _now()
    stmt = (
        update(ReportShareToken)
        .where(
            ReportShareToken.revoked_at.is_(None),
            ReportShareToken.expires_at < now,
        )
        .values(revoked_at=now)
    )
    res = await session.execute(stmt)
    await session.commit()
    count = getattr(res, "rowcount", 0) or 0
    return {"expired_count": int(count)}


@celery_app.task(name="app.tasks.reports.expire_share_tokens", queue="beat")  # type: ignore[untyped-decorator]
def expire_share_tokens() -> dict[str, Any]:
    """Mark expired share tokens with revoked_at so public reads return 410."""

    async def _do() -> dict[str, Any]:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        settings = get_settings()
        engine = create_async_engine(settings.database_url, future=True)
        sm = async_sessionmaker(engine, expire_on_commit=False)
        async with sm() as session:
            result = await expire_share_tokens_in_session(session)
        await engine.dispose()
        return result

    return _run_async(_do())
