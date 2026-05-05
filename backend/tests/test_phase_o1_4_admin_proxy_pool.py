"""Phase O.1.4 — admin proxy pool sub-router."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import ProxyHealthDaily, User
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


# ── /current ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_current_zero_state(client, admin_operator):
    resp = await client.get("/api/admin/proxy-pool/current", headers=_bearer(admin_operator))
    assert resp.status_code == 200
    assert resp.json()["proxies"] == []


@pytest.mark.asyncio
async def test_current_returns_latest_per_proxy(client, admin_operator, db_session: AsyncSession):
    today = _now()
    yesterday = today - timedelta(days=1)
    db_session.add_all(
        [
            ProxyHealthDaily(
                proxy_id=1,
                date=yesterday,
                total_requests=100,
                success_count=70,
                success_rate=0.70,
                avg_latency_ms=200,
                is_blocked=False,
            ),
            ProxyHealthDaily(
                proxy_id=1,
                date=today,
                total_requests=120,
                success_count=110,
                success_rate=0.92,
                avg_latency_ms=180,
                is_blocked=False,
            ),
            ProxyHealthDaily(
                proxy_id=2,
                date=today,
                total_requests=50,
                success_count=10,
                success_rate=0.20,
                avg_latency_ms=400,
                is_blocked=True,
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get("/api/admin/proxy-pool/current", headers=_bearer(admin_operator))
    body = resp.json()
    by_id = {p["proxy_id"]: p for p in body["proxies"]}
    # Latest for proxy 1 is today's row
    assert by_id[1]["success_rate"] == 0.92
    assert by_id[2]["is_blocked"] is True


@pytest.mark.asyncio
async def test_current_non_admin_403(client, regular_user):
    resp = await client.get("/api/admin/proxy-pool/current", headers=_bearer(regular_user))
    assert resp.status_code == 403


# ── /trends ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_trends_empty_proxy(client, admin_operator):
    resp = await client.get(
        "/api/admin/proxy-pool/trends?proxy_id=99999&days=30",
        headers=_bearer(admin_operator),
    )
    body = resp.json()
    assert body["proxy_id"] == 99999
    assert body["series"] == []
    assert body["summary"]["total_requests"] == 0


@pytest.mark.asyncio
async def test_trends_returns_series_and_summary(client, admin_operator, db_session: AsyncSession):
    today = _now()
    for i in range(5):
        db_session.add(
            ProxyHealthDaily(
                proxy_id=1,
                date=today - timedelta(days=4 - i),
                total_requests=100,
                success_count=80 + i * 2,
                success_rate=0.80 + i * 0.02,
                avg_latency_ms=200,
                is_blocked=False,
            )
        )
    await db_session.commit()

    resp = await client.get(
        "/api/admin/proxy-pool/trends?proxy_id=1&days=10",
        headers=_bearer(admin_operator),
    )
    body = resp.json()
    assert len(body["series"]) == 5
    assert body["summary"]["total_requests"] == 500
    assert body["summary"]["avg_success_rate"] == pytest.approx(0.84, rel=1e-3)


# ── /alerts ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_alerts_returns_blocked_or_below_threshold(
    client, admin_operator, db_session: AsyncSession
):
    today = _now()
    db_session.add_all(
        [
            ProxyHealthDaily(
                proxy_id=1,
                date=today,
                total_requests=100,
                success_count=92,
                success_rate=0.92,
                is_blocked=False,
            ),
            ProxyHealthDaily(
                proxy_id=2,
                date=today,
                total_requests=80,
                success_count=50,
                success_rate=0.625,  # below 0.85
                is_blocked=False,
            ),
            ProxyHealthDaily(
                proxy_id=3,
                date=today,
                total_requests=60,
                success_count=58,
                success_rate=0.97,
                is_blocked=True,  # blocked overrides threshold
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get("/api/admin/proxy-pool/alerts", headers=_bearer(admin_operator))
    body = resp.json()
    assert body["threshold"] == 0.85
    proxy_ids = {it["proxy_id"] for it in body["items"]}
    assert proxy_ids == {2, 3}  # proxy 1 (0.92, not blocked) excluded


@pytest.mark.asyncio
async def test_alerts_invalid_threshold_422(client, admin_operator):
    resp = await client.get(
        "/api/admin/proxy-pool/alerts?threshold=2.5",
        headers=_bearer(admin_operator),
    )
    assert resp.status_code == 422


# ── /blocked ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_blocked_returns_only_blocked(client, admin_operator, db_session: AsyncSession):
    today = _now()
    db_session.add_all(
        [
            ProxyHealthDaily(
                proxy_id=1,
                date=today,
                total_requests=100,
                success_count=92,
                success_rate=0.92,
                is_blocked=False,
            ),
            ProxyHealthDaily(
                proxy_id=2,
                date=today,
                total_requests=10,
                success_count=2,
                success_rate=0.2,
                is_blocked=True,
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get("/api/admin/proxy-pool/blocked", headers=_bearer(admin_operator))
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["proxy_id"] == 2
    assert body["items"][0]["is_blocked"] is True


@pytest.mark.asyncio
async def test_blocked_unauth_401(client):
    resp = await client.get("/api/admin/proxy-pool/blocked")
    assert resp.status_code == 401


# ── coverage gate ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_gate_with_proxy_pool_no_writes():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
