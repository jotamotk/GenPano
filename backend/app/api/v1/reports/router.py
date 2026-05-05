"""Phase RP.2 reports router — generate / list / share / public read."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from genpano_models import ReportJob, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.reports._dto import (
    PublicReportOut,
    ReportCreateIn,
    ReportDetailOut,
    ReportJobOut,
    ReportListOut,
    ReportShareIn,
    ReportShareOut,
)
from app.api.v1.reports.service import (
    create_job,
    create_share_token,
    get_job_with_payload,
    list_jobs,
    read_public_report,
    revoke_share_token,
)
from app.core.security import _DependsDb, current_user

router = APIRouter(tags=["Reports"])


def _to_out(job: ReportJob) -> ReportJobOut:
    return ReportJobOut(
        id=job.id,
        project_id=job.project_id,
        type=job.type,
        status=job.status,
        created_at=job.created_at,
        finished_at=job.finished_at,
        output_url=job.output_url,
        error=job.error,
    )


@router.get("/{project_id}/reports", response_model=ReportListOut)
async def list_my_reports(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    limit: int = 50,
) -> ReportListOut:
    rows = await list_jobs(session, user=user, project_id=project_id, limit=limit)
    items = [_to_out(r) for r in rows]
    return ReportListOut(items=items, total=len(items))


@router.post(
    "/{project_id}/reports",
    response_model=ReportDetailOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_my_report(
    project_id: str,
    payload: ReportCreateIn,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> ReportDetailOut:
    job, body = await create_job(
        session,
        user=user,
        project_id=project_id,
        report_type=payload.report_type,
        locale=payload.locale,
        reader_perspective=payload.reader_perspective,
        from_date=payload.from_date,
        to_date=payload.to_date,
    )
    out = _to_out(job)
    return ReportDetailOut(**out.model_dump(), payload=body)


@router.get(
    "/{project_id}/reports/{report_id}",
    response_model=ReportDetailOut,
)
async def get_my_report(
    project_id: str,
    report_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> ReportDetailOut:
    job, body = await get_job_with_payload(
        session, user=user, project_id=project_id, job_id=report_id
    )
    out = _to_out(job)
    return ReportDetailOut(**out.model_dump(), payload=body)


@router.post(
    "/{project_id}/reports/{report_id}/share",
    response_model=ReportShareOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_my_share_link(
    project_id: str,
    report_id: str,
    payload: ReportShareIn,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> ReportShareOut:
    row = await create_share_token(
        session,
        user=user,
        project_id=project_id,
        job_id=report_id,
        expires_in_hours=payload.expires_in_hours,
    )
    return ReportShareOut(
        token=row.token,
        url=f"/reports/public/{row.token}",
        expires_at=row.expires_at,
    )


@router.delete(
    "/{project_id}/reports/{report_id}/share/{token}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_my_share_link(
    project_id: str,
    report_id: str,
    token: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> None:
    await revoke_share_token(
        session,
        user=user,
        project_id=project_id,
        job_id=report_id,
        token=token,
    )


# ── Public (no auth) ────────────────────────────────────────────


public_router = APIRouter(tags=["Reports (public)"])


@public_router.get("/{token}", response_model=PublicReportOut)
async def public_report(
    token: str,
    session: AsyncSession = _DependsDb,
) -> PublicReportOut:
    row, payload = await read_public_report(session, token=token)
    return PublicReportOut(
        payload=payload,
        expires_at=row.expires_at,
        view_count=row.view_count,
    )
