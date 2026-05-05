"""Phase O.2.1 — admin cost dashboard + budget alerts."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import (
    AdminAuditLog,
    Alert,
    BudgetThreshold,
    CostEvent,
    User,
)
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
        email=f"user-{uuid.uuid4().hex[:6]}@example.com",
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


# ── daily endpoint ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_daily_cost_empty(client, admin_operator):
    resp = await client.get("/api/admin/cost/daily?days=7", headers=_bearer(admin_operator))
    assert resp.status_code == 200
    body = resp.json()
    assert body["days"] == 7
    assert body["grand_total"] == 0
    assert body["series"] == []


@pytest.mark.asyncio
async def test_daily_cost_aggregates_by_scope(client, admin_operator, db_session: AsyncSession):
    today = _now()
    db_session.add_all(
        [
            CostEvent(
                id=_new_id(),
                scope="pipeline",
                amount=12.5,
                source="ark_doubao",
                event_type="llm_call",
                occurred_at=today,
            ),
            CostEvent(
                id=_new_id(),
                scope="pipeline",
                amount=7.5,
                source="ark_doubao",
                event_type="llm_call",
                occurred_at=today,
            ),
            CostEvent(
                id=_new_id(),
                scope="mcp",
                amount=3.0,
                source="claude_anthropic",
                event_type="tool_call",
                occurred_at=today,
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get("/api/admin/cost/daily?days=7", headers=_bearer(admin_operator))
    body = resp.json()
    assert body["grand_total"] == pytest.approx(23.0)
    assert len(body["series"]) == 1  # one day
    today_slot = body["series"][0]["by_scope"]
    assert today_slot["pipeline"] == pytest.approx(20.0)
    assert today_slot["mcp"] == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_daily_cost_window_excludes_old(client, admin_operator, db_session: AsyncSession):
    db_session.add(
        CostEvent(
            id=_new_id(),
            scope="pipeline",
            amount=99.0,
            source="ancient",
            event_type="llm_call",
            occurred_at=_now() - timedelta(days=30),
        )
    )
    await db_session.commit()

    resp = await client.get("/api/admin/cost/daily?days=3", headers=_bearer(admin_operator))
    body = resp.json()
    assert body["grand_total"] == 0


@pytest.mark.asyncio
async def test_daily_cost_non_admin_403(client, regular_user):
    resp = await client.get("/api/admin/cost/daily", headers=_bearer(regular_user))
    assert resp.status_code == 403


# ── by-source endpoint ─────────────────────────────────────


@pytest.mark.asyncio
async def test_by_source_top_spenders(client, admin_operator, db_session: AsyncSession):
    today = _now()
    db_session.add_all(
        [
            CostEvent(
                id=_new_id(),
                scope="pipeline",
                amount=50.0,
                source="ark_doubao",
                event_type="llm_call",
                occurred_at=today,
            ),
            CostEvent(
                id=_new_id(),
                scope="pipeline",
                amount=10.0,
                source="deepseek",
                event_type="llm_call",
                occurred_at=today,
            ),
            CostEvent(
                id=_new_id(),
                scope="kg",
                amount=20.0,
                source="ark_doubao",
                event_type="kg_extract",
                occurred_at=today,
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get("/api/admin/cost/by-source?days=7", headers=_bearer(admin_operator))
    body = resp.json()
    items = body["items"]
    assert len(items) == 3
    # First is highest spend
    assert items[0]["total"] == pytest.approx(50.0)
    assert items[0]["source"] == "ark_doubao"
    assert items[0]["scope"] == "pipeline"


# ── budgets CRUD ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_budget_emits_audit(client, admin_operator, db_session: AsyncSession):
    resp = await client.put(
        "/api/admin/cost/budgets/pipeline",
        headers=_bearer(admin_operator),
        json={"daily_limit_cny": 100, "alert_at_pct": 80, "hard_stop_at_pct": 100},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope"] == "pipeline"
    assert body["daily_limit_cny"] == 100
    assert body["alert_at_pct"] == 80

    # Audit row written
    rows = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "budget_create",
                    AdminAuditLog.resource_id == "pipeline",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_update_budget(client, admin_operator):
    await client.put(
        "/api/admin/cost/budgets/pipeline",
        headers=_bearer(admin_operator),
        json={"daily_limit_cny": 100},
    )
    resp = await client.put(
        "/api/admin/cost/budgets/pipeline",
        headers=_bearer(admin_operator),
        json={"daily_limit_cny": 200, "alert_at_pct": 75, "hard_stop_at_pct": 95},
    )
    assert resp.status_code == 200
    assert resp.json()["daily_limit_cny"] == 200
    assert resp.json()["alert_at_pct"] == 75


@pytest.mark.asyncio
async def test_create_budget_invalid_scope_422(client, admin_operator):
    resp = await client.put(
        "/api/admin/cost/budgets/cosmic",
        headers=_bearer(admin_operator),
        json={"daily_limit_cny": 100},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_budget_invalid_pct_relationship_422(client, admin_operator):
    """alert_at_pct must be <= hard_stop_at_pct."""
    resp = await client.put(
        "/api/admin/cost/budgets/pipeline",
        headers=_bearer(admin_operator),
        json={"daily_limit_cny": 100, "alert_at_pct": 95, "hard_stop_at_pct": 80},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_budgets(client, admin_operator):
    await client.put(
        "/api/admin/cost/budgets/pipeline",
        headers=_bearer(admin_operator),
        json={"daily_limit_cny": 100},
    )
    await client.put(
        "/api/admin/cost/budgets/mcp",
        headers=_bearer(admin_operator),
        json={"daily_limit_cny": 50},
    )
    resp = await client.get("/api/admin/cost/budgets", headers=_bearer(admin_operator))
    assert resp.json()["total"] == 2


@pytest.mark.asyncio
async def test_delete_budget_emits_audit(client, admin_operator, db_session: AsyncSession):
    await client.put(
        "/api/admin/cost/budgets/pipeline",
        headers=_bearer(admin_operator),
        json={"daily_limit_cny": 100},
    )
    resp = await client.delete("/api/admin/cost/budgets/pipeline", headers=_bearer(admin_operator))
    assert resp.status_code == 204

    rows = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "budget_delete")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_delete_unknown_budget_404(client, admin_operator):
    resp = await client.delete("/api/admin/cost/budgets/pipeline", headers=_bearer(admin_operator))
    assert resp.status_code == 404


# ── record_cost_event helper + budget alert trigger ──────────


@pytest.mark.asyncio
async def test_record_cost_event_triggers_p1_alert_at_alert_pct(
    db_session: AsyncSession,
):
    """80% of ¥100 daily → alert_at_pct=80% trips P1 alert."""
    from app.api.admin.cost.router import record_cost_event

    db_session.add(
        BudgetThreshold(
            scope="pipeline",
            daily_limit_cny=100,
            alert_at_pct=80,
            hard_stop_at_pct=100,
        )
    )
    await db_session.commit()

    # First event under threshold → no alert
    await record_cost_event(
        db_session,
        scope="pipeline",
        amount=50,
        source="test",
        event_type="llm_call",
    )
    no_alerts = list(
        (await db_session.execute(select(Alert).where(Alert.source == "cost_overrun")))
        .scalars()
        .all()
    )
    assert len(no_alerts) == 0

    # Push total to 80% → P1 alert
    await record_cost_event(
        db_session,
        scope="pipeline",
        amount=30,
        source="test",
        event_type="llm_call",
    )
    p1 = list(
        (
            await db_session.execute(
                select(Alert).where(
                    Alert.source == "cost_overrun",
                    Alert.severity == "P1",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(p1) == 1
    assert "pipeline" in p1[0].title


@pytest.mark.asyncio
async def test_record_cost_event_triggers_p0_alert_at_hard_stop(
    db_session: AsyncSession,
):
    """100% of daily → P0 alert."""
    from app.api.admin.cost.router import record_cost_event

    db_session.add(
        BudgetThreshold(
            scope="mcp",
            daily_limit_cny=10,
            alert_at_pct=80,
            hard_stop_at_pct=100,
        )
    )
    await db_session.commit()

    await record_cost_event(
        db_session,
        scope="mcp",
        amount=11,  # >100%
        source="test",
        event_type="tool_call",
    )

    p0 = list(
        (await db_session.execute(select(Alert).where(Alert.severity == "P0"))).scalars().all()
    )
    assert len(p0) == 1


@pytest.mark.asyncio
async def test_record_cost_event_no_alert_without_budget(db_session: AsyncSession):
    """Without a budget threshold, no alert fires regardless of amount."""
    from app.api.admin.cost.router import record_cost_event

    await record_cost_event(
        db_session,
        scope="pipeline",
        amount=999_999,
        source="reckless",
        event_type="llm_call",
    )
    alerts = list(
        (await db_session.execute(select(Alert).where(Alert.source == "cost_overrun")))
        .scalars()
        .all()
    )
    assert len(alerts) == 0


@pytest.mark.asyncio
async def test_record_cost_event_dedupes_same_severity_same_day(
    db_session: AsyncSession,
):
    from app.api.admin.cost.router import record_cost_event

    db_session.add(
        BudgetThreshold(
            scope="pipeline",
            daily_limit_cny=10,
            alert_at_pct=50,
            hard_stop_at_pct=100,
        )
    )
    await db_session.commit()

    # Two events that both individually trip P1 (50%)
    await record_cost_event(
        db_session, scope="pipeline", amount=6, source="t", event_type="llm_call"
    )
    await record_cost_event(
        db_session, scope="pipeline", amount=1, source="t", event_type="llm_call"
    )

    p1_count = (
        (
            await db_session.execute(
                select(Alert).where(
                    Alert.source == "cost_overrun",
                    Alert.severity == "P1",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(list(p1_count)) == 1  # deduped


# ── coverage gate ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_with_cost_router():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
