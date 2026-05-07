"""Admin Accounts router — Phase 7 slice 7b (HIGHEST sensitivity).

Mounted at ``/api/admin/accounts`` (cookie ``current_admin``). The legacy
admin_console exposed these at ``/api/accounts/*`` WITHOUT admin auth;
the FastAPI port adds ``Depends(current_admin)`` to every handler — a
deliberate security hardening since these touch ``llm_accounts.cookies_json``
(operator credential data). The same handlers are re-mounted at
``/api/accounts/*`` in app/main.py as a legacy alias, also auth-protected,
so admin.html keeps working unchanged.

Routes:
- GET    /api/admin/accounts                       list (no cookies blob)
- POST   /api/admin/accounts/import_cookies        upsert cookies + emit_audit (high)
- POST   /api/admin/accounts/{id}/status           flip status + emit_audit (high)
- POST   /api/admin/accounts/{id}/reset            reset counters + emit_audit (med)
- DELETE /api/admin/accounts/{id}                  destructive delete + emit_audit (high)
- POST   /api/admin/accounts/{id}/auto_login       enqueue celery task + emit_audit (med)

Audit pattern:
- emit_audit fires AFTER the DB op; we never log the cookies_json blob —
  only counts + platform / label / status. This is on purpose.
- ``import_cookies`` is severity HIGH; ``delete`` is HIGH; ``status``
  flips to banned/cooldown are HIGH; ``reset`` + ``auto_login`` med.

Schema-drift safety (defense-in-depth, after PR #367 hit Query Pool):
- ``20260507_llm_accounts_schema_repair`` Alembic migration ALTERs every
  column we touch via ``ADD COLUMN IF NOT EXISTS``. Idempotent on healthy
  DBs, repairs legacy operator DBs.
- ``accounts_db.assert_llm_accounts_schema`` is a runtime guard: if the
  table is missing a required column we surface ``503
  llm_accounts_schema_outdated`` with the missing column list, instead of
  letting psycopg raise ``UndefinedColumn`` mid-query (which would 500).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from genpano_models import AdminUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.accounts import db as accounts_db
from app.admin.accounts.lib import (
    ACCOUNT_STATUSES,
    CookieImportError,
    normalize_account_status,
    parse_cookies_payload,
    safe_email_for_label,
)
from app.admin.audit import emit_audit
from app.api.admin.auth.router import current_admin
from app.core.errors import not_found
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Accounts"])


def _maybe_schema_error_response(error: RuntimeError) -> JSONResponse | None:
    """Map known ``llm_accounts`` schema errors to a 503 JSON response.

    Stable error codes:
    - ``llm_accounts_table_missing`` — the table doesn't exist (sqlite
      tests / fresh DB without legacy seed). Returned by every db helper.
    - ``llm_accounts_schema_outdated:<csv>`` — the table exists but is
      missing one or more columns slice 7b depends on. Defense-in-depth
      against the schema-drift bug class PR #367 hit on Query Pool.

    Returns ``None`` for any other ``RuntimeError`` so callers re-raise.
    """
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
                    "llm_accounts is missing columns the Admin Accounts API "
                    f"requires: {missing}. Run the latest Alembic migrations."
                ),
            },
        )
    return None


@router.get("", response_model=None)
async def list_accounts(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> Any:
    """List llm_accounts. Wire shape matches admin_console (cookies
    blob is never returned; only the cookie_count derived in SQL)."""
    try:
        rows = await accounts_db.fetch_accounts(session)
    except RuntimeError as error:
        response = _maybe_schema_error_response(error)
        if response is not None:
            return response
        raise
    return rows


@router.post("/import_cookies", response_model=None)
async def import_cookies(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Upsert cookies for an llm_accounts row.

    Validates payload via ``parse_cookies_payload`` (auto-detects
    EditThisCookie format, packs ``localStorage`` when present),
    UPSERTs into ``llm_accounts`` keyed on (llm_name, phone_number),
    and emits a HIGH-severity audit row with COUNTS only — never the
    cookies blob — so the audit log doesn't become a credential leak.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        platform, label, cookies_json_str, cookie_count, ls_count, daily_limit = (
            parse_cookies_payload(payload)
        )
    except CookieImportError as error:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": error.code, "message": error.message},
        )

    try:
        account_id, outcome = await accounts_db.upsert_account_from_cookies(
            session,
            platform=platform,
            label=label,
            cookies_json_str=cookies_json_str,
            daily_limit=daily_limit,
            email=safe_email_for_label(label, platform),
        )
    except RuntimeError as error:
        response = _maybe_schema_error_response(error)
        if response is not None:
            return response
        raise

    verb = "Created new" if outcome == "added" else "Updated"
    msg = f"{verb} #{account_id} ({platform}) with {cookie_count} cookies"
    if ls_count:
        msg += f" + {ls_count} localStorage items"

    await emit_audit(
        session,
        operator=operator,
        action="import_cookies",
        severity="high",
        resource_type="llm_account",
        resource_id=str(account_id),
        after={
            "platform": platform,
            "label": label,
            "cookie_count": cookie_count,
            "local_storage_count": ls_count,
            "outcome": outcome,
        },
        reason=str(payload.get("reason") or "import_cookies"),
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={"success": True, "account_id": account_id, "message": msg},
    )


@router.post("/{account_id}/status", response_model=None)
async def update_status(
    account_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Flip account status (active / banned / cooldown). emit_audit
    severity HIGH for banned/cooldown; med for active (de-restriction
    is less destructive)."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    new_status = normalize_account_status(payload.get("status") or "active")
    if new_status is None:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_status",
                "message": f"status must be one of {sorted(ACCOUNT_STATUSES)}",
            },
        )

    try:
        before = await accounts_db.get_account(session, account_id=account_id)
        if before is None:
            raise not_found("account_not_found")

        ok = await accounts_db.update_account_status(
            session, account_id=account_id, status=new_status
        )
    except RuntimeError as error:
        response = _maybe_schema_error_response(error)
        if response is not None:
            return response
        raise
    if not ok:
        raise not_found("account_not_found")

    severity: Literal["low", "med", "high"] = (
        "high" if new_status in {"banned", "cooldown"} else "med"
    )
    await emit_audit(
        session,
        operator=operator,
        action="update_account_status",
        severity=severity,
        resource_type="llm_account",
        resource_id=str(account_id),
        before={"status": before.get("status")},
        after={"status": new_status},
        reason=str(payload.get("reason") or "update_account_status"),
        request=request,
    )
    return JSONResponse(status_code=200, content={"success": True})


@router.post("/{account_id}/reset", response_model=None)
async def reset_fails(
    account_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Reset consecutive_fails + query_count_today + flip to active.
    emit_audit (med, action=reset_account_fails)."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        before = await accounts_db.get_account(session, account_id=account_id)
        if before is None:
            raise not_found("account_not_found")

        ok = await accounts_db.reset_account_fails(session, account_id=account_id)
    except RuntimeError as error:
        response = _maybe_schema_error_response(error)
        if response is not None:
            return response
        raise
    if not ok:
        raise not_found("account_not_found")

    await emit_audit(
        session,
        operator=operator,
        action="reset_account_fails",
        severity="med",
        resource_type="llm_account",
        resource_id=str(account_id),
        before={
            "status": before.get("status"),
            "consecutive_fails": before.get("consecutive_fails"),
            "daily_used": before.get("daily_used"),
        },
        after={"status": "active", "consecutive_fails": 0, "daily_used": 0},
        reason=str(payload.get("reason") or "reset_account_fails"),
        request=request,
    )
    return JSONResponse(status_code=200, content={"success": True})


@router.delete("/{account_id}", response_model=None)
async def delete_account(
    account_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Hard-delete (no soft-delete column on ``llm_accounts``).
    emit_audit (high, action=delete_account) — destructive op.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        before = await accounts_db.get_account(session, account_id=account_id)
        if before is None:
            raise not_found("account_not_found")

        ok = await accounts_db.delete_account(session, account_id=account_id)
    except RuntimeError as error:
        response = _maybe_schema_error_response(error)
        if response is not None:
            return response
        raise
    if not ok:
        raise not_found("account_not_found")

    await emit_audit(
        session,
        operator=operator,
        action="delete_account",
        severity="high",
        resource_type="llm_account",
        resource_id=str(account_id),
        before=before,
        after={"deleted": True},
        reason=str(payload.get("reason") or "delete_account"),
        request=request,
    )
    return JSONResponse(status_code=200, content={"success": True})


@router.post("/{account_id}/auto_login", response_model=None)
async def trigger_auto_login(
    account_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Enqueue a celery task to refresh login for ``account_id``.

    Backend mirrors admin_console's "celery is optional" pattern:
    when celery isn't installed/configured, returns 503 with
    ``celery_unavailable`` rather than crashing. emit_audit (med).
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    try:
        from celery import Celery  # noqa: F401  — availability probe
        from geo_tracker.celery_app import celery_app  # type: ignore[import-not-found]
    except Exception:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "celery_unavailable",
                "message": "Celery is not configured in this deployment",
            },
        )

    try:
        result = celery_app.send_task(
            "geo_tracker.tasks.celery_tasks.auto_login",
            kwargs={"account_id": account_id},
            queue="account_login",
        )
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "celery_dispatch_failed",
                "message": str(exc)[:300],
            },
        )

    await emit_audit(
        session,
        operator=operator,
        action="trigger_auto_login",
        severity="med",
        resource_type="llm_account",
        resource_id=str(account_id),
        after={"task_id": getattr(result, "id", None)},
        reason=str(payload.get("reason") or "trigger_auto_login"),
        request=request,
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"success": True, "task_id": getattr(result, "id", None)},
    )


# Re-exports for tests.
__all__ = ["router"]
