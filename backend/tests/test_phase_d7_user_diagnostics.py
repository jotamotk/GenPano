"""Phase D.7 — user-facing /v1/projects/:id/diagnostics endpoints."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import Alert, Diagnostic, GeoScoreDaily, Project, User
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
        email=f"d7-{uuid.uuid4().hex[:6]}@example.com",
        name="D7",
        role="paid",
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
        name="D7 Project",
        primary_brand_id=850,
    )
    db_session.add(p)
    await db_session.commit()
    return p


def _make_diag(
    *,
    project: Project,
    severity: str = "P1",
    category: str = "visibility_decline",
    status: str = "open",
    title: str = "issue",
) -> Diagnostic:
    return Diagnostic(
        id=_new_id(),
        project_id=project.id,
        brand_id=project.primary_brand_id,
        category=category,
        severity=severity,
        type="brand",
        title=title,
        evidence={},
        reader_hints=["operator"],
        rule_id=f"{category}_v1",
        status=status,
    )


# ── list ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_diagnostics_default(db_session, client, user, project):
    db_session.add_all(
        [
            _make_diag(project=project, severity="P1"),
            _make_diag(project=project, severity="P2"),
        ]
    )
    await db_session.commit()
    resp = await client.get(
        f"/api/v1/projects/{project.id}/diagnostics/",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2


@pytest.mark.asyncio
async def test_list_filter_by_severity(db_session, client, user, project):
    db_session.add_all(
        [
            _make_diag(project=project, severity="P1"),
            _make_diag(project=project, severity="P2"),
        ]
    )
    await db_session.commit()
    resp = await client.get(
        f"/api/v1/projects/{project.id}/diagnostics/?severity=P1",
        headers=_bearer(user),
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["severity"] == "P1"


@pytest.mark.asyncio
async def test_list_filter_by_status(db_session, client, user, project):
    db_session.add_all(
        [
            _make_diag(project=project, status="open"),
            _make_diag(project=project, status="resolved"),
        ]
    )
    await db_session.commit()
    resp = await client.get(
        f"/api/v1/projects/{project.id}/diagnostics/?status=resolved",
        headers=_bearer(user),
    )
    assert resp.json()["total"] == 1


# ── counts ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_counts_aggregates(db_session, client, user, project):
    db_session.add_all(
        [
            _make_diag(project=project, severity="P0", status="open"),
            _make_diag(project=project, severity="P1", status="open"),
            _make_diag(project=project, severity="P1", status="resolved"),
        ]
    )
    await db_session.commit()
    resp = await client.get(
        f"/api/v1/projects/{project.id}/diagnostics/counts",
        headers=_bearer(user),
    )
    body = resp.json()
    assert body["total"] == 3
    assert body["by_status"]["open"] == 2
    assert body["by_status"]["resolved"] == 1
    assert body["by_severity_open"]["P0"] == 1
    assert body["by_severity_open"]["P1"] == 1


# ── detail ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_detail(db_session, client, user, project):
    diag = _make_diag(project=project, title="My P0", severity="P0")
    db_session.add(diag)
    await db_session.commit()
    resp = await client.get(
        f"/api/v1/projects/{project.id}/diagnostics/{diag.id}",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "My P0"


@pytest.mark.asyncio
async def test_get_unknown_returns_404(client, user, project):
    resp = await client.get(
        f"/api/v1/projects/{project.id}/diagnostics/no-such",
        headers=_bearer(user),
    )
    assert resp.status_code == 404


# ── PATCH ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_patch_to_acknowledged(db_session, client, user, project):
    diag = _make_diag(project=project)
    db_session.add(diag)
    await db_session.commit()
    resp = await client.patch(
        f"/api/v1/projects/{project.id}/diagnostics/{diag.id}",
        headers=_bearer(user),
        json={"status": "acknowledged"},
    )
    body = resp.json()
    assert body["status"] == "acknowledged"
    assert body["acknowledged_at"] is not None


@pytest.mark.asyncio
async def test_patch_to_resolved_resolves_linked_alert(db_session, client, user, project):
    """When diagnostic transitions to resolved, linked alerts also resolve (D.8)."""
    diag = _make_diag(project=project, severity="P1")
    db_session.add(diag)
    await db_session.commit()
    # Seed a linked alert
    alert = Alert(
        id=_new_id(),
        project_id=project.id,
        brand_id=850,
        source="diagnostic",
        source_ref_id=diag.id,
        severity="P1",
        scope="user",
        title="x",
        status="unread",
    )
    db_session.add(alert)
    await db_session.commit()

    resp = await client.patch(
        f"/api/v1/projects/{project.id}/diagnostics/{diag.id}",
        headers=_bearer(user),
        json={"status": "resolved"},
    )
    assert resp.json()["status"] == "resolved"

    # Refresh the alert object so the test session re-reads the route's
    # committed state from DB.
    await db_session.refresh(alert)
    assert alert.status == "resolved"
    assert alert.resolved_at is not None


# ── refresh ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_runs_evaluator(db_session, client, user, project):
    """Strong visibility decline → P1 inserted on refresh."""
    today = datetime.now(UTC).replace(tzinfo=None).date()
    for i in range(30):
        d = today - timedelta(days=59 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=850,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                mention_rate=0.8,
                avg_geo_score=80.0,
                total_queries=100,
            )
        )
    for i in range(30):
        d = today - timedelta(days=29 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=850,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                mention_rate=0.3,
                avg_geo_score=40.0,
                total_queries=100,
            )
        )
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/projects/{project.id}/diagnostics/refresh",
        headers=_bearer(user),
    )
    body = resp.json()
    assert body["inserted"] >= 1
    assert body["project_id"] == project.id


# ── multi-tenancy ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_other_user_cannot_read_diagnostics(db_session, client, user, project):
    diag = _make_diag(project=project)
    db_session.add(diag)

    other = User(
        id=_new_id(),
        email=f"o-{uuid.uuid4().hex[:6]}@example.com",
        name="O",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(other)
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{project.id}/diagnostics/",
        headers=_bearer(other),
    )
    # get_project_for_user returns 404 on multi-tenant violation
    assert resp.status_code == 404
