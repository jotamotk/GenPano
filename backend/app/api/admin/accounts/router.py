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
    - ``account_profile_map_table_missing`` — the production-only
      profile-binding table isn't available (sqlite test fixture); the
      profile drawer / counts / auto-assign endpoints surface it as 503.

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
    if code == "account_profile_map_table_missing":
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "account_profile_map_unavailable",
                "message": "account_profile_map table is not available; run migrations first.",
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


@router.get("/profile_counts", response_model=None)
async def profile_counts(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> Any:
    """Return ``{account_id: {bindings, unacknowledged}}`` so the
    account pool table can render the 绑定Profiles column without N+1
    fetches. Empty dict when ``account_profile_map`` doesn't exist
    (sqlite tests / fresh DB)."""
    try:
        return await accounts_db.fetch_profile_counts(session)
    except RuntimeError as error:
        response = _maybe_schema_error_response(error)
        if response is not None:
            return response
        raise


@router.post("/auto_assign_profiles", response_model=None)
async def auto_assign_profiles(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Bulk-assign profiles to active accounts (round-robin per
    geo bucket).

    Body (all optional):
      - ``per_account`` (int 1..50, default 5): how many profiles per
        account.
      - ``skip_already_bound`` (bool, default true): skip accounts that
        already have ≥ ``per_account`` bindings. Re-run is idempotent.

    LLM-driven ranking from the Flask original is intentionally not
    ported — admin_console always fell back to round-robin in
    production (no API key provisioned in the backend container) and
    the parity tests run against the RR path. Operators who need
    LLM-driven assignment can keep using admin_console for now.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    try:
        per_account = max(1, min(int(payload.get("per_account", 5)), 50))
    except (TypeError, ValueError):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_per_account",
                "message": "per_account must be 1..50",
            },
        )
    skip_bound = bool(payload.get("skip_already_bound", True))

    try:
        accounts = await accounts_db.fetch_active_accounts_with_bound_count(session)
        all_profiles = await accounts_db.fetch_assignable_profiles(session)
    except RuntimeError as error:
        response = _maybe_schema_error_response(error)
        if response is not None:
            return response
        raise

    summary: dict[str, Any] = {
        "accounts_processed": 0,
        "accounts_skipped": 0,
        "bindings_inserted": 0,
        "method": "rr",
        "errors": [],
    }

    by_geo: dict[str, list[dict[str, Any]]] = {"CN": [], "US": [], "*": []}
    for profile in all_profiles:
        persona = profile.get("persona_json") or {}
        country: str | None = None
        for key in ("country_code", "country", "geo"):
            value = persona.get(key) or ""
            if isinstance(value, str) and value:
                country = value.upper()
                break
        if country == "CN":
            by_geo["CN"].append(profile)
        elif country in ("US", "NA", "GB"):
            by_geo["US"].append(profile)
        else:
            by_geo["*"].append(profile)

    rr_idx: dict[str, int] = {"CN": 0, "US": 0, "*": 0}
    inserted_total = 0
    bindings_changed = False
    try:
        for account in accounts:
            bound_count = int(account.get("bound_count") or 0)
            if skip_bound and bound_count >= per_account:
                summary["accounts_skipped"] += 1
                continue
            expected = accounts_db.account_engine_geo(account.get("llm_name"))
            bucket_key = expected if expected in by_geo else "*"
            pool = by_geo.get(bucket_key, []) + by_geo["*"]
            if not pool:
                continue
            start = rr_idx.get(bucket_key, 0)
            picks = [pool[(start + k) % len(pool)]["id"] for k in range(per_account)]
            rr_idx[bucket_key] = (start + per_account) % len(pool)

            try:
                inserted = await accounts_db.insert_auto_assigned_bindings(
                    session,
                    account_id=int(account["id"]),
                    profile_ids=picks,
                )
            except RuntimeError as error:
                response = _maybe_schema_error_response(error)
                if response is not None:
                    return response
                raise
            inserted_total += inserted
            summary["accounts_processed"] += 1
            bindings_changed = bindings_changed or inserted > 0
        if bindings_changed:
            await session.commit()
    except Exception:
        await session.rollback()
        raise

    summary["bindings_inserted"] = inserted_total

    await emit_audit(
        session,
        operator=operator,
        action="auto_assign_profiles",
        severity="med",
        resource_type="llm_account",
        resource_id="*",
        after={
            "per_account": per_account,
            "accounts_processed": summary["accounts_processed"],
            "accounts_skipped": summary["accounts_skipped"],
            "bindings_inserted": inserted_total,
            "method": summary["method"],
        },
        reason=str(payload.get("reason") or "auto_assign_profiles"),
        request=request,
    )

    return JSONResponse(
        status_code=200,
        content={"success": True, **summary},
    )


