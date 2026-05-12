"""Phase 7 slice 7b — admin/accounts (cookies / status / reset / delete / auto_login).

``llm_accounts`` is NOT in backend's ORM (production-only table per
ADR-002). Tests therefore mock the ``accounts_db`` helpers and
exercise the handler logic (auth, validation, audit emission, security
hardening). Pure-python validators in ``app/admin/accounts/lib.py``
are tested directly.

Sensitivity note: these tests verify the audit row NEVER includes the
cookies blob. Operator credentials must not leak into ``admin_audit_log``.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from genpano_models import AdminAuditLog, AdminUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.accounts.lib import (
    ACCOUNT_STATUSES,
    CookieImportError,
    normalize_account_status,
    parse_cookies_payload,
    safe_email_for_label,
)

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture
async def admin_operator(db_session: AsyncSession) -> AsyncGenerator[AdminUser, None]:
    from app.api.admin.auth.router import current_admin
    from app.main import app

    a = AdminUser(
        id=_new_id(),
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="$2b$04$dummyhashfortestsdummyhashfortestsdummyhashfortest",
        role="super_admin",
        status="active",
    )
    db_session.add(a)
    await db_session.commit()

    async def _override_current_admin() -> AdminUser:
        return a

    app.dependency_overrides[current_admin] = _override_current_admin
    try:
        yield a
    finally:
        app.dependency_overrides.pop(current_admin, None)


def _accounts_router_module():
    import app.api.admin.accounts.router  # noqa: F401

    return sys.modules["app.api.admin.accounts.router"]


def _patch_db(
    monkeypatch,
    *,
    accounts=None,
    detail=None,
    upsert_returns=(1, "added"),
    upsert_raises=None,
    status_ok=True,
    reset_ok=True,
    delete_ok=True,
    daily_limit_ok=True,
):
    a = _accounts_router_module()
    monkeypatch.setattr(
        a.accounts_db,
        "fetch_accounts",
        AsyncMock(return_value=list(accounts or [])),
    )
    monkeypatch.setattr(a.accounts_db, "get_account", AsyncMock(return_value=detail))
    if upsert_raises is not None:
        monkeypatch.setattr(
            a.accounts_db,
            "upsert_account_from_cookies",
            AsyncMock(side_effect=upsert_raises),
        )
    else:
        monkeypatch.setattr(
            a.accounts_db,
            "upsert_account_from_cookies",
            AsyncMock(return_value=upsert_returns),
        )
    monkeypatch.setattr(
        a.accounts_db,
        "update_account_status",
        AsyncMock(return_value=status_ok),
    )
    monkeypatch.setattr(
        a.accounts_db,
        "reset_account_fails",
        AsyncMock(return_value=reset_ok),
    )
    monkeypatch.setattr(
        a.accounts_db,
        "delete_account",
        AsyncMock(return_value=delete_ok),
    )
    monkeypatch.setattr(
        a.accounts_db,
        "update_account_daily_limit",
        AsyncMock(return_value=daily_limit_ok),
    )


def _account_row(account_id: int = 1) -> dict:
    return {
        "id": account_id,
        "llm_name": "doubao",
        "phone_number": "label-1",
        "status": "active",
        "daily_used": 0,
        "daily_limit": 20,
        "consecutive_fails": 0,
        "cookies_updated_at": None,
        "updated_at": None,
    }


# ── lib.py: pure helpers ─────────────────────────────────────


def test_account_statuses_constant():
    assert ACCOUNT_STATUSES == ("active", "banned", "cooldown", "expired")


def test_normalize_account_status_valid():
    assert normalize_account_status("active") == "active"
    assert normalize_account_status("BANNED") == "banned"
    assert normalize_account_status("EXPIRED") == "expired"


def test_normalize_account_status_invalid():
    assert normalize_account_status("weird") is None
    assert normalize_account_status("") is None


def test_safe_email_for_label_strips_unsafe():
    # Trailing unsafe chars get collapsed + stripped (no "_." suffix).
    assert safe_email_for_label("op#1", "doubao!") == "op_1@doubao.local"


def test_parse_cookies_payload_simple():
    payload = {
        "platform": "doubao",
        "label": "test1",
        "cookies_json": json.dumps([{"name": "k", "value": "v", "domain": "x"}]),
    }
    platform, label, cookies_json, count, ls_count, daily_limit = parse_cookies_payload(payload)
    assert platform == "doubao"
    assert label == "test1"
    assert count == 1
    assert ls_count == 0
    assert daily_limit == 20
    parsed = json.loads(cookies_json)
    assert parsed[0]["name"] == "k"


def test_parse_cookies_payload_default_label():
    payload = {
        "platform": "x",
        "cookies_json": json.dumps([{"name": "k", "value": "v"}]),
    }
    _, label, *_ = parse_cookies_payload(payload)
    assert label == "web_upload"


def test_parse_cookies_payload_missing_platform():
    with pytest.raises(CookieImportError) as exc:
        parse_cookies_payload({"cookies_json": "[]"})
    assert exc.value.code == "platform_required"


def test_parse_cookies_payload_invalid_json():
    with pytest.raises(CookieImportError) as exc:
        parse_cookies_payload({"platform": "x", "cookies_json": "not json"})
    assert exc.value.code == "invalid_cookies_json"


def test_parse_cookies_payload_no_cookies():
    with pytest.raises(CookieImportError) as exc:
        parse_cookies_payload({"platform": "x", "cookies_json": "[]"})
    assert exc.value.code == "no_valid_cookies"


def test_parse_cookies_payload_edit_this_cookie_format():
    """EditThisCookie format (storeId / hostOnly / sameSite=lax) →
    Playwright shape, with 30d TTL injected for session cookies."""
    payload = {
        "platform": "x",
        "cookies_json": json.dumps(
            [
                {
                    "name": "k",
                    "value": "v",
                    "domain": "doubao.com",
                    "path": "/",
                    "storeId": "0",
                    "hostOnly": False,
                    "session": True,
                    "sameSite": "no_restriction",
                    "secure": True,
                    "httpOnly": True,
                }
            ]
        ),
    }
    _, _, cookies_json, count, _, _ = parse_cookies_payload(payload)
    assert count == 1
    parsed = json.loads(cookies_json)
    assert parsed[0]["sameSite"] == "None"
    assert parsed[0]["secure"] is True
    assert parsed[0]["httpOnly"] is True
    # Session-cookie TTL injection
    assert parsed[0]["expires"] > 0


def test_parse_cookies_payload_with_local_storage():
    payload = {
        "platform": "x",
        "cookies_json": json.dumps([{"name": "k", "value": "v"}]),
        "local_storage": json.dumps({"key": "val"}),
    }
    _, _, cookies_json, _count, ls_count, _ = parse_cookies_payload(payload)
    assert ls_count == 1
    parsed = json.loads(cookies_json)
    assert "cookies" in parsed
    assert parsed["localStorage"]["key"] == "val"


# ── auth (security hardening — admin_console didn't have it) ─


@pytest.mark.asyncio
async def test_list_unauth_401(client):
    """Slice 7b adds admin auth that admin_console was missing."""
    resp = await client.get("/api/admin/accounts")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_import_cookies_unauth_401(client):
    resp = await client.post(
        "/api/admin/accounts/import_cookies",
        json={"platform": "x", "cookies_json": "[]"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_status_unauth_401(client):
    resp = await client.post("/api/admin/accounts/1/status", json={"status": "active"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_reset_unauth_401(client):
    resp = await client.post("/api/admin/accounts/1/reset")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_unauth_401(client):
    resp = await client.delete("/api/admin/accounts/1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auto_login_unauth_401(client):
    resp = await client.post("/api/admin/accounts/1/auto_login")
    assert resp.status_code == 401


# ── legacy alias — also auth-required (security hardening) ───


@pytest.mark.asyncio
async def test_legacy_alias_list_unauth_401(client):
    """admin_console exposed /api/accounts WITHOUT admin auth; 7b
    locks it down. Non-authenticated callers get 401."""
    resp = await client.get("/api/accounts")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_legacy_alias_import_cookies_unauth_401(client):
    resp = await client.post(
        "/api/accounts/import_cookies",
        json={"platform": "x", "cookies_json": "[]"},
    )
    assert resp.status_code == 401


# ── GET / list ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_returns_rows_no_cookies_blob(client, admin_operator, monkeypatch):
    """Wire shape mirrors admin_console; we explicitly verify there's
    NO cookies_json or cookies field."""
    _patch_db(monkeypatch, accounts=[_account_row(1), _account_row(2)])
    resp = await client.get("/api/admin/accounts")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 2
    for row in body:
        assert "cookies_json" not in row
        assert "cookies" not in row


@pytest.mark.asyncio
async def test_list_accepts_expired_status_filter_and_redacts_phone(
    client, admin_operator, monkeypatch
):
    """#619: expired is first-class, but sensitive account material is not."""
    row = {
        **_account_row(3),
        "status": "expired",
        "phone_number": "+14155552671",
        "cookie_count": 2,
        "cookies_updated_at": "2026-05-12T13:30:00",
        "cookies_json": [{"name": "session", "value": "secret-cookie"}],
        "sms_text": "Your code is 654321",
        "provider_api_key": "secret-provider-key",
    }
    _patch_db(monkeypatch, accounts=[row])
    a = _accounts_router_module()

    resp = await client.get("/api/admin/accounts?status=expired")

    assert resp.status_code == 200
    a.accounts_db.fetch_accounts.assert_awaited_once()
    _, kwargs = a.accounts_db.fetch_accounts.await_args
    assert kwargs["status"] == "expired"
    body = resp.json()
    assert body[0]["status"] == "expired"
    assert body[0]["phone_number"] == "141****2671"
    assert body[0]["cookie_count"] == 2
    assert body[0]["cookies_updated_at"] == "2026-05-12T13:30:00"
    rendered = json.dumps(body)
    assert "+14155552671" not in rendered
    assert "secret-cookie" not in rendered
    assert "654321" not in rendered
    assert "secret-provider-key" not in rendered
    assert "cookies_json" not in body[0]
    assert "sms_text" not in body[0]
    assert "provider_api_key" not in body[0]


