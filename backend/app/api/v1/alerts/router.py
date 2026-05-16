"""Phase N alerts + notifications router."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from genpano_models import User
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.alerts._dto import (
    AlertListOut,
    AlertOut,
    AlertPatchIn,
    AlertRuleIn,
    AlertRuleOut,
    AlertSnoozeIn,
    NotificationPrefsOut,
    NotificationPrefsPatch,
    UnreadCountOut,
)
from app.api.v1.alerts.service import (
    create_rule,
    delete_rule,
    get_or_create_prefs,
    list_rules,
    list_user_alerts,
    mark_all_read,
    patch_alert_status,
    snooze_alert,
    unread_count,
    update_prefs,
)
from app.core.security import _DependsDb, current_user

router = APIRouter(tags=["Alerts"])


# ── /v1/alerts ───────────────────────────────────────────────────


@router.get("/", response_model=AlertListOut)
async def list_alerts(
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
    status: str | None = Query(None),
    severity: str | None = Query(None),
    project_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> AlertListOut:
    rows = await list_user_alerts(
        session,
        user=user,
        status=status,
        severity=severity,
        project_id=project_id,
        limit=limit,
    )
    items = [AlertOut.model_validate(r) for r in rows]
    return AlertListOut(items=items, total=len(items))


@router.get("/unread-count", response_model=UnreadCountOut)
async def alerts_unread_count(
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> UnreadCountOut:
    """Top-bar bell badge counter."""
    return UnreadCountOut(**(await unread_count(session, user=user)))


@router.patch("/{alert_id}", response_model=AlertOut)
async def update_alert(
    alert_id: str,
    payload: AlertPatchIn,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> AlertOut:
    alert = await patch_alert_status(
        session, user=user, alert_id=alert_id, new_status=payload.status
    )
    return AlertOut.model_validate(alert)


@router.post("/mark-all-read")
async def mark_all_read_endpoint(
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> dict[str, int]:
    return {"updated_count": await mark_all_read(session, user=user)}


@router.post("/{alert_id}/snooze", response_model=AlertOut)
async def snooze_alert_endpoint(
    alert_id: str,
    payload: AlertSnoozeIn,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> AlertOut:
    """Defer a non-urgent alert for `hours` (PRD §4.8.7 / AC-4.8-15).

    During the snooze window the alert is excluded from the bell-badge
    `unread_count`. When `snoozed_until` is reached, the next read of
    the alerts list lazily flips it back to `unread`.
    """
    alert = await snooze_alert(session, user=user, alert_id=alert_id, hours=payload.hours)
    return AlertOut.model_validate(alert)


# ── /v1/users/me/notifications ───────────────────────────────────

prefs_router = APIRouter(tags=["Notifications"])


@prefs_router.get("/notifications", response_model=NotificationPrefsOut)
async def get_prefs(
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> NotificationPrefsOut:
    prefs = await get_or_create_prefs(session, user=user)
    return NotificationPrefsOut.model_validate(prefs)


@prefs_router.patch("/notifications", response_model=NotificationPrefsOut)
async def patch_prefs(
    payload: NotificationPrefsPatch,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> NotificationPrefsOut:
    prefs = await update_prefs(
        session,
        user=user,
        fields=payload.model_dump(exclude_unset=True, exclude_none=True),
    )
    return NotificationPrefsOut.model_validate(prefs)


# ── /v1/users/me/alert-rules (Phase N beta) ──────────────────────


@prefs_router.get("/alert-rules", response_model=list[AlertRuleOut])
async def list_alert_rules(
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> list[AlertRuleOut]:
    rows = await list_rules(session, user=user)
    return [AlertRuleOut.model_validate(r) for r in rows]


@prefs_router.post(
    "/alert-rules",
    response_model=AlertRuleOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_alert_rule(
    payload: AlertRuleIn,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> AlertRuleOut:
    rule = await create_rule(
        session,
        user=user,
        rule_type=payload.rule_type,
        project_id=payload.project_id,
        conditions=payload.conditions,
        channels=payload.channels,
        enabled=payload.enabled,
    )
    return AlertRuleOut.model_validate(rule)


@prefs_router.delete("/alert-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_rule(
    rule_id: str,
    user: Annotated[User, Depends(current_user)],
    session: AsyncSession = _DependsDb,
) -> None:
    await delete_rule(session, user=user, rule_id=rule_id)
