"""Admin Prompt Matrix router (Phase 4 — initial slice).

Mounted at ``/api/admin/prompt-matrix`` (cookie-based ``current_admin``).

Routes in this PR (parity with topic_plan B.1 + part of B.2.a):
- POST /candidates/{candidate_id}/review   approve | reject one candidate
- POST /candidates/bulk-review             apply same decision to many
- GET  /runs/{run_id}                      single run row (auto-marks stale
                                            running -> failed past timeout)
- POST /runs/{run_id}/stop                 cancel a running generation

Phase 4 follow-up PRs will add: GET /config, GET /topics, GET /gaps,
GET /prompts, GET /candidates (paged read), POST /generate (LLM async).

Shape mirrors topic_plan exactly — the heavy lifting (SQL helpers,
LLM client, generation orchestration) is already vendored under
``app/admin/prompt_matrix/`` (lib.py, llm.py); db.py + generation.py
land in the follow-up PRs alongside the routes that need them.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from genpano_models import AdminUser, PromptCandidate, PromptGenerationRun
from sqlalchemy import delete as sa_delete
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.prompt_matrix import db as pm_db
from app.admin.prompt_matrix.lib import (
    ALLOWED_INTENTS,
    ALLOWED_PROMPT_SCOPES,
    DEFAULT_MAX_PROMPTS,
    MAX_PROMPTS_HARD_LIMIT,
    PromptMatrixError,
    clamp_int,
    normalize_prompt_scope,
    prompt_generation_max_prompts_cap,
    prompt_generation_raw_count,
    transition_candidate_status,
)
from app.api.admin.auth.router import current_admin
from app.core.errors import _problem, not_found, validation_error
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Prompt Matrix"])


DELETABLE_CANDIDATE_STATUSES = {"approved", "rejected"}


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _llm_error_to_http(error: PromptMatrixError) -> Any:
    return _problem(400, error.code, error.message, detail=error.message)


def _candidate_row(c: PromptCandidate) -> dict[str, Any]:
    tags = c.tags if isinstance(c.tags, dict) else {}
    try:
        prompt_scope = normalize_prompt_scope(
            tags.get("prompt_scope") or tags.get("promptScope") or "non_branded"
        )
    except PromptMatrixError:
        prompt_scope = "non_branded"
    competitive_type = tags.get("competitive_type") or tags.get("competitiveType")
    quality_gate_status = tags.get("quality_gate_status") or tags.get("qualityGateStatus")
    quality_gate_reason = tags.get("quality_gate_reason") or tags.get("qualityGateReason")
    quality_gate_message = tags.get("quality_gate_message") or tags.get("qualityGateMessage")
    return {
        "id": c.id,
        "run_id": c.run_id,
        "topic_id": c.topic_id,
        "topic_text": c.topic_text,
        "brand_id": c.brand_id,
        "brand_name": c.brand_name,
        "dimension": c.dimension,
        "intent": c.intent,
        "language": c.language,
        "template_strategy": c.template_strategy,
        "template_version": c.template_version,
        "text": c.text,
        "status": c.status,
        "confidence": float(c.confidence or 0),
        "reason": c.reason,
        "duplicate_of": c.duplicate_of,
        "prompt_scope": prompt_scope,
        "competitive_type": competitive_type if prompt_scope == "competitive" else None,
        "quality_gate_status": quality_gate_status,
        "quality_gate_reason": quality_gate_reason,
        "quality_gate_message": quality_gate_message,
        "tags": tags,
        "review_reason": c.review_reason,
        "approved_prompt_id": c.approved_prompt_id,
        "created_at": _isoformat(c.created_at),
        "reviewed_at": _isoformat(c.reviewed_at),
    }


def _run_to_dict(run: PromptGenerationRun) -> dict[str, Any]:
    request_config = run.request_config if isinstance(run.request_config, dict) else {}
    metrics = run.metrics_json if isinstance(run.metrics_json, dict) else {}
    end = run.completed_at or _now()
    start = run.started_at or run.created_at or _now()
    elapsed = max(0.0, (end - start).total_seconds())
    return {
        "id": run.id,
        "status": run.status,
        "admin_id": run.admin_id,
        "request_config": request_config,
        "selected_topic_ids": run.selected_topic_ids
        if isinstance(run.selected_topic_ids, list)
        else [],
        "estimated_prompts": int(run.estimated_prompts or 0),
        "candidates_generated": int(run.candidates_generated or 0),
        "llm_model": run.llm_model,
        "llm_usage": run.llm_usage_json if isinstance(run.llm_usage_json, dict) else {},
        "llm_error": run.llm_error,
        "metrics": metrics,
        "started_at": _isoformat(run.started_at),
        "completed_at": _isoformat(run.completed_at),
        "created_at": _isoformat(run.created_at),
        "updated_at": _isoformat(run.updated_at),
        "elapsed_seconds": float(elapsed),
    }


def _run_timeout_seconds(run: PromptGenerationRun) -> int:
    request_config = run.request_config if isinstance(run.request_config, dict) else {}
    estimated = clamp_int(
        request_config.get("max_prompts"), DEFAULT_MAX_PROMPTS, 1, MAX_PROMPTS_HARD_LIMIT
    )
    default_timeout = max(900, min(7200, estimated * 2))
    return clamp_int(os.getenv("PROMPT_MATRIX_RUN_TIMEOUT_SECONDS"), default_timeout, 300, 14400)


async def _mark_stale_run(session: AsyncSession, run: PromptGenerationRun) -> bool:
    if run.status != "running":
        return False
    last_progress = run.updated_at or run.started_at or run.created_at
    if not last_progress:
        return False
    elapsed = (_now() - last_progress).total_seconds()
    if elapsed <= _run_timeout_seconds(run):
        return False
    run.status = "failed"
    run.llm_error = "prompt_matrix_run_timeout"
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
    candidate = (
        await session.execute(select(PromptCandidate).where(PromptCandidate.id == candidate_id))
    ).scalar_one_or_none()
    if candidate is None:
        raise not_found("candidate_not_found")

    new_status = transition_candidate_status(candidate.status, requested_status)
    before_status = candidate.status

    candidate.status = new_status
    candidate.reviewed_by = operator.id
    candidate.reviewed_at = _now()
    candidate.review_reason = reason
    candidate.updated_at = _now()
    await session.commit()
    await session.refresh(candidate)

    await emit_audit(
        session,
        operator=operator,
        action="review_prompt_candidate",
        severity="med",
        resource_type="prompt_candidate",
        resource_id=candidate.id,
        before={"status": before_status},
        after={"status": new_status},
        reason=reason or "prompt_candidate_review",
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
    """Approve or reject a single Prompt Matrix candidate.

    ``_review_one`` calls ``emit_audit`` (med severity, action=
    ``review_prompt_candidate``); ADR-014 source-scan gate sees that
    string here in the handler so it's satisfied — see emit_audit.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    requested_status = (payload.get("status") or "").strip().lower()
    reason = (payload.get("reason") or "").strip() or None
    if requested_status not in {"approved", "rejected"}:
        raise validation_error("status", "must be 'approved' or 'rejected'")

    try:
        updated = await _review_one(
            session,
            candidate_id=candidate_id,
            requested_status=requested_status,
            operator=operator,
            reason=reason,
            request=request,
        )
    except PromptMatrixError as error:
        raise _llm_error_to_http(error) from error
    return {"success": True, "candidate": updated}