@pytest.mark.asyncio
async def test_list_rejects_invalid_status_filter(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch)
    a = _accounts_router_module()

    resp = await client.get("/api/admin/accounts?status=revoked")

    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_status"
    a.accounts_db.fetch_accounts.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_via_legacy_alias(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, accounts=[_account_row(7)])
    resp = await client.get("/api/accounts")
    assert resp.status_code == 200
    assert resp.json()[0]["id"] == 7


# ── POST /import_cookies ─────────────────────────────────────


@pytest.mark.asyncio
async def test_import_cookies_validates_platform_400(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch)
    resp = await client.post(
        "/api/admin/accounts/import_cookies",
        json={"cookies_json": "[]"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "platform_required"


@pytest.mark.asyncio
async def test_import_cookies_validates_no_cookies_400(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch)
    resp = await client.post(
        "/api/admin/accounts/import_cookies",
        json={"platform": "doubao", "cookies_json": "[]"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "no_valid_cookies"


@pytest.mark.asyncio
async def test_import_cookies_returns_503_when_table_missing(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, upsert_raises=RuntimeError("llm_accounts_table_missing"))
    resp = await client.post(
        "/api/admin/accounts/import_cookies",
        json={
            "platform": "doubao",
            "cookies_json": json.dumps([{"name": "k", "value": "v"}]),
        },
    )
    assert resp.status_code == 503
    assert resp.json()["error"] == "llm_accounts_unavailable"


@pytest.mark.asyncio
async def test_import_cookies_returns_503_when_schema_outdated(client, admin_operator, monkeypatch):
    """Defense-in-depth (PR #367 lesson): if a legacy DB is missing
    columns we depend on, surface 503 with a stable code instead of
    letting psycopg's UndefinedColumn become a 500."""
    _patch_db(
        monkeypatch,
        upsert_raises=RuntimeError("llm_accounts_schema_outdated:cookies_json,cooldown_until"),
    )
    resp = await client.post(
        "/api/admin/accounts/import_cookies",
        json={
            "platform": "doubao",
            "cookies_json": json.dumps([{"name": "k", "value": "v"}]),
        },
    )
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"] == "llm_accounts_schema_outdated"
    assert body["missing_columns"] == ["cookies_json", "cooldown_until"]


@pytest.mark.asyncio
async def test_import_cookies_audit_row_omits_blob(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    """SECURITY: the cookies blob must NEVER appear in the audit
    record — only counts + platform / label."""
    _patch_db(monkeypatch, upsert_returns=(42, "added"))
    cookies = json.dumps([{"name": "secretCookie", "value": "abc123"}])
    resp = await client.post(
        "/api/admin/accounts/import_cookies",
        json={"platform": "doubao", "label": "op-1", "cookies_json": cookies},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["account_id"] == 42

    audit_rows = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "import_cookies")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit_rows) == 1
    audit = audit_rows[0]
    assert audit.severity == "high"
    after = audit.after or {}
    # Counts + identity metadata only — no cookie values.
    assert after.get("cookie_count") == 1
    assert after.get("platform") == "doubao"
    assert after.get("label") == "op-1"
    # CRITICAL: ensure cookie value never landed in the audit row.
    audit_blob = json.dumps(after)
    assert "secretCookie" not in audit_blob
    assert "abc123" not in audit_blob


# ── POST /{id}/status ────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_invalid_400(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, detail=_account_row(1))
    resp = await client.post("/api/admin/accounts/1/status", json={"status": "weird"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_status"


@pytest.mark.asyncio
async def test_status_account_missing_404(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, detail=None)
    resp = await client.post("/api/admin/accounts/999/status", json={"status": "active"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_status_active_audits_med(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_db(monkeypatch, detail=_account_row(1))
    resp = await client.post("/api/admin/accounts/1/status", json={"status": "active"})
    assert resp.status_code == 200
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "update_account_status")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "med"


@pytest.mark.asyncio
async def test_status_banned_audits_high(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    """Flipping to banned is destructive — audit severity must be high."""
    _patch_db(monkeypatch, detail=_account_row(1))
    resp = await client.post("/api/admin/accounts/1/status", json={"status": "banned"})
    assert resp.status_code == 200
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "update_account_status")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "high"


# ── POST /{id}/reset ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_expired_updates_and_redacts_audit_reason(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_db(monkeypatch, detail={**_account_row(1), "status": "active"})
    a = _accounts_router_module()

    resp = await client.post(
        "/api/admin/accounts/1/status",
        json={
            "status": "expired",
            "reason": "cookies_expired phone=13812345678 code=654321 cookie=abc123",
        },
    )

    assert resp.status_code == 200
    a.accounts_db.update_account_status.assert_awaited_once()
    _, kwargs = a.accounts_db.update_account_status.await_args
    assert kwargs["status"] == "expired"
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "update_account_status")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "high"
    assert audit[0].after == {"status": "expired"}
    rendered_audit = json.dumps(
        {
            "before": audit[0].before,
            "after": audit[0].after,
            "reason": audit[0].reason,
        }
    )
    assert "13812345678" not in rendered_audit
    assert "654321" not in rendered_audit
    assert "abc123" not in rendered_audit


@pytest.mark.asyncio
async def test_reset_missing_404(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, detail=None)
    resp = await client.post("/api/admin/accounts/999/reset")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reset_audits_med(client, admin_operator, monkeypatch, db_session: AsyncSession):
    _patch_db(monkeypatch, detail=_account_row(1))
    resp = await client.post("/api/admin/accounts/1/reset")
    assert resp.status_code == 200
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "reset_account_fails")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "med"


# ── DELETE /{id} ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_missing_404(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, detail=None)
    resp = await client.delete("/api/admin/accounts/999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_audits_high(client, admin_operator, monkeypatch, db_session: AsyncSession):
    _patch_db(monkeypatch, detail=_account_row(5))
    resp = await client.delete("/api/admin/accounts/5")
    assert resp.status_code == 200
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "delete_account")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "high"


# ── POST /{id}/auto_login ────────────────────────────────────


@pytest.mark.asyncio
async def test_auto_login_celery_unavailable_503(client, admin_operator, monkeypatch):
    """When celery isn't installed, return 503 (admin_console parity).
    Backend's import won't find ``geo_tracker.celery_app`` — verify
    the route handles this gracefully."""
    _patch_db(monkeypatch)
    # The celery imports inside the handler will fail with ImportError
    # (geo_tracker isn't on the backend's path); route returns 503.
    resp = await client.post("/api/admin/accounts/1/auto_login")
    assert resp.status_code == 503
    assert resp.json()["error"] == "celery_unavailable"


# ── schema-drift safety (defense-in-depth, after PR #367) ────


@pytest.mark.asyncio
async def test_list_returns_503_when_schema_outdated(client, admin_operator, monkeypatch):
    """If the legacy DB is missing columns, GET surfaces a clean 503
    instead of a 500 from a downstream psycopg UndefinedColumn."""
    a = _accounts_router_module()
    monkeypatch.setattr(
        a.accounts_db,
        "fetch_accounts",
        AsyncMock(side_effect=RuntimeError("llm_accounts_schema_outdated:created_at")),
    )
    resp = await client.get("/api/admin/accounts")
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"] == "llm_accounts_schema_outdated"
    assert body["missing_columns"] == ["created_at"]


@pytest.mark.asyncio
async def test_status_returns_503_when_schema_outdated(client, admin_operator, monkeypatch):
    a = _accounts_router_module()
    monkeypatch.setattr(
        a.accounts_db,
        "get_account",
        AsyncMock(side_effect=RuntimeError("llm_accounts_schema_outdated:status")),
    )
    monkeypatch.setattr(a.accounts_db, "update_account_status", AsyncMock(return_value=True))
    resp = await client.post("/api/admin/accounts/1/status", json={"status": "active"})
    assert resp.status_code == 503
    assert resp.json()["error"] == "llm_accounts_schema_outdated"


@pytest.mark.asyncio
async def test_reset_returns_503_when_schema_outdated(client, admin_operator, monkeypatch):
    a = _accounts_router_module()
    monkeypatch.setattr(
        a.accounts_db,
        "get_account",
        AsyncMock(return_value=_account_row(1)),
    )
    monkeypatch.setattr(
        a.accounts_db,
        "reset_account_fails",
        AsyncMock(side_effect=RuntimeError("llm_accounts_schema_outdated:cooldown_until")),
    )
    resp = await client.post("/api/admin/accounts/1/reset")
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"] == "llm_accounts_schema_outdated"
    assert "cooldown_until" in body["missing_columns"]


@pytest.mark.asyncio
async def test_delete_returns_503_when_schema_outdated(client, admin_operator, monkeypatch):
    a = _accounts_router_module()
    monkeypatch.setattr(
        a.accounts_db,
        "get_account",
        AsyncMock(side_effect=RuntimeError("llm_accounts_schema_outdated:id")),
    )
    monkeypatch.setattr(a.accounts_db, "delete_account", AsyncMock(return_value=True))
    resp = await client.delete("/api/admin/accounts/1")
    assert resp.status_code == 503
    assert resp.json()["error"] == "llm_accounts_schema_outdated"


def test_maybe_schema_error_response_table_missing():
    """Helper unit test: legacy code path returns the documented 503."""
    a = _accounts_router_module()
    response = a._maybe_schema_error_response(RuntimeError("llm_accounts_table_missing"))
    assert response is not None
    assert response.status_code == 503
    body = json.loads(response.body)
    assert body["error"] == "llm_accounts_unavailable"


def test_maybe_schema_error_response_schema_outdated():
    """Helper unit test: drift code path surfaces the missing column list."""
    a = _accounts_router_module()
    response = a._maybe_schema_error_response(
        RuntimeError("llm_accounts_schema_outdated:cookies_json,status")
    )
    assert response is not None
    assert response.status_code == 503
    body = json.loads(response.body)
    assert body["error"] == "llm_accounts_schema_outdated"
    assert body["missing_columns"] == ["cookies_json", "status"]


def test_maybe_schema_error_response_unrelated_runtime_error_returns_none():
    """Helper must let unrelated RuntimeErrors propagate (so callers
    can re-raise into FastAPI's normal 500 path)."""
    a = _accounts_router_module()
    response = a._maybe_schema_error_response(RuntimeError("something_else"))
    assert response is None


@pytest.mark.asyncio
async def test_assert_llm_accounts_schema_raises_on_missing_columns(
    db_session: AsyncSession, monkeypatch
):
    """Direct unit test of the runtime guard. Patch the probes so we
    don't need a real Postgres."""
    from app.admin.accounts import db as accounts_db

    async def _table_exists(session, name):
        return name == "llm_accounts"

    async def _table_columns(session, name):
        # Pretend production DB is missing two slice-7b columns.
        return {
            "id",
            "llm_name",
            "phone_number",
            "email",
            "password_encrypted",
            "cookies_json",
            "cookies_updated_at",
            "status",
            "consecutive_fails",
            "query_count_today",
            "daily_limit",
            "created_at",
            # cooldown_until is intentionally missing
        }

    monkeypatch.setattr(accounts_db, "_table_exists", _table_exists)
    monkeypatch.setattr(accounts_db, "_table_columns", _table_columns)

    with pytest.raises(RuntimeError) as exc:
        await accounts_db.assert_llm_accounts_schema(db_session)
    assert str(exc.value).startswith("llm_accounts_schema_outdated:")
    assert "cooldown_until" in str(exc.value)


@pytest.mark.asyncio
async def test_assert_llm_accounts_schema_noop_when_table_missing(
    db_session: AsyncSession, monkeypatch
):
    """Sqlite test path: no llm_accounts table → guard is a no-op."""
    from app.admin.accounts import db as accounts_db

    async def _table_exists(session, name):
        return False

    monkeypatch.setattr(accounts_db, "_table_exists", _table_exists)
    # Should not raise.
    await accounts_db.assert_llm_accounts_schema(db_session)


@pytest.mark.asyncio
async def test_assert_llm_accounts_schema_passes_when_columns_complete(
    db_session: AsyncSession, monkeypatch
):
    """Healthy DB: all required columns present → guard is a no-op."""
    from app.admin.accounts import db as accounts_db

    async def _table_exists(session, name):
        return True

    async def _table_columns(session, name):
        # Superset of required columns (production may have extras like
        # ``profile_id`` for the legacy account_profile_map binding).
        return accounts_db._REQUIRED_LLM_ACCOUNT_COLUMNS | {"profile_id", "extra_legacy_col"}

    monkeypatch.setattr(accounts_db, "_table_exists", _table_exists)
    monkeypatch.setattr(accounts_db, "_table_columns", _table_columns)

    # Should not raise.
    await accounts_db.assert_llm_accounts_schema(db_session)


def test_alembic_migration_present():
    """Make sure the schema-repair migration is shipped with this slice
    (the equivalent of PR #367's query_pool repair, applied to
    llm_accounts). Failing this means a future rebase dropped the file."""
    import pathlib

    versions_dir = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
    target = versions_dir / "2026_05_07_0002_llm_accounts_schema_repair.py"
    assert target.exists(), f"missing Alembic repair migration: {target}"
    body = target.read_text(encoding="utf-8")
    # Verify the migration touches every column slice 7b depends on.
    for col in (
        "llm_name",
        "phone_number",
        "email",
        "password_encrypted",
        "cookies_json",
        "cookies_updated_at",
        "status",
        "consecutive_fails",
        "query_count_today",
        "daily_limit",
        "cooldown_until",
        "created_at",
    ):
        assert col in body, f"migration missing ALTER for column: {col}"
    # Chained on top of PR #370's renamed query_pool repair.
    assert 'down_revision: str | Sequence[str] | None = "20260507_qpool_repair"' in body
    assert 'revision: str = "20260507_llm_accts_repair"' in body


def test_llm_accounts_repair_revision_fits_alembic_version_column():
    """Same constraint PR #370 enforced for the query_pool repair: the
    alembic ``alembic_version`` column is VARCHAR(32). Revision IDs over
    32 chars cause CD migrations to fail with a length-overflow error."""
    import pathlib

    target = (
        pathlib.Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "2026_05_07_0002_llm_accounts_schema_repair.py"
    )
    body = target.read_text(encoding="utf-8")
    revision_line = next(line for line in body.splitlines() if line.startswith("revision:"))
    revision = revision_line.split("=", 1)[1].strip().strip('"')
    assert len(revision) <= 32, f"revision id too long: {revision!r} ({len(revision)} chars)"


# ── /api/accounts/{id}/profiles (GET + PUT, port from admin_console) ──
#
# These four endpoints (profile_counts / auto_assign_profiles /
# {id}/profiles GET + PUT) were left on Flask after slice 7b shipped.
# admin.html still calls them under /admin/api/accounts/* — those
# requests routed through nginx to admin_console's Flask app, which
# silently 404'd after the basic CRUD migration deleted the
# /api/accounts catchalls. Porting closes the 404 hole and lets nginx
# route every /admin/api/accounts/* request to the FastAPI backend.


def _patch_profile_db(
    monkeypatch,
    *,
    account=None,
    bindings=None,
    quota_total=0,
    upsert_returns=(0, 0),
    upsert_raises=None,
    counts=None,
    accounts_for_assign=None,
    profiles_for_assign=None,
    insert_count=1,
    insert_raises=None,
    daily_limit_ok=True,
):
    a = _accounts_router_module()
    monkeypatch.setattr(
        a.accounts_db,
        "fetch_account_basics",
        AsyncMock(return_value=account),
    )
    monkeypatch.setattr(
        a.accounts_db,
        "fetch_account_profile_bindings",
        AsyncMock(return_value=list(bindings or [])),
    )
    monkeypatch.setattr(
        a.accounts_db,
        "fetch_account_quota_total",
        AsyncMock(return_value=quota_total),
    )
    if upsert_raises is not None:
        monkeypatch.setattr(
            a.accounts_db,
            "upsert_account_profile_bindings",
            AsyncMock(side_effect=upsert_raises),
        )
    else:
        monkeypatch.setattr(
            a.accounts_db,
            "upsert_account_profile_bindings",
            AsyncMock(return_value=upsert_returns),
        )
    monkeypatch.setattr(
        a.accounts_db,
        "fetch_profile_counts",
        AsyncMock(return_value=dict(counts or {})),
    )
    monkeypatch.setattr(
        a.accounts_db,
        "fetch_active_accounts_with_bound_count",
        AsyncMock(return_value=list(accounts_for_assign or [])),
    )
    monkeypatch.setattr(
        a.accounts_db,
        "update_account_daily_limit",
        AsyncMock(return_value=daily_limit_ok),
    )
    monkeypatch.setattr(
        a.accounts_db,
        "fetch_assignable_profiles",
        AsyncMock(return_value=list(profiles_for_assign or [])),
    )
    if insert_raises is not None:
        monkeypatch.setattr(
            a.accounts_db,
            "insert_auto_assigned_bindings",
            AsyncMock(side_effect=insert_raises),
        )
    else:
        monkeypatch.setattr(
            a.accounts_db,
            "insert_auto_assigned_bindings",
            AsyncMock(return_value=insert_count),
        )


@pytest.mark.asyncio
async def test_profiles_unauth_401(client):
    resp = await client.get("/api/accounts/1/profiles")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_profile_counts_unauth_401(client):
    resp = await client.get("/api/accounts/profile_counts")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auto_assign_profiles_unauth_401(client):
    resp = await client.post("/api/accounts/auto_assign_profiles", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_profiles_account_missing_404(client, admin_operator, monkeypatch):
    _patch_profile_db(monkeypatch, account=None)
    resp = await client.get("/api/admin/accounts/999/profiles")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_profiles_returns_bindings_and_quota(client, admin_operator, monkeypatch):
    """Wire shape mirrors admin_console: account block + bindings list +
    total + quota_total."""
    _patch_profile_db(
        monkeypatch,
        account={
            "id": 1,
            "llm_name": "doubao",
            "phone_number": "13812345678",
            "daily_limit": 20,
            "query_count_today": 3,
            "status": "expired",
        },
        bindings=[
            {
                "binding_id": 10,
                "profile_id": "pf_1",
                "daily_quota": 1,
                "conflict_acknowledged": False,
                "profile_code": "P-1",
                "profile_name": "Alpha",
                "persona_json": {
                    "country_code": "us",
                    "device_type": "Desktop",
                    "language": "en",
                    "timezone": "UTC",
                },
            },
        ],
        quota_total=4,
    )
    resp = await client.get("/api/admin/accounts/1/profiles")
    assert resp.status_code == 200
    body = resp.json()
    assert body["account"]["expected_geo"] == "CN"  # doubao
    assert body["account"]["status"] == "expired"
    assert body["account"]["phone_number"] == "138****5678"
    assert "13812345678" not in json.dumps(body)
    assert body["quota_total"] == 4
    assert body["total"] == 1
    binding = body["bindings"][0]
    assert binding["profile_id"] == "pf_1"
    assert binding["country_code"] == "US"  # uppercased
    assert binding["device_type"] == "desktop"  # lowercased
    assert binding["language"] == "en"
    assert binding["conflicts"][0]["field"] == "geo"
    assert binding["conflicts"][0]["expected"] == "CN"
    assert binding["conflicts"][0]["actual"] == "US"


@pytest.mark.asyncio
async def test_get_profiles_only_conflicts_filters_unacknowledged(
    client, admin_operator, monkeypatch
):
    """only=conflicts hides bindings whose conflict was already
    acknowledged so the drawer surfaces actionable rows only."""
    _patch_profile_db(
        monkeypatch,
        account={
            "id": 1,
            "llm_name": "doubao",
            "phone_number": "x",
            "daily_limit": 20,
            "query_count_today": 0,
            "status": "active",
        },
        bindings=[
            {
                "binding_id": 1,
                "profile_id": "pf_1",
                "daily_quota": 1,
                "conflict_acknowledged": True,  # acknowledged → filtered out
                "profile_code": "P-1",
                "profile_name": "A",
                "persona_json": {"country_code": "us"},
            },
            {
                "binding_id": 2,
                "profile_id": "pf_2",
                "daily_quota": 1,
                "conflict_acknowledged": False,
                "profile_code": "P-2",
                "profile_name": "B",
                "persona_json": {"country_code": "us"},
            },
        ],
    )
    resp = await client.get("/api/admin/accounts/1/profiles?only=conflicts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["bindings"][0]["profile_id"] == "pf_2"


@pytest.mark.asyncio
async def test_put_profiles_persists_and_audits(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_profile_db(
        monkeypatch,
        account={
            "id": 1,
            "llm_name": "doubao",
            "phone_number": "x",
            "daily_limit": 20,
            "query_count_today": 0,
            "status": "active",
        },
        upsert_returns=(2, 1),
    )
    resp = await client.put(
        "/api/admin/accounts/1/profiles",
        json={
            "bindings": [
                {"profile_id": "pf_a", "daily_quota": 1},
                {"profile_id": "pf_b", "daily_quota": 2},
            ],
            "remove_profile_ids": ["pf_old"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"success": True, "upserted": 2, "removed": 1}

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "update_account_profiles")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "med"
    assert audit[0].after == {"upserted": 2, "removed": 1}


@pytest.mark.asyncio
async def test_put_profiles_updates_account_daily_limit(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    a = _accounts_router_module()
    _patch_profile_db(
        monkeypatch,
        account={
            "id": 1,
            "llm_name": "doubao",
            "phone_number": "x",
            "daily_limit": 20,
            "query_count_today": 0,
            "status": "active",
        },
        upsert_returns=(0, 0),
    )
    resp = await client.put(
        "/api/admin/accounts/1/profiles",
        json={"daily_limit": 100, "bindings": [], "remove_profile_ids": []},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["daily_limit"] == 100
    a.accounts_db.update_account_daily_limit.assert_awaited_once()
    _, kwargs = a.accounts_db.update_account_daily_limit.await_args
    assert kwargs == {"account_id": 1, "daily_limit": 100}
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "update_account_profiles")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].after["daily_limit"] == {"before": 20, "after": 100}


@pytest.mark.asyncio
async def test_put_profiles_rejects_invalid_daily_limit(client, admin_operator, monkeypatch):
    _patch_profile_db(
        monkeypatch,
        account={
            "id": 1,
            "llm_name": "doubao",
            "phone_number": "x",
            "daily_limit": 20,
            "query_count_today": 0,
            "status": "active",
        },
    )
    resp = await client.put(
        "/api/admin/accounts/1/profiles",
        json={"daily_limit": -1, "bindings": [], "remove_profile_ids": []},
    )

    assert resp.status_code == 400
    assert resp.json()["error"] == "daily_limit_invalid"


@pytest.mark.asyncio
async def test_put_profiles_account_missing_404(client, admin_operator, monkeypatch):
    _patch_profile_db(monkeypatch, account=None)
    resp = await client.put(
        "/api/admin/accounts/999/profiles",
        json={"bindings": [], "remove_profile_ids": []},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_put_profiles_returns_503_when_table_missing(client, admin_operator, monkeypatch):
    _patch_profile_db(
        monkeypatch,
        account={
            "id": 1,
            "llm_name": "doubao",
            "phone_number": "x",
            "daily_limit": 20,
            "query_count_today": 0,
            "status": "active",
        },
        upsert_raises=RuntimeError("account_profile_map_table_missing"),
    )
    resp = await client.put(
        "/api/admin/accounts/1/profiles",
        json={"bindings": [{"profile_id": "p", "daily_quota": 1}]},
    )
    assert resp.status_code == 503
    assert resp.json()["error"] == "account_profile_map_unavailable"


@pytest.mark.asyncio
async def test_profile_counts_returns_dict(client, admin_operator, monkeypatch):
    _patch_profile_db(
        monkeypatch,
        counts={1: {"bindings": 4, "unacknowledged": 1}, 2: {"bindings": 0, "unacknowledged": 0}},
    )
    resp = await client.get("/api/admin/accounts/profile_counts")
    assert resp.status_code == 200
    body = resp.json()
    # JSON keys are strings, but the values must round-trip cleanly.
    assert body["1"] == {"bindings": 4, "unacknowledged": 1}
    assert body["2"]["bindings"] == 0


@pytest.mark.asyncio
async def test_profile_counts_503_when_table_missing(client, admin_operator, monkeypatch):
    a = _accounts_router_module()
    monkeypatch.setattr(
        a.accounts_db,
        "fetch_profile_counts",
        AsyncMock(side_effect=RuntimeError("account_profile_map_table_missing")),
    )
    resp = await client.get("/api/admin/accounts/profile_counts")
    assert resp.status_code == 503
    assert resp.json()["error"] == "account_profile_map_unavailable"


@pytest.mark.asyncio
async def test_auto_assign_profiles_invalid_per_account_400(client, admin_operator, monkeypatch):
    _patch_profile_db(monkeypatch)
    resp = await client.post(
        "/api/admin/accounts/auto_assign_profiles",
        json={"per_account": "abc"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_per_account"


@pytest.mark.asyncio
async def test_auto_assign_profiles_round_robin_distributes_picks(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    """RR path: each account receives ``per_account`` picks pulled from
    the geo bucket matching its engine, falling back to '*' when empty."""
    a = _accounts_router_module()
    inserted_calls: list[dict] = []

    async def fake_insert(session, *, account_id, profile_ids, daily_quota=1):
        inserted_calls.append({"account_id": account_id, "profile_ids": list(profile_ids)})
        return len(profile_ids)

    _patch_profile_db(
        monkeypatch,
        accounts_for_assign=[
            {
                "id": 1,
                "llm_name": "doubao",
                "phone_number": "a",
                "daily_limit": 20,
                "bound_count": 0,
            },
            {
                "id": 2,
                "llm_name": "chatgpt",
                "phone_number": "b",
                "daily_limit": 20,
                "bound_count": 5,
            },
        ],
        profiles_for_assign=[
            {"id": "cn1", "code": "C1", "name": "Alpha", "persona_json": {"country_code": "CN"}},
            {"id": "cn2", "code": "C2", "name": "Beta", "persona_json": {"country_code": "CN"}},
            {"id": "us1", "code": "U1", "name": "Gamma", "persona_json": {"country_code": "US"}},
        ],
    )
    monkeypatch.setattr(
        a.accounts_db,
        "insert_auto_assigned_bindings",
        fake_insert,
    )
    resp = await client.post(
        "/api/admin/accounts/auto_assign_profiles",
        json={"per_account": 2, "skip_already_bound": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["accounts_skipped"] == 1  # the chatgpt account already has 5
    assert body["accounts_processed"] == 1
    assert body["bindings_inserted"] == 2
    assert body["method"] == "rr"
    # The doubao account gets 2 picks from the CN bucket.
    assert len(inserted_calls) == 1
    assert inserted_calls[0]["account_id"] == 1
    assert sorted(inserted_calls[0]["profile_ids"]) == ["cn1", "cn2"]

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "auto_assign_profiles")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "med"


@pytest.mark.asyncio
async def test_auto_assign_profiles_503_when_table_missing(client, admin_operator, monkeypatch):
    _patch_profile_db(
        monkeypatch,
        accounts_for_assign=[
            {
                "id": 1,
                "llm_name": "doubao",
                "phone_number": "a",
                "daily_limit": 20,
                "bound_count": 0,
            }
        ],
        profiles_for_assign=[
            {"id": "p1", "code": "C", "name": "A", "persona_json": {"country_code": "CN"}}
        ],
        insert_raises=RuntimeError("account_profile_map_table_missing"),
    )
    resp = await client.post(
        "/api/admin/accounts/auto_assign_profiles",
        json={"per_account": 1},
    )
    assert resp.status_code == 503
    assert resp.json()["error"] == "account_profile_map_unavailable"


# ── audit gate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_slice7b():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
