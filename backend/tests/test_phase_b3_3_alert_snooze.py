"""[#1044 B3-3] Alert snooze state (PRD §4.8.7 / AC-4.8-15).

Acceptance:
  - POST /v1/alerts/:id/snooze with hours=N sets snoozed_until = now + N hours
  - During the snooze window the alert is hidden from unread_count
  - On expiry (snoozed_until <= now) the alert auto-flips to 'unread' on
    next list call; subsequent unread_count counts it again
  - Status CHECK accepts 'snoozed' alongside the existing enum
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import Alert, Project, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"snz-{uuid.uuid4().hex[:6]}@example.com",
        name="snz",
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
        name="P-snooze",
        primary_brand_id=42,
    )
    db_session.add(p)
    await db_session.commit()
    return p


async def _create_unread_alert(
    db_session: AsyncSession, project: Project, severity: str = "P1"
) -> Alert:
    a = Alert(
        id=_new_id(),
        project_id=project.id,
        brand_id=42,
        source="diagnostic",
        source_ref_id=_new_id(),
        severity=severity,
        scope="user",
        title=f"alert-{severity}",
        body="...",
        status="unread",
    )
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    return a


# ── DB-level: CHECK constraint accepts 'snoozed' ─────────────────


@pytest.mark.asyncio
async def test_alert_status_check_accepts_snoozed(db_session, project):
    """Direct insert with status='snoozed' must not fail the CHECK."""
    a = Alert(
        id=_new_id(),
        project_id=project.id,
        brand_id=42,
        source="diagnostic",
        source_ref_id=_new_id(),
        severity="P1",
        scope="user",
        title="snoozed-test",
        status="snoozed",
        snoozed_until=_now() + timedelta(hours=24),
    )
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    assert a.status == "snoozed"
    assert a.snoozed_until is not None


# ── endpoint: POST /v1/alerts/:id/snooze ─────────────────────────


@pytest.mark.asyncio
async def test_snooze_endpoint_sets_snoozed_until(client, user, project, db_session):
    alert = await _create_unread_alert(db_session, project)
    before = _now()
    resp = await client.post(
        f"/api/v1/alerts/{alert.id}/snooze",
        headers=_bearer(user),
        json={"hours": 24},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "snoozed"
    assert body["snoozed_until"] is not None
    su = datetime.fromisoformat(body["snoozed_until"])
    # Should be ~24h in the future from request time
    delta = su - before
    assert timedelta(hours=23, minutes=55) < delta < timedelta(hours=24, minutes=5)


@pytest.mark.asyncio
async def test_snooze_endpoint_default_hours_is_24(client, user, project, db_session):
    """Body omitting `hours` uses the AC-4.8-15 default of 24h."""
    alert = await _create_unread_alert(db_session, project)
    before = _now()
    resp = await client.post(
        f"/api/v1/alerts/{alert.id}/snooze",
        headers=_bearer(user),
        json={},
    )
    assert resp.status_code == 200
    su = datetime.fromisoformat(resp.json()["snoozed_until"])
    assert timedelta(hours=23, minutes=55) < su - before < timedelta(hours=24, minutes=5)


@pytest.mark.asyncio
async def test_snooze_endpoint_rejects_zero_or_negative_hours(client, user, project, db_session):
    alert = await _create_unread_alert(db_session, project)
    resp = await client.post(
        f"/api/v1/alerts/{alert.id}/snooze",
        headers=_bearer(user),
        json={"hours": 0},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_snooze_endpoint_cross_tenant_404(client, user, project, db_session):
    """Another user can't snooze an alert in this user's project."""
    other = User(
        id=_new_id(),
        email=f"o-{uuid.uuid4().hex[:6]}@example.com",
        name="o",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(other)
    await db_session.commit()

    alert = await _create_unread_alert(db_session, project)
    resp = await client.post(
        f"/api/v1/alerts/{alert.id}/snooze",
        headers=_bearer(other),
        json={"hours": 24},
    )
    assert resp.status_code == 404


# ── unread_count hides snoozed during window ─────────────────────


@pytest.mark.asyncio
async def test_unread_count_excludes_snoozed_during_window(client, user, project, db_session):
    alert = await _create_unread_alert(db_session, project, severity="P0")
    # Baseline: 1 unread
    r0 = await client.get("/api/v1/alerts/unread-count", headers=_bearer(user))
    assert r0.json()["unread_count"] == 1

    # Snooze 24h
    await client.post(
        f"/api/v1/alerts/{alert.id}/snooze",
        headers=_bearer(user),
        json={"hours": 24},
    )
    r1 = await client.get("/api/v1/alerts/unread-count", headers=_bearer(user))
    assert r1.json()["unread_count"] == 0
    assert r1.json()["by_severity"] == {}


@pytest.mark.asyncio
async def test_unread_count_counts_snoozed_past_expiry(client, user, project, db_session):
    """When snoozed_until has passed, unread_count must count the alert
    again — even before list is called (PRD AC-4.8-15)."""
    alert = await _create_unread_alert(db_session, project, severity="P0")
    # Manually backdate snoozed_until to be in the past
    alert.status = "snoozed"
    alert.snoozed_until = _now() - timedelta(seconds=1)
    await db_session.commit()

    r = await client.get("/api/v1/alerts/unread-count", headers=_bearer(user))
    body = r.json()
    assert body["unread_count"] == 1
    assert body["by_severity"] == {"P0": 1}


# ── list lazily expires snoozed past their window ────────────────


@pytest.mark.asyncio
async def test_list_alerts_auto_flips_expired_snooze_to_unread(client, user, project, db_session):
    alert = await _create_unread_alert(db_session, project, severity="P0")
    alert.status = "snoozed"
    alert.snoozed_until = _now() - timedelta(seconds=1)
    await db_session.commit()

    resp = await client.get("/api/v1/alerts/", headers=_bearer(user))
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "unread"

    # And it's persisted
    await db_session.refresh(alert)
    assert alert.status == "unread"


@pytest.mark.asyncio
async def test_list_alerts_keeps_snoozed_status_during_window(client, user, project, db_session):
    alert = await _create_unread_alert(db_session, project, severity="P1")
    alert.status = "snoozed"
    alert.snoozed_until = _now() + timedelta(hours=24)
    await db_session.commit()

    resp = await client.get("/api/v1/alerts/", headers=_bearer(user))
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "snoozed"
    assert items[0]["snoozed_until"] is not None
