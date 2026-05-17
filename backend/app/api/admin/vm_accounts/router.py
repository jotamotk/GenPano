"""Admin vm_session router (Issue #1116 — Refs Epic #1110).

Mounted at ``/api/admin/vm/*`` (canonical) and ``/admin/api/vm/*``
(SPA-facing path). The two mount points share the same handler set;
the second exists so the admin.html shell can call them at the
``/admin/api/vm/*`` URL prefix without going through the legacy
``/admin/api/admin/vm`` double-nest.

Endpoints:

- ``GET    /accounts``                — list vm_session accounts
- ``POST   /accounts``                — create vm_session account
- ``PATCH  /accounts/{id}``           — toggle execution_mode (local_cookie ↔ vm_session)
- ``POST   /needs_relogin``           — VM-side watchdog webhook
- ``POST   /relogin_done``            — operator confirms relogin completed

Auth: cookie-based ``current_admin`` (same dependency every other
``/api/admin/*`` route uses). The needs_relogin webhook is also
``current_admin``-protected: in the VM-per-account architecture the
VM-side watchdog runs with a service account that holds an admin
session cookie. A future hardening (Phase 3) may swap that for an
mTLS-signed payload, but the cookie path is sufficient for the MVP
since the webhook lives inside the same operator network boundary.

R2.5 defense-in-depth: every mutation that could land cookies on a
vm_session row passes through ``validate_create_payload`` /
``validate_toggle_payload`` before reaching DB. The Phase 1 (#1114)
CHECK ``chk_exec_mode_cookies`` is the last-resort backstop; this
layer surfaces a clean ``vm_session_cookies_forbidden`` 400 instead.

Audit: each mutation emits an ``admin_audit_log`` row with severity
``med`` (toggle / mark / clear) or ``high`` (create / delete) so the
audit timeline mirrors the existing accounts router pattern. Cookies
are never logged.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from genpano_models import AdminUser
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.vm_accounts import db as vm_db
from app.admin.vm_accounts.db import (
    MVP_ENGINES,
    NEEDS_RELOGIN_STATUS,
    VmAccountValidationError,
)
from app.admin.vm_accounts.slack import notify_relogin_needed
from app.api.admin.auth.router import current_admin
from app.core.errors import not_found
from app.core.security import _DependsDb

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Admin · VM Accounts"])


# ---------------------------------------------------------------------------
# Schema-error → 503 mapping (mirrors app/api/admin/accounts/router.py).
# ---------------------------------------------------------------------------


def _maybe_schema_error_response(error: RuntimeError) -> JSONResponse | None:
    code = str(error)
    if code == "llm_accounts_table_missing":
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "llm_accounts_unavailable",
                "message": "llm_accounts table is not available; run migrations first.",
            },
        )
    if code.startswith("llm_accounts_schema_outdated:"):
        missing = code.split(":", 1)[1]
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "llm_accounts_schema_outdated",
                "missing_columns": missing.split(",") if missing else [],
                "message": (
                    "llm_accounts is missing columns the VM Admin API "
                    f"requires: {missing}. Run the latest Alembic migrations."
                ),
            },
        )
    return None


def _check_constraint_error_response(error: IntegrityError) -> JSONResponse | None:
    """Translate the Phase 1 CHECK constraint failure into a 400 with a
    stable error code so the SPA can render a localized message.
    """
    text = str(getattr(error, "orig", error)).lower()
    if "chk_exec_mode_cookies" in text:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "vm_session_cookies_forbidden",
                "message": (
                    "vm_session accounts must not carry cookies_json (R2.5 "
                    "self-cloning device prevention)."
                ),
            },
        )
    return None


# ---------------------------------------------------------------------------
# GET /accounts — list vm_session accounts
# ---------------------------------------------------------------------------


@router.get("/accounts", response_model=None)
async def list_vm_accounts(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> Any:
    """Return every ``llm_accounts`` row with execution_mode='vm_session'.

    Fields per row: ``id, engine_id, vm_id, segment_group, status,
    daily_used, daily_limit, last_used_at, last_relogin_at,
    success_count_7d``. Cookies blob is never returned (R2.5).
    """
    try:
        rows = await vm_db.fetch_vm_accounts(session)
    except RuntimeError as error:
        response = _maybe_schema_error_response(error)
        if response is not None:
            return response
        raise
    return {"items": rows, "count": len(rows), "mvp_engines": sorted(MVP_ENGINES)}


# ---------------------------------------------------------------------------
# POST /accounts — create vm_session account
# ---------------------------------------------------------------------------


@router.post("/accounts", response_model=None)
async def create_vm_account(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Create a new vm_session account.

    Required body: ``engine_id`` (must be in MVP 3), ``vm_id``
    (non-empty), ``segment_group`` (optional, free-form). The
    ``cookies_json`` field is **forbidden** here — supplying it is a
    400 ``vm_session_cookies_forbidden`` so the operator sees the R2.5
    failure surface at write time rather than as a production ban.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    try:
        engine_id, vm_id, segment_group = vm_db.validate_create_payload(
            engine_id=payload.get("engine_id"),
            vm_id=payload.get("vm_id"),
            segment_group=payload.get("segment_group"),
            cookies_json=payload.get("cookies_json"),
        )
    except VmAccountValidationError as exc:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": exc.code, "message": exc.message},
        )

    try:
        account_id = await vm_db.create_vm_account(
            session,
            engine_id=engine_id,
            vm_id=vm_id,
            segment_group=segment_group,
        )
    except RuntimeError as error:
        response = _maybe_schema_error_response(error)
        if response is not None:
            return response
        raise
    except IntegrityError as error:
        response = _check_constraint_error_response(error)
        if response is not None:
            return response
        raise

    await emit_audit(
        session,
        operator=operator,
        action="create_vm_account",
        severity="high",
        resource_type="llm_account",
        resource_id=str(account_id),
        after={
            "engine_id": engine_id,
            "vm_id": vm_id,
            "segment_group": segment_group,
            "execution_mode": "vm_session",
        },
        reason="create_vm_account",
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "account_id": account_id,
            "message": f"Created vm_session account #{account_id} ({engine_id} / {vm_id})",
        },
    )


# ---------------------------------------------------------------------------
# PATCH /accounts/{id} — toggle execution_mode
# ---------------------------------------------------------------------------


@router.patch("/accounts/{account_id}", response_model=None)
async def toggle_execution_mode(
    account_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Flip an account's ``execution_mode`` between ``local_cookie`` and
    ``vm_session``.

    Contract (enforced by ``validate_toggle_payload``):

    - vm_session → local_cookie: ``vm_id`` MUST be cleared (or absent)
      AND a non-empty ``cookies_json`` MUST be provided in the same
      request.
    - local_cookie → vm_session: ``cookies_json`` MUST be null/absent
      AND ``vm_id`` MUST be provided.

    Defense-in-depth above the Phase 1 (#1114) CHECK
    ``chk_exec_mode_cookies``: the SPA gets a clean error code without
    relying on the IntegrityError name.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    try:
        new_mode, vm_id, cookies_json = vm_db.validate_toggle_payload(
            new_mode=payload.get("execution_mode"),
            vm_id=payload.get("vm_id"),
            cookies_json=payload.get("cookies_json"),
        )
    except VmAccountValidationError as exc:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": exc.code, "message": exc.message},
        )

    try:
        before = await vm_db.get_vm_account(session, account_id=account_id)
        if before is None:
            raise not_found("vm_account_not_found")
        ok = await vm_db.toggle_execution_mode(
            session,
            account_id=account_id,
            new_mode=new_mode,
            vm_id=vm_id,
            cookies_json=cookies_json,
        )
    except RuntimeError as error:
        response = _maybe_schema_error_response(error)
        if response is not None:
            return response
        raise
    except IntegrityError as error:
        response = _check_constraint_error_response(error)
        if response is not None:
            return response
        raise
    if not ok:
        raise not_found("vm_account_not_found")

    await emit_audit(
        session,
        operator=operator,
        action="toggle_execution_mode",
        severity="high",
        resource_type="llm_account",
        resource_id=str(account_id),
        before={
            "execution_mode": before.get("execution_mode"),
            "vm_id": before.get("vm_id"),
        },
        after={
            "execution_mode": new_mode,
            "vm_id": vm_id,
            # Never log the cookies blob — only whether one was set.
            "cookies_supplied": cookies_json is not None,
        },
        reason="toggle_execution_mode",
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={"success": True, "execution_mode": new_mode, "vm_id": vm_id},
    )


# ---------------------------------------------------------------------------
# POST /needs_relogin — VM-side watchdog webhook
# ---------------------------------------------------------------------------


@router.post("/needs_relogin", response_model=None)
async def needs_relogin_webhook(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Receive the VM-side watchdog's relogin alert.

    Body: ``{vm_id, engine, reason, novnc_url?}``. Marks the matching
    vm_session account as ``needs_relogin`` and fires a fire-and-forget
    Slack notification (no-op when ``SLACK_WEBHOOK_URL`` is unset).

    Returns 200 even when no matching account exists (the watchdog can
    emit before the operator has provisioned the row; the Slack ping
    still surfaces the issue).
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    vm_id = str(payload.get("vm_id") or "").strip()
    engine = str(payload.get("engine") or "").strip()
    reason = str(payload.get("reason") or "").strip() or None
    novnc_url = str(payload.get("novnc_url") or "").strip() or None

    if not vm_id or not engine:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "vm_id_and_engine_required",
                "message": "Body must include both vm_id and engine.",
            },
        )

    account_id = await vm_db.mark_needs_relogin(session, vm_id=vm_id, engine=engine)

    # Fire-and-forget Slack notification. The webhook responder must
    # not block on Slack — if Slack is down, the watchdog should still
    # see a 200 and avoid retry storms. We hold a strong reference to
    # the task on ``request.state`` so the asyncio event loop's weak
    # reference doesn't garbage-collect it mid-flight (ruff RUF006).
    request.state.slack_task = asyncio.create_task(
        notify_relogin_needed(vm_id=vm_id, engine=engine, novnc_url=novnc_url, reason=reason)
    )

    if account_id is not None:
        await emit_audit(
            session,
            operator=operator,
            action="vm_needs_relogin",
            severity="med",
            resource_type="llm_account",
            resource_id=str(account_id),
            after={
                "status": NEEDS_RELOGIN_STATUS,
                "vm_id": vm_id,
                "engine": engine,
                "reason": reason,
            },
            reason="vm_needs_relogin webhook",
            request=request,
        )

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "account_id": account_id,
            "slack_notified": True,
            "message": (
                f"Marked vm {vm_id} ({engine}) as {NEEDS_RELOGIN_STATUS}."
                if account_id is not None
                else (
                    f"No vm_session account found for vm={vm_id} engine={engine}; "
                    "Slack ping queued anyway."
                )
            ),
        },
    )


# ---------------------------------------------------------------------------
# POST /relogin_done — operator confirms relogin completed
# ---------------------------------------------------------------------------


@router.post("/relogin_done", response_model=None)
async def relogin_done(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Operator confirms that a vm_session account has been re-authed.

    Body: ``{vm_id, engine}``. Flips status back to ``active`` and
    stamps ``last_relogin_at`` so the dashboard shows the recovery
    timestamp.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    vm_id = str(payload.get("vm_id") or "").strip()
    engine = str(payload.get("engine") or "").strip()
    if not vm_id or not engine:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "vm_id_and_engine_required",
                "message": "Body must include both vm_id and engine.",
            },
        )

    account_id = await vm_db.clear_needs_relogin(session, vm_id=vm_id, engine=engine)
    if account_id is None:
        raise not_found("vm_account_not_found")

    await emit_audit(
        session,
        operator=operator,
        action="vm_relogin_done",
        severity="med",
        resource_type="llm_account",
        resource_id=str(account_id),
        after={"status": "active", "vm_id": vm_id, "engine": engine},
        reason="vm_relogin_done operator confirmation",
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "account_id": account_id,
            "message": f"Cleared {NEEDS_RELOGIN_STATUS} for vm {vm_id} ({engine}).",
        },
    )
