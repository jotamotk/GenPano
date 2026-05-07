"""Admin Brand Management router (Phase 7 slice 7a — CRUD + industries).

Mounted at ``/api/admin/brand-management`` (cookie ``current_admin``).

Routes in this PR:
- GET    /industries        distinct industries currently in ``brands``
- GET    /                  paged list with industry/source/status/search
- GET    /{brand_id}        detail
- POST   /                  create + emit_audit (med, action=create_brand)
- PUT    /{brand_id}        update + emit_audit (med, action=update_brand)
- DELETE /{brand_id}        soft delete (status='archived') + emit_audit (high)

Bulk import + LLM generate / enrich are deferred to slice 7a-bis. Cookies
+ accounts are slice 7b.

Notes:
- ``brands`` is an upstream stub in backend's ORM (ADR-002); all DB ops
  use raw text() with defensive ``information_schema`` probes — see
  app/admin/brand_management/db.py.
- The optional ``kg_brands`` mirror + competitor relation candidates that
  admin_console's handlers wrote alongside the main brand row are
  intentionally NOT ported here. They were ``_run_optional_brand_side_effect``
  best-effort writes; the ``kg_discovery`` admin job repopulates kg_brands
  from brands periodically. Slice 7a-bis can reintroduce the relation
  candidates path if needed.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from genpano_models import AdminUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.brand_management import db as brand_db
from app.admin.brand_management.lib import (
    BrandManagementError,
    brand_management_status_for_error,
    normalize_brand_draft,
    normalize_brand_source_input,
)
from app.api.admin.auth.router import current_admin
from app.core.errors import not_found, validation_error
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Brand Management"])


@router.get("/industries", response_model=None)
async def list_industries(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Distinct industries with brand counts (for filter dropdowns)."""
    industries = await brand_db.fetch_industries(session)
    return {"success": True, "industries": industries}


@router.get("", response_model=None)
async def list_brands(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
    page: int = Query(1, ge=1, le=100_000),
    per_page: int = Query(25, ge=1, le=200),
    q: str | None = Query(None),
    industry: str | None = Query(None),
    source: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
) -> dict[str, Any]:
    """Paginated brand list — same wire shape as admin_console."""
    rows, total = await brand_db.fetch_brands(
        session,
        page=page,
        per_page=per_page,
        q=q,
        industry=industry,
        source=source,
        status=status_filter,
    )
    total_pages = (total + per_page - 1) // per_page if per_page else 1
    return {
        "success": True,
        "brands": rows,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
    }


@router.get("/{brand_id}", response_model=None)
async def get_brand(
    brand_id: int,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    row = await brand_db.get_brand(session, brand_id)
    if row is None:
        raise not_found("brand_not_found")
    return {"success": True, "brand": row}


@router.post("", response_model=None)
async def create_brand(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Insert a new brand + emit_audit (med, action=create_brand).

    400 on validation error (``missing_brand_name`` /
    ``invalid_brand_payload``); 409 on duplicate brand name.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        draft = normalize_brand_draft(payload)
    except BrandManagementError as error:
        raise validation_error("payload", error.code) from error
    draft["source"] = normalize_brand_source_input(payload.get("source")) or "manual"

    if await brand_db.brand_name_exists(session, draft["name"]):
        return JSONResponse(
            status_code=409,
            content={"success": False, "error": "duplicate_brand_name"},
        )

    try:
        brand_id = await brand_db.persist_brand_draft(session, draft, admin_id=operator.id)
    except Exception as exc:
        # Fall through to controlled 500 (admin_console returned the
        # same on unexpected DB errors).
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "brand_create_failed", "message": str(exc)[:300]},
        )

    row = await brand_db.get_brand(session, brand_id)
    await emit_audit(
        session,
        operator=operator,
        action="create_brand",
        severity="med",
        resource_type="brand",
        resource_id=str(brand_id),
        after={
            "name": draft["name"],
            "industry": draft["industry"],
            "source": draft["source"],
        },
        reason=str(payload.get("reason") or "create_brand"),
        request=request,
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"success": True, "brand": row, "relation_candidates": 0},
    )


