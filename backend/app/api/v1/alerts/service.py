"""Phase N alerts + notification preferences service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from genpano_models import (
    Alert,
    AlertRule,
    Project,
    User,
    UserNotificationPreferences,
)
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import not_found


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ── Alerts ────────────────────────────────────────────────────────


async def list_user_alerts(
    session: AsyncSession,
    *,
    user: User,
    status: str | None = None,
    severity: str | None = None,
    project_id: str | None = None,
    limit: int = 50,
) -> list[Alert]:
    """List alerts visible to `user` (scope='user', optionally filtered).

    Phase N implementation: alerts are filtered by `project.user_id == user.id`
    via subquery on projects (since alerts have project_id but no user_id).
    """
    user_projects = (
        select(Project.id).where(and_(Project.user_id == user.id, Project.deleted_at.is_(None)))
    ).scalar_subquery()

    stmt = select(Alert).where(
        and_(
            Alert.scope == "user",
            Alert.project_id.in_(user_projects),
        )
    )
    if status:
        stmt = stmt.where(Alert.status == status)
    if severity:
        stmt = stmt.where(Alert.severity == severity)
    if project_id:
        stmt = stmt.where(Alert.project_id == project_id)
    stmt = stmt.order_by(Alert.triggered_at.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def unread_count(session: AsyncSession, *, user: User) -> dict[str, Any]:
    """Bell badge count + breakdown by severity."""
    user_projects = (
        select(Project.id).where(and_(Project.user_id == user.id, Project.deleted_at.is_(None)))
    ).scalar_subquery()

    stmt = (
        select(Alert.severity, func.count())
        .where(
            and_(
                Alert.scope == "user",
                Alert.status == "unread",
                Alert.project_id.in_(user_projects),
            )
        )
        .group_by(Alert.severity)
    )
    rows = (await session.execute(stmt)).all()
    by_sev = {sev: int(cnt) for sev, cnt in rows}
    return {
        "unread_count": sum(by_sev.values()),
        "by_severity": by_sev,
    }


async def patch_alert_status(
    session: AsyncSession,
    *,
    user: User,
    alert_id: str,
    new_status: str,
) -> Alert:
    """Update an alert's status. Multi-tenant guard: alert.project must be
    owned by user."""
    user_projects = (
        select(Project.id).where(and_(Project.user_id == user.id, Project.deleted_at.is_(None)))
    ).scalar_subquery()

    stmt = select(Alert).where(
        and_(
            Alert.id == alert_id,
            Alert.scope == "user",
            Alert.project_id.in_(user_projects),
        )
    )
    alert = (await session.execute(stmt)).scalar_one_or_none()
    if alert is None:
        raise not_found("alert not found")
    alert.status = new_status
    if new_status == "read" and alert.read_at is None:
        alert.read_at = _now()
        alert.read_by = user.id
    elif new_status == "resolved" and alert.resolved_at is None:
        alert.resolved_at = _now()
    await session.commit()
    await session.refresh(alert)
    return alert


async def mark_all_read(session: AsyncSession, *, user: User) -> int:
    """Bulk mark all unread user-scope alerts as read. Returns count."""
    user_projects = (
        select(Project.id).where(and_(Project.user_id == user.id, Project.deleted_at.is_(None)))
    ).scalar_subquery()

    stmt = select(Alert).where(
        and_(
            Alert.scope == "user",
            Alert.status == "unread",
            Alert.project_id.in_(user_projects),
        )
    )
    rows = list((await session.execute(stmt)).scalars().all())
    now = _now()
    for a in rows:
        a.status = "read"
        a.read_at = now
        a.read_by = user.id
    await session.commit()
    return len(rows)


# ── Notification preferences ──────────────────────────────────────


DEFAULT_PREFS = {
    "p0p1_alerts": True,
    "weekly_report": True,
    "competitor_alert": False,
    "email_locale": "zh-CN",
    "quiet_hours": None,
    "channels": ["email", "inapp"],
}


async def get_or_create_prefs(session: AsyncSession, *, user: User) -> UserNotificationPreferences:
    stmt = select(UserNotificationPreferences).where(UserNotificationPreferences.user_id == user.id)
    prefs = (await session.execute(stmt)).scalar_one_or_none()
    if prefs is not None:
        return prefs
    prefs = UserNotificationPreferences(
        user_id=user.id,
        **{k: v for k, v in DEFAULT_PREFS.items() if k != "channels"},
        channels=DEFAULT_PREFS["channels"],
    )
    session.add(prefs)
    await session.commit()
    await session.refresh(prefs)
    return prefs


async def update_prefs(
    session: AsyncSession,
    *,
    user: User,
    fields: dict[str, Any],
) -> UserNotificationPreferences:
    prefs = await get_or_create_prefs(session, user=user)
    for k, v in fields.items():
        if v is not None:
            setattr(prefs, k, v)
    prefs.updated_at = _now()
    await session.commit()
    await session.refresh(prefs)
    return prefs


# ── AlertRules ────────────────────────────────────────────────────


async def list_rules(session: AsyncSession, *, user: User) -> list[AlertRule]:
    stmt = (
        select(AlertRule).where(AlertRule.user_id == user.id).order_by(AlertRule.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def create_rule(
    session: AsyncSession,
    *,
    user: User,
    rule_type: str,
    project_id: str | None,
    conditions: dict[str, Any] | None,
    channels: list[str] | None,
    enabled: bool,
) -> AlertRule:
    rule = AlertRule(
        id=_new_id(),
        user_id=user.id,
        project_id=project_id,
        rule_type=rule_type,
        conditions=conditions,
        channels=channels,
        enabled=enabled,
    )
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return rule


async def delete_rule(session: AsyncSession, *, user: User, rule_id: str) -> None:
    stmt = select(AlertRule).where(and_(AlertRule.id == rule_id, AlertRule.user_id == user.id))
    rule = (await session.execute(stmt)).scalar_one_or_none()
    if rule is None:
        raise not_found("alert rule not found")
    await session.delete(rule)
    await session.commit()
