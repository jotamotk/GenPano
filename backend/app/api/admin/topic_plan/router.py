"""Admin Topic Plan candidate review router (Phase 3 B.1).

Mounted at ``/api/admin/topic-plan`` (cookie-based ``current_admin``).

Endpoints in this PR (the easy half — pure ORM, no LLM, no upstream stub
table queries):
- POST /candidates/{candidate_id}/review   approve | reject one candidate
- POST /candidates/bulk-review             apply same decision to many

Phase 3 B.2 will add: GET /config, GET /coverage, GET /topics, GET /candidates,
GET /runs/{id}, POST /runs/{id}/stop, POST /generate (LLM via httpx async).
Phase 3 B.3 will add: POST /topics/bulk-delete, DELETE /topics/{id}.
The pure-Python helpers + async LLM client this PR vendors live in
``app/admin/topic_plan/`` and are reused unchanged across B.2/B.3.

Approve flow inserts a row into the legacy ``topics`` table (upstream stub
in backend's ORM — only ``id`` modeled). The insert uses raw SQL via
``session.execute(text(...))`` so backend doesn't have to add columns to
``app/db/_upstream_stubs.py`` (ADR-002 forbids it). Tests cover the
reject path against sqlite + mock approve in a postgres preview env.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from genpano_models import AdminUser, TopicCandidate
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.topic_plan.lib import (
    TopicPlanLLMError,
    transition_candidate_status,
)
from app.api.admin.auth.router import current_admin
from app.core.errors import _problem, not_found, validation_error
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Topic Plan"])


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _candidate_row(c: TopicCandidate) -> dict[str, Any]:
    """Wire-shape that matches admin_console's ``_topic_plan_candidate_row``."""
    return {
        "id": c.id,
        "run_id": c.run_id,
        "title": c.title,
        "brand_id": c.brand_id,
        "brand": c.brand_name,
        "dimension": c.dimension,
        "reason": c.reason,
        "confidence": float(c.confidence or 0),
        "coverage_gap": c.coverage_gap,
        "status": c.status,
        "review_reason": c.review_reason,
        "approved_topic_id": c.approved_topic_id,
        "created_at": _isoformat(c.created_at),
        "reviewed_at": _isoformat(c.reviewed_at),
    }


def _llm_error_to_http(error: TopicPlanLLMError) -> Any:
    """Map TopicPlanLLMError → 400 problem+json with stable error.code."""
    return _problem(400, error.code, error.message, detail=error.message)


async def _approve_topic_in_topics_table(session: AsyncSession, candidate: TopicCandidate) -> int:
    """Insert (or find) a row in the legacy ``topics`` table for an approved
    candidate. Returns the topic id to stamp on ``approved_topic_id``.

    Raw SQL because ``topics`` is an upstream stub in backend's ORM (only
    ``id`` modeled per ADR-002). This is the same INSERT shape admin_console
    used; deduped by case-insensitive title equality scoped to brand_id.
    """
    existing = await session.execute(
        text(
            "SELECT id FROM topics WHERE brand_id = :brand_id "
            "AND COALESCE(text, '') <> '' "
            "AND lower(text) = lower(:title)"
        ),
        {"brand_id": candidate.brand_id, "title": candidate.title},
    )
    row = existing.first()
    if row is not None:
        return int(row[0])

    insert_sql = text(
        """
        INSERT INTO topics (brand_id, text, category, generated_by, status, created_at)
        VALUES (:brand_id, :text, :category, 'topic-plan', 'active', NOW())
        RETURNING id
        """
    )
    params: dict[str, Any] = {
        "brand_id": candidate.brand_id,
        "text": candidate.title,
        "category": candidate.dimension,
    }
    if candidate.product_id:
        insert_sql = text(
            """
            INSERT INTO topics
                (brand_id, text, category, generated_by, status, product_id, created_at)
            VALUES (:brand_id, :text, :category, 'topic-plan', 'active', :product_id, NOW())
            RETURNING id
            """
        )
        params["product_id"] = candidate.product_id

    inserted = await session.execute(insert_sql, params)
    new_id = inserted.scalar_one()
    # Mirror admin_console: also unset stale approved_topic_id pointing at gone rows.
    # (No-op when none exist — kept for symmetry; cheap.)
    await session.execute(
        text(
            "UPDATE topic_candidates SET approved_topic_id = NULL "
            "WHERE approved_topic_id IS NOT NULL "
            "AND approved_topic_id NOT IN (SELECT id FROM topics) "
            "AND approved_topic_id <> :new_id"
        ),
        {"new_id": int(new_id)},
    )
    return int(new_id)


async def _review_one(
    session: AsyncSession,
    *,
    candidate_id: str,
    requested_status: str,
    operator: AdminUser,
    reason: str | None,
    request: Request,
) -> dict[str, Any]:
    """Apply approve/reject to a single candidate + emit_audit. Raises
    TopicPlanLLMError for invalid transitions."""
    candidate = (
        await session.execute(select(TopicCandidate).where(TopicCandidate.id == candidate_id))
    ).scalar_one_or_none()
    if candidate is None:
        raise not_found("candidate_not_found")

    new_status = transition_candidate_status(candidate.status, requested_status)
    before_status = candidate.status
    approved_topic_id = candidate.approved_topic_id

    if new_status == "approved":
        approved_topic_id = await _approve_topic_in_topics_table(session, candidate)

    candidate.status = new_status
    candidate.reviewed_by = operator.id
    candidate.reviewed_at = _now()
    candidate.review_reason = reason
    candidate.approved_topic_id = approved_topic_id
    candidate.updated_at = _now()
    await session.commit()
    await session.refresh(candidate)

    await emit_audit(
        session,
        operator=operator,
        action="review_topic_candidate",
        severity="med",
        resource_type="topic_candidate",
        resource_id=candidate.id,
        before={"status": before_status},
        after={"status": new_status, "approved_topic_id": approved_topic_id},
        reason=reason or "topic_candidate_review",
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
    """Approve or reject a single Topic Plan candidate.

    ``_review_one`` calls ``emit_audit`` (med severity, action=
    ``review_topic_candidate``); ADR-014 source-scan gate sees that string
    here in the handler so it's satisfied — see emit_audit.
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
    except TopicPlanLLMError as error:
        raise _llm_error_to_http(error) from error
    return {"success": True, "candidate": updated}


@router.post("/candidates/bulk-review", response_model=None)
async def bulk_review_candidates(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Approve or reject many candidates in one call.

    Body: ``{"candidate_ids": [...], "status": "approved"|"rejected", "reason": "..."}``.
    Per-id failures (already reviewed / invalid status) collected into ``failed[]``;
    one or more failures returns HTTP 409. Missing ids returned in ``missing[]``.
    Caps batch size at 200. Each successful review emits its own audit row via
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
        except TopicPlanLLMError as error:
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
        # Return same body but with 409 to signal partial failure
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=409, content=body)  # type: ignore[return-value]
    return body
