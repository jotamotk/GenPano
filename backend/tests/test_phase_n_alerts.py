"""Phase N — alerts + notifications endpoints."""

from __future__ import annotations

import os
import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from genpano_models import Alert, Project, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"a-{uuid.uuid4().hex[:6]}@example.com",
        name="Alert User",
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
async def project_with_alerts(db_session: AsyncSession, user: User) -> Project:
    p = Project(user_id=user.id, name="Alert Proj", primary_brand_id=42)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    # 3 user-scope alerts: 1 P0 unread, 1 P1 unread, 1 P2 read
    db_session.add(
        Alert(
            id=_new_id(),
            project_id=p.id,
            source="diagnostic",
            severity="P0",
            scope="user",
            title="Critical metric drop",
            status="unread",
            triggered_at=datetime.now(),
        )
    )
    db_session.add(
        Alert(
            id=_new_id(),
            project_id=p.id,
            source="diagnostic",
            severity="P1",
            scope="user",
            title="Sentiment anomaly",
            status="unread",
            triggered_at=datetime.now(),
        )
    )
    db_session.add(
        Alert(
            id=_new_id(),
            project_id=p.id,
            source="competitor_overtake",
            severity="P2",
            scope="user",
            title="Competitor surge",
            status="read",
            triggered_at=datetime.now(),
        )
    )
    # Operator-scope alert (should NOT show up for user)
    db_session.add(
        Alert(
            id=_new_id(),
            project_id=p.id,
            source="cost_overrun",
            severity="P1",
            scope="operator",
            title="Cost over budget",
            status="unread",
            triggered_at=datetime.now(),
        )
    )
    await db_session.commit()
    return p


# ── /v1/alerts ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_user_alerts(client, user, project_with_alerts):
    resp = await client.get("/api/v1/alerts/", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    # Only 3 user-scope alerts visible (operator scope filtered out)
    assert body["total"] == 3
    sources = {a["source"] for a in body["items"]}
    assert "cost_overrun" not in sources  # operator-only


@pytest.mark.asyncio
async def test_unread_count(client, user, project_with_alerts):
    resp = await client.get("/api/v1/alerts/unread-count", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["unread_count"] == 2  # P0 + P1
    assert body["by_severity"] == {"P0": 1, "P1": 1}


@pytest.mark.asyncio
async def test_filter_by_status(client, user, project_with_alerts):
    resp = await client.get("/api/v1/alerts/?status=read", headers=_bearer(user))
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "read"


@pytest.mark.asyncio
async def test_patch_alert_to_read(client, user, project_with_alerts, db_session):
    """Mark an unread alert as read; read_at is populated."""
    from genpano_models import Alert as AlertModel
    from sqlalchemy import select

    stmt = (
        select(AlertModel).where(AlertModel.scope == "user", AlertModel.status == "unread").limit(1)
    )
    alert = (await db_session.execute(stmt)).scalar_one()
    aid = alert.id

    resp = await client.patch(
        f"/api/v1/alerts/{aid}", headers=_bearer(user), json={"status": "read"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "read"
    assert body["read_at"] is not None


@pytest.mark.asyncio
async def test_patch_alert_cross_tenant_404(client, user, project_with_alerts, db_session):
    """User can't patch alerts they don't own."""
    other = User(
        id=_new_id(),
        email=f"o-{uuid.uuid4().hex[:6]}@example.com",
        name="Other",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(other)
    await db_session.commit()

    from genpano_models import Alert as AlertModel
    from sqlalchemy import select

    stmt = select(AlertModel).where(AlertModel.scope == "user").limit(1)
    aid = (await db_session.execute(stmt)).scalar_one().id

    resp = await client.patch(
        f"/api/v1/alerts/{aid}", headers=_bearer(other), json={"status": "read"}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mark_all_read(client, user, project_with_alerts):
    resp = await client.post("/api/v1/alerts/mark-all-read", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated_count"] == 2  # 2 unread → read

    # Now unread_count is 0
    resp = await client.get("/api/v1/alerts/unread-count", headers=_bearer(user))
    assert resp.json()["unread_count"] == 0


# ── Notification preferences ─────────────────────────────────────


@pytest.mark.asyncio
async def test_get_default_prefs(client, user):
    resp = await client.get("/api/v1/users/me/notifications", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["p0p1_alerts"] is True
    assert body["weekly_report"] is True
    assert body["competitor_alert"] is False
    assert body["email_locale"] == "zh-CN"


@pytest.mark.asyncio
async def test_patch_prefs(client, user):
    resp = await client.patch(
        "/api/v1/users/me/notifications",
        headers=_bearer(user),
        json={
            "competitor_alert": True,
            "email_locale": "en-US",
            "quiet_hours": {"start": "22:00", "end": "08:00", "tz": "Asia/Shanghai"},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["competitor_alert"] is True
    assert body["email_locale"] == "en-US"
    assert body["quiet_hours"]["start"] == "22:00"


# ── Alert rules ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_alert_rule_crud(client, user):
    # Create
    resp = await client.post(
        "/api/v1/users/me/alert-rules",
        headers=_bearer(user),
        json={
            "rule_type": "p1_diagnostic",
            "conditions": {"min_severity": "P1"},
            "channels": ["email", "inapp"],
        },
    )
    assert resp.status_code == 201
    rule_id = resp.json()["id"]

    # List
    resp = await client.get("/api/v1/users/me/alert-rules", headers=_bearer(user))
    assert resp.status_code == 200
    assert any(r["id"] == rule_id for r in resp.json())

    # Delete
    resp = await client.delete(f"/api/v1/users/me/alert-rules/{rule_id}", headers=_bearer(user))
    assert resp.status_code == 204

    # Confirm gone
    resp = await client.get("/api/v1/users/me/alert-rules", headers=_bearer(user))
    assert all(r["id"] != rule_id for r in resp.json())


@pytest.mark.asyncio
async def test_alerts_no_auth_returns_401(client):
    resp = await client.get("/api/v1/alerts/")
    assert resp.status_code == 401
