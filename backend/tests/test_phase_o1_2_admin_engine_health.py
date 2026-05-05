"""Phase O.1.2 — admin engine health sub-router."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import EngineHealthDaily, User
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
    resp = await client.get("/api/admin/engine-health/current", headers=_bearer(admin_operator))
    assert resp.status_code == 200
    body = resp.json()
    assert body["engines"] == []


@pytest.mark.asyncio
async def test_current_returns_latest_per_engine(client, admin_operator, db_session: AsyncSession):
    today = _now()
    yesterday = today - timedelta(days=1)
    # ChatGPT — 2 days
    db_session.add_all(
        [
            EngineHealthDaily(
                engine="chatgpt",
                date=yesterday,
                total_attempts=100,
                success_count=70,
                failed_count=30,
                success_rate=0.70,
                p50_latency_ms=200,
                p95_latency_ms=600,
            ),
            EngineHealthDaily(
                engine="chatgpt",
                date=today,
                total_attempts=120,
                success_count=110,
                failed_count=10,
                success_rate=0.92,
                p50_latency_ms=180,
                p95_latency_ms=500,
            ),
            EngineHealthDaily(
                engine="doubao",
                date=today,
                total_attempts=50,
                success_count=48,
                failed_count=2,
                success_rate=0.96,
                p50_latency_ms=150,
                p95_latency_ms=400,
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get("/api/admin/engine-health/current", headers=_bearer(admin_operator))
    body = resp.json()
    by_engine = {e["engine"]: e for e in body["engines"]}
    assert len(body["engines"]) == 2
    # Latest chatgpt row is today's
    assert by_engine["chatgpt"]["success_rate"] == 0.92
    assert by_engine["doubao"]["success_rate"] == 0.96


@pytest.mark.asyncio
async def test_current_non_admin_403(client, regular_user):
    resp = await client.get("/api/admin/engine-health/current", headers=_bearer(regular_user))
    assert resp.status_code == 403


# ── /trends ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_trends_empty_engine(client, admin_operator):
    resp = await client.get(
        "/api/admin/engine-health/trends?engine=unknown_engine&days=30",
        headers=_bearer(admin_operator),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["engine"] == "unknown_engine"
    assert body["series"] == []
    assert body["summary"]["total_attempts"] == 0


@pytest.mark.asyncio
async def test_trends_returns_series_and_summary(client, admin_operator, db_session: AsyncSession):
    today = _now()
    for i in range(5):
        db_session.add(
            EngineHealthDaily(
                engine="chatgpt",
                date=today - timedelta(days=4 - i),
                total_attempts=100,
                success_count=80 + i * 2,
                failed_count=20 - i * 2,
                success_rate=0.80 + i * 0.02,
                p50_latency_ms=200,
            )
        )
    await db_session.commit()

    resp = await client.get(
        "/api/admin/engine-health/trends?engine=chatgpt&days=10",
        headers=_bearer(admin_operator),
    )
    body = resp.json()
    assert len(body["series"]) == 5
    assert body["summary"]["total_attempts"] == 500
    # weighted avg of [0.80, 0.82, 0.84, 0.86, 0.88] all equal weight = 0.84
    assert body["summary"]["avg_success_rate"] == pytest.approx(0.84, rel=1e-3)


@pytest.mark.asyncio
async def test_trends_window_excludes_old(client, admin_operator, db_session: AsyncSession):
    db_session.add(
        EngineHealthDaily(
            engine="chatgpt",
            date=_now() - timedelta(days=60),
            total_attempts=100,
            success_count=99,
            failed_count=1,
            success_rate=0.99,
        )
    )
    await db_session.commit()

    resp = await client.get(
        "/api/admin/engine-health/trends?engine=chatgpt&days=30",
        headers=_bearer(admin_operator),
    )
    assert resp.json()["summary"]["total_attempts"] == 0


# ── /alerts ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_alerts_returns_low_health_engines(client, admin_operator, db_session: AsyncSession):
    today = _now()
    db_session.add_all(
        [
            EngineHealthDaily(
                engine="chatgpt",
                date=today,
                total_attempts=100,
                success_count=92,
                failed_count=8,
                success_rate=0.92,
            ),
            EngineHealthDaily(
                engine="doubao",
                date=today,
                total_attempts=80,
                success_count=50,
                failed_count=30,
                success_rate=0.625,
            ),
            EngineHealthDaily(
                engine="deepseek",
                date=today,
                total_attempts=60,
                success_count=40,
                failed_count=20,
                success_rate=0.667,
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get("/api/admin/engine-health/alerts", headers=_bearer(admin_operator))
    body = resp.json()
    assert body["threshold"] == 0.80
    engines = {it["engine"] for it in body["items"]}
    # chatgpt is healthy (92%) — excluded
    assert engines == {"doubao", "deepseek"}
    # Highest total_attempts first → doubao (80) > deepseek (60)
    assert body["items"][0]["engine"] == "doubao"


@pytest.mark.asyncio
async def test_alerts_custom_threshold(client, admin_operator, db_session: AsyncSession):
    today = _now()
    db_session.add_all(
        [
            EngineHealthDaily(
                engine="chatgpt",
                date=today,
                total_attempts=100,
                success_count=92,
                failed_count=8,
                success_rate=0.92,
            ),
        ]
    )
    await db_session.commit()

    # threshold 0.95 → chatgpt's 0.92 falls below → returned
    resp = await client.get(
        "/api/admin/engine-health/alerts?threshold=0.95",
        headers=_bearer(admin_operator),
    )
    assert any(it["engine"] == "chatgpt" for it in resp.json()["items"])


@pytest.mark.asyncio
async def test_alerts_invalid_threshold_422(client, admin_operator):
    resp = await client.get(
        "/api/admin/engine-health/alerts?threshold=2.0",
        headers=_bearer(admin_operator),
    )
    assert resp.status_code == 422


# ── coverage gate ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_gate_with_engine_health_no_writes():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
