"""Issue #1116 — Admin vm_session accounts router tests.

Covers all five endpoints of ``app.api.admin.vm_accounts.router``:

- GET  /admin/api/vm/accounts            list
- POST /admin/api/vm/accounts            create (R2.5 reject cookies)
- PATCH /admin/api/vm/accounts/{id}      toggle execution_mode
- POST /admin/api/vm/needs_relogin       watchdog webhook + Slack fan-out
- POST /admin/api/vm/relogin_done        operator relogin confirmation

Both the SPA-facing ``/admin/api/vm/*`` path and the canonical
``/api/admin/vm/*`` mount are exercised so the legacy alias doesn't
silently drift away from the canonical handler.

``llm_accounts`` is NOT in backend's ORM (production-only per
ADR-002), so tests monkeypatch the ``vm_db`` helpers — same pattern
``test_phase_7_slice7b_admin_accounts.py`` uses for the
``llm_accounts.cookies_json`` table.

Slack is mocked: we assert the helper is called (or NOT called) and
verify the no-op path runs when ``SLACK_WEBHOOK_URL`` is unset.
"""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from genpano_models import AdminUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.vm_accounts.db import (
    MVP_ENGINES,
    NEEDS_RELOGIN_STATUS,
    VmAccountValidationError,
    validate_create_payload,
    validate_toggle_payload,
)

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture
async def admin_operator(db_session: AsyncSession) -> AsyncGenerator[AdminUser, None]:
    """Provision an AdminUser + override ``current_admin`` so the cookie
    auth path is bypassed for the duration of the test (mirrors the
    pattern from ``test_phase_7_slice7b_admin_accounts.py``).
    """
    from app.api.admin.auth.router import current_admin
    from app.main import app

    a = AdminUser(
        id=_new_id(),
        email=f"vm-admin-{uuid.uuid4().hex[:6]}@example.com",
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


def _router_module():
    """Return the live router module so monkeypatch can swap its
    ``vm_db`` reference (not the import alias in our test file)."""
    import app.api.admin.vm_accounts.router  # noqa: F401

    return sys.modules["app.api.admin.vm_accounts.router"]


def _patch_vm_db(
    monkeypatch,
    *,
    rows: list[dict] | None = None,
    detail: dict | None = None,
    create_returns: int | RuntimeError = 1,
    toggle_returns: bool = True,
    mark_returns: int | None = 1,
    clear_returns: int | None = 1,
):
    """Swap every vm_db helper for an AsyncMock. Each test passes the
    minimum it actually exercises; defaults give a happy-path mock set."""
    r = _router_module()
    monkeypatch.setattr(
        r.vm_db,
        "fetch_vm_accounts",
        AsyncMock(return_value=list(rows or [])),
    )
    monkeypatch.setattr(r.vm_db, "get_vm_account", AsyncMock(return_value=detail))
    if isinstance(create_returns, Exception):
        monkeypatch.setattr(r.vm_db, "create_vm_account", AsyncMock(side_effect=create_returns))
    else:
        monkeypatch.setattr(r.vm_db, "create_vm_account", AsyncMock(return_value=create_returns))
    monkeypatch.setattr(r.vm_db, "toggle_execution_mode", AsyncMock(return_value=toggle_returns))
    monkeypatch.setattr(r.vm_db, "mark_needs_relogin", AsyncMock(return_value=mark_returns))
    monkeypatch.setattr(r.vm_db, "clear_needs_relogin", AsyncMock(return_value=clear_returns))


# ---------------------------------------------------------------------------
# Pure-helper tests: validate_create_payload / validate_toggle_payload
# ---------------------------------------------------------------------------


def test_mvp_engines_locked_to_three():
    """R2.5 / ADAPTER_CONTRACT §1.1 — the engine universe is exactly 3."""
    assert MVP_ENGINES == frozenset({"chatgpt", "doubao", "deepseek-CN"})


def test_validate_create_payload_happy_path():
    engine, vm, seg = validate_create_payload(
        engine_id="doubao", vm_id="vm-001", segment_group="seg-A", cookies_json=None
    )
    assert engine == "doubao"
    assert vm == "vm-001"
    assert seg == "seg-A"


def test_validate_create_payload_rejects_non_mvp_engine():
    """Gemini / Perplexity / Kimi / Grok / 智谱 / Claude are Phase 2+."""
    with pytest.raises(VmAccountValidationError) as exc:
        validate_create_payload(
            engine_id="gemini", vm_id="vm-1", segment_group=None, cookies_json=None
        )
    assert exc.value.code == "engine_id_invalid"


def test_validate_create_payload_rejects_cookies():
    """R2.5: vm_session rows MUST NOT carry cookies_json."""
    with pytest.raises(VmAccountValidationError) as exc:
        validate_create_payload(
            engine_id="chatgpt", vm_id="vm-1", segment_group=None, cookies_json="[]"
        )
    assert exc.value.code == "vm_session_cookies_forbidden"


def test_validate_create_payload_requires_vm_id():
    with pytest.raises(VmAccountValidationError) as exc:
        validate_create_payload(
            engine_id="chatgpt", vm_id="", segment_group=None, cookies_json=None
        )
    assert exc.value.code == "vm_id_required"


def test_validate_create_payload_segment_group_optional():
    _, _, seg = validate_create_payload(
        engine_id="chatgpt", vm_id="vm-1", segment_group=None, cookies_json=None
    )
    assert seg is None
    _, _, seg2 = validate_create_payload(
        engine_id="chatgpt", vm_id="vm-1", segment_group="   ", cookies_json=None
    )
    assert seg2 is None


def test_validate_toggle_payload_to_vm_session_requires_vm_id():
    with pytest.raises(VmAccountValidationError) as exc:
        validate_toggle_payload(new_mode="vm_session", vm_id=None, cookies_json=None)
    assert exc.value.code == "vm_id_required"


def test_validate_toggle_payload_to_vm_session_rejects_cookies():
    """R2.5: toggling to vm_session AND supplying cookies = ban risk."""
    with pytest.raises(VmAccountValidationError) as exc:
        validate_toggle_payload(new_mode="vm_session", vm_id="vm-1", cookies_json="[{}]")
    assert exc.value.code == "vm_session_cookies_forbidden"


def test_validate_toggle_payload_to_local_cookie_requires_cookies():
    with pytest.raises(VmAccountValidationError) as exc:
        validate_toggle_payload(new_mode="local_cookie", vm_id=None, cookies_json=None)
    assert exc.value.code == "cookies_json_required"


def test_validate_toggle_payload_to_local_cookie_requires_vm_id_clear():
    """The local connector has no use for vm_id — supplying it on a
    toggle to local_cookie is a contract violation."""
    with pytest.raises(VmAccountValidationError) as exc:
        validate_toggle_payload(new_mode="local_cookie", vm_id="vm-1", cookies_json="[]")
    assert exc.value.code == "vm_id_must_be_null"


def test_validate_toggle_payload_to_local_cookie_happy_path():
    mode, vm, cookies = validate_toggle_payload(
        new_mode="local_cookie", vm_id=None, cookies_json="[{}]"
    )
    assert mode == "local_cookie"
    assert vm is None
    assert cookies == "[{}]"


def test_validate_toggle_payload_to_vm_session_happy_path():
    mode, vm, cookies = validate_toggle_payload(
        new_mode="vm_session", vm_id="vm-2", cookies_json=None
    )
    assert mode == "vm_session"
    assert vm == "vm-2"
    assert cookies is None


def test_validate_toggle_payload_rejects_unknown_mode():
    with pytest.raises(VmAccountValidationError) as exc:
        validate_toggle_payload(new_mode="weird", vm_id="vm-1", cookies_json=None)
    assert exc.value.code == "execution_mode_invalid"


def test_validate_toggle_payload_accepts_dict_cookies():
    """Frontend may send a parsed JSON dict; helper normalises to str."""
    mode, _, cookies = validate_toggle_payload(
        new_mode="local_cookie", vm_id=None, cookies_json={"cookies": [{"name": "x"}]}
    )
    assert mode == "local_cookie"
    assert cookies is not None
    assert "cookies" in cookies


# ---------------------------------------------------------------------------
# Auth: every endpoint requires admin session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_unauth_401(client):
    resp = await client.get("/admin/api/vm/accounts")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_unauth_401(client):
    resp = await client.post(
        "/admin/api/vm/accounts", json={"engine_id": "doubao", "vm_id": "vm-1"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_patch_unauth_401(client):
    resp = await client.patch(
        "/admin/api/vm/accounts/1",
        json={"execution_mode": "vm_session", "vm_id": "vm-1"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_needs_relogin_unauth_401(client):
    resp = await client.post(
        "/admin/api/vm/needs_relogin",
        json={"vm_id": "vm-1", "engine": "doubao", "reason": "captcha"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_relogin_done_unauth_401(client):
    resp = await client.post(
        "/admin/api/vm/relogin_done", json={"vm_id": "vm-1", "engine": "doubao"}
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Canonical mount also auth-protected (/api/admin/vm/*)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_canonical_mount_list_unauth_401(client):
    """The canonical /api/admin/vm/* path inherits the same auth."""
    resp = await client.get("/api/admin/vm/accounts")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /accounts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_returns_rows(client, admin_operator, monkeypatch):
    fake_rows = [
        {
            "id": 1,
            "engine_id": "doubao",
            "vm_id": "vm-001",
            "execution_mode": "vm_session",
            "status": "active",
            "segment_group": "seg-A",
            "last_used_at": None,
            "last_relogin_at": None,
            "success_count_7d": 12,
        }
    ]
    _patch_vm_db(monkeypatch, rows=fake_rows)
    resp = await client.get("/admin/api/vm/accounts")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 1
    assert body["mvp_engines"] == sorted(MVP_ENGINES)
    assert body["items"][0]["vm_id"] == "vm-001"
    assert body["items"][0]["execution_mode"] == "vm_session"


@pytest.mark.asyncio
async def test_list_503_when_schema_outdated(client, admin_operator, monkeypatch):
    """Schema-drift guard surfaces a clean 503 instead of psycopg crash."""
    r = _router_module()
    monkeypatch.setattr(
        r.vm_db,
        "fetch_vm_accounts",
        AsyncMock(side_effect=RuntimeError("llm_accounts_schema_outdated:execution_mode,vm_id")),
    )
    resp = await client.get("/admin/api/vm/accounts")
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"] == "llm_accounts_schema_outdated"
    assert "execution_mode" in body["missing_columns"]


@pytest.mark.asyncio
async def test_list_canonical_mount_matches(client, admin_operator, monkeypatch):
    """The /api/admin/vm/* canonical mount serves the same handler."""
    _patch_vm_db(monkeypatch, rows=[])
    resp = await client.get("/api/admin/vm/accounts")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


# ---------------------------------------------------------------------------
# POST /accounts (create)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_happy_path(client, admin_operator, monkeypatch):
    _patch_vm_db(monkeypatch, create_returns=42)
    resp = await client.post(
        "/admin/api/vm/accounts",
        json={"engine_id": "doubao", "vm_id": "vm-001", "segment_group": "seg-A"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["account_id"] == 42


@pytest.mark.asyncio
async def test_create_rejects_non_mvp_engine(client, admin_operator, monkeypatch):
    """Gemini and Perplexity are Phase 2+ — must 400 here."""
    _patch_vm_db(monkeypatch)
    resp = await client.post(
        "/admin/api/vm/accounts", json={"engine_id": "gemini", "vm_id": "vm-1"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "engine_id_invalid"


@pytest.mark.asyncio
async def test_create_rejects_cookies_payload(client, admin_operator, monkeypatch):
    """R2.5: even if the operator pastes cookies into the modal, the
    backend rejects before DB. Defense-in-depth above the CHECK
    constraint."""
    _patch_vm_db(monkeypatch)
    resp = await client.post(
        "/admin/api/vm/accounts",
        json={
            "engine_id": "doubao",
            "vm_id": "vm-1",
            "cookies_json": '[{"name": "sid"}]',
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "vm_session_cookies_forbidden"


@pytest.mark.asyncio
async def test_create_rejects_empty_vm_id(client, admin_operator, monkeypatch):
    _patch_vm_db(monkeypatch)
    resp = await client.post("/admin/api/vm/accounts", json={"engine_id": "doubao", "vm_id": "   "})
    assert resp.status_code == 400
    assert resp.json()["error"] == "vm_id_required"


@pytest.mark.asyncio
async def test_create_503_when_table_missing(client, admin_operator, monkeypatch):
    """Sqlite test fixtures hit this path — the DB helper raises
    ``llm_accounts_table_missing`` and the router 503s with a stable
    error code."""
    _patch_vm_db(monkeypatch, create_returns=RuntimeError("llm_accounts_table_missing"))
    resp = await client.post(
        "/admin/api/vm/accounts", json={"engine_id": "doubao", "vm_id": "vm-1"}
    )
    assert resp.status_code == 503
    assert resp.json()["error"] == "llm_accounts_unavailable"


# ---------------------------------------------------------------------------
# PATCH /accounts/{id} — toggle execution_mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_toggle_to_local_cookie(client, admin_operator, monkeypatch):
    """vm_session → local_cookie requires cookies_json AND vm_id cleared."""
    _patch_vm_db(
        monkeypatch,
        detail={"id": 1, "execution_mode": "vm_session", "vm_id": "vm-1"},
    )
    resp = await client.patch(
        "/admin/api/vm/accounts/1",
        json={
            "execution_mode": "local_cookie",
            "vm_id": None,
            "cookies_json": '[{"name": "sid"}]',
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["execution_mode"] == "local_cookie"


@pytest.mark.asyncio
async def test_patch_toggle_to_vm_session(client, admin_operator, monkeypatch):
    """local_cookie → vm_session requires vm_id AND cookies_json null."""
    _patch_vm_db(
        monkeypatch,
        detail={"id": 1, "execution_mode": "local_cookie", "vm_id": None},
    )
    resp = await client.patch(
        "/admin/api/vm/accounts/1",
        json={"execution_mode": "vm_session", "vm_id": "vm-7"},
    )
    assert resp.status_code == 200
    assert resp.json()["vm_id"] == "vm-7"


@pytest.mark.asyncio
async def test_patch_to_vm_session_with_cookies_rejected(client, admin_operator, monkeypatch):
    """R2.5: the operator must not be able to flip a logged-in cookie
    account into vm_session without first clearing the cookies."""
    _patch_vm_db(
        monkeypatch,
        detail={"id": 1, "execution_mode": "local_cookie", "vm_id": None},
    )
    resp = await client.patch(
        "/admin/api/vm/accounts/1",
        json={
            "execution_mode": "vm_session",
            "vm_id": "vm-7",
            "cookies_json": "[{}]",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "vm_session_cookies_forbidden"


@pytest.mark.asyncio
async def test_patch_404_when_account_missing(client, admin_operator, monkeypatch):
    """The detail-fetch returns None → 404 before any DB write."""
    _patch_vm_db(monkeypatch, detail=None)
    resp = await client.patch(
        "/admin/api/vm/accounts/999",
        json={"execution_mode": "vm_session", "vm_id": "vm-1"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /needs_relogin — webhook from VM-side watchdog
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_needs_relogin_marks_account_and_fires_slack(client, admin_operator, monkeypatch):
    """Happy path: matching account marked + Slack helper called."""
    _patch_vm_db(monkeypatch, mark_returns=42)
    r = _router_module()
    slack_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(r, "notify_relogin_needed", slack_mock)
    resp = await client.post(
        "/admin/api/vm/needs_relogin",
        json={
            "vm_id": "vm-1",
            "engine": "doubao",
            "reason": "captcha",
            "novnc_url": "https://novnc.example.com/vm-1",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["account_id"] == 42
    # Slack fan-out is fire-and-forget so we await one tick to let the
    # task drain. ``await asyncio.sleep(0)`` is enough for AsyncMock.
    import asyncio

    await asyncio.sleep(0)
    slack_mock.assert_awaited_once()
    args = slack_mock.call_args.kwargs
    assert args["vm_id"] == "vm-1"
    assert args["engine"] == "doubao"
    assert args["novnc_url"] == "https://novnc.example.com/vm-1"


@pytest.mark.asyncio
async def test_needs_relogin_returns_200_when_no_match(client, admin_operator, monkeypatch):
    """If the watchdog emits before the operator provisions the row,
    we still want a 200 + Slack ping so the operator gets notified."""
    _patch_vm_db(monkeypatch, mark_returns=None)
    r = _router_module()
    slack_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(r, "notify_relogin_needed", slack_mock)
    resp = await client.post(
        "/admin/api/vm/needs_relogin",
        json={"vm_id": "ghost", "engine": "doubao", "reason": "captcha"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["account_id"] is None
    import asyncio

    await asyncio.sleep(0)
    slack_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_needs_relogin_400_when_missing_fields(client, admin_operator, monkeypatch):
    _patch_vm_db(monkeypatch)
    resp = await client.post("/admin/api/vm/needs_relogin", json={"vm_id": ""})
    assert resp.status_code == 400
    assert resp.json()["error"] == "vm_id_and_engine_required"


# ---------------------------------------------------------------------------
# POST /relogin_done — operator confirmation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_relogin_done_happy_path(client, admin_operator, monkeypatch):
    _patch_vm_db(monkeypatch, clear_returns=42)
    resp = await client.post(
        "/admin/api/vm/relogin_done", json={"vm_id": "vm-1", "engine": "doubao"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["account_id"] == 42


@pytest.mark.asyncio
async def test_relogin_done_404_when_no_match(client, admin_operator, monkeypatch):
    _patch_vm_db(monkeypatch, clear_returns=None)
    resp = await client.post(
        "/admin/api/vm/relogin_done", json={"vm_id": "vm-x", "engine": "doubao"}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_relogin_done_400_when_missing_fields(client, admin_operator, monkeypatch):
    _patch_vm_db(monkeypatch)
    resp = await client.post("/admin/api/vm/relogin_done", json={"engine": "doubao"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Slack helper — SLACK_WEBHOOK_URL unset = no-op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slack_no_op_when_env_unset(monkeypatch):
    """Production-safe default: when SLACK_WEBHOOK_URL is empty,
    ``notify_relogin_needed`` returns True without making any HTTP
    call. Verified by patching httpx and asserting it wasn't touched.
    """
    from app.admin.vm_accounts import slack as slack_mod

    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    # Sentinel: replace AsyncClient with an explicit failure so any
    # network attempt blows up loudly.
    monkeypatch.setattr(
        slack_mod.httpx,
        "AsyncClient",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("httpx must not be called when SLACK_WEBHOOK_URL unset")
        ),
    )
    result = await slack_mod.notify_relogin_needed(vm_id="vm-1", engine="doubao")
    assert result is True


@pytest.mark.asyncio
async def test_slack_fires_when_env_set(monkeypatch):
    """When SLACK_WEBHOOK_URL is set, the helper POSTs to it."""
    from app.admin.vm_accounts import slack as slack_mod

    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://slack.example/hook")

    posted = {}

    class _FakeResponse:
        status_code = 200

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json):
            posted["url"] = url
            posted["json"] = json
            return _FakeResponse()

    monkeypatch.setattr(slack_mod.httpx, "AsyncClient", _FakeClient)
    result = await slack_mod.notify_relogin_needed(
        vm_id="vm-1", engine="doubao", novnc_url="https://novnc/vm-1"
    )
    assert result is True
    assert posted["url"] == "https://slack.example/hook"
    assert "VM vm-1" in posted["json"]["text"]
    assert "novnc" in posted["json"]["text"]


@pytest.mark.asyncio
async def test_slack_swallows_http_failure(monkeypatch):
    """Slack 5xx must not bubble — the watchdog should still see 200."""
    from app.admin.vm_accounts import slack as slack_mod

    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://slack.example/hook")

    class _FakeResponse:
        status_code = 500

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            return _FakeResponse()

    monkeypatch.setattr(slack_mod.httpx, "AsyncClient", _FakeClient)
    result = await slack_mod.notify_relogin_needed(vm_id="vm-1", engine="doubao")
    assert result is False


@pytest.mark.asyncio
async def test_slack_swallows_network_error(monkeypatch):
    """Slack DNS failure / timeout → log + return False, never raise."""
    from app.admin.vm_accounts import slack as slack_mod

    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://slack.example/hook")

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            raise RuntimeError("network down")

    monkeypatch.setattr(slack_mod.httpx, "AsyncClient", _FakeClient)
    result = await slack_mod.notify_relogin_needed(vm_id="vm-1", engine="doubao")
    assert result is False


# ---------------------------------------------------------------------------
# Integration: end-to-end audit log row written
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_emits_audit_row(client, admin_operator, monkeypatch, env):
    """Audit ledger captures the create event with the public fields
    (NEVER the cookies blob — but vm_session rows don't have one)."""
    _patch_vm_db(monkeypatch, create_returns=77)
    resp = await client.post(
        "/admin/api/vm/accounts",
        json={"engine_id": "chatgpt", "vm_id": "vm-77", "segment_group": "seg-X"},
    )
    assert resp.status_code == 200
    # Inspect the audit row written via emit_audit
    from genpano_models import AdminAuditLog
    from sqlalchemy import select

    async with env.sessionmaker() as session:
        rows = list(
            (
                await session.execute(
                    select(AdminAuditLog)
                    .where(AdminAuditLog.action == "create_vm_account")
                    .order_by(AdminAuditLog.occurred_at.desc())
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1
    after = rows[0].after or {}
    assert after.get("engine_id") == "chatgpt"
    assert after.get("execution_mode") == "vm_session"
    # Defense check: cookies blob must never appear in audit
    assert "cookies_json" not in after
    assert "cookies" not in (rows[0].reason or "").lower() or after.get("cookies_supplied") is None


# ---------------------------------------------------------------------------
# Smoke: NEEDS_RELOGIN_STATUS sentinel value matches what the SPA expects
# ---------------------------------------------------------------------------


def test_needs_relogin_sentinel_value():
    """The SPA highlights this exact status string. Don't rename
    without coordinating with the admin.html template."""
    assert NEEDS_RELOGIN_STATUS == "needs_relogin"
