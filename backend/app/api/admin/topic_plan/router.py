"""Admin Topic Plan router (Phase 3 B.1 + B.2.a).

Mounted at ``/api/admin/topic-plan`` (cookie-based ``current_admin``).

Endpoints (B.1 — candidate review):
- POST /candidates/{candidate_id}/review   approve | reject one candidate
- POST /candidates/bulk-review             apply same decision to many

Endpoints (B.2.a — read paths + run lifecycle):
- GET  /config                             industries / categories / brands /
                                            defaults / pending summary
- GET  /coverage                           per-brand coverage rows + gaps
- GET  /candidates                         paged list of topic_candidates
- GET  /topics                             paged list of topics with prompt /
                                            query counts
- GET  /runs/{run_id}                      single run row
- POST /runs/{run_id}/stop                 cancel a running generation

Phase 3 B.2.b will add: POST /generate (LLM call via httpx async).
Phase 3 B.3 will add: POST /topics/bulk-delete, DELETE /topics/{id}.

Read paths against ``brands`` / ``topics`` / ``prompts`` / ``queries``
(upstream stubs per ADR-002 — only ``id`` modeled in backend's ORM)
go through ``app/admin/topic_plan/db.py`` which uses
``session.execute(text(...))`` directly. Production schema (postgres) is
assumed; sqlite test harnesses mock those helpers. ``topic_plan_runs`` /
``topic_candidates`` are real ORM models.

Approve flow inserts a row into the legacy ``topics`` table (upstream stub
in backend's ORM — only ``id`` modeled). The insert uses raw SQL via
``session.execute(text(...))`` so backend doesn't have to add columns to
``app/db/_upstream_stubs.py`` (ADR-002 forbids it). Tests cover the
reject path against sqlite + mock approve in a postgres preview env.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from genpano_models import AdminUser, TopicCandidate, TopicPlanRun
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.topic_plan import db as tp_db
from app.admin.topic_plan.lib import (
    TopicPlanLLMError,
    load_doubao_config,
    transition_candidate_status,
)
from app.api.admin.auth.router import current_admin
from app.core.errors import _problem, not_found, validation_error
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Topic Plan"])

ALLOWED_TOPIC_DIMENSIONS = {"brand", "product", "category", "scenario", "question"}
ALLOWED_TOPIC_STATUSES = {"active", "draft", "archived", "all"}
ALLOWED_CANDIDATE_STATUSES = {"pending", "approved", "rejected", "all"}


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


# ---------------------------------------------------------------------------
# B.2.a — config / coverage / candidates / topics / runs
# ---------------------------------------------------------------------------


def _parse_int_list_query(value: str | None) -> list[int]:
    if value is None:
        return []
    try:
        return tp_db.parse_int_list(value)
    except ValueError as exc:
        raise validation_error("brand_ids", "must be a comma-separated integer list") from exc


def _clamp(value: int | None, default: int, lo: int, hi: int) -> int:
    if value is None:
        return default
    return max(lo, min(int(value), hi))


@router.get("/config", response_model=None)
async def get_config(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
    industry_id: str | None = Query(None),
    category_id: str | None = Query(None),
) -> dict[str, Any]:
    """Top-level Topic Plan tab config — populates the SPA dropdowns."""
    brands = await tp_db.fetch_brands(session)
    industries = [
        {"id": value, "name": value}
        for value in sorted({b.get("industry_id") or "Uncategorized" for b in brands})
    ]
    categories = await tp_db.fetch_categories(session)
    default_industry = industry_id or (industries[0]["id"] if industries else "")
    default_category = category_id or ""
    scoped = tp_db.scope_brands(brands, industry_id=default_industry)
    selected_ids = {
        int(b["id"])
        for b in sorted(scoped, key=lambda item: item.get("topic_count", 0), reverse=True)[:4]
    }
    for brand in brands:
        brand["selected"] = int(brand["id"]) in selected_ids

    pending = await tp_db.pending_summary(session, brand_ids=list(selected_ids))
    try:
        load_doubao_config()
        llm_configured = True
    except TopicPlanLLMError:
        llm_configured = False

    return {
        "success": True,
        "industries": industries,
        "categories": categories,
        "brands": brands,
        "defaults": {
            "industryId": default_industry,
            "categoryId": default_category,
            "maxPerBrand": 40,
            "maxTopics": 180,
            "gapPriority": "p12",
            "overflowPolicy": "review",
        },
        "summary": {
            "pending_candidates": pending["pending"],
            "low_confidence": pending["low_confidence"],
            "llm_configured": llm_configured,
        },
    }


@router.get("/coverage", response_model=None)
async def get_coverage(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
    industry_id: str | None = Query(None),
    category_id: str | None = Query(None),
    brand_ids: str | None = Query(None),
    max_per_brand: int = Query(40, ge=1, le=200),
) -> dict[str, Any]:
    parsed_brand_ids = _parse_int_list_query(brand_ids)
    all_brands = await tp_db.fetch_brands(session)
    brands = tp_db.scope_brands(all_brands, industry_id=industry_id, brand_ids=parsed_brand_ids)
    coverage = await tp_db.build_coverage(
        session,
        brands,
        category_id=category_id,
        max_per_brand=max_per_brand,
    )
    return {
        "success": True,
        "rows": coverage["rows"],
        "gaps": coverage["gaps"],
        "summary": coverage["summary"],
    }


@router.get("/candidates", response_model=None)
async def get_candidates(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
    status: str = Query("pending"),
    brand_ids: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    run_id: str | None = Query(None),
) -> dict[str, Any]:
    status_norm = status.strip().lower()
    if status_norm not in ALLOWED_CANDIDATE_STATUSES:
        raise validation_error("status", f"must be one of {sorted(ALLOWED_CANDIDATE_STATUSES)}")
    parsed_brand_ids = _parse_int_list_query(brand_ids)
    candidate_brand_ids = None if run_id else (parsed_brand_ids or None)

    rows = await tp_db.fetch_candidates(
        session,
        status=status_norm,
        brand_ids=candidate_brand_ids,
        query=q,
        limit=limit,
        run_id=run_id,
    )
    pending = await tp_db.pending_summary(session, brand_ids=candidate_brand_ids, run_id=run_id)
    return {
        "success": True,
        "rows": rows,
        "summary": {
            "pending_candidates": pending["pending"],
            "low_confidence": pending["low_confidence"],
        },
    }


@router.get("/topics", response_model=None)
async def get_topics(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
    industry_id: str | None = Query(None),
    category_id: str | None = Query(None),
    brand_ids: str | None = Query(None),
    dimension: str | None = Query(None),
    status: str = Query("all"),
    q: str | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
) -> dict[str, Any]:
    parsed_brand_ids = _parse_int_list_query(brand_ids)
    dim_norm = (dimension or "").strip().lower() or None
    if dim_norm and dim_norm not in ALLOWED_TOPIC_DIMENSIONS:
        raise validation_error("dimension", f"must be one of {sorted(ALLOWED_TOPIC_DIMENSIONS)}")
    status_norm = (status or "all").strip().lower()
    if status_norm not in ALLOWED_TOPIC_STATUSES:
        raise validation_error("status", f"must be one of {sorted(ALLOWED_TOPIC_STATUSES)}")

    rows, summary = await tp_db.fetch_topics(
        session,
        industry_id=industry_id,
        category_id=category_id,
        brand_ids=parsed_brand_ids or None,
        dimension=dim_norm,
        status=status_norm,
        query=q,
        limit=limit,
    )
    return {"success": True, "rows": rows, "summary": summary}


@router.get("/runs/{run_id}", response_model=None)
async def get_run(
    run_id: str,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    run = (
        await session.execute(select(TopicPlanRun).where(TopicPlanRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise not_found("run_not_found")
    await tp_db.mark_stale_run(session, run)
    return {"success": True, "run": tp_db.run_to_dict(run)}


@router.post("/runs/{run_id}/stop", response_model=None)
async def stop_run(
    run_id: str,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Cancel a running Topic Plan generation. Idempotent on terminal runs.

    Audit emit (severity=med, action=topic_plan_run_cancelled). Already-
    finalized runs return success with ``already_finalized: true`` and the
    same run row — no audit row in that case.
    """
    run = (
        await session.execute(select(TopicPlanRun).where(TopicPlanRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise not_found("run_not_found")

    if run.status in {"completed", "failed", "cancelled"}:
        return {
            "success": True,
            "already_finalized": True,
            "run": tp_db.run_to_dict(run),
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
        action="topic_plan_run_cancelled",
        severity="med",
        resource_type="topic_plan_run",
        resource_id=run.id,
        before={"status": before_status},
        after={"status": "cancelled"},
        reason="topic_plan_stop",
        request=request,
    )
    return {"success": True, "run": tp_db.run_to_dict(run)}
