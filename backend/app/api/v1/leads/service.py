"""Service for /v1/leads (Phase 4)."""

from __future__ import annotations

import uuid
from typing import Any

from genpano_models.commercial_lead import CommercialLead
from sqlalchemy.ext.asyncio import AsyncSession


def _new_id() -> str:
    return str(uuid.uuid4())


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
    return lead
