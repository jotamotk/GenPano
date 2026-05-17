"""POST /api/queries/{id}/retry_via_vm — quick "Retry via VM" admin endpoint.

Refs Epic #1110 / Issue #1144.

PARALLEL to (not replacing) the existing ``POST /api/queries/{id}/retry``
cookie-inject path. Both endpoints coexist. The "via VM" path:

  1. Loads the query by id (404 if missing).
  2. Opens a Playwright CDP connection to the doubao-01 VM
     (``VM_QUICK_RETRY_CDP_ENDPOINT``, default ``http://127.0.0.1:9222``).
  3. Sends the prompt to Doubao using the manually-logged-in session.
  4. Captures rawText / screenshot.
  5. Appends an attempt to ``ai_responses.attempts`` with
     ``execution_mode='vm_session_quick'``, ``vm_id='doubao-01'``.
  6. Returns ``{"status":"ok","raw_text_chars":N,"attempt_n":N}``.

Error surface (per Issue #1144 Acceptance Matrix):

  - 200 with status=ok on success.
  - 404 when the query doesn't exist.
  - 503 with ``{"error":"cdp_unreachable"}`` when CDP connect fails.
  - 503 with ``{"error":"vm_not_logged_in"}`` when Doubao rendered
    the login form (manual re-login via noVNC required).
  - 503 with ``{"error":"queries_unavailable"}`` if the queries table
    is missing (sqlite test path / fresh DB).

This endpoint does NOT inherit the existing retry path's celery
dispatch — it executes inline, then commits. Audit emit uses
``severity='med'`` (matches the existing ``retry_query`` audit row).
"""
from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from genpano_models import AdminUser
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.queries import db as queries_db
from app.api.admin.auth.router import current_admin
from app.core.security import _DependsDb

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Queries via VM"])


@router.post("/queries/{query_id}/retry_via_vm", response_model=None)
async def retry_query_via_vm(
    query_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Quick decoupled retry path that bypasses cookie inject + celery.

    See module docstring for the full contract. The route catches
    ``QuickRetryError`` and maps it to the issue-defined 503 codes;
    every other exception bubbles up as a 500 (the route does not
    silently swallow unknown failures — operator visibility wins over
    a clean response).
    """
    # 1. Load query row. Returns 503 when the queries table is absent
    #    (sqlite test path) so the operator's UI can show a clear cause.
    try:
        if not await queries_db._table_exists(session, "queries"):
            return JSONResponse(
                status_code=503,
                content={
                    "success": False,
                    "error": "queries_unavailable",
                    "message": "queries table is not available; run migrations first.",
                },
            )
    except Exception as exc:
        logger.warning("retry_via_vm: table-exists check raised %r", exc)
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "queries_unavailable",
                "message": f"queries table check failed: {exc!r}",
            },
        )

    row = (
        (
            await session.execute(
                sa_text("SELECT id, target_llm, query_text FROM queries WHERE id = :id"),
                {"id": query_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "not_found", "message": "Query not found"},
        )

    target_llm = (row.get("target_llm") or "").strip()
    query_text = row.get("query_text") or ""

    # 2. Dispatch to the quick-retry helper. Imported lazily so
    #    importing this module does not pull Playwright (the test
    #    harness without Playwright installed can still import the
    #    route module for URL discovery).
    from geo_tracker.agent.vm_quick_retry import (
        ERR_CDP_UNREACHABLE,
        ERR_VM_NOT_LOGGED_IN,
        QuickRetryError,
        run_quick_retry,
    )

    try:
        result = await run_quick_retry(
            query_id=query_id,
            query_text=query_text,
            target_llm=target_llm,
            session=session,
        )
    except QuickRetryError as exc:
        # Audit the failed attempt so the operator log shows the
        # attempt was made (matches the existing retry path's audit
        # behavior — every operator-triggered retry is logged).
        try:
            await emit_audit(
                session,
                operator=operator,
                action="retry_query_via_vm",
                severity="med",
                resource_type="query",
                resource_id=str(query_id),
                after={
                    "target_llm": target_llm,
                    "error": exc.code,
                    "execution_mode": "vm_session_quick",
                },
                reason=f"retry_via_vm:{exc.code}",
                request=request,
            )
        except Exception as audit_exc:
            logger.warning("retry_via_vm: audit emit failed: %r", audit_exc)

        status_code = 503 if exc.code in (ERR_CDP_UNREACHABLE, ERR_VM_NOT_LOGGED_IN) else 500
        return JSONResponse(
            status_code=status_code,
            content={
                "success": False,
                "error": exc.code,
                "message": exc.detail or exc.code,
            },
        )

    # 3. Success — emit audit + return the 200 OK body per Acceptance
    #    Matrix row 1.
    try:
        await emit_audit(
            session,
            operator=operator,
            action="retry_query_via_vm",
            severity="med",
            resource_type="query",
            resource_id=str(query_id),
            after={
                "target_llm": target_llm,
                "execution_mode": "vm_session_quick",
                "vm_id": result.get("vm_id"),
                "raw_text_chars": result.get("raw_text_chars"),
                "attempt_n": result.get("attempt_n"),
            },
            reason="retry_via_vm:success",
            request=request,
        )
    except Exception as audit_exc:
        logger.warning("retry_via_vm: success audit emit failed: %r", audit_exc)

    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "success": True,
            "raw_text_chars": int(result.get("raw_text_chars") or 0),
            "attempt_n": int(result.get("attempt_n") or 0),
            "vm_id": result.get("vm_id"),
            "execution_mode": "vm_session_quick",
        },
    )


__all__ = ["router"]