@router.put("/{brand_id}", response_model=None)
async def update_brand(
    brand_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Update a brand + emit_audit (med, action=update_brand)."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        draft = normalize_brand_draft(payload)
    except BrandManagementError as error:
        raise validation_error("payload", error.code) from error

    existing = await brand_db.get_brand(session, brand_id)
    if existing is None:
        raise not_found("brand_not_found")

    if await brand_db.brand_name_exists(session, draft["name"], exclude_id=brand_id):
        return JSONResponse(
            status_code=409,
            content={"success": False, "error": "duplicate_brand_name"},
        )

    try:
        await brand_db.persist_brand_draft(session, draft, admin_id=operator.id, brand_id=brand_id)
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "brand_update_failed",
                "message": str(exc)[:300],
            },
        )

    row = await brand_db.get_brand(session, brand_id)
    await emit_audit(
        session,
        operator=operator,
        action="update_brand",
        severity="med",
        resource_type="brand",
        resource_id=str(brand_id),
        before=existing,
        after={"name": draft["name"], "status": draft["status"]},
        reason=str(payload.get("reason") or "update_brand"),
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={"success": True, "brand": row},
    )


@router.delete("/{brand_id}", response_model=None)
async def archive_brand(
    brand_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Soft-delete (status='archived') + emit_audit (high, action=archive_brand).

    Hard delete is intentionally not supported here — it would cascade
    into ``kg_brands`` / ``brand_mentions`` and other upstream tables.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    existing = await brand_db.get_brand(session, brand_id)
    if existing is None:
        raise not_found("brand_not_found")
    archived = await brand_db.archive_brand(session, brand_id)
    if not archived:
        raise not_found("brand_not_found")
    await emit_audit(
        session,
        operator=operator,
        action="archive_brand",
        severity="high",
        resource_type="brand",
        resource_id=str(brand_id),
        before=existing,
        after={"status": "archived"},
        reason=str(payload.get("reason") or "archive_brand"),
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={"success": True, "status": "archived"},
    )


# Re-export for slice 7a-bis tests + backward-compat with admin_console
# error mapping conventions.
__all__ = [
    "BrandManagementError",
    "brand_management_status_for_error",
    "router",
]


# ---------------------------------------------------------------------------
# Phase 7 slice 7a-bis — generate / enrich / enrich-job / import
# ---------------------------------------------------------------------------


from app.admin.brand_management.enrich_jobs import (  # noqa: E402
    execute_brand_enrich_sync,
    get_brand_enrich_job,
    schedule_brand_enrich_job,
)
from app.admin.brand_management.llm import (  # noqa: E402
    BrandManagementService,
)
from app.db.session import AsyncSessionLocal  # noqa: E402


@router.post("/generate", response_model=None)
async def generate_brands(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """LLM-generate reviewable brand drafts for an industry.

    No DB writes to ``brands`` — drafts are returned for the operator
    to import via ``POST /import``. A best-effort row is appended to
    ``brand_generation_logs`` (best-effort because the table is
    admin_console-only and may not exist on fresh deployments).
    Emits ``generate_brands`` audit on success.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    industry = (payload.get("industry") or "").strip()
    if not industry:
        raise validation_error("industry", "industry_required")

    seeds = await brand_db.fetch_industry_seeds(session, industry)

    service = BrandManagementService(
        model=payload.get("llm_model"),
        allow_fallback=False,
    )
    try:
        result = await service.generate_brands(
            industry=industry,
            count=int(payload.get("count") or 8),
            region=str(payload.get("region") or ""),
            positioning=str(payload.get("positioning") or ""),
            seed_brands=list(payload.get("seed_brands") or seeds),
            constraints=str(payload.get("constraints") or ""),
            language=str(payload.get("language") or "auto"),
        )
    except BrandManagementError as error:
        return JSONResponse(
            status_code=brand_management_status_for_error(error),
            content={
                "success": False,
                "error": error.code,
                "message": error.message,
            },
        )

    await brand_db.write_brand_generation_log(
        session,
        admin_id=operator.id,
        industry=industry,
        seeds=seeds,
        model=result.model,
        prompt=result.prompt,
        payload=payload,
        items=result.items,
        usage=result.usage,
        estimated_cost=result.estimated_cost,
    )
    await emit_audit(
        session,
        operator=operator,
        action="generate_brands",
        severity="med",
        resource_type="brand",
        resource_id="",
        after={
            "industry": industry,
            "count": len(result.items),
            "model": result.model,
        },
        reason=str(payload.get("reason") or "generate_brands"),
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "drafts": result.items,
            "model": result.model,
            "usage": result.usage,
            "industry": industry,
        },
    )


@router.post("/enrich", response_model=None)
async def enrich_brand(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """LLM-enrich one brand from a name + optional context.

    Two modes (mirror admin_console):
    - ``async_generation: true`` → 202 + ``{job_id}``; SPA polls
      ``GET /enrich/{job_id}`` until terminal.
    - default sync → 200 with ``draft`` (or 409 with ``choices`` when
      multiple ambiguous candidates).

    Emits ``enrich_brand`` audit on success.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    name = (payload.get("name") or payload.get("brand_name") or "").strip()
    if not name:
        raise validation_error("name", "name_required")

    if payload.get("async_generation") or payload.get("async"):
        job_id = await schedule_brand_enrich_job(
            AsyncSessionLocal,
            operator_id=operator.id,
            name=name,
            payload=payload,
        )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "success": True,
                "pending": True,
                "status": "queued",
                "job_id": job_id,
            },
        )

    # Sync path. emit_audit fires inside execute_brand_enrich_sync.
    try:
        result = await execute_brand_enrich_sync(
            session,
            operator=operator,
            name=name,
            payload=payload,
            request=request,
        )
    except BrandManagementError as error:
        return JSONResponse(
            status_code=brand_management_status_for_error(error),
            content={
                "success": False,
                "error": error.code,
                "message": error.message,
            },
        )

    drafts = list(result.items or [])
    if len(drafts) > 1:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": "ambiguous_brand",
                "message": "Multiple brand matches were returned. Please choose one.",
                "choices": drafts,
                "model": result.model,
                "usage": result.usage,
            },
        )
    draft = drafts[0] if drafts else None
    if not draft:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "empty_result",
                "message": "LLM returned no usable draft",
            },
        )
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "draft": draft,
            "model": result.model,
            "usage": result.usage,
        },
    )


