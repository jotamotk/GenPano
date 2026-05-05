"""Service for /v1/leads (Phase 4 + Phase RP.8 auto-diagnostic)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from genpano_models import Project, ReportJob
from genpano_models.commercial_lead import CommercialLead
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def submit_lead(
    session: AsyncSession,
    *,
    user_id: str | None,
    source: str,
    project_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> CommercialLead:
    """Insert a commercial lead row.

    User can be None for anonymous CTA submissions (later linked when user
    registers). Status starts at 'new'.

    Phase RP.8: when a project_id is provided and resolves to a real
    project, also persist a 'done' `lead_diagnostic` ReportJob so the BD
    team has a 4-layer summary on contact. The payload is computed lazily
    (on report fetch) — this just creates the job row.
    """
    lead = CommercialLead(
        id=_new_id(),
        user_id=user_id,
        source=source,
        project_id=project_id,
        context=context,
        status="new",
    )
    session.add(lead)
    await session.commit()
    await session.refresh(lead)

    if project_id:
        await _try_create_lead_diagnostic_job(session, project_id=project_id, user_id=user_id)

    return lead


async def _try_create_lead_diagnostic_job(
    session: AsyncSession, *, project_id: str, user_id: str | None
) -> ReportJob | None:
    """Persist a 'done' lead_diagnostic ReportJob if the project exists."""
    project = (
        await session.execute(
            select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if project is None:
        return None

    job = ReportJob(
        id=_new_id(),
        project_id=project.id,
        type="json",
        scope=json.dumps(
            {
                "report_type": "lead_diagnostic",
                "locale": "zh-CN",
                "reader_perspective": "lead",
                "from_date": None,
                "to_date": None,
            }
        ),
        status="done",
        created_by=user_id,
        finished_at=_now(),
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job
