"""Module A user management endpoints — Y1-Y5 integration + RBAC + J5.

Covers `app/admin/api/v1/users.py` + `app/admin/middleware/rbac.py` +
`tests/admin/fixtures_j5.py`. Each test runs against an isolated
in-memory aiosqlite engine that is created per-test with the seven
tables the Module A surface needs:

  - 4 admin auth tables (AdminUser, AdminSession, AdminLoginAttempt,
    AdminPasswordReset) so /login + JWT cookie set work end-to-end
  - users (the Step 3 promotion target)
  - user_moderation_actions (the freeze / soft_delete audit trail)
  - admin_audit_log is a Session 3' future table — record_audit() is a
    stub that emits a logger.info envelope, captured via caplog.

Verifications:
  - Y1 GET / — empty / pagination / is_frozen derivation / 400 limits
  - Y2 GET /{user_id} — detail + recent_moderation / 404 / is_frozen
  - Y3 POST /freeze — moderation row + audit; users untouched
  - Y4 POST /force-password-reset — moderation row + audit
  - Y5 DELETE — sets deletion_requested_at + moderation; 409 on dupes
  - RBAC role mismatch + admin-not-found unit branches
  - J5 invariant: assert_user_write_columns whitelist + flush guard
  - audit_context dependency surface

Decision references:
- CLAUDE.md #30.H (Path B Variant 2)
- CLAUDE.md #24.E (admin runtime + cookie + JWT shape)
- ADMIN_PRD §4.1 Module A
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.admin.auth.password import hash_password
from app.admin.middleware.rbac import AuditContext, audit_context, require_role
from app.models.admin import (
    AdminLoginAttempt,
    AdminPasswordReset,
    AdminSession,
    AdminUser,
    AdminUserModerationAction,
)
from app.models.user import User
from tests.admin.fixtures_j5 import (
    ALLOWED_USER_WRITE_COLUMNS,
    J5InvariantViolation,
    assert_user_write_columns,
    install_j5_guard,
)

_TABLES: list[Table] = [
    cast(Table, AdminUser.__table__),
    cast(Table, AdminSession.__table__),
    cast(Table, AdminPasswordReset.__table__),
    cast(Table, AdminLoginAttempt.__table__),
    cast(Table, User.__table__),
    cast(Table, AdminUserModerationAction.__table__),
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


async def _seed_user(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    email: str,
    name_zh: str | None = None,
    name_en: str | None = None,
    deletion_requested_at: datetime | None = None,
    created_at: datetime | None = None,
) -> User:
    """Seed a user. `created_at` defaults to server's `func.now()` but
    callers that depend on deterministic ordering should pass explicit
    values — SQLite resolves `func.now()` to single-second granularity
    so multiple seeds in the same test will tie."""
    async with sessionmaker() as session:
        kwargs: dict[str, object] = dict(
            email=email,
            name_zh=name_zh,
            name_en=name_en,
            deletion_requested_at=deletion_requested_at,
        )
        if created_at is not None:
            kwargs["created_at"] = created_at
            kwargs["updated_at"] = created_at
        user = User(**kwargs)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _seed_freeze(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    user_id: str,
    operator_id: str,
    expires_at: datetime | None = None,
) -> AdminUserModerationAction:
    async with sessionmaker() as session:
        row = AdminUserModerationAction(
            user_id=user_id,
            operator_id=operator_id,
            action="freeze",
            reason="prior",
            expires_at=expires_at,
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


# ---------------------------------------------------------------------------
# Y1 GET / — list (5 cases)
# ---------------------------------------------------------------------------


async def test_list_users_empty_returns_empty_items(http_env: HttpEnv) -> None:
    admin = await _seed_super_admin(http_env.sessionmaker)
    await _login(http_env, admin.email)

    res = await http_env.client.get("/admin/api/v1/users")

    assert res.status_code == 200
    body = res.json()
    assert body == {"items": [], "total": 0}


async def test_list_users_returns_paginated_items_with_freeze_derivation(
    http_env: HttpEnv,
) -> None:
    admin = await _seed_super_admin(http_env.sessionmaker)
    base = datetime(2026, 4, 28, 12, 0, 0)
    u1 = await _seed_user(
        http_env.sessionmaker,
        email="alice@example.com",
        name_zh="爱丽丝",
        created_at=base,
    )
    u2 = await _seed_user(
        http_env.sessionmaker,
        email="bob@example.com",
        name_en="Bob",
        created_at=base + timedelta(seconds=1),
    )
    await _seed_user(
        http_env.sessionmaker,
        email="carol@example.com",
        created_at=base + timedelta(seconds=2),
    )
    # Active freeze on u1, expired freeze on u2 (past expires_at), no freeze on carol.
    await _seed_freeze(http_env.sessionmaker, user_id=u1.id, operator_id=admin.id)
    expired = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
    await _seed_freeze(
        http_env.sessionmaker, user_id=u2.id, operator_id=admin.id, expires_at=expired
    )
    await _login(http_env, admin.email)

    res = await http_env.client.get("/admin/api/v1/users?limit=2&offset=0")

    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    by_email = {item["email"]: item for item in body["items"]}
    # Newest two by created_at desc — u2 + u3 (created after u1).
    assert "carol@example.com" in by_email
    assert "bob@example.com" in by_email
    assert by_email["bob@example.com"]["is_frozen"] is False
    assert by_email["carol@example.com"]["is_frozen"] is False
    assert all(item["is_deleted"] is False for item in body["items"])

    # Page 2 picks up u1 (oldest) with active freeze.
    res2 = await http_env.client.get("/admin/api/v1/users?limit=2&offset=2")
    body2 = res2.json()
    assert len(body2["items"]) == 1
    [item1] = body2["items"]
    assert item1["email"] == "alice@example.com"
    assert item1["is_frozen"] is True


async def test_list_users_invalid_limit_returns_400(http_env: HttpEnv) -> None:
    admin = await _seed_super_admin(http_env.sessionmaker)
    await _login(http_env, admin.email)

    res = await http_env.client.get("/admin/api/v1/users?limit=0")
    assert res.status_code == 400
    assert res.json()["detail"]["reason"] == "invalid_limit"

    res2 = await http_env.client.get("/admin/api/v1/users?limit=501")
    assert res2.status_code == 400
    assert res2.json()["detail"]["reason"] == "invalid_limit"


async def test_list_users_invalid_offset_returns_400(http_env: HttpEnv) -> None:
    admin = await _seed_super_admin(http_env.sessionmaker)
    await _login(http_env, admin.email)

    res = await http_env.client.get("/admin/api/v1/users?offset=-1")
    assert res.status_code == 400
    assert res.json()["detail"]["reason"] == "invalid_offset"


async def test_list_users_without_session_returns_401(http_env: HttpEnv) -> None:
    res = await http_env.client.get("/admin/api/v1/users")
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# Y2 GET /{user_id} — detail (3 cases)
# ---------------------------------------------------------------------------


async def test_get_user_returns_full_detail_with_recent_moderation(
    http_env: HttpEnv,
) -> None:
    admin = await _seed_super_admin(http_env.sessionmaker)
    user = await _seed_user(
        http_env.sessionmaker, email="ya@example.com", name_zh="测试", name_en="Test"
    )
    await _seed_freeze(http_env.sessionmaker, user_id=user.id, operator_id=admin.id)
    await _login(http_env, admin.email)

    res = await http_env.client.get(f"/admin/api/v1/users/{user.id}")

    assert res.status_code == 200
    body = res.json()
    assert body["id"] == user.id
    assert body["email"] == "ya@example.com"
    assert body["name_zh"] == "测试"
    assert body["name_en"] == "Test"
    assert body["is_frozen"] is True
    assert body["deletion_requested_at"] is None
    assert len(body["recent_moderation"]) == 1
    [entry] = body["recent_moderation"]
    assert entry["action"] == "freeze"
    assert entry["operator_id"] == admin.id


async def test_get_user_not_found_returns_404(http_env: HttpEnv) -> None:
    admin = await _seed_super_admin(http_env.sessionmaker)
    await _login(http_env, admin.email)

    res = await http_env.client.get("/admin/api/v1/users/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404
    assert res.json()["detail"]["reason"] == "user_not_found"


async def test_get_user_with_no_active_freeze_is_not_frozen(http_env: HttpEnv) -> None:
    admin = await _seed_super_admin(http_env.sessionmaker)
    user = await _seed_user(http_env.sessionmaker, email="fresh@example.com")
    await _login(http_env, admin.email)

    res = await http_env.client.get(f"/admin/api/v1/users/{user.id}")
    body = res.json()
    assert body["is_frozen"] is False
    assert body["recent_moderation"] == []


# ---------------------------------------------------------------------------
# Y3 POST /freeze (3 cases)
# ---------------------------------------------------------------------------


async def test_freeze_user_inserts_moderation_and_audits_without_touching_users(
    http_env: HttpEnv, caplog: pytest.LogCaptureFixture
) -> None:
    admin = await _seed_super_admin(http_env.sessionmaker)
    user = await _seed_user(http_env.sessionmaker, email="target@example.com")
    await _login(http_env, admin.email)

    expires_at = (datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)).isoformat()
    with caplog.at_level(logging.INFO, logger="app.services.admin_audit"):
        res = await http_env.client.post(
            f"/admin/api/v1/users/{user.id}/freeze",
            json={"reason": "spamming", "expires_at": expires_at},
        )

    assert res.status_code == 200
    assert res.json() == {"user_id": user.id, "action": "freeze"}

    async with http_env.sessionmaker() as s:
        [row] = (await s.execute(select(AdminUserModerationAction))).scalars().all()
        assert row.action == "freeze"
        assert row.reason == "spamming"
        assert row.operator_id == admin.id
        assert row.user_id == user.id
        # users.deletion_requested_at must remain unchanged (J5 invariant).
        fetched = (await s.execute(select(User).where(User.id == user.id))).scalar_one()
        assert fetched.deletion_requested_at is None
    # admin_audit.stub envelope emitted.
    assert any("admin_audit.stub" in r.getMessage() for r in caplog.records)


async def test_freeze_user_404_when_user_missing(http_env: HttpEnv) -> None:
    admin = await _seed_super_admin(http_env.sessionmaker)
    await _login(http_env, admin.email)

    res = await http_env.client.post(
        "/admin/api/v1/users/00000000-0000-0000-0000-000000000000/freeze",
        json={"reason": "abuse"},
    )
    assert res.status_code == 404


async def test_freeze_user_rejects_empty_reason(http_env: HttpEnv) -> None:
    admin = await _seed_super_admin(http_env.sessionmaker)
    user = await _seed_user(http_env.sessionmaker, email="x@example.com")
    await _login(http_env, admin.email)

    res = await http_env.client.post(
        f"/admin/api/v1/users/{user.id}/freeze",
        json={"reason": ""},
    )
    # Pydantic v2 min_length=1 rejection → 422
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# Y4 POST /force-password-reset (1 case)
# ---------------------------------------------------------------------------


async def test_force_password_reset_inserts_moderation_row(
    http_env: HttpEnv, caplog: pytest.LogCaptureFixture
) -> None:
    admin = await _seed_super_admin(http_env.sessionmaker)
    user = await _seed_user(http_env.sessionmaker, email="rotate@example.com")
    await _login(http_env, admin.email)

    with caplog.at_level(logging.INFO, logger="app.services.admin_audit"):
        res = await http_env.client.post(
            f"/admin/api/v1/users/{user.id}/force-password-reset",
            json={},  # reason is optional
        )

    assert res.status_code == 200
    assert res.json() == {"user_id": user.id, "action": "force_password_reset"}
    async with http_env.sessionmaker() as s:
        [row] = (await s.execute(select(AdminUserModerationAction))).scalars().all()
        assert row.action == "force_password_reset"
        assert row.reason is None
    assert any("admin_audit.stub" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# Y5 DELETE /{user_id} (3 cases)
# ---------------------------------------------------------------------------


async def test_soft_delete_sets_timestamp_and_writes_moderation_row(
    http_env: HttpEnv, caplog: pytest.LogCaptureFixture
) -> None:
    admin = await _seed_super_admin(http_env.sessionmaker)
    user = await _seed_user(http_env.sessionmaker, email="bye@example.com")
    await _login(http_env, admin.email)

    with caplog.at_level(logging.INFO, logger="app.services.admin_audit"):
        res = await http_env.client.request(
            "DELETE",
            f"/admin/api/v1/users/{user.id}",
            json={"reason": "user requested deletion"},
        )

    assert res.status_code == 200
    assert res.json() == {"user_id": user.id, "action": "soft_delete"}

    async with http_env.sessionmaker() as s:
        fetched = (await s.execute(select(User).where(User.id == user.id))).scalar_one()
        assert fetched.deletion_requested_at is not None
        [mod] = (await s.execute(select(AdminUserModerationAction))).scalars().all()
        assert mod.action == "soft_delete"
        assert mod.reason == "user requested deletion"
    assert any("admin_audit.stub" in r.getMessage() for r in caplog.records)


async def test_soft_delete_returns_409_when_already_deleted(
    http_env: HttpEnv,
) -> None:
    admin = await _seed_super_admin(http_env.sessionmaker)
    user = await _seed_user(
        http_env.sessionmaker,
        email="gone@example.com",
        deletion_requested_at=datetime.now(UTC).replace(tzinfo=None),
    )
    await _login(http_env, admin.email)

    res = await http_env.client.request(
        "DELETE",
        f"/admin/api/v1/users/{user.id}",
        json={"reason": "second time"},
    )
    assert res.status_code == 409
    assert res.json()["detail"]["reason"] == "already_deleted"


async def test_soft_delete_404_when_user_missing(http_env: HttpEnv) -> None:
    admin = await _seed_super_admin(http_env.sessionmaker)
    await _login(http_env, admin.email)

    res = await http_env.client.request(
        "DELETE",
        "/admin/api/v1/users/00000000-0000-0000-0000-000000000000",
        json={"reason": "ghost"},
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# RBAC unit branches (2 cases) — call _dependency directly
# ---------------------------------------------------------------------------


async def test_require_role_returns_admin_user_when_role_matches(
    http_env: HttpEnv,
) -> None:
    admin = await _seed_super_admin(http_env.sessionmaker)
    dep = require_role("super_admin")

    class _Payload:
        sub = admin.id

    async with http_env.sessionmaker() as session:
        ctx = AuditContext(operator_id=admin.id, ip="127.0.0.1", ua="pytest")
        result = await dep(payload=_Payload(), ctx=ctx, db=session)
        assert result.id == admin.id


async def test_require_role_403_when_role_mismatches_and_audits_denied(
    http_env: HttpEnv, caplog: pytest.LogCaptureFixture
) -> None:
    """A0 only allows role='super_admin' on AdminUser (CHECK constraint
    per decision #24.C2). To cover the role-mismatch branch without
    breaking that CHECK, ask for a different role on a real super_admin
    seed; the dependency's mismatch check fires either way."""
    admin = await _seed_super_admin(http_env.sessionmaker)
    dep = require_role("ops_admin")  # required != actual

    class _Payload:
        sub = admin.id

    async with http_env.sessionmaker() as session:
        ctx = AuditContext(operator_id=admin.id, ip="127.0.0.1", ua="pytest")
        with caplog.at_level(logging.INFO, logger="app.services.admin_audit"):
            with pytest.raises(HTTPException) as exc_info:
                await dep(payload=_Payload(), ctx=ctx, db=session)

    assert exc_info.value.status_code == 403
    forbidden_detail: object = exc_info.value.detail
    assert forbidden_detail == {"reason": "forbidden"}
    # access_denied audit envelope was emitted by record_audit().
    assert any(
        "admin_audit.stub" in r.getMessage()
        and getattr(r, "audit", {}).get("action") == "access_denied"
        for r in caplog.records
    )


async def test_require_role_401_when_admin_user_missing(
    http_env: HttpEnv,
) -> None:
    dep = require_role("super_admin")

    class _Payload:
        sub = "00000000-0000-0000-0000-000000000000"

    async with http_env.sessionmaker() as session:
        ctx = AuditContext(operator_id=_Payload.sub, ip=None, ua=None)
        with pytest.raises(HTTPException) as exc_info:
            await dep(payload=_Payload(), ctx=ctx, db=session)
    assert exc_info.value.status_code == 401
    detail: object = exc_info.value.detail
    assert detail == {"reason": "no_session"}


async def test_audit_context_returns_envelope_from_request_and_payload() -> None:
    """Smoke-test the dataclass directly so the dependency wiring stays
    a one-liner that doesn't need its own integration test."""
    ctx = AuditContext(operator_id="op-1", ip="1.2.3.4", ua="curl/8.0")
    assert ctx.operator_id == "op-1"
    assert ctx.ip == "1.2.3.4"
    assert ctx.ua == "curl/8.0"
    # The dependency is just a wrapper; calling it with a stub Request +
    # a payload-like object proves the AuditContext is returned, not a
    # behavioural quirk of FastAPI's DI graph.

    class _Payload:
        sub = "op-1"

    class _Headers:
        def get(self, _k: str) -> str | None:
            return None

    class _Req:
        headers = _Headers()
        client = None

    out = audit_context(_Req(), payload=_Payload())  # type: ignore[arg-type]
    assert out.operator_id == "op-1"
    assert out.ip is None
    assert out.ua is None


# ---------------------------------------------------------------------------
# J5 fixture invariant (3 cases)
# ---------------------------------------------------------------------------


def test_j5_assert_user_write_columns_passes_for_whitelist() -> None:
    assert ALLOWED_USER_WRITE_COLUMNS == frozenset({"deletion_requested_at"})
    # Should NOT raise.
    assert_user_write_columns(["deletion_requested_at"])
    assert_user_write_columns([])


def test_j5_assert_user_write_columns_raises_on_violation() -> None:
    with pytest.raises(J5InvariantViolation):
        assert_user_write_columns(["email"])
    with pytest.raises(J5InvariantViolation):
        assert_user_write_columns(["deletion_requested_at", "preferences"])


async def test_j5_install_guard_blocks_non_whitelisted_user_mutation(
    http_env: HttpEnv,
) -> None:
    """Round-trip the guard: a deletion_requested_at write passes, a
    preferences write trips the J5InvariantViolation at flush time."""
    user = await _seed_user(http_env.sessionmaker, email="j5@example.com")

    # Guard installed: writing deletion_requested_at is fine.
    async with http_env.sessionmaker() as session:
        install_j5_guard(session)
        # Calling install_j5_guard a second time is a no-op (idempotency check).
        install_j5_guard(session)
        fetched = (await session.execute(select(User).where(User.id == user.id))).scalar_one()
        fetched.deletion_requested_at = datetime.now(UTC).replace(tzinfo=None)
        await session.commit()

    # Guard installed: writing preferences trips the guard at flush.
    async with http_env.sessionmaker() as session:
        install_j5_guard(session)
        fetched = (await session.execute(select(User).where(User.id == user.id))).scalar_one()
        fetched.preferences = {"locale": "en-US"}
        with pytest.raises(J5InvariantViolation):
            await session.commit()
        await session.rollback()