@router.get("/enrich/{job_id}", response_model=None)
async def get_brand_enrich_job_route(
    job_id: str,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Poll the async enrich job. Returns the snapshot or 404 if unknown.
    Mirrors admin_console: ambiguous (>1 draft) → 409 with ``choices``;
    empty draft → 503.
    """
    job = await get_brand_enrich_job(job_id)
    if not job:
        raise not_found("brand_enrich_job_not_found")
    if job.get("status") == "failed":
        return JSONResponse(
            status_code=int(job.get("http_status") or 500),
            content={
                "success": False,
                "pending": False,
                "job_id": job_id,
                "status": job.get("status"),
                "error": job.get("error") or "brand_enrich_failed",
                "message": job.get("message") or "Brand enrichment failed",
            },
        )
    if job.get("pending"):
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "pending": True,
                "job_id": job_id,
                "status": job.get("status"),
                "message": job.get("message"),
            },
        )
    drafts = list(job.get("drafts") or [])
    if len(drafts) > 1:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "pending": False,
                "job_id": job_id,
                "status": job.get("status"),
                "error": "ambiguous_brand",
                "message": "Multiple brand matches were returned. Please choose one.",
                "choices": drafts,
                "model": job.get("model"),
                "usage": job.get("usage") or {},
            },
        )
    draft = job.get("draft") or (drafts[0] if drafts else None)
    if not draft:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "pending": False,
                "job_id": job_id,
                "status": job.get("status"),
                "error": "empty_result",
                "message": "LLM returned no usable draft",
            },
        )
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "pending": False,
            "job_id": job_id,
            "status": job.get("status"),
            "draft": draft,
            "model": job.get("model"),
            "usage": job.get("usage") or {},
        },
    )


@router.post("/import", response_model=None)
async def import_brands(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Persist reviewed drafts. Mirror of /api/segments/import.

    Each draft is normalized + upserted (matching by LOWER(name)).
    Per-row failures recorded in ``skipped_rows`` rather than
    aborting. Single ``import_brands`` audit row covers the batch.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    drafts_raw = payload.get("drafts") or payload.get("brands") or []
    if not isinstance(drafts_raw, list) or not drafts_raw:
        raise validation_error("drafts", "drafts_required")
    default_industry = str(payload.get("default_industry") or payload.get("industry") or "").strip()

    try:
        result = await brand_db.import_brands_bulk(
            session,
            drafts_raw,
            admin_id=operator.id,
            default_industry=default_industry,
        )
    except BrandManagementError as error:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": error.code,
                "message": error.message,
            },
        )

    await emit_audit(
        session,
        operator=operator,
        action="import_brands",
        severity="med",
        resource_type="brand",
        resource_id="",
        after={
            "added": result["added"],
            "updated": result["updated"],
            "skipped": result["skipped"],
        },
        reason=str(payload.get("reason") or "import_brands"),
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={"success": True, **result},
    )
