"""Phase O.1.5 — admin KG discovery logs sub-router."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import DiscoveryLog, User
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
        name="User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


# ── /list ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_empty(client, admin_operator):
    resp = await client.get("/api/admin/kg-discovery/list", headers=_bearer(admin_operator))
    assert resp.status_code == 200
    assert resp.json()["items"] == []


@pytest.mark.asyncio
async def test_list_seeded(client, admin_operator, db_session: AsyncSession):
    now = _now()
    db_session.add_all(
        [
            DiscoveryLog(
                id=_new_id(),
                source="kg_extractor",
                llm_model="doubao-1.5-pro",
                confidence=0.92,
                hallucination_flag=False,
                occurred_at=now,
            ),
            DiscoveryLog(
                id=_new_id(),
                source="kg_extractor",
                llm_model="deepseek-r1",
                confidence=0.45,
                hallucination_flag=True,
                hallucination_evidence={"reason": "made up brand"},
                occurred_at=now,
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get("/api/admin/kg-discovery/list", headers=_bearer(admin_operator))
    assert resp.json()["returned"] == 2


@pytest.mark.asyncio
async def test_list_hallucination_only(client, admin_operator, db_session: AsyncSession):
    now = _now()
    db_session.add_all(
        [
            DiscoveryLog(
                id=_new_id(), source="x", confidence=0.9, hallucination_flag=False, occurred_at=now
            ),
            DiscoveryLog(
                id=_new_id(), source="x", confidence=0.4, hallucination_flag=True, occurred_at=now
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get(
        "/api/admin/kg-discovery/list?hallucination_only=true",
        headers=_bearer(admin_operator),
    )
    assert resp.json()["returned"] == 1
    assert resp.json()["items"][0]["hallucination_flag"] is True


@pytest.mark.asyncio
async def test_list_filter_by_source(client, admin_operator, db_session: AsyncSession):
    now = _now()
    db_session.add_all(
        [
            DiscoveryLog(id=_new_id(), source="kg_extractor", confidence=0.9, occurred_at=now),
            DiscoveryLog(id=_new_id(), source="rule_based", confidence=0.5, occurred_at=now),
        ]
    )
    await db_session.commit()

    resp = await client.get(
        "/api/admin/kg-discovery/list?source=rule_based",
        headers=_bearer(admin_operator),
    )
    assert resp.json()["returned"] == 1
    assert resp.json()["items"][0]["source"] == "rule_based"


@pytest.mark.asyncio
async def test_list_window_excludes_old(client, admin_operator, db_session: AsyncSession):
    db_session.add(
        DiscoveryLog(
            id=_new_id(),
            source="kg_extractor",
            confidence=0.9,
            hallucination_flag=False,
            occurred_at=_now() - timedelta(days=30),
        )
    )
    await db_session.commit()

    resp = await client.get("/api/admin/kg-discovery/list?days=7", headers=_bearer(admin_operator))
    assert resp.json()["returned"] == 0


@pytest.mark.asyncio
async def test_list_non_admin_403(client, regular_user):
    resp = await client.get("/api/admin/kg-discovery/list", headers=_bearer(regular_user))
    assert resp.status_code == 403


# ── /summary ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_summary_zero_state(client, admin_operator):
    resp = await client.get("/api/admin/kg-discovery/summary", headers=_bearer(admin_operator))
    body = resp.json()
    assert body["total_events"] == 0
    assert body["hallucination_count"] == 0
    assert body["hallucination_rate"] == 0
    assert body["avg_confidence"] is None


@pytest.mark.asyncio
async def test_summary_aggregates(client, admin_operator, db_session: AsyncSession):
    now = _now()
    db_session.add_all(
        [
            DiscoveryLog(
                id=_new_id(),
                source="A",
                llm_model="m1",
                confidence=0.9,
                hallucination_flag=False,
                occurred_at=now,
            ),
            DiscoveryLog(
                id=_new_id(),
                source="A",
                llm_model="m1",
                confidence=0.8,
                hallucination_flag=False,
                occurred_at=now,
            ),
            DiscoveryLog(
                id=_new_id(),
                source="B",
                llm_model="m2",
                confidence=0.4,
                hallucination_flag=True,
                occurred_at=now,
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get("/api/admin/kg-discovery/summary", headers=_bearer(admin_operator))
    body = resp.json()
    assert body["total_events"] == 3
    assert body["hallucination_count"] == 1
    assert body["hallucination_rate"] == pytest.approx(0.3333, rel=1e-2)
    assert body["avg_confidence"] == pytest.approx(0.7, rel=1e-2)
    assert body["by_source"] == {"A": 2, "B": 1}
    assert body["by_model"] == {"m1": 2, "m2": 1}


@pytest.mark.asyncio
async def test_summary_excludes_null_models(client, admin_operator, db_session: AsyncSession):
    now = _now()
    db_session.add_all(
        [
            DiscoveryLog(
                id=_new_id(),
                source="A",
                llm_model=None,
                confidence=0.9,
                hallucination_flag=False,
                occurred_at=now,
            ),
            DiscoveryLog(
                id=_new_id(),
                source="A",
                llm_model="m1",
                confidence=0.9,
                hallucination_flag=False,
                occurred_at=now,
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get("/api/admin/kg-discovery/summary", headers=_bearer(admin_operator))
    body = resp.json()
    assert body["total_events"] == 2
    assert body["by_model"] == {"m1": 1}


@pytest.mark.asyncio
async def test_summary_unauth_401(client):
    resp = await client.get("/api/admin/kg-discovery/summary")
    assert resp.status_code == 401


# ── coverage gate ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_gate_with_kg_discovery_no_writes():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
