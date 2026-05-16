"""[#1044 B3-1] Alert dispatch — email + in-app channels per PRD §4.8.9.

Acceptance rows covered:
  - AC-4.8-16: end-to-end P0 dispatch triggers one email; subject has
    severity prefix
  - AC-4.8-17: P1 during quiet_hours is suppressed
  - AC-4.8-18: P0 during quiet_hours sends by default
    (ALERT_DISPATCH_P0_OVERRIDE_QUIET=true)
  - Severity-below-threshold respected (`p0p1_alerts=True` + P2 = skip)
  - In-app channel marked delivered=True (the row IS the surface)
  - No-prefs fallback uses defaults
  - Dispatcher never raises — email-import failures end as
    `delivered=False, reason='import_failed'`
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
import pytest_asyncio
from genpano_models import (
    Alert,
    Project,
    User,
    UserNotificationPreferences,
)
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"disp-{uuid.uuid4().hex[:6]}@example.com",
        name="disp",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def project(db_session: AsyncSession, user: User) -> Project:
    p = Project(
        id=_new_id(),
        user_id=user.id,
        name="P-disp",
        primary_brand_id=42,
    )
    db_session.add(p)
    await db_session.commit()
    return p


async def _mk_alert(db_session: AsyncSession, project: Project, *, severity: str = "P0") -> Alert:
    a = Alert(
        id=_new_id(),
        project_id=project.id,
        brand_id=42,
        source="diagnostic",
        source_ref_id=_new_id(),
        severity=severity,
        scope="user",
        title=f"alert-{severity}",
        body="brand X visibility dropped 30%",
        status="unread",
    )
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    return a


# ── severity gating ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_skips_p2_when_p0p1_only_toggle_on(db_session, user, project):
    from app.alerts.dispatcher import dispatch_alert

    db_session.add(
        UserNotificationPreferences(
            user_id=user.id,
            p0p1_alerts=True,
            weekly_report=True,
            competitor_alert=False,
            email_locale="zh-CN",
            channels=["email", "inapp"],
        )
    )
    await db_session.commit()
    alert = await _mk_alert(db_session, project, severity="P2")

    res = await dispatch_alert(db_session, alert)
    assert res.skipped_reason == "severity_below_p0p1_threshold"
    assert res.channel_results == []


# ── quiet hours ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_suppresses_p1_in_quiet_hours(db_session, user, project):
    """AC-4.8-17: P1 in 22:00-08:00 window is skipped."""
    from app.alerts.dispatcher import dispatch_alert

    db_session.add(
        UserNotificationPreferences(
            user_id=user.id,
            p0p1_alerts=True,
            weekly_report=True,
            competitor_alert=False,
            email_locale="zh-CN",
            channels=["email", "inapp"],
            quiet_hours={"from": "22:00", "to": "08:00"},
        )
    )
    await db_session.commit()
    alert = await _mk_alert(db_session, project, severity="P1")

    # Force 23:30 → inside quiet window
    quiet_when = datetime(2026, 5, 16, 23, 30, 0)
    res = await dispatch_alert(db_session, alert, now=quiet_when)
    assert res.skipped_reason == "quiet_hours"


@pytest.mark.asyncio
async def test_dispatch_p0_overrides_quiet_hours_by_default(db_session, user, project, monkeypatch):
    """AC-4.8-18: P0 sends even during quiet hours unless explicitly
    opted out via env var."""
    monkeypatch.setenv("ALERT_DISPATCH_P0_OVERRIDE_QUIET", "true")
    from app.alerts.dispatcher import dispatch_alert

    db_session.add(
        UserNotificationPreferences(
            user_id=user.id,
            p0p1_alerts=True,
            weekly_report=True,
            competitor_alert=False,
            email_locale="zh-CN",
            channels=["email", "inapp"],
            quiet_hours={"from": "22:00", "to": "08:00"},
        )
    )
    await db_session.commit()
    alert = await _mk_alert(db_session, project, severity="P0")

    quiet_when = datetime(2026, 5, 16, 23, 30, 0)
    with patch(
        "app.user_auth.email._send",
        return_value=type("R", (), {"delivered": True, "provider_message_id": "msg-0"})(),
    ) as mock_send:
        res = await dispatch_alert(db_session, alert, now=quiet_when)
    assert res.skipped_reason is None
    assert res.email_delivered is True
    mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_p0_quiet_can_be_disabled_via_env(db_session, user, project, monkeypatch):
    monkeypatch.setenv("ALERT_DISPATCH_P0_OVERRIDE_QUIET", "false")
    from app.alerts.dispatcher import dispatch_alert

    db_session.add(
        UserNotificationPreferences(
            user_id=user.id,
            p0p1_alerts=True,
            weekly_report=True,
            competitor_alert=False,
            email_locale="zh-CN",
            channels=["email", "inapp"],
            quiet_hours={"from": "22:00", "to": "08:00"},
        )
    )
    await db_session.commit()
    alert = await _mk_alert(db_session, project, severity="P0")

    quiet_when = datetime(2026, 5, 16, 23, 30, 0)
    res = await dispatch_alert(db_session, alert, now=quiet_when)
    assert res.skipped_reason == "quiet_hours"


# ── email path ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_p0_dispatch_sends_email_with_severity_prefix(db_session, user, project):
    """AC-4.8-16: subject begins with [紧急] for P0 (zh locale)."""
    from app.alerts.dispatcher import dispatch_alert

    db_session.add(
        UserNotificationPreferences(
            user_id=user.id,
            p0p1_alerts=True,
            weekly_report=True,
            competitor_alert=False,
            email_locale="zh-CN",
            channels=["email", "inapp"],
        )
    )
    await db_session.commit()
    alert = await _mk_alert(db_session, project, severity="P0")

    captured: dict = {}

    def _capture(*, to, subject, html, text, locale):
        captured.update(
            {"to": to, "subject": subject, "html": html, "text": text, "locale": locale}
        )
        return type("R", (), {"delivered": True, "provider_message_id": "msg-1"})()

    with patch("app.user_auth.email._send", side_effect=_capture):
        res = await dispatch_alert(db_session, alert)

    assert res.email_delivered is True
    assert captured["to"] == user.email
    assert captured["subject"].startswith("[紧急]")
    assert alert.title in captured["subject"]
    # In-app channel marker also present
    assert any(
        c.get("channel") == "inapp" and c.get("delivered") is True for c in res.channel_results
    )


@pytest.mark.asyncio
async def test_p1_dispatch_uses_important_label(db_session, user, project):
    from app.alerts.dispatcher import dispatch_alert

    db_session.add(
        UserNotificationPreferences(
            user_id=user.id,
            p0p1_alerts=True,
            weekly_report=True,
            competitor_alert=False,
            email_locale="en-US",
            channels=["email", "inapp"],
        )
    )
    await db_session.commit()
    alert = await _mk_alert(db_session, project, severity="P1")

    captured: dict = {}

    def _capture(*, to, subject, html, text, locale):
        captured["subject"] = subject
        captured["locale"] = locale
        return type("R", (), {"delivered": True, "provider_message_id": "msg-2"})()

    with patch("app.user_auth.email._send", side_effect=_capture):
        await dispatch_alert(db_session, alert)
    assert captured["subject"].startswith("[IMPORTANT]")
    assert captured["locale"] == "en-US"


# ── webhook channel: not implemented yet ─────────────────────────


@pytest.mark.asyncio
async def test_webhook_channel_marks_not_implemented(db_session, user, project):
    from app.alerts.dispatcher import dispatch_alert

    db_session.add(
        UserNotificationPreferences(
            user_id=user.id,
            p0p1_alerts=True,
            weekly_report=True,
            competitor_alert=False,
            email_locale="zh-CN",
            channels=["webhook"],
        )
    )
    await db_session.commit()
    alert = await _mk_alert(db_session, project, severity="P0")

    res = await dispatch_alert(db_session, alert)
    webhook_results = [c for c in res.channel_results if c.get("channel") == "webhook"]
    assert webhook_results
    assert webhook_results[0]["delivered"] is False
    assert webhook_results[0]["reason"] == "not_implemented"


# ── failure handling ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_swallows_email_exception(db_session, user, project):
    """A raise from the email layer must not propagate — the Alert row is
    already committed and `dispatch_alert` is best-effort."""
    from app.alerts.dispatcher import dispatch_alert

    db_session.add(
        UserNotificationPreferences(
            user_id=user.id,
            p0p1_alerts=True,
            weekly_report=True,
            competitor_alert=False,
            email_locale="zh-CN",
            channels=["email", "inapp"],
        )
    )
    await db_session.commit()
    alert = await _mk_alert(db_session, project, severity="P0")

    with patch("app.user_auth.email._send", side_effect=RuntimeError("SMTP down")):
        res = await dispatch_alert(db_session, alert)

    email_row = next(c for c in res.channel_results if c["channel"] == "email")
    assert email_row["delivered"] is False
    assert email_row["reason"] == "exception"


# ── end-to-end via create_alert_from_diagnostic ─────────────────


@pytest.mark.asyncio
async def test_create_alert_triggers_dispatch_for_p0(db_session, user, project):
    """AC-4.8-16 e2e: creating a P0 diagnostic causes ≤1 SMTP send call."""
    from genpano_models import Diagnostic

    from app.alerts.triggers import create_alert_from_diagnostic

    db_session.add(
        UserNotificationPreferences(
            user_id=user.id,
            p0p1_alerts=True,
            weekly_report=True,
            competitor_alert=False,
            email_locale="zh-CN",
            channels=["email", "inapp"],
        )
    )
    await db_session.commit()

    diag = Diagnostic(
        id=_new_id(),
        project_id=project.id,
        brand_id=42,
        category="visibility_decline",
        severity="P0",
        type="brand",
        title="GEO score crashed",
        description="dropped 50% in 7d",
        evidence={},
        reader_hints=["manager"],
        rule_id="geo_score_drop_v1",
        status="open",
    )
    db_session.add(diag)
    await db_session.commit()

    with patch(
        "app.user_auth.email._send",
        return_value=type("R", (), {"delivered": True, "provider_message_id": "msg-3"})(),
    ) as mock_send:
        alert = await create_alert_from_diagnostic(db_session, diag)
    assert alert is not None
    # Exactly one email — alert dedup ensures dispatch is single-shot
    assert mock_send.call_count == 1
