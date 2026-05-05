"""/v1/leads router (Phase 4)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from genpano_models import User
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.leads._dto import LeadIn, LeadOut
from app.api.v1.leads.service import submit_lead
from app.core.security import _DependsDb, current_user

router = APIRouter(tags=["Leads"])


@router.post("/", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
async def create_lead(
    payload: LeadIn,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> LeadOut:
    """Submit a commercial lead. PRD §4.7.5 + §4.9 commercial funnel."""
    lead = await submit_lead(
        session,
        user_id=user.id,
        source=payload.source,
        project_id=payload.project_id,
        context=payload.context,
    )
    return LeadOut.model_validate(lead)
