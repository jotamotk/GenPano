"""Phase RP.2 reports service — orchestrates ReportJob lifecycle + share tokens."""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from genpano_models import Project, ReportJob, ReportShareToken, User
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects.service import get_project_for_user
from app.core.errors import gone, not_found, validation_error
from app.reports import build_report
from app.reports.lead_diagnostic_builder import build_lead_diagnostic

VALID_REPORT_TYPES: set[str] = {"weekly", "monthly", "on_demand", "lead_diagnostic"}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _new_id() -> str:
    return str(uuid.uuid4())


async def list_jobs(
    session: AsyncSession, *, user: User, project_id: str, limit: int = 50
) -> list[ReportJob]:
    project = await get_project_for_user(session, user, project_id)
    stmt = (
        select(ReportJob)
        .where(ReportJob.project_id == project.id)
        .order_by(ReportJob.created_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def create_job(
    session: AsyncSession,
    *,
    user: User,
    project_id: str,
    report_type: str,
    locale: str,
    reader_perspective: str,
    from_date: Any | None,
    to_date: Any | None,
) -> tuple[ReportJob, dict[str, Any]]:
    """Build report payload synchronously, persist as 'done' job + return payload.

    Phase RP.2 inlines build_report (no Celery yet) — sufficient to wire FE
    end-to-end. Phase RP.7 splits to async background task.
    """
    if report_type not in VALID_REPORT_TYPES:
        raise validation_error(
            "report_type",
            f"must be one of {sorted(VALID_REPORT_TYPES)}",
        )

    project = await get_project_for_user(session, user, project_id)

    if report_type == "lead_diagnostic":
        # Phase RP.8 — dedicated 4-layer view, NOT SECTION_MATRIX
        payload = await build_lead_diagnostic(session, project=project, locale=locale)
    else:
        payload = await build_report(
            session,
            project=project,
            report_type=report_type,
            locale=locale,
            reader_perspective=reader_perspective,
            from_date=from_date,
            to_date=to_date,
        )

    job = ReportJob(
        id=_new_id(),
        project_id=project.id,
        type="json",
        scope=json.dumps(
            {
                "report_type": report_type,
                "locale": locale,
                "reader_perspective": reader_perspective,
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
            }
        ),
        status="done",
        output_url=None,  # Phase RP.5 wires S3 URL when async pipeline lands
        created_by=user.id,
        finished_at=_now(),
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job, payload


async def get_job_with_payload(
    session: AsyncSession, *, user: User, project_id: str, job_id: str
) -> tuple[ReportJob, dict[str, Any] | None]:
    project = await get_project_for_user(session, user, project_id)

    stmt = select(ReportJob).where(and_(ReportJob.id == job_id, ReportJob.project_id == project.id))
    job = (await session.execute(stmt)).scalar_one_or_none()
    if job is None:
        raise not_found("report not found")

    payload: dict[str, Any] | None = None
    if job.status == "done":
        scope = _decode_scope(job.scope)
        rt = scope.get("report_type", "weekly")
        if rt == "lead_diagnostic":
            payload = await build_lead_diagnostic(
                session,
                project=project,
                locale=scope.get("locale", "zh-CN"),
            )
        else:
            payload = await build_report(
                session,
                project=project,
                report_type=rt,
                locale=scope.get("locale", "zh-CN"),
                reader_perspective=scope.get("reader_perspective", "manager"),
            )
    return job, payload


async def create_share_token(
    session: AsyncSession,
    *,
    user: User,
    project_id: str,
    job_id: str,
    expires_in_hours: int,
) -> ReportShareToken:
    project = await get_project_for_user(session, user, project_id)
    stmt = select(ReportJob).where(and_(ReportJob.id == job_id, ReportJob.project_id == project.id))
    if (await session.execute(stmt)).scalar_one_or_none() is None:
        raise not_found("report not found")

    token = secrets.token_urlsafe(32)
    row = ReportShareToken(
        token=token,
        report_id=job_id,
        expires_at=_now() + timedelta(hours=expires_in_hours),
        created_by=user.id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def revoke_share_token(
    session: AsyncSession,
    *,
    user: User,
    project_id: str,
    job_id: str,
    token: str,
) -> None:
    project = await get_project_for_user(session, user, project_id)
    rep_stmt = select(ReportJob).where(
        and_(ReportJob.id == job_id, ReportJob.project_id == project.id)
    )
    if (await session.execute(rep_stmt)).scalar_one_or_none() is None:
        raise not_found("share token not found")
    stmt = select(ReportShareToken).where(
        and_(ReportShareToken.token == token, ReportShareToken.report_id == job_id)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise not_found("share token not found")
    row.revoked_at = _now()
    await session.commit()


async def read_public_report(
    session: AsyncSession, *, token: str
) -> tuple[ReportShareToken, dict[str, Any]]:
    """Public access (no auth) — increments view_count. 410 if expired/revoked."""
    stmt = select(ReportShareToken).where(ReportShareToken.token == token)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise not_found("share link not found")
    if row.revoked_at is not None:
        raise gone("share link revoked")
    if row.expires_at < _now():
        raise gone("share link expired")

    job_stmt = select(ReportJob).where(ReportJob.id == row.report_id)
    job = (await session.execute(job_stmt)).scalar_one_or_none()
    if job is None:
        raise not_found("underlying report not found")
    proj_stmt = select(Project).where(Project.id == job.project_id)
    project = (await session.execute(proj_stmt)).scalar_one_or_none()
    if project is None:
        raise not_found("underlying project not found")

    scope = _decode_scope(job.scope)
    rt = scope.get("report_type", "weekly")
    if rt == "lead_diagnostic":
        payload = await build_lead_diagnostic(
            session,
            project=project,
            locale=scope.get("locale", "zh-CN"),
        )
    else:
        payload = await build_report(
            session,
            project=project,
            report_type=rt,
            locale=scope.get("locale", "zh-CN"),
            reader_perspective=scope.get("reader_perspective", "manager"),
        )

    row.view_count = (row.view_count or 0) + 1
    await session.commit()
    await session.refresh(row)
    return row, payload


def _decode_scope(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}