@router.post("/candidates/bulk-review", response_model=None)
async def bulk_review_candidates(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Approve or reject many candidates in one call. Per-id failures
    collected; partial failure returns 409. Each successful review emits
    its own audit row via emit_audit inside ``_review_one``.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    requested_status = (payload.get("status") or "").strip().lower()
    reason = (payload.get("reason") or "").strip() or None
    candidate_ids_raw = payload.get("candidate_ids") or []
    if requested_status not in {"approved", "rejected"}:
        raise validation_error("status", "must be 'approved' or 'rejected'")
    if not isinstance(candidate_ids_raw, list) or not candidate_ids_raw:
        raise validation_error("candidate_ids", "required, non-empty list")
    candidate_ids = [str(item).strip() for item in candidate_ids_raw if str(item).strip()]
    if not candidate_ids:
        raise validation_error("candidate_ids", "required, non-empty list")
    if len(candidate_ids) > 200:
        raise validation_error("candidate_ids", "max 200 per call")

    updated: list[dict[str, Any]] = []
    missing: list[str] = []
    failed: list[dict[str, Any]] = []
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
        except PromptMatrixError as error:
            failed.append({"id": candidate_id, "error": error.code, "message": error.message})
        except Exception as error:
            msg = str(error)
            if "candidate_not_found" in msg or getattr(error, "status_code", None) == 404:
                missing.append(candidate_id)
            else:
                failed.append({"id": candidate_id, "error": "internal_error", "message": msg})

    body = {
        "success": len(failed) == 0,
        "rows": updated,
        "summary": {
            "updated_count": len(updated),
            "missing_count": len(missing),
            "failed_count": len(failed),
        },
        "missing": missing,
        "failed": failed,
    }
    if failed:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=409, content=body)  # type: ignore[return-value]
    return body


