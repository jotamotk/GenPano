"""Phase B3-1 — alert delivery (email + future webhook) per PRD §4.8.9.

Closes audit #1044 B3-1. Previously `create_alert_from_diagnostic` only
wrote a DB row; the user's `UserNotificationPreferences.channels` were
read by no caller. This module is the dispatch layer:

  1. Load the project owner + their `UserNotificationPreferences`.
  2. Honor `p0p1_alerts` (only fire for P0/P1 if the toggle is on).
  3. Honor `quiet_hours` — P0 may override (env
     `ALERT_DISPATCH_P0_OVERRIDE_QUIET` default true; PRD AC-4.8-18).
  4. For each enabled channel, call the channel-specific sender.
     - `inapp` is implicit (the Alert row IS the in-app surface; no
       dispatch action).
     - `email` builds a locale-aware subject + body and calls the
       low-level `app.user_auth.email._send`.
     - `webhook` is not yet implemented — flagged in the result and
       tracked for the future PR (§4.8.9 declares it "未来").

Best-effort: dispatch failure MUST NOT roll back the Alert row. Callers
wrap in try/except (mirroring `create_alert_from_diagnostic` semantics).

Spec anchors:
  - PRD AC-4.8-16: end-to-end P0 dispatch must trigger one email
    within 60s with subject containing brand name + `[紧急]` prefix.
  - PRD AC-4.8-17: P1 during `quiet_hours` is suppressed (not sent).
  - PRD AC-4.8-18: P0 sends during `quiet_hours` by default.
  - PRD AC-4.8-19: prefs structure mirrors the existing
    `UserNotificationPreferences` ORM.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Any

from genpano_models import (
    Alert,
    Project,
    User,
    UserNotificationPreferences,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


@dataclass
class DispatchResult:
    """Per-alert dispatch outcome surfaced to caller + tests.

    Channels are recorded individually:
        channel='email' delivered=True   → SMTP call succeeded
        channel='email' delivered=False  → skipped (prefs/quiet/no-provider)
        channel='inapp' delivered=True   → always (row exists already)
        channel='webhook' delivered=False reason='not_implemented'
    """

    alert_id: str
    severity: str
    channel_results: list[dict[str, Any]]
    skipped_reason: str | None = None

    @property
    def email_delivered(self) -> bool:
        return any(
            c.get("channel") == "email" and c.get("delivered") is True for c in self.channel_results
        )


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _in_quiet_hours(prefs_quiet_hours: dict[str, Any] | None, now: datetime) -> bool:
    """Return True when `now` falls inside the user's quiet window.

    `quiet_hours` shape: `{"from": "22:00", "to": "08:00"}`. Window may
    span midnight; we handle both same-day and overnight cases.
    """
    if not prefs_quiet_hours:
        return False
    raw_from = prefs_quiet_hours.get("from")
    raw_to = prefs_quiet_hours.get("to")
    if not raw_from or not raw_to:
        return False
    try:
        from_t = time.fromisoformat(str(raw_from))
        to_t = time.fromisoformat(str(raw_to))
    except (ValueError, TypeError):
        return False
    now_t = now.time()
    if from_t <= to_t:
        return from_t <= now_t < to_t
    # Overnight (e.g. 22:00 → 08:00)
    return now_t >= from_t or now_t < to_t


def _p0_overrides_quiet() -> bool:
    """Per AC-4.8-18, P0 sends through quiet hours by default. Operators
    may flip the env var to suppress P0 too."""
    raw = os.environ.get("ALERT_DISPATCH_P0_OVERRIDE_QUIET", "true").lower()
    return raw not in {"0", "false", "no", "off"}


async def _load_owner(session: AsyncSession, *, project_id: str | None) -> User | None:
    if not project_id:
        return None
    stmt = select(User).join(Project, Project.user_id == User.id).where(Project.id == project_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def _load_prefs(session: AsyncSession, *, user_id: str) -> UserNotificationPreferences | None:
    stmt = select(UserNotificationPreferences).where(UserNotificationPreferences.user_id == user_id)
    return (await session.execute(stmt)).scalar_one_or_none()


def _build_email_subject(severity: str, title: str, locale: str) -> str:
    """PRD AC-4.8-16: subject contains severity prefix + alert title.

    P0 → "[紧急]" / "[URGENT]"
    P1 → "[重要]" / "[IMPORTANT]"
    Other severities ride through (this dispatcher only fires for P0/P1
    when `p0p1_alerts=True`, but we keep the function safe for any
    severity).
    """
    is_zh = locale.startswith("zh")
    label = {
        "P0": "[紧急]" if is_zh else "[URGENT]",
        "P1": "[重要]" if is_zh else "[IMPORTANT]",
    }.get(severity, "[GenPano]")
    return f"{label} {title}"


def _build_email_text(alert: Alert, locale: str) -> str:
    is_zh = locale.startswith("zh")
    parts = [
        alert.title,
        "",
        (alert.body or "")
        if (alert.body or "").strip()
        else ("本期诊断触发了告警。" if is_zh else "A diagnostic triggered this alert."),
        "",
        "──────────",
        (f"严重度: {alert.severity}" if is_zh else f"Severity: {alert.severity}"),
        (
            f"项目: {alert.project_id or '(none)'}"
            if is_zh
            else f"Project: {alert.project_id or '(none)'}"
        ),
        (
            f"触发时间: {alert.triggered_at.isoformat()}"
            if is_zh
            else f"Triggered: {alert.triggered_at.isoformat()}"
        ),
    ]
    return "\n".join(parts)


def _build_email_html(alert: Alert, locale: str) -> str:
    is_zh = locale.startswith("zh")
    body_zh_default = "本期诊断触发了告警,请登录 GenPano 查看详情。"
    body_en_default = "A diagnostic triggered this alert. Open GenPano to review."
    body = (alert.body or "").strip() or (body_zh_default if is_zh else body_en_default)
    return (
        f"<h2>{alert.title}</h2>"
        f"<p>{body}</p>"
        f"<ul>"
        f"<li>{'严重度' if is_zh else 'Severity'}: <b>{alert.severity}</b></li>"
        f"<li>{'项目' if is_zh else 'Project'}: {alert.project_id or '-'}</li>"
        f"<li>{'触发时间' if is_zh else 'Triggered'}: {alert.triggered_at.isoformat()}</li>"
        f"</ul>"
    )


async def dispatch_alert(
    session: AsyncSession,
    alert: Alert,
    *,
    now: datetime | None = None,
) -> DispatchResult:
    """Deliver `alert` through the project owner's enabled channels.

    Returns a `DispatchResult` summarizing each channel. Never raises —
    failures are logged + recorded in the result. Caller treats this as
    best-effort.
    """
    when = now or _now()
    channel_results: list[dict[str, Any]] = []

    owner = await _load_owner(session, project_id=alert.project_id)
    if owner is None:
        return DispatchResult(
            alert_id=alert.id,
            severity=alert.severity,
            channel_results=channel_results,
            skipped_reason="no_owner",
        )

    prefs = await _load_prefs(session, user_id=owner.id)
    if prefs is None:
        # No prefs row → default behavior: email + inapp on for P0/P1.
        channels = ["email", "inapp"]
        p0p1_only = True
        quiet_hours = None
        email_locale = owner.locale or "zh-CN"
    else:
        channels = list(prefs.channels or ["email", "inapp"])
        p0p1_only = bool(prefs.p0p1_alerts)
        quiet_hours = prefs.quiet_hours
        email_locale = prefs.email_locale or owner.locale or "zh-CN"

    if p0p1_only and alert.severity not in {"P0", "P1"}:
        return DispatchResult(
            alert_id=alert.id,
            severity=alert.severity,
            channel_results=channel_results,
            skipped_reason="severity_below_p0p1_threshold",
        )

    if _in_quiet_hours(quiet_hours, when):
        if not (alert.severity == "P0" and _p0_overrides_quiet()):
            return DispatchResult(
                alert_id=alert.id,
                severity=alert.severity,
                channel_results=channel_results,
                skipped_reason="quiet_hours",
            )

    for channel in channels:
        if channel == "inapp":
            # The Alert row IS the in-app surface. Record success.
            channel_results.append({"channel": "inapp", "delivered": True})
            continue
        if channel == "email":
            result = await _dispatch_email(alert=alert, owner=owner, locale=email_locale)
            channel_results.append(result)
            continue
        if channel == "webhook":
            channel_results.append(
                {
                    "channel": "webhook",
                    "delivered": False,
                    "reason": "not_implemented",
                }
            )
            continue
        channel_results.append(
            {"channel": channel, "delivered": False, "reason": "unknown_channel"}
        )

    return DispatchResult(
        alert_id=alert.id,
        severity=alert.severity,
        channel_results=channel_results,
    )


async def _dispatch_email(*, alert: Alert, owner: User, locale: str) -> dict[str, Any]:
    """Send the alert as an email to the project owner. Wraps the user-auth
    email module's low-level `_send` so we share SMTP/provider config."""
    try:
        from app.user_auth.email import _send
    except Exception as exc:  # pragma: no cover — defensive
        log.warning("alert_email.import_failed: %s", exc)
        return {"channel": "email", "delivered": False, "reason": "import_failed"}

    subject = _build_email_subject(alert.severity, alert.title, locale)
    html = _build_email_html(alert, locale)
    text = _build_email_text(alert, locale)

    try:
        result = _send(
            to=owner.email,
            subject=subject,
            html=html,
            text=text,
            locale=locale,  # type: ignore[arg-type]
        )
    except Exception as exc:
        log.warning(
            "alert_email.send_failed",
            extra={
                "alert_id": alert.id,
                "to": owner.email,
                "error": str(exc),
            },
        )
        return {"channel": "email", "delivered": False, "reason": "exception"}

    return {
        "channel": "email",
        "delivered": bool(getattr(result, "delivered", False)),
        "provider_message_id": getattr(result, "provider_message_id", None),
        "subject": subject,
    }
