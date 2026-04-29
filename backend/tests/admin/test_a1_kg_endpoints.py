"""Module C KG admin endpoints — Y24-Y27 integration + RBAC + audit (Step 4 v2).

Covers `app/admin/api/v1/kg.py` per Option Z scope (CLAUDE.md #30.J).
A1' Step 4 limits the deliverable to the 4 admin-side endpoints over the
3 admin tables already in Step 1 baseline:

  - alias_conflicts
  - brand_submissions
  - kg_review_queue (read-only consumers in Module C frontend; not yet
    written-to in Step 4)

Verifications:
  - Y24 GET /alias-conflicts — derived candidate_count + is_resolved;
    `?status=pending` filter excludes resolved rows
  - Y25 POST /alias-conflicts/{id}/resolve — candidate validation
    (round 9 / #30.H N-候选 protection); already-resolved → 409;
    audit `alias_resolve` emitted
  - Y26 GET /submissions — derived sla_overdue (24h cutoff) + ordering
    on sla_started_at ascending
  - Y27.1 POST /submissions/{id}/approve — pending → approved transition
    + `submission_approve` audit; not-pending → 409
  - Y27.2 POST /submissions/{id}/reject — required reason; pending →
    rejected; missing reason → 422

Decision references:
- CLAUDE.md #30.J (Option Z scope-cut for A1' Step 4)
- CLAUDE.md #30.H (Path B Variant 2 — N-候选 JSONB invariant)
- CLAUDE.md #30.G (round 8 — alias_conflicts schema = N-候选 JSONB)
- ADMIN_PRD §4.3 Module C
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.admin.auth.password import hash_password
from app.models.admin import (
    AdminLoginAttempt,
    AdminPasswordReset,
    AdminSession,
    AdminUser,
    AliasConflict,
    BrandSubmission,
    KgReviewQueue,
)

_TABLES: list[Table] = [
    cast(Table, AdminUser.__table__),
    cast(Table, AdminSession.__table__),
    cast(Table, AdminPasswordReset.__table__),
    cast(Table, AdminLoginAttempt.__table__),
    cast(Table, AliasConflict.__table__),
    cast(Table, BrandSubmission.__table__),
    cast(Table, KgReviewQueue.__table__),
]

_KNOWN_PASSWORD = "Tr0ub4dor&3-Long"


@dataclass
class HttpEnv:
    client: AsyncClient
    sessionmaker: async_sessionmaker[AsyncSession]


@pytest_asyncio.fixture
async def http_env() -> AsyncGenerator[HttpEnv, None]:
    from app.admin.auth.rate_limiter import reset_for_tests
    from app.db.session import get_db
    from app.main import app

    reset_for_tests()

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        for table in _TABLES:
            await conn.run_sync(table.create)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield HttpEnv(client=client, sessionmaker=sessionmaker)
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
        reset_for_tests()


@pytest.fixture(autouse=True)
def _admin_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_JWT_SECRET", "x" * 64)


def _utc_naive_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _seed_super_admin(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    email: str = "ops@genpano.com",
) -> AdminUser:
    async with sessionmaker() as session:
        admin = AdminUser(
            email=email,
            password_hash=hash_password(_KNOWN_PASSWORD),
            role="super_admin",
            status="active",
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        return admin


async def _seed_alias_conflict(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    alias_value: str,
    language: str,
    candidate_ids: list[str],
    resolved_to_id: str | None = None,
    resolved_admin_id: str | None = None,
) -> AliasConflict:
    async with sessionmaker() as session:
        row = AliasConflict(
            alias_value=alias_value,
            language=language,
            candidate_ids=candidate_ids,
            resolved_to_id=resolved_to_id,
            resolved_admin_id=resolved_admin_id,
            resolved_at=_utc_naive_now() if resolved_to_id else None,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def _seed_submission(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    brand_name_zh: str | None,
    status_value: str,
    sla_started_at: datetime,
    aliases: list[str] | None = None,
) -> BrandSubmission:
    async with sessionmaker() as session:
        row = BrandSubmission(
            brand_name_zh=brand_name_zh,
            brand_name_en=None,
            aliases=aliases,
            status=status_value,
            sla_started_at=sla_started_at,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def _login(env: HttpEnv, email: str) -> None:
    res = await env.client.post(
        "/admin/api/v1/auth/login",
        json={"email": email, "password": _KNOWN_PASSWORD},
    )
    assert res.status_code == 200, res.text


def _audit_records(caplog: pytest.LogCaptureFixture, action: str) -> list[logging.LogRecord]:
    return [
        r
        for r in caplog.records
        if "admin_audit.stub" in r.getMessage() and getattr(r, "audit", {}).get("action") == action
    ]


# ---------------------------------------------------------------------------
# Y24 GET /alias-conflicts (2 cases)
# ---------------------------------------------------------------------------


async def test_list_alias_conflicts_returns_items_with_derived_count_and_status(
    http_env: HttpEnv,
) -> None:
    admin = await _seed_super_admin(http_env.sessionmaker)
    await _seed_alias_conflict(
        http_env.sessionmaker,
        alias_value="LV",
        language="en",
        candidate_ids=["brand-1", "brand-2", "brand-3"],
    )
    await _seed_alias_conflict(
        http_env.sessionmaker,
        alias_value="兰蔻",
        language="zh-CN",
        candidate_ids=["brand-4", "brand-5"],
        resolved_to_id="brand-4",
        resolved_admin_id=admin.id,
    )
    await _login(http_env, admin.email)

    res = await http_env.client.get("/admin/api/v1/kg/alias-conflicts")

    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2
    by_alias = {item["alias_value"]: item for item in body["items"]}

    lv = by_alias["LV"]
    assert lv["candidate_count"] == 3
    assert lv["candidate_ids"] == ["brand-1", "brand-2", "brand-3"]
    assert lv["is_resolved"] is False
    assert lv["resolved_to_id"] is None

    lancome = by_alias["兰蔻"]
    assert lancome["candidate_count"] == 2
    assert lancome["is_resolved"] is True
    assert lancome["resolved_to_id"] == "brand-4"
    assert lancome["resolved_admin_id"] == admin.id


async def test_list_alias_conflicts_status_filter_pending_excludes_resolved(
    http_env: HttpEnv,
) -> None:
    admin = await _seed_super_admin(http_env.sessionmaker)
    await _seed_alias_conflict(
        http_env.sessionmaker,
        alias_value="pending-alias",
        language="en",
        candidate_ids=["x", "y"],
    )
    await _seed_alias_conflict(
        http_env.sessionmaker,
        alias_value="resolved-alias",
        language="en",
        candidate_ids=["a", "b"],
        resolved_to_id="a",
        resolved_admin_id=admin.id,
    )
    await _login(http_env, admin.email)

    res = await http_env.client.get("/admin/api/v1/kg/alias-conflicts?status=pending")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["alias_value"] == "pending-alias"

    res2 = await http_env.client.get("/admin/api/v1/kg/alias-conflicts?status=resolved")
    body2 = res2.json()
    assert body2["total"] == 1
    assert body2["items"][0]["alias_value"] == "resolved-alias"

    res3 = await http_env.client.get("/admin/api/v1/kg/alias-conflicts?status=bogus")
    assert res3.status_code == 400
    assert res3.json()["detail"]["reason"] == "invalid_status_filter"


# ---------------------------------------------------------------------------
# Y25 POST /alias-conflicts/{id}/resolve (3 cases) — N-候选 invariant
# ---------------------------------------------------------------------------


async def test_resolve_alias_conflict_with_candidate_succeeds_and_audits(
    http_env: HttpEnv, caplog: pytest.LogCaptureFixture
) -> None:
    admin = await _seed_super_admin(http_env.sessionmaker)
    conflict = await _seed_alias_conflict(
        http_env.sessionmaker,
        alias_value="兰蔻",
        language="zh-CN",
        candidate_ids=["brand-lancome-zh", "brand-lancome-fr", "brand-lancome-jp"],
    )
    await _login(http_env, admin.email)

    with caplog.at_level(logging.INFO, logger="app.services.admin_audit"):
        res = await http_env.client.post(
            f"/admin/api/v1/kg/alias-conflicts/{conflict.id}/resolve",
            json={"resolved_to_id": "brand-lancome-fr"},
        )

    assert res.status_code == 200
    assert res.json() == {
        "conflict_id": conflict.id,
        "resolved_to_id": "brand-lancome-fr",
    }

    async with http_env.sessionmaker() as s:
        fetched = (
            await s.execute(select(AliasConflict).where(AliasConflict.id == conflict.id))
        ).scalar_one()
        assert fetched.resolved_to_id == "brand-lancome-fr"
        assert fetched.resolved_admin_id == admin.id
        assert fetched.resolved_at is not None

    audit_rows = _audit_records(caplog, "alias_resolve")
    assert len(audit_rows) == 1
    [audit_row] = audit_rows
    audit = getattr(audit_row, "audit", {})
    assert audit["target_type"] == "alias_conflict"
    assert audit["target_id"] == conflict.id
    assert audit["diff"]["resolved_to_id"] == "brand-lancome-fr"
    assert audit["diff"]["candidate_ids"] == [
        "brand-lancome-zh",
        "brand-lancome-fr",
        "brand-lancome-jp",
    ]


async def test_resolve_alias_conflict_with_non_candidate_returns_422(
    http_env: HttpEnv, caplog: pytest.LogCaptureFixture
) -> None:
    """Round 9 / #30.H invariant: chosen id MUST be in candidate_ids JSONB.
    Spoofing or bug-induced off-list selection is rejected before any UPDATE."""
    admin = await _seed_super_admin(http_env.sessionmaker)
    conflict = await _seed_alias_conflict(
        http_env.sessionmaker,
        alias_value="LV",
        language="en",
        candidate_ids=["brand-louis-vuitton", "brand-las-vegas"],
    )
    await _login(http_env, admin.email)

    with caplog.at_level(logging.INFO, logger="app.services.admin_audit"):
        res = await http_env.client.post(
            f"/admin/api/v1/kg/alias-conflicts/{conflict.id}/resolve",
            json={"resolved_to_id": "brand-not-in-list"},
        )

    assert res.status_code == 422
    assert res.json()["detail"]["reason"] == "resolved_to_id_not_in_candidates"

    async with http_env.sessionmaker() as s:
        fetched = (
            await s.execute(select(AliasConflict).where(AliasConflict.id == conflict.id))
        ).scalar_one()
        assert fetched.resolved_to_id is None
        assert fetched.resolved_admin_id is None

    assert _audit_records(caplog, "alias_resolve") == []


async def test_resolve_alias_conflict_already_resolved_returns_409(
    http_env: HttpEnv,
) -> None:
    admin = await _seed_super_admin(http_env.sessionmaker)
    conflict = await _seed_alias_conflict(
        http_env.sessionmaker,
        alias_value="dup",
        language="en",
        candidate_ids=["x", "y"],
        resolved_to_id="x",
        resolved_admin_id=admin.id,
    )
    await _login(http_env, admin.email)

    res = await http_env.client.post(
        f"/admin/api/v1/kg/alias-conflicts/{conflict.id}/resolve",
        json={"resolved_to_id": "y"},
    )
    assert res.status_code == 409
    assert res.json()["detail"]["reason"] == "already_resolved"


# ---------------------------------------------------------------------------
# Y26 GET /submissions (1 case) — 24h SLA derivation + ordering
# ---------------------------------------------------------------------------


async def test_list_submissions_returns_items_with_sla_overdue_derivation(
    http_env: HttpEnv,
) -> None:
    admin = await _seed_super_admin(http_env.sessionmaker)
    now = _utc_naive_now()
    overdue_pending = await _seed_submission(
        http_env.sessionmaker,
        brand_name_zh="过期品牌",
        status_value="pending",
        sla_started_at=now - timedelta(hours=30),
    )
    fresh_pending = await _seed_submission(
        http_env.sessionmaker,
        brand_name_zh="新品牌",
        status_value="pending",
        sla_started_at=now - timedelta(hours=1),
    )
    old_approved = await _seed_submission(
        http_env.sessionmaker,
        brand_name_zh="已批",
        status_value="approved",
        sla_started_at=now - timedelta(hours=72),
    )
    await _login(http_env, admin.email)

    res = await http_env.client.get("/admin/api/v1/kg/submissions")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 3
    # Sorted ascending on sla_started_at — oldest first.
    assert [item["id"] for item in body["items"]] == [
        old_approved.id,
        overdue_pending.id,
        fresh_pending.id,
    ]
    by_id = {item["id"]: item for item in body["items"]}
    assert by_id[overdue_pending.id]["sla_overdue"] is True
    assert by_id[overdue_pending.id]["hours_since_submission"] >= 24
    assert by_id[fresh_pending.id]["sla_overdue"] is False
    # Status != pending → never overdue regardless of age.
    assert by_id[old_approved.id]["sla_overdue"] is False

    # status filter narrows correctly.
    res_pending = await http_env.client.get("/admin/api/v1/kg/submissions?status=pending")
    body_pending = res_pending.json()
    assert body_pending["total"] == 2
    assert {item["id"] for item in body_pending["items"]} == {
        overdue_pending.id,
        fresh_pending.id,
    }


# ---------------------------------------------------------------------------
# Y27.1 POST /submissions/{id}/approve (2 cases)
# ---------------------------------------------------------------------------


async def test_approve_submission_transitions_to_approved_and_audits(
    http_env: HttpEnv, caplog: pytest.LogCaptureFixture
) -> None:
    admin = await _seed_super_admin(http_env.sessionmaker)
    submission = await _seed_submission(
        http_env.sessionmaker,
        brand_name_zh="待审品牌",
        status_value="pending",
        sla_started_at=_utc_naive_now() - timedelta(hours=2),
    )
    await _login(http_env, admin.email)

    with caplog.at_level(logging.INFO, logger="app.services.admin_audit"):
        res = await http_env.client.post(
            f"/admin/api/v1/kg/submissions/{submission.id}/approve",
            json={"reason": "verified by ops"},
        )

    assert res.status_code == 200
    assert res.json() == {"submission_id": submission.id, "action": "approve"}

    async with http_env.sessionmaker() as s:
        fetched = (
            await s.execute(select(BrandSubmission).where(BrandSubmission.id == submission.id))
        ).scalar_one()
        assert fetched.status == "approved"
        assert fetched.resolved_admin_id == admin.id
        assert fetched.resolved_at is not None

    audit_rows = _audit_records(caplog, "submission_approve")
    assert len(audit_rows) == 1
    audit = getattr(audit_rows[0], "audit", {})
    assert audit["target_type"] == "brand_submission"
    assert audit["target_id"] == submission.id
    assert audit["diff"] == {"from": "pending", "to": "approved"}
    assert audit["reason"] == "verified by ops"


async def test_approve_submission_not_pending_returns_409(http_env: HttpEnv) -> None:
    admin = await _seed_super_admin(http_env.sessionmaker)
    submission = await _seed_submission(
        http_env.sessionmaker,
        brand_name_zh="已批品牌",
        status_value="approved",
        sla_started_at=_utc_naive_now() - timedelta(hours=10),
    )
    await _login(http_env, admin.email)

    res = await http_env.client.post(
        f"/admin/api/v1/kg/submissions/{submission.id}/approve",
        json={"reason": "second time"},
    )
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert detail["reason"] == "not_pending"
    assert detail["current_status"] == "approved"


# ---------------------------------------------------------------------------
# Y27.2 POST /submissions/{id}/reject (2 cases)
# ---------------------------------------------------------------------------


async def test_reject_submission_with_reason_transitions_to_rejected_and_audits(
    http_env: HttpEnv, caplog: pytest.LogCaptureFixture
) -> None:
    admin = await _seed_super_admin(http_env.sessionmaker)
    submission = await _seed_submission(
        http_env.sessionmaker,
        brand_name_zh="待拒品牌",
        status_value="pending",
        sla_started_at=_utc_naive_now() - timedelta(hours=3),
    )
    await _login(http_env, admin.email)

    with caplog.at_level(logging.INFO, logger="app.services.admin_audit"):
        res = await http_env.client.post(
            f"/admin/api/v1/kg/submissions/{submission.id}/reject",
            json={"reason": "duplicate of existing brand"},
        )

    assert res.status_code == 200
    assert res.json() == {"submission_id": submission.id, "action": "reject"}

    async with http_env.sessionmaker() as s:
        fetched = (
            await s.execute(select(BrandSubmission).where(BrandSubmission.id == submission.id))
        ).scalar_one()
        assert fetched.status == "rejected"
        assert fetched.resolved_admin_id == admin.id

    audit_rows = _audit_records(caplog, "submission_reject")
    assert len(audit_rows) == 1
    audit = getattr(audit_rows[0], "audit", {})
    assert audit["target_id"] == submission.id
    assert audit["diff"] == {"from": "pending", "to": "rejected"}
    assert audit["reason"] == "duplicate of existing brand"


async def test_reject_submission_missing_reason_returns_422(http_env: HttpEnv) -> None:
    admin = await _seed_super_admin(http_env.sessionmaker)
    submission = await _seed_submission(
        http_env.sessionmaker,
        brand_name_zh="待拒品牌",
        status_value="pending",
        sla_started_at=_utc_naive_now() - timedelta(hours=1),
    )
    await _login(http_env, admin.email)

    res = await http_env.client.post(
        f"/admin/api/v1/kg/submissions/{submission.id}/reject",
        json={},
    )
    # Pydantic v2 — required field missing → 422.
    assert res.status_code == 422

    res2 = await http_env.client.post(
        f"/admin/api/v1/kg/submissions/{submission.id}/reject",
        json={"reason": ""},
    )
    # min_length=1 also rejected.
    assert res2.status_code == 422
