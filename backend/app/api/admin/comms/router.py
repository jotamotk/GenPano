"""Admin comms router (Phase O.3.2) — operator announcements CRUD + send.

Mounted at `/api/admin/comms`. Backed by `comms_announcements` table
(Phase O migration). Adheres to ADR-014 audit emit on all writes.

State machine (PRD §4.4.4):
  draft → scheduled → sending → sent
                    ↓
                cancelled
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from genpano_models import CommsAnnouncement, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.security import current_admin_operator
from app.core.errors import conflict, not_found, validation_error
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Comms"])

VALID_CHANNELS = {"inapp", "email", "both"}
VALID_AUDIENCES = {"all", "paid", "free", "operators"}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@router.get("/", response_model=None)
async def list_announcements(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    stmt = select(CommsAnnouncement).order_by(CommsAnnouncement.created_at.desc()).limit(limit)
    if status_filter:
        stmt = stmt.where(CommsAnnouncement.status == status_filter)
    rows = list((await session.execute(stmt)).scalars().all())
    items = [
        {
            "id": r.id,
            "title_zh": r.title_zh,
            "title_en": r.title_en,
            "channel": r.channel,
            "audience": r.audience,
            "status": r.status,
            "scheduled_at": r.scheduled_at.isoformat() if r.scheduled_at else None,
            "sent_at": r.sent_at.isoformat() if r.sent_at else None,
            "sent_count": r.sent_count,
        }
        for r in rows
    ]
    return {"items": items, "total": len(items)}


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=None)
async def create_announcement(
    request: Request,
    operator: Annotated[User, Depends(current_admin_operator)],
    payload: dict[str, Any],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Create a draft announcement."""
    channel = payload.get("channel")
    audience = payload.get("audience")
    if channel not in VALID_CHANNELS:
        raise validation_error("channel", f"must be one of {sorted(VALID_CHANNELS)}")
    if audience not in VALID_AUDIENCES:
        raise validation_error("audience", f"must be one of {sorted(VALID_AUDIENCES)}")

    row = CommsAnnouncement(
        title_zh=payload.get("title_zh"),
        title_en=payload.get("title_en"),
        body_zh=payload.get("body_zh"),
        body_en=payload.get("body_en"),
        channel=channel,
        audience=audience,
        status="draft",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    await emit_audit(
        session,
        operator=operator,
        action="comms_create",
        severity="low",
        resource_type="comms_announcement",
        resource_id=row.id,
        after={"channel": channel, "audience": audience, "status": "draft"},
        request=request,
    )

    return {"id": row.id, "status": row.status}


@router.patch("/{ann_id}", response_model=None)
async def update_announcement(
    ann_id: str,
    request: Request,
    operator: Annotated[User, Depends(current_admin_operator)],
    payload: dict[str, Any],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Update draft fields (title / body / channel / audience).

    Forbidden once status leaves 'draft' — content is locked at send time.
    """
    row = (
        await session.execute(select(CommsAnnouncement).where(CommsAnnouncement.id == ann_id))
    ).scalar_one_or_none()
    if row is None:
        raise not_found("announcement not found")
    if row.status != "draft":
        raise conflict("immutable_after_send", "announcement is no longer a draft")

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field in ("title_zh", "title_en", "body_zh", "body_en"):
        if field in payload:
            before[field] = getattr(row, field)
            setattr(row, field, payload[field])
            after[field] = payload[field]
    if "channel" in payload:
        if payload["channel"] not in VALID_CHANNELS:
            raise validation_error("channel", f"must be one of {sorted(VALID_CHANNELS)}")
        before["channel"] = row.channel
        row.channel = payload["channel"]
        after["channel"] = payload["channel"]
    if "audience" in payload:
        if payload["audience"] not in VALID_AUDIENCES:
            raise validation_error("audience", f"must be one of {sorted(VALID_AUDIENCES)}")
        before["audience"] = row.audience
        row.audience = payload["audience"]
        after["audience"] = payload["audience"]

    await session.commit()

    await emit_audit(
        session,
        operator=operator,
        action="comms_update",
        severity="low",
        resource_type="comms_announcement",
        resource_id=ann_id,
        before=before,
        after=after,
        request=request,
    )

    return {"id": row.id, "status": row.status}


@router.post("/{ann_id}/send", response_model=None)
async def send_announcement(
    ann_id: str,
    request: Request,
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Trigger send. State must be 'draft' or 'scheduled'.

    Phase O.3.2 marks status='sent' synchronously without actually fan-out;
    Phase RP.7 wires Celery batch sender — admin_audit_log already locked
    the high-risk surface.
    """
    row = (
        await session.execute(select(CommsAnnouncement).where(CommsAnnouncement.id == ann_id))
    ).scalar_one_or_none()
    if row is None:
        raise not_found("announcement not found")
    if row.status not in {"draft", "scheduled"}:
        raise conflict(
            "invalid_state",
            f"cannot send from status='{row.status}'",
        )

    row.status = "sent"
    row.sent_at = _now()
    # sent_count placeholder — Celery sender will overwrite
    row.sent_count = 0
    await session.commit()

    await emit_audit(
        session,
        operator=operator,
        action="comms_send",
        severity="med",
        resource_type="comms_announcement",
        resource_id=ann_id,
        after={"status": "sent", "sent_at": row.sent_at.isoformat()},
        request=request,
    )

    return {"id": row.id, "status": row.status, "sent_at": row.sent_at.isoformat()}


@router.post("/{ann_id}/cancel", response_model=None)
async def cancel_announcement(
    ann_id: str,
    request: Request,
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Cancel a draft / scheduled announcement (cannot cancel after sent)."""
    row = (
        await session.execute(select(CommsAnnouncement).where(CommsAnnouncement.id == ann_id))
    ).scalar_one_or_none()
    if row is None:
        raise not_found("announcement not found")
    if row.status in {"sent", "cancelled"}:
        raise conflict("invalid_state", f"cannot cancel from status='{row.status}'")

    before = {"status": row.status}
    row.status = "cancelled"
    await session.commit()

    await emit_audit(
        session,
        operator=operator,
        action="comms_cancel",
        severity="low",
        resource_type="comms_announcement",
        resource_id=ann_id,
        before=before,
        after={"status": "cancelled"},
        request=request,
    )

    return {"id": row.id, "status": row.status}
