"""Phase R.4 — admin diagnostics sub-router (cross-tenant + manual trigger)."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from genpano_models import AdminAuditLog, Diagnostic, Project, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def admin_operator(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        name="Admin",
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
async def regular_user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"u-{uuid.uuid4().hex[:6]}@example.com",
        name="Regular",
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
async def project_with_diags(
    db_session: AsyncSession, regular_user: User
) -> tuple[Project, list[Diagnostic]]:
    p = Project(user_id=regular_user.id, name="P-diag", primary_brand_id=42)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    diags = [
        Diagnostic(
            id=_new_id(),
            project_id=p.id,
            category="visibility_decline",
            severity="P0",
            type="brand",
            title="d1",
            rule_id="r1",
            evidence={},
            reader_hints=["manager"],
            status="open",
            detected_at=_now(),
        ),
        Diagnostic(
            id=_new_id(),
            project_id=p.id,
            category="sentiment_drop",
            severity="P1",
            type="brand",
            title="d2",
            rule_id="r2",
            evidence={},
            reader_hints=["manager"],
            status="open",
            detected_at=_now(),
        ),
        Diagnostic(
            id=_new_id(),
            project_id=p.id,
            category="topic_loss",
            severity="P3",
            type="brand",
            title="d3",
            rule_id="r3",
            evidence={},
            reader_hints=["manager"],
            status="resolved",
            detected_at=_now(),
        ),
    ]
    db_session.add_all(diags)
    await db_session.commit()
    return p, diags


# ── /list ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_returns_all_projects(client, admin_operator, project_with_diags):
    resp = await client.get("/api/admin/diagnostics/", headers=_bearer(admin_operator))
    assert resp.status_code == 200
    assert resp.json()["returned"] == 3


@pytest.mark.asyncio
async def test_list_filter_by_severity(client, admin_operator, project_with_diags):
    resp = await client.get(
        "/api/admin/diagnostics/?severity=P0",
        headers=_bearer(admin_operator),
    )
    body = resp.json()
    assert body["returned"] == 1
    assert body["items"][0]["severity"] == "P0"


@pytest.mark.asyncio
async def test_list_filter_by_status(client, admin_operator, project_with_diags):
    resp = await client.get(
        "/api/admin/diagnostics/?status=resolved",
        headers=_bearer(admin_operator),
    )
    assert resp.json()["returned"] == 1


@pytest.mark.asyncio
async def test_list_filter_by_project_id(client, admin_operator, project_with_diags):
    p, _ = project_with_diags
    resp = await client.get(
        f"/api/admin/diagnostics/?project_id={p.id}",
        headers=_bearer(admin_operator),
    )
    assert resp.json()["returned"] == 3


@pytest.mark.asyncio
async def test_list_non_admin_403(client, regular_user):
    resp = await client.get("/api/admin/diagnostics/", headers=_bearer(regular_user))
    assert resp.status_code == 403


# ── /counts ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_counts_zero_state(client, admin_operator):
    resp = await client.get("/api/admin/diagnostics/counts", headers=_bearer(admin_operator))
    body = resp.json()
    assert body["total"] == 0
    assert body["open_high_severity"] == 0
    assert body["open_by_severity"] == {}
    assert body["by_status"] == {}


@pytest.mark.asyncio
async def test_counts_aggregates(client, admin_operator, project_with_diags):
    resp = await client.get("/api/admin/diagnostics/counts", headers=_bearer(admin_operator))
    body = resp.json()
    assert body["total"] == 3
    assert body["open_high_severity"] == 2  # P0 + P1 open; P3 is resolved
    assert body["open_by_severity"]["P0"] == 1
    assert body["open_by_severity"]["P1"] == 1
    assert body["by_status"]["open"] == 2
    assert body["by_status"]["resolved"] == 1


# ── /refresh (one project) ───────────────────────────────


@pytest.mark.asyncio
async def test_refresh_one_project_emits_audit(
    client, admin_operator, project_with_diags, db_session: AsyncSession
):
    p, _ = project_with_diags
    resp = await client.post(
        "/api/admin/diagnostics/refresh",
        headers=_bearer(admin_operator),
        json={"project_id": p.id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == p.id
    assert "new_diagnostics" in body

    audits = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "diagnostics_refresh",
                    AdminAuditLog.resource_id == p.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 1
    assert audits[0].severity == "med"


@pytest.mark.asyncio
async def test_refresh_unknown_project_404(client, admin_operator):
    resp = await client.post(
        "/api/admin/diagnostics/refresh",
        headers=_bearer(admin_operator),
        json={"project_id": "no-such-id"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_refresh_missing_project_id_422(client, admin_operator):
    resp = await client.post(
        "/api/admin/diagnostics/refresh",
        headers=_bearer(admin_operator),
        json={},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_refresh_non_admin_403(client, regular_user, project_with_diags):
    p, _ = project_with_diags
    resp = await client.post(
        "/api/admin/diagnostics/refresh",
        headers=_bearer(regular_user),
        json={"project_id": p.id},
    )
    assert resp.status_code == 403


# ── /refresh-all (high-risk) ─────────────────────────────


@pytest.mark.asyncio
async def test_refresh_all_emits_high_audit(
    client, admin_operator, project_with_diags, db_session: AsyncSession
):
    resp = await client.post(
        "/api/admin/diagnostics/refresh-all",
        headers=_bearer(admin_operator),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["projects_scanned"] >= 1
    assert "total_new_diagnostics" in body

    audits = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "diagnostics_refresh_all",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 1
    assert audits[0].severity == "high"
    assert audits[0].operator_id == admin_operator.id


@pytest.mark.asyncio
async def test_refresh_all_no_projects_zero_count(client, admin_operator):
    resp = await client.post(
        "/api/admin/diagnostics/refresh-all",
        headers=_bearer(admin_operator),
    )
    body = resp.json()
    assert body["projects_scanned"] == 0
    assert body["total_new_diagnostics"] == 0


@pytest.mark.asyncio
async def test_refresh_all_non_admin_403(client, regular_user):
    resp = await client.post("/api/admin/diagnostics/refresh-all", headers=_bearer(regular_user))
    assert resp.status_code == 403


# ── audit gate ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_gate_with_admin_diagnostics_writes():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
