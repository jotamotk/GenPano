"""POST /api/queries/{id}/retry_via_vm — quick "Retry via VM" admin endpoint.

Refs Epic #1110 / Issue #1144.

PARALLEL to (not replacing) the existing ``POST /api/queries/{id}/retry``
cookie-inject path. Both endpoints coexist. The "via VM" path:

  1. Loads the query by id (404 if missing).
  2. Opens a Playwright CDP connection to the doubao-01 / doubao-02 VM
     (``VM_QUICK_RETRY_CDP_ENDPOINT``, default ``http://127.0.0.1:9222``).
  3. Sends the prompt to Doubao (or DeepSeek, sharing the same Chrome
     profile) using the manually-logged-in session.
  4. Captures rawText / screenshot.
  5. Appends an attempt to ``ai_responses.attempts`` with
     ``execution_mode='vm_session_quick'``, ``vm_id='doubao-01'``.
  6. Returns ``{"status":"ok","raw_text_chars":N,"attempt_n":N}``.

Error surface (per Issue #1144 Acceptance Matrix):

  - 200 with status=ok on success.
  - 404 when the query doesn't exist.
  - 503 with ``{"error":"cdp_unreachable"}`` when CDP connect fails.
  - 503 with ``{"error":"vm_not_logged_in"}`` when login form was rendered
    (manual re-login via noVNC required).
  - 503 with ``{"error":"queries_unavailable"}`` if the queries table
    is missing (sqlite test path / fresh DB).

This endpoint does NOT inherit the existing retry path's celery
dispatch — it executes inline, then commits. Audit emit uses
``severity='med'`` (matches the existing ``retry_query`` audit row).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated, Any, Optional

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


def _cdp_override_for_vm(requested_vm: Optional[str]) -> Optional[str]:
    """Map vm_id alias to CDP endpoint URL.

    Returns None when caller did not pin a specific VM (env-derived
    default is used). Two known aliases: doubao-01 → :9222,
    doubao-02 → :9223. DeepSeek queries reuse the same containers
    (Epic #1110 architecture decision: same Chrome profile, different
    tab) so no new vm_id alias is needed.
    """
    if requested_vm == "doubao-01":
        return "http://127.0.0.1:9222"
    if requested_vm == "doubao-02":
        return "http://127.0.0.1:9223"
    return None


@dataclass
class _PerQueryOutcome:
    """Outcome shape returned by ``_run_one_via_vm`` for one query_id.

    Attributes:
        status_code: HTTP-style status for the single attempt. The
            batch endpoint groups 200 into success, others into failed.
        body: JSON body to return for a single-query route, OR the
            failed-row body for the batch endpoint.
        error_code: ``cdp_unreachable`` / ``vm_not_logged_in`` /
            ``not_found`` etc, or None on success.
    """

    status_code: int
    body: dict[str, Any]
    error_code: Optional[str]


async def _run_one_via_vm(
    *,
    session: AsyncSession,
    operator: AdminUser,
    request: Request,
    query_id: int,
    requested_vm: Optional[str],
) -> _PerQueryOutcome:
    """Run a single retry-via-VM attempt and emit an audit row.

    Pulled out of the single-row route so the batch route can reuse it
    without duplicating audit/error handling. Behavior identical to the
    original single endpoint: loads queries row, runs run_quick_retry,
    maps QuickRetryError to a 503, emits audit on both success and
    failure paths.
    """
    # 1. Load query row.
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
        return _PerQueryOutcome(
            status_code=404,
            body={"success": False, "error": "not_found", "message": "Query not found"},
            error_code="not_found",
        )

    target_llm = (row.get("target_llm") or "").strip()
    query_text = row.get("query_text") or ""

    # 2. Dispatch to the quick-retry helper. Imported lazily so
    #    importing this module does not pull Playwright (the test
    #    harness without Playwright installed can still import the
    #    route module for URL discovery).
    from geo_tracker.agent.vm_quick_retry import (  # type: ignore[import-not-found]
        ERR_CDP_UNREACHABLE,
        ERR_VM_NOT_LOGGED_IN,
        QuickRetryError,
        run_quick_retry,
    )

    cdp_override = _cdp_override_for_vm(requested_vm)

    try:
        result = await run_quick_retry(
            query_id=query_id,
            query_text=query_text,
            target_llm=target_llm,
            session=session,
            cdp_endpoint=cdp_override,
            vm_id=requested_vm,
        )
    except QuickRetryError as exc:
        # Audit the failed attempt so the operator log shows the attempt
        # was made (matches the existing retry path's audit behavior).
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
        return _PerQueryOutcome(
            status_code=status_code,
            body={
                "success": False,
                "error": exc.code,
                "message": exc.detail or exc.code,
            },
            error_code=exc.code,
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

    return _PerQueryOutcome(
        status_code=200,
        body={
            "status": "ok",
            "success": True,
            "raw_text_chars": int(result.get("raw_text_chars") or 0),
            "attempt_n": int(result.get("attempt_n") or 0),
            "vm_id": result.get("vm_id"),
            "execution_mode": "vm_session_quick",
        },
        error_code=None,
    )


async def _queries_table_unavailable_response(
    session: AsyncSession,
) -> Optional[JSONResponse]:
    """Return a 503 response when the queries table is absent, else None."""
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
    return None


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
    unavailable = await _queries_table_unavailable_response(session)
    if unavailable is not None:
        return unavailable

    # Optional body params: {"vm_id": "doubao-01"|"doubao-02"} so the
    # operator can pick which container (= which logged-in account) runs
    # the retry. Maps to CDP port via the static doubao-01 → 9222,
    # doubao-02 → 9223 convention. Empty body keeps default behaviour
    # (env-derived endpoint, vm_id from env).
    body: dict[str, object] = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    requested_vm = (body.get("vm_id") if isinstance(body, dict) else None) or None

    outcome = await _run_one_via_vm(
        session=session,
        operator=operator,
        request=request,
        query_id=query_id,
        requested_vm=requested_vm if isinstance(requested_vm, str) else None,
    )
    return JSONResponse(status_code=outcome.status_code, content=outcome.body)


@router.post("/queries/batch_retry_via_vm", response_model=None)
async def batch_retry_query_via_vm(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Bulk "Retry via VM" — sequentially run each query_id through the VM.

    Body shape: ``{"query_ids": [int], "vm_id": "doubao-01"|"doubao-02"}``.
    ``vm_id`` is optional; when absent the env-derived default is used.

    Behavior:
      - For each query_id, sequentially call ``run_quick_retry`` (the
        same code path as the single ``/retry_via_vm`` endpoint).
      - Accumulate success/failed counts.
      - Per-query audit rows are emitted by ``_run_one_via_vm`` —
        same severity='med' as the single-row path.

    Response body:
      ``{"total": N, "success": N, "failed": [{"id": qid, "error": "..."}]}``
    Status code is 200 even on partial failure — the per-query errors
    are reported in the body so the operator can re-trigger only the
    failed rows.

    Returns 400 when ``query_ids`` is missing or empty, 503 when the
    queries table is absent.
    """
    unavailable = await _queries_table_unavailable_response(session)
    if unavailable is not None:
        return unavailable

    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    raw_ids = body.get("query_ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "missing_query_ids",
                "message": "Request body must include non-empty 'query_ids' list",
            },
        )

    # Normalize to int, dropping non-numeric / non-positive ids.
    query_ids: list[int] = []
    for raw in raw_ids:
        try:
            qid = int(raw)
        except (TypeError, ValueError):
            continue
        if qid > 0:
            query_ids.append(qid)
    if not query_ids:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_query_ids",
                "message": "All query_ids were non-numeric or non-positive",
            },
        )

    requested_vm = body.get("vm_id") if isinstance(body, dict) else None
    if not isinstance(requested_vm, str):
        requested_vm = None

    success_count = 0
    failed: list[dict[str, Any]] = []
    for qid in query_ids:
        outcome = await _run_one_via_vm(
            session=session,
            operator=operator,
            request=request,
            query_id=qid,
            requested_vm=requested_vm,
        )
        if outcome.status_code == 200:
            success_count += 1
        else:
            failed.append(
                {
                    "id": qid,
                    "error": outcome.error_code or "unknown_error",
                }
            )

    return JSONResponse(
        status_code=200,
        content={
            "total": len(query_ids),
            "success": success_count,
            "failed": failed,
        },
    )


__all__ = ["router"]
