"""/v1/projects/:id/exports + /v1/brands/submissions + /v1/projects/:id/simulator/run

Phase E endpoints (PRD §4.7.4 / §4.7.5 / §4.7.6).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from genpano_models import User
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.exports._dto import (
    BrandSubmissionIn,
    BrandSubmissionOut,
    ExportJobIn,
    ExportJobOut,
    SimulatorBreakdown,
    SimulatorIn,
    SimulatorOut,
)
from app.api.v1.exports.service import (
    create_export_job,
    get_export_job,
    list_user_submissions,
    simulate_authority_boost,
    submit_brand,
)
from app.api.v1.projects.service import get_project_for_user
from app.core.security import _DependsDb, current_user

router = APIRouter(tags=["Exports"])


# ── Exports ──────────────────────────────────────────────────────


@router.post(
    "/{project_id}/exports",
    response_model=ExportJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_export(
    project_id: str,
    payload: ExportJobIn,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> ExportJobOut:
    project = await get_project_for_user(session, user, project_id)
    job = await create_export_job(
        session, project=project, user=user, export_type=payload.export_type, scope=payload.scope
    )
    return ExportJobOut.model_validate(job)


@router.get("/{project_id}/exports/{export_id}", response_model=ExportJobOut)
async def export_status(
    project_id: str,
    export_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> ExportJobOut:
    project = await get_project_for_user(session, user, project_id)
    job = await get_export_job(session, project=project, export_id=export_id)
    return ExportJobOut.model_validate(job)


# ── Simulator ────────────────────────────────────────────────────


@router.post("/{project_id}/simulator/run", response_model=SimulatorOut)
async def run_simulator(
    project_id: str,
    payload: SimulatorIn,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> SimulatorOut:
    """Authority boost simulation (PRD §4.7.6). Shared with MCP Phase M tool."""
    project = await get_project_for_user(session, user, project_id)
    result = await simulate_authority_boost(
        session,
        brand_id=payload.brand_id,
        delta_by_tier=payload.delta_by_tier,
        industry_id=project.industry_id,
        confidence_override=payload.confidence_override,
    )
    return SimulatorOut(
        current_pano_a=result["current_pano_a"],
        simulated_pano_a=result["simulated_pano_a"],
        delta=result["delta"],
        delta_breakdown=SimulatorBreakdown(**result["delta_breakdown"]),
        base_price_equivalent_cny=result["base_price_equivalent_cny"],
        confidence=result["confidence"],
    )


# ── Brand Submission ─────────────────────────────────────────────

submission_router = APIRouter(tags=["Brand Submissions"])


@submission_router.post(
    "/submissions",
    response_model=BrandSubmissionOut,
    status_code=status.HTTP_201_CREATED,
)
async def submit_brand_endpoint(
    payload: BrandSubmissionIn,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> BrandSubmissionOut:
    """User submits a new brand (PRD §4.7.5). admin reviews."""
    sub = await submit_brand(
        session,
        user=user,
        proposed_name=payload.proposed_name,
        proposed_industry_id=payload.proposed_industry_id,
        proposed_aliases=payload.proposed_aliases,
        proposed_official_domains=payload.proposed_official_domains,
        notes=payload.notes,
        source_url=payload.source_url,
    )
    return BrandSubmissionOut.model_validate(sub)


@submission_router.get("/me/submissions", response_model=list[BrandSubmissionOut])
async def list_my_submissions(
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> list[BrandSubmissionOut]:
    rows = await list_user_submissions(session, user=user)
    return [BrandSubmissionOut.model_validate(r) for r in rows]
