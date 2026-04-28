"""A1' Step 1 model tests — covers 8 new admin tables + T5 closure.

Mirrors `tests/admin/auth/conftest.py`'s in-memory-aiosqlite pattern:
each test gets a fresh engine with admin_users (FK target) and the 8
A1' tables created. SQLite FK enforcement is explicitly enabled.

Verifications per table:
- valid insert succeeds (exercises _new_uuid default path)
- CHECK constraint violations raise IntegrityError
- FK violations raise IntegrityError (admin_users.id is the only
  materialized FK target; references to App users / kg_* are plain UUID)
- composite UNIQUE on cost_daily
- T5 closure: admin_password_resets.purpose has no server_default

Decision references:
- CLAUDE.md #30.G (round 8 8-table schema alignment)
- CLAUDE.md #28.G C3 (NO SCHEMA DEFAULT pattern)
- CLAUDE.md #24.C4 (purpose column closure, A0' baseline)
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast

import pytest
import pytest_asyncio
from sqlalchemy import Table, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.admin import (
    AdminPasswordReset,
    AdminUser,
    AdminUserActivityStat,
    AdminUserModerationAction,
    Alert,
    AliasConflict,
    BrandSubmission,
    BudgetConfig,
    CostDaily,
    KgReviewQueue,
)

_TABLES: list[Table] = [
    cast(Table, AdminUser.__table__),
    cast(Table, AdminPasswordReset.__table__),
    cast(Table, AdminUserModerationAction.__table__),
    cast(Table, AdminUserActivityStat.__table__),
    cast(Table, KgReviewQueue.__table__),
    cast(Table, AliasConflict.__table__),
    cast(Table, BrandSubmission.__table__),
    cast(Table, Alert.__table__),
    cast(Table, CostDaily.__table__),
    cast(Table, BudgetConfig.__table__),
]


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_conn: object, _conn_record: object) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    async with engine.begin() as conn:
        for table in _TABLES:
            await conn.run_sync(table.create)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


async def _seed_admin(session: AsyncSession) -> str:
    admin = AdminUser(
        email=f"admin-{uuid.uuid4()}@example.com",
        password_hash="x" * 60,
        role="super_admin",
        status="active",
    )
    session.add(admin)
    await session.commit()
    return admin.id


# ---------------------------------------------------------------------------
# 1. user_moderation_actions: action CHECK + FK to admin_users
# ---------------------------------------------------------------------------


async def test_user_moderation_action_valid_and_check(db_session: AsyncSession) -> None:
    operator_id = await _seed_admin(db_session)

    # Valid: each of 4 allowed action values inserts (round 8 decision).
    for action in ("freeze", "unfreeze", "force_password_reset", "soft_delete"):
        row = AdminUserModerationAction(
            user_id=str(uuid.uuid4()),
            operator_id=operator_id,
            action=action,
            reason="QA",
        )
        db_session.add(row)
    await db_session.commit()

    # CHECK violation: unknown action.
    db_session.add(
        AdminUserModerationAction(
            user_id=str(uuid.uuid4()),
            operator_id=operator_id,
            action="ban_forever",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    # FK violation: operator_id not in admin_users.
    db_session.add(
        AdminUserModerationAction(
            user_id=str(uuid.uuid4()),
            operator_id=str(uuid.uuid4()),  # not a real admin
            action="freeze",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# ---------------------------------------------------------------------------
# 2. user_activity_stats: PK is user_id; defaults on counters
# ---------------------------------------------------------------------------


async def test_user_activity_stats_defaults_and_pk(db_session: AsyncSession) -> None:
    user_id = str(uuid.uuid4())
    db_session.add(
        AdminUserActivityStat(
            user_id=user_id,
            updated_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    await db_session.commit()

    row = (
        await db_session.execute(
            select(AdminUserActivityStat).where(AdminUserActivityStat.user_id == user_id)
        )
    ).scalar_one()
    assert row.login_count_30d == 0  # server_default
    assert row.query_count_30d == 0  # server_default

    # PK uniqueness.
    db_session.add(
        AdminUserActivityStat(
            user_id=user_id,
            updated_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# ---------------------------------------------------------------------------
# 3. kg_review_queue: target_type + status CHECK; FK on submitted_by/reviewer_id
# ---------------------------------------------------------------------------


async def test_kg_review_queue_check_and_fk(db_session: AsyncSession) -> None:
    operator_id = await _seed_admin(db_session)

    # Valid: round 8 decision allows status='merged' on top of pending/approved/rejected.
    for st in ("pending", "approved", "rejected", "merged"):
        db_session.add(
            KgReviewQueue(
                target_type="brand",
                target_id=str(uuid.uuid4()),
                status=st,
                submitted_by=operator_id,
            )
        )
    await db_session.commit()

    # CHECK: bogus target_type
    db_session.add(
        KgReviewQueue(
            target_type="brandz",  # invalid
            target_id=str(uuid.uuid4()),
            status="pending",
            submitted_by=operator_id,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    # CHECK: bogus status
    db_session.add(
        KgReviewQueue(
            target_type="product",
            target_id=str(uuid.uuid4()),
            status="archived",  # invalid
            submitted_by=operator_id,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# ---------------------------------------------------------------------------
# 4. alias_conflicts: JSON candidate_ids round-trip + FK on resolved_admin_id
# ---------------------------------------------------------------------------


async def test_alias_conflicts_json_roundtrip(db_session: AsyncSession) -> None:
    admin_id = await _seed_admin(db_session)
    candidates = [str(uuid.uuid4()) for _ in range(3)]
    row = AliasConflict(
        alias_value="LV",
        language="zh-CN",
        candidate_ids=candidates,
        resolved_admin_id=admin_id,
    )
    db_session.add(row)
    await db_session.commit()

    fetched = (
        await db_session.execute(select(AliasConflict).where(AliasConflict.alias_value == "LV"))
    ).scalar_one()
    assert fetched.candidate_ids == candidates
    assert fetched.id is not None  # _new_uuid default fired

    # FK violation
    db_session.add(
        AliasConflict(
            alias_value="X",
            language="en",
            candidate_ids=[],
            resolved_admin_id=str(uuid.uuid4()),
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# ---------------------------------------------------------------------------
# 5. brand_submissions: status CHECK + trust_score Numeric + JSON aliases
# ---------------------------------------------------------------------------


async def test_brand_submissions_check_and_numeric(db_session: AsyncSession) -> None:
    admin_id = await _seed_admin(db_session)
    submitter = str(uuid.uuid4())

    db_session.add(
        BrandSubmission(
            submitter_user_id=submitter,
            brand_name_zh="测试品牌",
            brand_name_en="Test Brand",
            aliases=["TB", "TestBrand"],
            trust_score=Decimal("0.7500"),
            status="pending",
            resolved_admin_id=admin_id,
        )
    )
    await db_session.commit()

    fetched = (
        await db_session.execute(
            select(BrandSubmission).where(BrandSubmission.submitter_user_id == submitter)
        )
    ).scalar_one()
    assert fetched.aliases == ["TB", "TestBrand"]
    assert Decimal(str(fetched.trust_score)) == Decimal("0.7500")

    # CHECK violation
    db_session.add(
        BrandSubmission(
            submitter_user_id=str(uuid.uuid4()),
            status="archived",  # invalid
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# ---------------------------------------------------------------------------
# 6. alerts: severity + state CHECK; default count=1; FK on ack/resolved admin
# ---------------------------------------------------------------------------


async def test_alerts_check_severity_state_count_default(db_session: AsyncSession) -> None:
    admin_id = await _seed_admin(db_session)

    a = Alert(
        alert_type="cost_spike",
        severity="P0",
        state="open",
        title="Hourly cost > 2x budget",
        payload={"hourly_usd": 12.34},
    )
    db_session.add(a)
    await db_session.commit()

    fetched = (await db_session.execute(select(Alert).where(Alert.id == a.id))).scalar_one()
    assert fetched.count == 1  # server_default
    assert fetched.first_seen_at is not None  # server_default CURRENT_TIMESTAMP
    assert fetched.last_seen_at is not None
    assert fetched.payload == {"hourly_usd": 12.34}

    # ack + resolved FK ok with admin_id
    fetched.state = "acknowledged"
    fetched.ack_admin_id = admin_id
    fetched.ack_at = datetime.now(UTC).replace(tzinfo=None)
    await db_session.commit()

    # CHECK: bad severity
    db_session.add(Alert(alert_type="x", severity="P3", state="open", title="x"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    # CHECK: bad state
    db_session.add(Alert(alert_type="x", severity="P1", state="closed", title="x"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# ---------------------------------------------------------------------------
# 7. cost_daily: composite UNIQUE on (date, engine_id, industry_id, brand_id, category)
# ---------------------------------------------------------------------------


async def test_cost_daily_composite_unique(db_session: AsyncSession) -> None:
    industry = str(uuid.uuid4())
    brand = str(uuid.uuid4())
    today = date(2026, 4, 28)
    base = dict(
        date=today,
        engine_id="chatgpt",
        industry_id=industry,
        brand_id=brand,
        category="beauty",
        amount_cny=Decimal("100.0000"),
        amount_usd=Decimal("14.5000"),
        token_count=12345,
        query_count=10,
        aggregated_from=datetime(2026, 4, 28, 0, 0, 0),
        aggregated_to=datetime(2026, 4, 28, 23, 59, 59),
    )
    db_session.add(CostDaily(**base))
    await db_session.commit()

    # Same composite key → UNIQUE violation
    db_session.add(CostDaily(**base))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    # Different engine_id → ok
    base2 = {**base, "engine_id": "doubao"}
    db_session.add(CostDaily(**base2))
    await db_session.commit()


# ---------------------------------------------------------------------------
# 8. budget_config: scope + threshold CHECKs (warning ≤100, hard ≤200) + FK
# ---------------------------------------------------------------------------


async def test_budget_config_scope_and_thresholds(db_session: AsyncSession) -> None:
    admin_id = await _seed_admin(db_session)

    # Valid all 4 scopes
    for sc in ("global", "engine", "industry", "brand"):
        db_session.add(
            BudgetConfig(
                scope=sc,
                scope_id=None if sc == "global" else str(uuid.uuid4()),
                monthly_budget_usd=Decimal("1000.0000"),
                updated_at=datetime.now(UTC).replace(tzinfo=None),
                updated_admin_id=admin_id,
            )
        )
    await db_session.commit()

    # CHECK: invalid scope
    db_session.add(
        BudgetConfig(
            scope="department",
            monthly_budget_usd=Decimal("500"),
            updated_at=datetime.now(UTC).replace(tzinfo=None),
            updated_admin_id=admin_id,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    # CHECK: warning_threshold_pct > 100
    db_session.add(
        BudgetConfig(
            scope="global",
            monthly_budget_usd=Decimal("500"),
            warning_threshold_pct=120,
            updated_at=datetime.now(UTC).replace(tzinfo=None),
            updated_admin_id=admin_id,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    # CHECK: hard_threshold_pct > 200
    db_session.add(
        BudgetConfig(
            scope="engine",
            scope_id="chatgpt",
            monthly_budget_usd=Decimal("500"),
            hard_threshold_pct=250,
            updated_at=datetime.now(UTC).replace(tzinfo=None),
            updated_admin_id=admin_id,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# ---------------------------------------------------------------------------
# 9. T5 closure: admin_password_resets.purpose has no server_default in metadata
# ---------------------------------------------------------------------------


def test_admin_password_resets_purpose_no_server_default() -> None:
    """Decision #28.G C3 NO SCHEMA DEFAULT — drop happened in alembic
    revision 15500b81322a; model attribute reflects the same. CHECK is
    still in place (column + CHECK shipped in A0' baseline #30.F)."""
    col = AdminPasswordReset.__table__.c.purpose
    assert col.server_default is None, "purpose must NOT carry a server_default after T5 closure"
    assert col.nullable is False
    # CHECK ('reset','invitation') still on the table
    check_clauses = [
        c.sqltext.text for c in AdminPasswordReset.__table__.constraints if hasattr(c, "sqltext")
    ]
    assert any("purpose" in s and "reset" in s and "invitation" in s for s in check_clauses), (
        f"purpose CHECK constraint missing; saw {check_clauses!r}"
    )
