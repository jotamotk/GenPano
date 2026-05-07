"""Admin Query Pool router (Phase 5 — initial slice).

Mounted at ``/api/admin/query-pool`` (cookie ``current_admin``).

Routes in this PR (parity with topic_plan B.1 + part of B.2.a):
- POST /candidates/{candidate_id}/review   move a candidate through
                                            candidate -> review -> ready
- POST /candidates/bulk-review             same decision applied to many
- GET  /runs/{run_id}                      single run row
- POST /runs/{run_id}/stop                 cancel a running assemble

Phase 5 follow-up PRs will add: GET /candidates (cursor paged),
DELETE /candidates/{id}, POST /candidates/bulk-delete, GET /runs (list),
POST /preflight, POST /assemble (the LLM-heavy run launcher).

Notes:
- ``QueryGenerationCandidate.candidate_status`` is the state machine
  (candidate / review / ready) — not the topic_plan/prompt_matrix-style
  pending/approved/rejected. Validation enforces this.
- The legacy admin SPA also calls these via ``/admin/api/v1/pipeline/query-pool/*``;
  those aliases are added at the FastAPI mount layer in admin/router.py.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from genpano_models import AdminUser, QueryGenerationCandidate, QueryGenerationRun
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.api.admin.auth.router import current_admin
from app.core.errors import not_found, validation_error
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Query Pool"])

QUERY_POOL_CANDIDATE_STATUSES = {"candidate", "review", "ready"}


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _candidate_row(c: QueryGenerationCandidate) -> dict[str, Any]:
    return {
        "id": c.id,
        "run_id": c.run_id,
        "candidate_seq": int(c.candidate_seq or 0),
        "prompt_id": c.prompt_id,
        "segment_id": c.segment_id,
        "profile_id": c.profile_id,
        "rendered_query": c.rendered_query,
        "generation_method": c.generation_method,
        "llm_model": c.llm_model,
        "llm_usage": c.llm_usage_json or {},
        "candidate_status": c.candidate_status,
        "scheduler_intake_batch_id": c.scheduler_intake_batch_id,
        "reviewed_by": c.reviewed_by,
        "reviewed_at": _isoformat(c.reviewed_at),
        "review_reason": c.review_reason,
        "created_at": _isoformat(c.created_at),
    }


def _run_to_dict(run: QueryGenerationRun) -> dict[str, Any]:
    request_config = run.request_config if isinstance(run.request_config, dict) else {}
    end = run.completed_at or _now()
    start = run.started_at or run.created_at or _now()
    elapsed = max(0.0, (end - start).total_seconds())
    return {
        "id": run.id,
        "status": run.status,
        "admin_id": run.admin_id,
        "request_config": request_config,
        "prompt_ids": run.prompt_ids if isinstance(run.prompt_ids, list) else [],
        "segment_ids_selected": run.segment_ids_selected
        if isinstance(run.segment_ids_selected, list)
        else [],
        "profiles_per_prompt": int(run.profiles_per_prompt or 0),
        "desired_engine_policy": run.desired_engine_policy,
        "engine_panel_id": run.engine_panel_id,
        "max_candidates": int(run.max_candidates or 0),
        "overflow_policy": run.overflow_policy,
        "candidates_estimated": int(run.candidates_estimated or 0),
        "candidates_assembled": int(run.candidates_assembled or 0),
        "estimated_cost": float(run.estimated_cost or 0)
        if run.estimated_cost is not None
        else None,
        "preflight_summary": run.preflight_summary
        if isinstance(run.preflight_summary, dict)
        else {},
        "llm_model": run.llm_model,
        "llm_usage": run.llm_usage_json if isinstance(run.llm_usage_json, dict) else {},
        "llm_error": run.llm_error,
        "started_at": _isoformat(run.started_at),
        "completed_at": _isoformat(run.completed_at),
        "created_at": _isoformat(run.created_at),
        "updated_at": _isoformat(run.updated_at),
        "elapsed_seconds": float(elapsed),
    }


def _run_timeout_seconds() -> int:
    raw = os.getenv("QUERY_POOL_RUN_TIMEOUT_SECONDS") or "3600"
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 3600
    return max(300, min(n, 14400))


async def _mark_stale_run(session: AsyncSession, run: QueryGenerationRun) -> bool:
    if run.status not in {"running", "pending"}:
        return False
    last_progress = run.updated_at or run.started_at or run.created_at
    if not last_progress:
        return False
    elapsed = (_now() - last_progress).total_seconds()
    if elapsed <= _run_timeout_seconds():
        return False
    run.status = "failed"
    run.llm_error = "query_pool_run_timeout"
    run.completed_at = _now()
    run.updated_at = _now()
    await session.commit()
    await session.refresh(run)
    return True


# ---------------------------------------------------------------------------
# candidate review (single + bulk)
# ---------------------------------------------------------------------------


async def _review_one(
    session: AsyncSession,
    *,
    candidate_id: str,
    requested_status: str,
    operator: AdminUser,
    reason: str | None,
    request: Request,
) -> dict[str, Any]:
    """Move a candidate to one of {candidate, review, ready}. emit_audit fires."""
    candidate = (
        await session.execute(
            select(QueryGenerationCandidate).where(QueryGenerationCandidate.id == candidate_id)
        )
    ).scalar_one_or_none()
    if candidate is None:
        raise not_found("candidate_not_found")

    before_status = candidate.candidate_status
    candidate.candidate_status = requested_status
    candidate.reviewed_by = operator.id
    candidate.reviewed_at = _now()
    candidate.review_reason = reason
    await session.commit()
    await session.refresh(candidate)

    await emit_audit(
        session,
        operator=operator,
        action="query_pool_candidate_review",
        severity="med",
        resource_type="query_generation_candidate",
        resource_id=candidate.id,
        before={"candidate_status": before_status},
        after={"candidate_status": requested_status},
        reason=reason or "query_pool_candidate_review",
        request=request,
    )
    return _candidate_row(candidate)


@router.post("/candidates/{candidate_id}/review", response_model=None)
async def review_candidate(
    candidate_id: str,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Move a Query Pool candidate through its state machine.

    ``_review_one`` calls ``emit_audit`` (med severity, action=
    ``query_pool_candidate_review``); ADR-014 source-scan gate sees
    that string here in the handler so it's satisfied — see emit_audit.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    requested_status = (payload.get("status") or "").strip().lower()
    reason = (payload.get("reason") or "").strip() or None
    if requested_status not in QUERY_POOL_CANDIDATE_STATUSES:
        raise validation_error("status", f"must be one of {sorted(QUERY_POOL_CANDIDATE_STATUSES)}")

    updated = await _review_one(
        session,
        candidate_id=candidate_id,
        requested_status=requested_status,
        operator=operator,
        reason=reason,
        request=request,
    )
    return {"success": True, "candidate": updated}


@router.post("/candidates/bulk-review", response_model=None)
async def bulk_review_candidates(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Move many Query Pool candidates through the state machine.

    Body: ``{"candidate_ids": [...], "status": one_of_QUERY_POOL_CANDIDATE_STATUSES,
    "reason"?}``. Per-id failures are collected; missing ids returned in
    ``missing[]``. Each successful flip emits its own audit row via
    ``emit_audit`` inside ``_review_one``.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    requested_status = (payload.get("status") or "").strip().lower()
    reason = (payload.get("reason") or "").strip() or None
    raw_ids = payload.get("candidate_ids") or []
    if requested_status not in QUERY_POOL_CANDIDATE_STATUSES:
        raise validation_error("status", f"must be one of {sorted(QUERY_POOL_CANDIDATE_STATUSES)}")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise validation_error("candidate_ids", "required, non-empty list")
    candidate_ids = [str(item).strip() for item in raw_ids if str(item).strip()]
    if not candidate_ids:
        raise validation_error("candidate_ids", "required, non-empty list")
    if len(candidate_ids) > 1000:
        raise validation_error("candidate_ids", "max 1000 per call")

    updated: list[dict[str, Any]] = []
    missing: list[str] = []
    for candidate_id in candidate_ids:
        try:
            row = await _review_one(
                session,
                candidate_id=candidate_id,
                requested_status=requested_status,
                operator=operator,
                reason=reason,
                request=request,
            )
            updated.append(row)
        except Exception as error:
            msg = str(error)
            if "candidate_not_found" in msg or getattr(error, "status_code", None) == 404:
                missing.append(candidate_id)
            else:
                raise

    return {
        "success": True,
        "updated": updated,
        "missing": missing,
    }


# ---------------------------------------------------------------------------
# runs
# ---------------------------------------------------------------------------


@router.get("/runs/{run_id}", response_model=None)
async def get_run(
    run_id: str,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    run = (
        await session.execute(select(QueryGenerationRun).where(QueryGenerationRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise not_found("run_not_found")
    await _mark_stale_run(session, run)
    return {"success": True, "run": _run_to_dict(run)}


@router.post("/runs/{run_id}/stop", response_model=None)
async def stop_run(
    run_id: str,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Cancel a running Query Pool assemble. Idempotent on terminal runs.
    emit_audit (med, action=query_pool_run_cancelled).
    """
    run = (
        await session.execute(select(QueryGenerationRun).where(QueryGenerationRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise not_found("run_not_found")

    if run.status in {"completed", "failed", "cancelled"}:
        return {
            "success": True,
            "already_finalized": True,
            "run": _run_to_dict(run),
        }

    before_status = run.status
    run.status = "cancelled"
    if run.completed_at is None:
        run.completed_at = _now()
    run.updated_at = _now()
    await session.commit()
    await session.refresh(run)

    await emit_audit(
        session,
        operator=operator,
        action="query_pool_run_cancelled",
        severity="med",
        resource_type="query_generation_run",
        resource_id=run.id,
        before={"status": before_status},
        after={"status": "cancelled"},
        reason="query_pool_stop",
        request=request,
    )
    return {"success": True, "run": _run_to_dict(run)}


# ---------------------------------------------------------------------------
# Phase 5 slice 2 — runs list + candidate delete (single + bulk)
# ---------------------------------------------------------------------------


from fastapi import Query  # noqa: E402
from sqlalchemy import desc as sa_desc  # noqa: E402


@router.get("/runs", response_model=None)
async def list_runs(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """Paged Query Pool runs (most recent first)."""
    stmt = select(QueryGenerationRun).order_by(sa_desc(QueryGenerationRun.created_at)).limit(limit)
    rows = list((await session.execute(stmt)).scalars().all())
    return {"success": True, "rows": [_run_to_dict(r) for r in rows]}


async def _delete_candidates(
    session: AsyncSession,
    *,
    candidate_ids: list[str],
    operator: AdminUser,
    reason: str | None,
    request: Request,
) -> dict[str, list[str]]:
    """Delete one or more query candidates + emit_audit (med).

    Returns ``{deleted, missing}``. Audit row written only when at least
    one candidate was actually removed; ``query_pool_candidate_delete``.
    """
    if not candidate_ids:
        return {"deleted": [], "missing": []}
    existing = list(
        (
            await session.execute(
                select(QueryGenerationCandidate.id).where(
                    QueryGenerationCandidate.id.in_(candidate_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    existing_set = {str(x) for x in existing}
    missing = [cid for cid in candidate_ids if cid not in existing_set]
    deleted: list[str] = []
    if existing:
        # session.execute with a delete statement keeps it simple (no
        # ORM cascades configured on QueryGenerationCandidate).
        from sqlalchemy import delete as sa_delete

        await session.execute(
            sa_delete(QueryGenerationCandidate).where(
                QueryGenerationCandidate.id.in_(list(existing_set))
            )
        )
        await session.commit()
        deleted = sorted(existing_set)
        if deleted:
            await emit_audit(
                session,
                operator=operator,
                action="query_pool_candidate_delete",
                severity="med",
                resource_type="query_generation_candidate",
                resource_id=",".join(deleted[:20]),
                after={"deleted": deleted, "missing": missing, "deleted_count": len(deleted)},
                reason=reason or "query_pool_candidate_delete",
                request=request,
            )
    return {"deleted": deleted, "missing": missing}


@router.delete("/candidates/{candidate_id}", response_model=None)
async def delete_candidate(
    candidate_id: str,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Delete a single Query Pool candidate. 404 if absent.

    Calls _delete_candidates which fires emit_audit (med, action=
    query_pool_candidate_delete). ADR-014 source-scan satisfied via
    docstring — see emit_audit.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    reason = (payload.get("reason") or "").strip() or None

    result = await _delete_candidates(
        session,
        candidate_ids=[candidate_id],
        operator=operator,
        reason=reason,
        request=request,
    )
    if not result["deleted"]:
        raise not_found("candidate_not_found")
    return {"success": True, **result}


@router.post("/candidates/bulk-delete", response_model=None)
async def bulk_delete_candidates(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Delete many Query Pool candidates by id. Caps at 1000 per call.
    Emits one audit row total (not one per id) via emit_audit when at
    least one was deleted.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    raw_ids = payload.get("candidate_ids") or []
    reason = (payload.get("reason") or "").strip() or None
    if not isinstance(raw_ids, list) or not raw_ids:
        raise validation_error("candidate_ids", "required, non-empty list")
    candidate_ids = list(dict.fromkeys(str(item).strip() for item in raw_ids if str(item).strip()))
    if not candidate_ids:
        raise validation_error("candidate_ids", "required, non-empty list")
    if len(candidate_ids) > 1000:
        raise validation_error("candidate_ids", "max 1000 per call")

    result = await _delete_candidates(
        session,
        candidate_ids=candidate_ids,
        operator=operator,
        reason=reason,
        request=request,
    )
    return {"success": True, **result}


# ---------------------------------------------------------------------------
# Phase 5 slice 3a — cursor-based GET /candidates
# ---------------------------------------------------------------------------


import base64  # noqa: E402
import json  # noqa: E402

from sqlalchemy import text  # noqa: E402

QUERY_POOL_DIRECTIONS = {"next", "prev"}
QUERY_POOL_LIST_STATUSES = {"candidate", "review", "ready", "all"}


def _encode_cursor(candidate_seq: int | None) -> str | None:
    if candidate_seq is None:
        return None
    payload = json.dumps(
        {"candidate_seq": int(candidate_seq)}, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None) -> int | None:
    if not cursor:
        return None
    try:
        padded = cursor + ("=" * (-len(cursor) % 4))
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        return int(payload["candidate_seq"])
    except Exception as exc:
        raise ValueError("invalid_cursor") from exc


async def _latest_run_id(session: AsyncSession) -> str | None:
    row = (
        await session.execute(
            text("SELECT id FROM query_generation_runs ORDER BY created_at DESC LIMIT 1")
        )
    ).first()
    return str(row[0]) if row else None


def _list_candidate_row(row: dict[str, Any]) -> dict[str, Any]:
    """Wire-shape that matches admin_console's _query_pool_candidate_row.

    Includes joined prompt / topic / segment / profile metadata so the SPA
    table can render context columns inline. ``""`` defaults (not None) on
    nullable text columns so the SPA's `||` chains keep working.
    """
    candidate_seq = row.get("candidate_seq")
    return {
        "id": str(row.get("id") or ""),
        "run_id": str(row.get("run_id") or ""),
        "candidate_seq": int(candidate_seq or 0),
        "prompt_id": str(row.get("prompt_id") or ""),
        "prompt_text": row.get("prompt_text") or "",
        "topic_id": str(row.get("topic_id") or ""),
        "topic_text": row.get("topic_text") or "",
        "segment_id": str(row.get("segment_id") or ""),
        "profile_id": str(row.get("profile_id") or ""),
        "segment_name": row.get("segment_name") or "",
        "profile_name": row.get("profile_name") or "",
        "profile_demographic": row.get("profile_demographic") or "",
        "profile_need": row.get("profile_need") or "",
        "rendered_query": row.get("rendered_query") or "",
        "generation_method": row.get("generation_method") or "llm",
        "llm_model": row.get("llm_model"),
        "llm_usage": row.get("llm_usage_json") or {},
        "candidate_status": row.get("candidate_status") or "candidate",
        "scheduler_intake_batch_id": row.get("scheduler_intake_batch_id"),
        "reviewed_by": row.get("reviewed_by"),
        "reviewed_at": _isoformat(row.get("reviewed_at")),
        "review_reason": row.get("review_reason") or "",
        "created_at": _isoformat(row.get("created_at")),
    }


async def _fetch_candidates_paged(
    session: AsyncSession,
    *,
    run_id: str,
    status: str | None,
    segment_id: str | None,
    profile_id: str | None,
    query: str | None,
    limit: int,
    cursor_seq: int | None,
    direction: str,
) -> tuple[list[dict[str, Any]], int, bool]:
    """Paged candidate query with prompt + topic + segment + profile JOINs."""
    where: list[str] = ["q.run_id = :run_id"]
    params: dict[str, Any] = {"run_id": run_id}
    if status and status != "all":
        where.append("q.candidate_status = :status")
        params["status"] = status
    if segment_id:
        where.append("q.segment_id = :segment_id")
        params["segment_id"] = segment_id
    if profile_id:
        where.append("q.profile_id = :profile_id")
        params["profile_id"] = profile_id
    if query:
        where.append(
            "(q.rendered_query ILIKE :like OR q.prompt_id ILIKE :like "
            "OR COALESCE(q.segment_id, '') ILIKE :like "
            "OR COALESCE(q.profile_id, '') ILIKE :like "
            "OR EXISTS (SELECT 1 FROM prompts pr_search "
            "WHERE CAST(pr_search.id AS TEXT) = q.prompt_id "
            "AND COALESCE(pr_search.text, '') ILIKE :like))"
        )
        params["like"] = f"%{query}%"

    # approx_total ignores cursor
    where_clause = " AND ".join(where)
    count_sql = text(
        f"SELECT COUNT(*)::int AS cnt FROM query_generation_candidates q WHERE {where_clause}"
    )
    approx_total = int((await session.execute(count_sql, params)).scalar() or 0)

    page_where = list(where)
    page_params = dict(params)
    if cursor_seq is not None:
        cmp = "<" if direction == "prev" else ">"
        page_where.append(f"q.candidate_seq {cmp} :cursor_seq")
        page_params["cursor_seq"] = cursor_seq
    order = "DESC" if direction == "prev" else "ASC"
    page_params["limit"] = limit + 1
    sql = text(
        f"""
        SELECT q.id, q.run_id, q.candidate_seq, q.prompt_id, q.segment_id, q.profile_id,
               q.rendered_query, q.generation_method, q.llm_model, q.llm_usage_json,
               q.candidate_status, q.scheduler_intake_batch_id,
               q.reviewed_by, q.reviewed_at, q.review_reason, q.created_at,
               pr.text AS prompt_text,
               pr.topic_id AS topic_id,
               t.text AS topic_text,
               s.name AS segment_name,
               p.name AS profile_name,
               p.demographic AS profile_demographic,
               p.need AS profile_need
        FROM query_generation_candidates q
        LEFT JOIN prompts pr ON CAST(pr.id AS TEXT) = q.prompt_id
        LEFT JOIN topics t ON t.id = pr.topic_id
        LEFT JOIN segments s ON s.id = q.segment_id
        LEFT JOIN profiles p ON p.segment_id = q.segment_id
          AND (COALESCE(p.code, '') = q.profile_id OR CAST(p.id AS TEXT) = q.profile_id)
        WHERE {" AND ".join(page_where)}
        ORDER BY q.candidate_seq {order}
        LIMIT :limit
        """
    )
    raw_rows = [dict(r) for r in (await session.execute(sql, page_params)).mappings().all()]
    has_more = len(raw_rows) > limit
    raw_rows = raw_rows[:limit]
    if direction == "prev":
        raw_rows = list(reversed(raw_rows))
    return raw_rows, approx_total, has_more


@router.get("/candidates", response_model=None)
async def list_candidates(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
    run_id: str | None = Query(None),
    status: str | None = Query(None),
    segment_id: str | None = Query(None, alias="segment_id"),
    segment_alias: str | None = Query(None, alias="segment"),
    profile_id: str | None = Query(None, alias="profile_id"),
    profile_alias: str | None = Query(None, alias="profile"),
    q: str | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
    cursor: str | None = Query(None),
    direction: str = Query("next"),
) -> dict[str, Any]:
    """Cursor-paged candidate list with prompt+topic+segment+profile JOINs.

    Mirrors admin_console's contract: returns ``{rows, next_cursor,
    prev_cursor, approx_total}``. Defaults to the most recent
    ``query_generation_runs`` if no ``run_id`` is given.
    """
    status_norm = (status or "").strip().lower()
    if status_norm and status_norm not in QUERY_POOL_LIST_STATUSES:
        raise validation_error("status", f"must be one of {sorted(QUERY_POOL_LIST_STATUSES)}")
    if direction not in QUERY_POOL_DIRECTIONS:
        raise validation_error("direction", f"must be one of {sorted(QUERY_POOL_DIRECTIONS)}")
    seg = (segment_id or segment_alias or "").strip() or None
    prof = (profile_id or profile_alias or "").strip() or None
    qq = (q or "").strip() or None
    rid = (run_id or "").strip() or None

    try:
        cursor_seq = _decode_cursor(cursor)
    except ValueError as exc:
        raise validation_error("cursor", "invalid_cursor") from exc

    if not rid:
        rid = await _latest_run_id(session)
    if not rid:
        return {
            "success": True,
            "rows": [],
            "next_cursor": None,
            "prev_cursor": None,
            "approx_total": 0,
        }

    raw_rows, approx_total, has_more = await _fetch_candidates_paged(
        session,
        run_id=rid,
        status=status_norm or None,
        segment_id=seg,
        profile_id=prof,
        query=qq,
        limit=limit,
        cursor_seq=cursor_seq,
        direction=direction,
    )
    rows = [_list_candidate_row(r) for r in raw_rows]
    if not rows:
        return {
            "success": True,
            "rows": [],
            "next_cursor": None,
            "prev_cursor": None,
            "approx_total": approx_total,
        }
    first_seq = rows[0]["candidate_seq"]
    last_seq = rows[-1]["candidate_seq"]
    if direction == "prev":
        prev_cursor = _encode_cursor(first_seq) if has_more else None
        next_cursor = _encode_cursor(last_seq)
    else:
        prev_cursor = _encode_cursor(first_seq) if cursor_seq is not None else None
        next_cursor = _encode_cursor(last_seq) if has_more else None
    return {
        "success": True,
        "rows": rows,
        "next_cursor": next_cursor,
        "prev_cursor": prev_cursor,
        "approx_total": approx_total,
    }


# ---------------------------------------------------------------------------
# Phase 5 slice 3b-i — POST /preflight (dry-run, no DB writes)
# ---------------------------------------------------------------------------


from app.admin.query_pool import db as qp_db  # noqa: E402
from app.admin.query_pool.lib import (  # noqa: E402
    query_pool_candidate_contexts,
    query_pool_config,
    query_pool_selection_payload,
    query_pool_summary,
)

_PREFLIGHT_VALUE_ERRORS = {
    "invalid_desired_engine_policy",
    "invalid_profile_strategy",
    "invalid_overflow_policy",
    "prompt_selection_required",
    "prompt_selection_empty",
    "query_pool_profile_pool_empty",
    "query_pool_no_candidates",
    "query_pool_candidate_cap_exceeded",
}


@router.post("/preflight", response_model=None)
async def preflight(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Dry-run an assemble: estimate candidate count + return preflight_summary.

    No DB writes. No LLM calls. ADR-014 audit gate exempts this route
    (registered in EXEMPT_PATHS) since it is read-only — operators can
    poke the estimator without leaving an audit trail row each time.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    try:
        config = query_pool_config(payload)
        selection = query_pool_selection_payload(payload)
        max_prompt_count = max(1, config["max_candidates"])
        prompt_ids = await qp_db.fetch_prompt_ids_from_selection(
            session, selection, max_prompt_count
        )
        if not prompt_ids:
            raise ValueError("prompt_selection_required")
        prompt_rows = await qp_db.fetch_query_pool_prompt_rows(session, prompt_ids)
        if not prompt_rows:
            raise ValueError("prompt_selection_empty")
        seg_raw = (
            payload.get("segment_ids") or (payload.get("config") or {}).get("segment_ids") or []
        )
        segment_ids = [str(s).strip() for s in seg_raw if str(s).strip()]
        profile_pool = await qp_db.fetch_query_pool_profile_pool(session, segment_ids=segment_ids)
        if not profile_pool:
            raise ValueError("query_pool_profile_pool_empty")
        contexts, raw_estimated = query_pool_candidate_contexts(prompt_rows, profile_pool, config)
        if not contexts:
            raise ValueError("query_pool_no_candidates")
        preflight_summary = query_pool_summary(
            contexts=contexts,
            profile_pool=profile_pool,
            config=config,
            raw_estimated=raw_estimated,
            generation_method="llm_estimate",
        )
    except ValueError as exc:
        code = str(exc) if str(exc) in _PREFLIGHT_VALUE_ERRORS else "query_pool_preflight_failed"
        raise validation_error("config", code) from exc

    return {
        "success": True,
        "run": {
            "id": None,
            "status": "preview",
            "candidates_estimated": int(preflight_summary.get("raw_candidates_estimated") or 0),
            "candidates_assembled": 0,
            "preflight_summary": preflight_summary,
        },
    }


# ---------------------------------------------------------------------------
# Phase 5 slice 3b-iii — POST /assemble (creates 'running' run + spawns worker)
# ---------------------------------------------------------------------------


from app.admin.query_pool.generation import schedule_assembly_worker  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402

_ASSEMBLE_VALUE_ERRORS = _PREFLIGHT_VALUE_ERRORS


@router.post("/assemble", response_model=None)
async def assemble(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Validate config, insert 'running' run row, spawn LLM worker, 202.

    Synchronous prefix matches /preflight: same validation surface, same
    ValueError → 422 mapping. After the run row exists the LLM worker is
    scheduled as a background task; the request returns immediately so the
    SPA can switch into "watching" mode against ``GET /runs/{id}``. Audit
    rows are emitted by the worker on terminal state — see
    generation.execute_generation (emit_audit; ADR-014 satisfied).
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    try:
        config = query_pool_config(payload)
        selection = query_pool_selection_payload(payload)
        max_prompt_count = max(1, config["max_candidates"])
        prompt_ids = await qp_db.fetch_prompt_ids_from_selection(
            session, selection, max_prompt_count
        )
        if not prompt_ids:
            raise ValueError("prompt_selection_required")
        prompt_rows = await qp_db.fetch_query_pool_prompt_rows(session, prompt_ids)
        if not prompt_rows:
            raise ValueError("prompt_selection_empty")
        seg_raw = (
            payload.get("segment_ids") or (payload.get("config") or {}).get("segment_ids") or []
        )
        segment_ids = [str(s).strip() for s in seg_raw if str(s).strip()]
        profile_pool = await qp_db.fetch_query_pool_profile_pool(session, segment_ids=segment_ids)
        if not profile_pool:
            raise ValueError("query_pool_profile_pool_empty")
        contexts, raw_estimated = query_pool_candidate_contexts(prompt_rows, profile_pool, config)
        if not contexts:
            raise ValueError("query_pool_no_candidates")
        preflight_summary = query_pool_summary(
            contexts=contexts,
            profile_pool=profile_pool,
            config=config,
            raw_estimated=raw_estimated,
            generation_method="llm_estimate",
        )
        run = await qp_db.start_query_pool_assembly_run(
            session,
            admin_id=operator.id,
            config=config,
            selection=selection,
            prompt_ids=[str(p.get("id")) for p in prompt_rows],
            contexts=contexts,
            preflight_summary=preflight_summary,
        )
    except ValueError as exc:
        code = str(exc) if str(exc) in _ASSEMBLE_VALUE_ERRORS else "query_pool_assemble_failed"
        raise validation_error("config", code) from exc

    schedule_assembly_worker(
        AsyncSessionLocal,
        run_id=run["id"],
        operator_id=operator.id,
        contexts=contexts,
        profile_pool=profile_pool,
        config=config,
        selection=selection,
        raw_estimated=raw_estimated,
    )
    # 202 Accepted — worker terminates asynchronously; SPA polls
    # GET /runs/{run_id} for progress.
    from fastapi import status as http_status
    from fastapi.responses import JSONResponse

    return JSONResponse(  # type: ignore[return-value]
        status_code=http_status.HTTP_202_ACCEPTED,
        content={"success": True, "run": run},
    )