@router.get("/{account_id}/profiles", response_model=None)
async def list_account_profiles(
    account_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> Any:
    """Return paginated Profile bindings for an account with soft-conflict
    flags computed against the engine's expected geo.

    Query params:
    - ``q``: search across profile id/code/name.
    - ``only``: ``conflicts`` to filter to unacknowledged conflict
      bindings; anything else returns all.
    - ``limit`` (default 50, max 200), ``offset`` (default 0).
    """
    q = (request.query_params.get("q") or "").strip() or None
    only = (request.query_params.get("only") or "all").strip().lower()
    try:
        limit = max(1, min(int(request.query_params.get("limit", 50)), 200))
    except (TypeError, ValueError):
        limit = 50
    try:
        offset = max(0, int(request.query_params.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0

    try:
        account = await accounts_db.fetch_account_basics(session, account_id=account_id)
        if not account:
            raise not_found("account_not_found")
        rows = await accounts_db.fetch_account_profile_bindings(session, account_id=account_id, q=q)
        quota_total = await accounts_db.fetch_account_quota_total(session, account_id=account_id)
    except RuntimeError as error:
        response = _maybe_schema_error_response(error)
        if response is not None:
            return response
        raise

    expected_geo = accounts_db.account_engine_geo(account.get("llm_name"))
    bindings: list[dict[str, Any]] = []
    for row in rows:
        persona_raw = row.get("persona_json") or {}
        persona = persona_raw if isinstance(persona_raw, dict) else {}
        country = persona.get("country_code") or ""
        country = country.upper() if isinstance(country, str) and country else None
        device = persona.get("device_type") or ""
        device = device.lower() if isinstance(device, str) and device else None
        language = persona.get("language") or ""
        language = language.lower() if isinstance(language, str) and language else None
        timezone_value = persona.get("timezone") or None
        conflicts: list[dict[str, Any]] = []
        if expected_geo and country and country != expected_geo:
            conflicts.append({"field": "geo", "expected": expected_geo, "actual": country})
        bindings.append(
            {
                "binding_id": row.get("binding_id"),
                "profile_id": row.get("profile_id"),
                "profile_code": row.get("profile_code"),
                "profile_name": row.get("profile_name"),
                "daily_quota": int(row.get("daily_quota") or 0),
                "country_code": country,
                "device_type": device,
                "language": language,
                "timezone": timezone_value,
                "conflicts": conflicts,
                "conflict_acknowledged": bool(row.get("conflict_acknowledged")),
            }
        )

    if only == "conflicts":
        bindings = [b for b in bindings if b["conflicts"] and not b["conflict_acknowledged"]]

    total = len(bindings)
    page = bindings[offset : offset + limit]

    return {
        "account": {
            "id": account.get("id"),
            "llm_name": account.get("llm_name"),
            "phone_number": account.get("phone_number"),
            "daily_limit": int(account.get("daily_limit") or 0),
            "query_count_today": int(account.get("query_count_today") or 0),
            "status": account.get("status"),
            "expected_geo": expected_geo,
        },
        "bindings": page,
        "total": total,
        "quota_total": quota_total,
    }


@router.put("/{account_id}/profiles", response_model=None)
async def upsert_account_profiles(
    account_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Upsert (and optionally remove) profile bindings for an account.

    Body shape:
        {
          "bindings": [{"profile_id": "pf_…", "daily_quota": 1,
                        "conflict_acknowledged": false}, …],
          "remove_profile_ids": ["pf_…", …]
        }
    emit_audit (med, action=update_account_profiles).
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    bindings_in = payload.get("bindings") or []
    remove_ids_in = payload.get("remove_profile_ids") or []
    if not isinstance(bindings_in, list):
        bindings_in = []
    if not isinstance(remove_ids_in, list):
        remove_ids_in = []
    daily_limit_raw = payload.get("daily_limit")
    daily_limit: int | None = None
    if daily_limit_raw is not None:
        try:
            daily_limit = int(daily_limit_raw)
        except (TypeError, ValueError):
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "daily_limit_invalid",
                    "message": "daily_limit must be an integer between 0 and 10000",
                },
            )
        if daily_limit < 0 or daily_limit > 10_000:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "daily_limit_invalid",
                    "message": "daily_limit must be an integer between 0 and 10000",
                },
            )

    try:
        account = await accounts_db.fetch_account_basics(session, account_id=account_id)
        if not account:
            raise not_found("account_not_found")
        daily_limit_changed = daily_limit is not None and daily_limit != int(
            account.get("daily_limit") or 0
        )
        if daily_limit_changed:
            ok = await accounts_db.update_account_daily_limit(
                session, account_id=account_id, daily_limit=daily_limit
            )
            if not ok:
                raise not_found("account_not_found")
        upserted, removed = await accounts_db.upsert_account_profile_bindings(
            session,
            account_id=account_id,
            bindings=[b for b in bindings_in if isinstance(b, dict)],
            remove_profile_ids=[str(p) for p in remove_ids_in if p],
        )
    except RuntimeError as error:
        response = _maybe_schema_error_response(error)
        if response is not None:
            return response
        raise

    await emit_audit(
        session,
        operator=operator,
        action="update_account_profiles",
        severity="med",
        resource_type="llm_account",
        resource_id=str(account_id),
        after={
            "upserted": upserted,
            "removed": removed,
            **(
                {
                    "daily_limit": {
                        "before": int(account.get("daily_limit") or 0),
                        "after": daily_limit,
                    }
                }
                if daily_limit_changed
                else {}
            ),
        },
        reason=str(payload.get("reason") or "update_account_profiles"),
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "upserted": upserted,
            "removed": removed,
            **({"daily_limit": daily_limit} if daily_limit is not None else {}),
        },
    )


# Re-exports for tests.
__all__ = ["router"]