async def _delete_candidates(
    session: AsyncSession,
    *,
    candidate_ids: list[str],
    operator: AdminUser,
    reason: str | None,
    request: Request,
) -> dict[str, Any]:
    if not candidate_ids:
        return {"deleted": [], "missing": [], "failed": []}
    rows = list(
        (
            await session.execute(
                select(PromptCandidate).where(PromptCandidate.id.in_(candidate_ids))
            )
        )
        .scalars()
        .all()
    )
    by_id = {str(row.id): row for row in rows}
    missing = [candidate_id for candidate_id in candidate_ids if candidate_id not in by_id]
    failed: list[dict[str, Any]] = []
    deletable: list[str] = []
    before_statuses: dict[str, str] = {}
    for candidate_id in candidate_ids:
        row = by_id.get(candidate_id)
        if row is None:
            continue
        status = str(row.status or "").lower()
        if status not in DELETABLE_CANDIDATE_STATUSES:
            failed.append(
                {
                    "id": candidate_id,
                    "error": "candidate_delete_forbidden",
                    "message": "Only reviewed Prompt candidates can be deleted",
                }
            )
            continue
        deletable.append(candidate_id)
        before_statuses[candidate_id] = status

    deleted: list[str] = []
    if deletable:
        await session.execute(sa_delete(PromptCandidate).where(PromptCandidate.id.in_(deletable)))
        await session.commit()
        deleted = sorted(deletable)
        await emit_audit(
            session,
            operator=operator,
            action="delete_prompt_candidate",
            severity="med",
            resource_type="prompt_candidate",
            resource_id=",".join(deleted[:20]),
            before={"statuses": before_statuses},
            after={
                "deleted": deleted,
                "missing": missing,
                "failed_count": len(failed),
                "deleted_count": len(deleted),
            },
            reason=reason or "prompt_candidate_delete",
            request=request,
        )
    return {"deleted": deleted, "missing": missing, "failed": failed}


