"""Phase O.2.2 — admin audit log filters + CSV export."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import AdminAuditLog, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


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
        name="Reg",
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
async def audit_rows(db_session: AsyncSession, admin_operator: User) -> list[AdminAuditLog]:
    """Seed 4 audit rows with varied dimensions for filter coverage."""
    base = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2)
    rows = [
        AdminAuditLog(
            id=_new_id(),
            operator_id=admin_operator.id,
            action="brand_merge",
            resource_type="brand",
            resource_id="b-101",
            severity="high",
            ip="10.0.0.1",
            reason="dedup duplicate",
            occurred_at=base + timedelta(minutes=0),
        ),
        AdminAuditLog(
            id=_new_id(),
            operator_id=admin_operator.id,
            action="config_change",
            resource_type="config",
            resource_id=None,
            severity="med",
            ip="10.0.0.1",
            reason=None,
            occurred_at=base + timedelta(minutes=30),
        ),
        AdminAuditLog(
            id=_new_id(),
            operator_id=admin_operator.id,
            action="brand_merge",
            resource_type="brand",
            resource_id="b-202",
            severity="high",
            ip="10.0.0.2",
            occurred_at=base + timedelta(hours=1, minutes=0),
        ),
        AdminAuditLog(
            id=_new_id(),
            operator_id=admin_operator.id,
            action="kg_candidate_approved",
            resource_type="kg_relation_candidate",
            resource_id="cand-1",
            severity="med",
            occurred_at=base + timedelta(hours=1, minutes=30),
        ),
    ]
    db_session.add_all(rows)
    await db_session.commit()
    return rows


# ── filters on /audit-log ────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_log_no_filters_returns_all(client, admin_operator, audit_rows):
    resp = await client.get("/api/admin/audit-log", headers=_bearer(admin_operator))
    body = resp.json()
    assert body["total"] >= 4


@pytest.mark.asyncio
async def test_audit_log_filter_action(client, admin_operator, audit_rows):
    resp = await client.get(
        "/api/admin/audit-log?action=brand_merge",
        headers=_bearer(admin_operator),
    )
    body = resp.json()
    assert body["total"] == 2
    for it in body["items"]:
        assert it["action"] == "brand_merge"


@pytest.mark.asyncio
async def test_audit_log_filter_severity(client, admin_operator, audit_rows):
    resp = await client.get(
        "/api/admin/audit-log?severity=high",
        headers=_bearer(admin_operator),
    )
    body = resp.json()
    assert body["total"] == 2
    for it in body["items"]:
        assert it["severity"] == "high"


@pytest.mark.asyncio
async def test_audit_log_filter_resource_type(client, admin_operator, audit_rows):
    resp = await client.get(
        "/api/admin/audit-log?resource_type=brand",
        headers=_bearer(admin_operator),
    )
    body = resp.json()
    assert body["total"] == 2


@pytest.mark.asyncio
async def test_audit_log_filter_resource_id(client, admin_operator, audit_rows):
    resp = await client.get(
        "/api/admin/audit-log?resource_id=cand-1",
        headers=_bearer(admin_operator),
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["resource_id"] == "cand-1"


@pytest.mark.asyncio
async def test_audit_log_filter_operator_id(client, admin_operator, audit_rows):
    resp = await client.get(
        f"/api/admin/audit-log?operator_id={admin_operator.id}",
        headers=_bearer(admin_operator),
    )
    body = resp.json()
    assert body["total"] >= 4


@pytest.mark.asyncio
async def test_audit_log_filter_combined(client, admin_operator, audit_rows):
    """action=brand_merge AND severity=high → 2 rows (both brand_merge are high)."""
    resp = await client.get(
        "/api/admin/audit-log?action=brand_merge&severity=high",
        headers=_bearer(admin_operator),
    )
    body = resp.json()
    assert body["total"] == 2


@pytest.mark.asyncio
async def test_audit_log_filter_date_range(client, admin_operator, audit_rows):
    """`to=` 1h before now excludes the rows from the last 30min and 1h.

    The fixture's `base` was 2h ago, so rows at base+0/+30min are >=1.5h
    old; rows at base+1h/+1h30min are <=1h old. Setting `to=` 1h ago
    keeps only the older two.
    """
    to_cutoff = (
        datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1, minutes=10)
    ).isoformat()
    resp = await client.get(
        f"/api/admin/audit-log?to={to_cutoff}",
        headers=_bearer(admin_operator),
    )
    body = resp.json()
    # First 2 rows (1.5h+ old) match the to= filter
    assert body["total"] == 2


# ── CSV export ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_log_export_csv(client, admin_operator, audit_rows):
    resp = await client.get(
        "/api/admin/audit-log/export.csv",
        headers=_bearer(admin_operator),
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    body = resp.text
    # Header row + at least 4 data rows
    lines = body.strip().split("\n")
    assert lines[0].startswith("id,occurred_at,operator_id,action")
    assert len(lines) >= 5  # header + 4 rows


@pytest.mark.asyncio
async def test_audit_log_export_csv_respects_filter(client, admin_operator, audit_rows):
    resp = await client.get(
        "/api/admin/audit-log/export.csv?action=brand_merge",
        headers=_bearer(admin_operator),
    )
    body = resp.text
    lines = body.strip().split("\n")
    # header + 2 brand_merge rows = 3 lines total
    data_rows = lines[1:]
    assert len(data_rows) == 2
    for row in data_rows:
        assert "brand_merge" in row


# ── auth gate ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_log_non_admin_denied(client, regular_user):
    resp = await client.get("/api/admin/audit-log", headers=_bearer(regular_user))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_audit_log_export_non_admin_denied(client, regular_user):
    resp = await client.get(
        "/api/admin/audit-log/export.csv",
        headers=_bearer(regular_user),
    )
    assert resp.status_code == 403
