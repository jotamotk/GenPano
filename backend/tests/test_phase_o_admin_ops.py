"""Phase O — Admin operations 8 tables ORM tests."""

from __future__ import annotations

import os
import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from genpano_models import (
    AdminAuditLog,
    BudgetThreshold,
    CommsAnnouncement,
    CostEvent,
    DiscoveryLog,
    EngineHealthDaily,
    McpCallLog,
    ProxyHealthDaily,
    User,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture
async def operator(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"op-{uuid.uuid4().hex[:6]}@example.com",
        name="Operator",
        role="paid",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest.mark.asyncio
async def test_engine_health_daily_unique(db_session: AsyncSession) -> None:
    db_session.add(
        EngineHealthDaily(
            engine="chatgpt",
            date=datetime(2026, 5, 5),
            total_attempts=100,
            success_count=95,
        )
    )
    await db_session.commit()
    db_session.add(
        EngineHealthDaily(
            engine="chatgpt",
            date=datetime(2026, 5, 5),
            total_attempts=200,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_proxy_health_basic(db_session: AsyncSession) -> None:
    db_session.add(
        ProxyHealthDaily(
            proxy_id=1,
            date=datetime(2026, 5, 5),
            total_requests=500,
            success_count=480,
            success_rate=0.96,
            is_blocked=False,
        )
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_discovery_log_records(db_session: AsyncSession) -> None:
    db_session.add(
        DiscoveryLog(
            source="relation_extractor",
            llm_model="doubao",
            confidence=0.92,
            hallucination_flag=False,
        )
    )
    db_session.add(
        DiscoveryLog(
            source="brand_detector",
            llm_model="deepseek",
            confidence=0.45,
            hallucination_flag=True,
            hallucination_evidence={"reason": "non-existent brand"},
        )
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_cost_event_scope_check(db_session: AsyncSession) -> None:
    db_session.add(
        CostEvent(
            scope="pipeline",
            amount=0.05,
            source="doubao_analyzer",
            event_type="llm_call",
        )
    )
    await db_session.commit()

    db_session.add(
        CostEvent(
            scope="invalid_scope",
            amount=0.05,
            source="x",
            event_type="x",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_budget_threshold(db_session: AsyncSession) -> None:
    db_session.add(
        BudgetThreshold(
            scope="mcp",
            daily_limit_cny=100.00,
            weekly_limit_cny=600.00,
            monthly_limit_cny=2000.00,
        )
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_admin_audit_log_severity_check(db_session: AsyncSession, operator: User) -> None:
    db_session.add(
        AdminAuditLog(
            operator_id=operator.id,
            action="brand_merge",
            resource_type="brand",
            resource_id="42",
            severity="high",
            before={"name": "old"},
            after={"name": "new"},
        )
    )
    await db_session.commit()

    db_session.add(
        AdminAuditLog(
            operator_id=operator.id,
            action="x",
            resource_type="brand",
            severity="critical",  # invalid
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_comms_announcement_status_check(db_session: AsyncSession, operator: User) -> None:
    db_session.add(
        CommsAnnouncement(
            title_zh="Title",
            body_zh="Body",
            channel="email",
            audience="all",
            status="draft",
            created_by=operator.id,
        )
    )
    await db_session.commit()

    db_session.add(
        CommsAnnouncement(
            title_zh="Title",
            body_zh="Body",
            channel="email",
            audience="all",
            status="weird",  # invalid
            created_by=operator.id,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_mcp_call_log_basic(db_session: AsyncSession) -> None:
    db_session.add(
        McpCallLog(
            api_key_id=_new_id(),
            user_id=_new_id(),
            tool="genpano_get_brand_visibility",
            status="success",
            http_status=200,
            latency_ms=120,
            cost_estimate_cny=0.002,
        )
    )
    await db_session.commit()