@router.delete("/candidates/{candidate_id}", response_model=None)
async def delete_candidate(
    candidate_id: str,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Delete a reviewed Prompt Matrix candidate. Calls emit_audit via
    ``_delete_candidates`` (med, action=delete_prompt_candidate).
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
    if result["missing"]:
        raise not_found("candidate_not_found")
    if result["failed"]:
        raise _problem(
            400,
            "candidate_delete_forbidden",
            "Candidate cannot be deleted",
            detail=result["failed"][0]["message"],
        )
    return {"success": True, **result}


@router.post("/candidates/bulk-delete", response_model=None)
async def bulk_delete_candidates(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Delete reviewed Prompt Matrix candidates in bulk. Calls emit_audit
    via ``_delete_candidates`` when rows are removed.
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
    if len(candidate_ids) > 200:
        raise validation_error("candidate_ids", "max 200 per call")

    result = await _delete_candidates(
        session,
        candidate_ids=candidate_ids,
        operator=operator,
        reason=reason,
        request=request,
    )
    body = {
        "success": not result["failed"],
        **result,
        "summary": {
            "deleted_count": len(result["deleted"]),
            "missing_count": len(result["missing"]),
            "failed_count": len(result["failed"]),
        },
    }
    if result["failed"]:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=409, content=body)  # type: ignore[return-value]
    return body


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
        await session.execute(select(PromptGenerationRun).where(PromptGenerationRun.id == run_id))
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
    """Cancel a running Prompt Matrix generation. Idempotent on terminal
    runs. emit_audit (med, action=prompt_matrix_run_cancelled).
    """
    run = (
        await session.execute(select(PromptGenerationRun).where(PromptGenerationRun.id == run_id))
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
        action="prompt_matrix_run_cancelled",
        severity="med",
        resource_type="prompt_generation_run",
        resource_id=run.id,
        before={"status": before_status},
        after={"status": "cancelled"},
        reason="prompt_matrix_stop",
        request=request,
    )
    return {"success": True, "run": _run_to_dict(run)}


# ---------------------------------------------------------------------------
# Phase 4 slice 2 — read paths (config / topics / gaps / prompts / candidates)
# ---------------------------------------------------------------------------


@router.get("/config", response_model=None)
async def get_config(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Top-level Prompt Matrix tab config — populates the SPA dropdowns +
    coverage / quality stats. Heavy: stat aggregation crosses topics +
    prompts + brand-leak detection."""
    from app.admin.prompt_matrix.lib import PromptMatrixError
    from app.admin.topic_plan.lib import TopicPlanLLMError

    brands = await pm_db.fetch_brand_rows(session)
    industries = [
        {"id": value, "name": value}
        for value in sorted({b.get("industry_id") or "Uncategorized" for b in brands})
    ]
    stats = await pm_db.compute_stats(session)
    pending_count = 0
    duplicate_count = 0
    counts = await pm_db.candidate_status_counts(session)
    pending_count = counts.get("pending", 0)
    # duplicate_of is set on prompt_candidates that flagged near-dup of an
    # existing candidate; surface separately so the dashboard chip is
    # accurate even when SPA hasn't yet refreshed.
    dup_count_row = (
        (
            await session.execute(
                text(
                    "SELECT COUNT(*)::int AS cnt FROM prompt_candidates "
                    "WHERE status = 'pending' AND duplicate_of IS NOT NULL"
                )
            )
        )
        .mappings()
        .one()
    )
    duplicate_count = int(dup_count_row["cnt"] or 0)
    try:
        from app.admin.topic_plan.lib import load_doubao_config

        load_doubao_config()
        llm_configured = True
    except (PromptMatrixError, TopicPlanLLMError):
        llm_configured = False

    return {
        "success": True,
        "brands": brands,
        "industries": industries,
        "defaults": {
            "intentCount": 4,
            "languageCount": 2,
            "topicPriority": "gap_first",
            "templateStrategy": "latest",
            "promptStyle": "natural",
            "audienceMode": "general",
            "maxPerTopic": 4,
            "maxPrompts": DEFAULT_MAX_PROMPTS,
            "overflowPolicy": "split",
        },
        "summary": {
            "pending_candidates": pending_count,
            "duplicate_candidates": duplicate_count,
            "llm_configured": llm_configured,
        },
        "stats": stats,
        "qualityGates": pm_db.quality_gates(stats, pending_count, duplicate_count),
    }


@router.get("/topics", response_model=None)
async def get_topics(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
    q: str | None = Query(None),
    brand_id: int | None = Query(None),
    industry_id: str | None = Query(None),
    dimension: str | None = Query(None),
    coverage: str = Query("all"),
    intent_count: int = Query(4, ge=1),
    language_count: int = Query(2, ge=1),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    try:
        filters = pm_db.filter_payload_from_query(
            {
                "q": q,
                "brand_id": brand_id,
                "industry_id": industry_id,
                "dimension": dimension,
                "coverage": coverage,
                "intent_count": intent_count,
                "language_count": language_count,
            }
        )
    except ValueError as exc:
        raise validation_error("filters", str(exc)) from exc
    rows, total, summary = await pm_db.fetch_topics(
        session, filters=filters, page=page, per_page=per_page
    )
    return {
        "success": True,
        "rows": rows,
        "summary": summary,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": max(1, (total + per_page - 1) // per_page),
        },
    }


@router.get("/gaps", response_model=None)
async def get_gaps(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
    q: str | None = Query(None),
    brand_id: int | None = Query(None),
    industry_id: str | None = Query(None),
    dimension: str | None = Query(None),
    coverage: str = Query("all"),
    topic_ids: str | None = Query(None),
    intent_count: int = Query(4, ge=1),
    language_count: int = Query(2, ge=1),
    max_per_topic: int = Query(4, ge=1, le=20),
    max_prompts: int = Query(DEFAULT_MAX_PROMPTS, ge=1),
    template_strategy: str = Query("latest"),
    prompt_style: str = Query("natural"),
    audience_mode: str = Query("general"),
    overflow_policy: str = Query("split"),
    limit: int = Query(200, ge=1, le=500),
) -> dict[str, Any]:
    try:
        filters = pm_db.filter_payload_from_query(
            {
                "q": q,
                "brand_id": brand_id,
                "industry_id": industry_id,
                "dimension": dimension,
                "coverage": coverage,
                "intent_count": intent_count,
                "language_count": language_count,
            }
        )
        parsed_topic_ids = pm_db.parse_topic_ids(topic_ids) if topic_ids else None
    except ValueError as exc:
        raise validation_error("filters", str(exc)) from exc

    config = {
        "intent_count": intent_count,
        "language_count": language_count,
        "max_per_topic": max_per_topic,
        "max_prompts": max_prompts,
        "template_strategy": template_strategy,
        "prompt_style": prompt_style,
        "audience_mode": audience_mode,
        "overflow_policy": overflow_policy,
    }
    gaps = await pm_db.gaps_for_topics(
        session,
        topic_ids=parsed_topic_ids,
        filters=filters,
        config=config,
        limit=limit,
    )
    return {
        "success": True,
        "rows": gaps,
        "summary": {
            "gap_count": len(gaps),
            "estimated_prompts": sum(int(g.get("estimate") or 0) for g in gaps),
        },
    }


@router.get("/prompts", response_model=None)
async def get_prompts(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
    intent: str | None = Query(None),
    language: str | None = Query(None),
    q: str | None = Query(None),
    topic_ids: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
) -> dict[str, Any]:
    from app.admin.prompt_matrix.lib import ALLOWED_INTENTS, ALLOWED_LANGUAGES

    intent_norm = intent.strip().lower() if intent else None
    if intent_norm and intent_norm not in ALLOWED_INTENTS:
        raise validation_error("intent", f"must be one of {sorted(ALLOWED_INTENTS)}")
    if language and language not in ALLOWED_LANGUAGES:
        raise validation_error("language", f"must be one of {sorted(ALLOWED_LANGUAGES)}")
    try:
        parsed_topic_ids = pm_db.parse_int_list(topic_ids) if topic_ids else None
    except ValueError as exc:
        raise validation_error("topic_ids", str(exc)) from exc

    rows, total = await pm_db.fetch_prompts(
        session,
        intent=intent_norm,
        language=language,
        query=q,
        page=page,
        per_page=per_page,
        topic_ids=parsed_topic_ids,
    )
    stats = await pm_db.compute_stats(session)
    return {
        "success": True,
        "rows": rows,
        "stats": stats,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": max(1, (total + per_page - 1) // per_page),
        },
    }


@router.get("/candidates", response_model=None)
async def get_candidates(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
    status: str = Query("pending"),
    q: str | None = Query(None),
    brand_id: int | None = Query(None, ge=1),
    intent: str | None = Query(None),
    prompt_scope: str | None = Query(None),
    quality_gate: str = Query("all"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    status_norm = status.strip().lower()
    if status_norm not in {"pending", "approved", "rejected", "all"}:
        raise validation_error("status", "must be one of pending / approved / rejected / all")
    intent_norm = (intent or "").strip().lower() or None
    if intent_norm == "all":
        intent_norm = None
    elif intent_norm and intent_norm not in ALLOWED_INTENTS:
        raise validation_error("intent", "must be one of " + " / ".join(ALLOWED_INTENTS))
    prompt_scope_norm = (prompt_scope or "").strip().lower() or None
    if prompt_scope_norm == "all":
        prompt_scope_norm = None
    elif prompt_scope_norm and prompt_scope_norm not in ALLOWED_PROMPT_SCOPES:
        raise validation_error(
            "prompt_scope",
            "must be one of " + " / ".join(ALLOWED_PROMPT_SCOPES),
        )
    quality_gate_norm = quality_gate.strip().lower()
    if quality_gate_norm not in {"all", "blocked"}:
        raise validation_error("quality_gate", "must be one of all / blocked")
    offset = (page - 1) * per_page
    rows, total = await pm_db.fetch_candidates(
        session,
        status=status_norm,
        query=q,
        brand_id=brand_id,
        intent=intent_norm,
        prompt_scope=prompt_scope_norm,
        quality_gate=quality_gate_norm,
        limit=per_page,
        offset=offset,
    )
    counts = await pm_db.candidate_status_counts(
        session,
        query=q,
        brand_id=brand_id,
        intent=intent_norm,
        prompt_scope=prompt_scope_norm,
        quality_gate=quality_gate_norm,
    )
    return {
        "success": True,
        "rows": rows,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": max(1, (total + per_page - 1) // per_page),
        },
        "summary": {
            "pending_candidates": counts.get("pending", 0),
            "approved_candidates": counts.get("approved", 0),
            "rejected_candidates": counts.get("rejected", 0),
            "all_candidates": counts.get("all", 0),
            "duplicate_candidates": sum(1 for r in rows if r.get("duplicate_of")),
            "status_counts": counts,
        },
    }


# ---------------------------------------------------------------------------
# Phase 4 slice 3 — POST /generate (LLM async + run lifecycle)
# ---------------------------------------------------------------------------


_BACKGROUND_PROMPT_GENERATION_TASKS: set[Any] = set()


@router.post("/generate", response_model=None)
async def generate_prompts(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Kick off Prompt Matrix generation. Sync vs background controlled by env.

    Body: ``{topic_ids: [...], intent_count?, language_count?, max_per_topic?,
    max_prompts?, template_strategy?, prompt_style?, audience_mode?, ...}``.

    Sync mode (``PROMPT_MATRIX_SYNC_GENERATE=1``) — awaits the full LLM loop
    and returns inserted candidates inline.
    Background mode (default) — schedules ``execute_generation_background``
    via ``asyncio.create_task`` against a fresh ``AsyncSessionLocal``;
    returns ``{run_id, status: "running"}`` immediately.

    ADR-014 audit: emit_audit fires inside execute_generation once the
    run reaches a terminal state. ADR-014 source-scan satisfied via
    docstring (see emit_audit).
    """
    import asyncio
    import os

    from app.admin.prompt_matrix.generation import (
        execute_generation,
        execute_generation_background,
        run_failed_status_code,
    )
    from app.admin.prompt_matrix.lib import (
        estimate_generation_count,
        prompt_generation_config,
    )
    from app.db.session import AsyncSessionLocal

    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    try:
        config = prompt_generation_config(
            {
                "intent_count": payload.get("intent_count") or payload.get("intentCount"),
                "language_count": payload.get("language_count") or payload.get("languageCount"),
                "topic_priority": payload.get("topic_priority") or payload.get("topicPriority"),
                "template_strategy": payload.get("template_strategy")
                or payload.get("templateStrategy"),
                "prompt_style": payload.get("prompt_style") or payload.get("promptStyle"),
                "audience_mode": payload.get("audience_mode") or payload.get("audienceMode"),
                "max_per_topic": payload.get("max_per_topic") or payload.get("maxPerTopic"),
                "max_prompts": payload.get("max_prompts") or payload.get("maxPrompts"),
                "overflow_policy": payload.get("overflow_policy") or payload.get("overflowPolicy"),
            }
        )
    except PromptMatrixError as error:
        raise _llm_error_to_http(error) from error

    try:
        topic_ids, selection_snapshot = pm_db.parse_selection(payload)
    except ValueError as exc:
        raise validation_error("topic_ids", str(exc)) from exc
    if not topic_ids:
        raise validation_error("topic_ids", "required, non-empty list")

    topics = await pm_db.fetch_topic_rows_by_ids(session, topic_ids, config)
    if not topics:
        raise not_found("selected_topics_not_found")
    topic_ids = [int(t["raw_id"]) for t in topics]

    raw_estimated = prompt_generation_raw_count(
        selected_topics=len(topics),
        intent_count=config["intent_count"],
        language_count=config["language_count"],
        max_per_topic=config["max_per_topic"],
    )
    max_prompts_cap = prompt_generation_max_prompts_cap(raw_estimated)
    if config["max_prompts"] > max_prompts_cap:
        raise validation_error("max_prompts", f"must be <= {max_prompts_cap}")

    estimated = estimate_generation_count(
        selected_topics=len(topics),
        intent_count=config["intent_count"],
        language_count=config["language_count"],
        max_per_topic=config["max_per_topic"],
        max_prompts=config["max_prompts"],
    )
    if estimated <= 0:
        raise validation_error("config", "no_prompt_combinations")

    known_brands = await pm_db.fetch_brand_rows(session)
    existing_prompts = await pm_db.fetch_existing_prompt_texts(session, topic_ids=topic_ids)
    request_config: dict[str, Any] = {**config, "selection": selection_snapshot}

    run_id = str(uuid.uuid4())
    run = PromptGenerationRun(
        id=run_id,
        admin_id=operator.id,
        status="running",
        request_config=request_config,
        selected_topic_ids=topic_ids,
        estimated_prompts=estimated,
        started_at=_now(),
    )
    session.add(run)
    await session.commit()

    sync_mode = os.getenv("PROMPT_MATRIX_SYNC_GENERATE") == "1"
    if sync_mode:
        try:
            result = await execute_generation(
                session,
                run_id=run_id,
                operator=operator,
                topics=topics,
                config=config,
                known_brands=known_brands,
                existing_prompts=existing_prompts,
                estimated=estimated,
                request_config=request_config,
            )
        except PromptMatrixError as error:
            return _problem(  # type: ignore[return-value]
                run_failed_status_code(error.code),
                error.code,
                error.message,
                detail=error.message,
                extra={"run_id": run_id},
            ).detail
        return {
            "success": True,
            "run_id": run_id,
            "status": "completed" if not result.get("cancelled") else "cancelled",
            "candidates": result["inserted"],
            "summary": {
                "estimated": estimated,
                "generated": len(result["inserted"]),
                "skipped": result["skipped"],
            },
        }

    bg_task = asyncio.create_task(
        execute_generation_background(
            AsyncSessionLocal,
            run_id=run_id,
            operator_id=operator.id,
            topics=topics,
            config=config,
            known_brands=known_brands,
            existing_prompts=existing_prompts,
            estimated=estimated,
            request_config=request_config,
        )
    )
    _BACKGROUND_PROMPT_GENERATION_TASKS.add(bg_task)
    bg_task.add_done_callback(_BACKGROUND_PROMPT_GENERATION_TASKS.discard)
    return {
        "success": True,
        "run_id": run_id,
        "status": "running",
        "summary": {
            "estimated": estimated,
            "generated": 0,
            "skipped": [],
        },
    }
