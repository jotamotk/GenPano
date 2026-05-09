"""Admin LLM extraction candidates API."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from genpano_models import AdminUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.llm_extraction.lib import (
    VALID_ENTITY_TYPES,
    VALID_STATUSES,
    LLMExtractionError,
    approve_attribute_candidate,
    approve_claim_candidate,
    approve_entity_candidate,
    backfill_extraction_candidates,
    list_attribute_candidates,
    list_claim_candidates,
    list_entity_candidates,
    reject_attribute_candidate,
    reject_claim_candidate,
    reject_entity_candidate,
)
from app.api.admin.auth.router import current_admin
from app.core.errors import conflict, not_found, validation_error
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin 路 LLM Extraction"])


def _raise_for_error(error: LLMExtractionError) -> None:
    if error.code == "candidate_not_found":
        raise not_found("candidate_not_found")
    if error.code == "invalid_state":
        raise conflict("invalid_state", error.message)
    raise validation_error("candidate", error.message)


async def _json_payload(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _validate_status(status: str) -> str:
    value = (status or "pending").strip().lower()
    if value not in VALID_STATUSES:
        raise validation_error("status", "must be one of pending / approved / rejected / all")
    return value


def _validate_entity_type(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized == "all":
        return None
    if normalized not in VALID_ENTITY_TYPES:
        raise validation_error(
            "entity_type",
            "must be one of " + " / ".join(sorted(VALID_ENTITY_TYPES)),
        )
    return normalized


@router.get("/candidates", response_model=None)
async def get_entity_candidates(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
    status: str = Query("pending"),
    entity_type: str | None = Query(None),
    brand_id: int | None = Query(None, ge=1),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    status_norm = _validate_status(status)
    entity_type_norm = _validate_entity_type(entity_type)
    rows, total = await list_entity_candidates(
        session,
        status=status_norm,
        entity_type=entity_type_norm,
        brand_id=brand_id,
        query=q,
        limit=per_page,
        offset=(page - 1) * per_page,
    )
    return {
        "success": True,
        "items": rows,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": max(1, (total + per_page - 1) // per_page),
        },
    }


@router.get("/attributes", response_model=None)
async def get_attribute_candidates(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
    status: str = Query("pending"),
    entity_kind: str | None = Query(None),
    brand_id: int | None = Query(None, ge=1),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    status_norm = _validate_status(status)
    entity_kind_norm = _validate_entity_type(entity_kind)
    rows, total = await list_attribute_candidates(
        session,
        status=status_norm,
        entity_kind=entity_kind_norm,
        brand_id=brand_id,
        query=q,
        limit=per_page,
        offset=(page - 1) * per_page,
    )
    return {
        "success": True,
        "items": rows,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": max(1, (total + per_page - 1) // per_page),
        },
    }


@router.get("/claims", response_model=None)
async def get_claim_candidates(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
    status: str = Query("pending"),
    entity_kind: str | None = Query(None),
    brand_id: int | None = Query(None, ge=1),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    status_norm = _validate_status(status)
    entity_kind_norm = _validate_entity_type(entity_kind)
    rows, total = await list_claim_candidates(
        session,
        status=status_norm,
        entity_kind=entity_kind_norm,
        brand_id=brand_id,
        query=q,
        limit=per_page,
        offset=(page - 1) * per_page,
    )
    return {
        "success": True,
        "items": rows,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": max(1, (total + per_page - 1) // per_page),
        },
    }


@router.post("/candidates/{candidate_id}/approve", response_model=None)
async def approve_entity(
    candidate_id: str,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Approve an entity candidate and emit_audit (action=llm_entity_approved)."""
    payload = await _json_payload(request)
    reason = str(payload.get("reason") or "llm_entity_approve")
    try:
        item = await approve_entity_candidate(
            session,
            candidate_id=candidate_id,
            admin_id=operator.id,
            reason=reason,
        )
    except LLMExtractionError as error:
        _raise_for_error(error)
    await emit_audit(
        session,
        operator=operator,
        action="llm_entity_approved",
        severity="med",
        resource_type="llm_entity_candidate",
        resource_id=candidate_id,
        after={"status": "approved"},
        reason=reason,
        request=request,
    )
    return {"success": True, "item": item}


@router.post("/candidates/{candidate_id}/reject", response_model=None)
async def reject_entity(
    candidate_id: str,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Reject an entity candidate and emit_audit (action=llm_entity_rejected)."""
    payload = await _json_payload(request)
    reason = str(payload.get("reason") or "llm_entity_reject")
    try:
        item = await reject_entity_candidate(
            session,
            candidate_id=candidate_id,
            admin_id=operator.id,
            reason=reason,
        )
    except LLMExtractionError as error:
        _raise_for_error(error)
    await emit_audit(
        session,
        operator=operator,
        action="llm_entity_rejected",
        severity="med",
        resource_type="llm_entity_candidate",
        resource_id=candidate_id,
        after={"status": "rejected"},
        reason=reason,
        request=request,
    )
    return {"success": True, "item": item}


@router.post("/attributes/{candidate_id}/approve", response_model=None)
async def approve_attribute(
    candidate_id: str,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Approve an attribute candidate and emit_audit (action=llm_attribute_approved)."""
    payload = await _json_payload(request)
    reason = str(payload.get("reason") or "llm_attribute_approve")
    try:
        item = await approve_attribute_candidate(
            session,
            candidate_id=candidate_id,
            admin_id=operator.id,
            reason=reason,
        )
    except LLMExtractionError as error:
        _raise_for_error(error)
    await emit_audit(
        session,
        operator=operator,
        action="llm_attribute_approved",
        severity="med",
        resource_type="llm_attribute_candidate",
        resource_id=candidate_id,
        after={"status": "approved"},
        reason=reason,
        request=request,
    )
    return {"success": True, "item": item}


@router.post("/attributes/{candidate_id}/reject", response_model=None)
async def reject_attribute(
    candidate_id: str,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Reject an attribute candidate and emit_audit (action=llm_attribute_rejected)."""
    payload = await _json_payload(request)
    reason = str(payload.get("reason") or "llm_attribute_reject")
    try:
        item = await reject_attribute_candidate(
            session,
            candidate_id=candidate_id,
            admin_id=operator.id,
            reason=reason,
        )
    except LLMExtractionError as error:
        _raise_for_error(error)
    await emit_audit(
        session,
        operator=operator,
        action="llm_attribute_rejected",
        severity="med",
        resource_type="llm_attribute_candidate",
        resource_id=candidate_id,
        after={"status": "rejected"},
        reason=reason,
        request=request,
    )
    return {"success": True, "item": item}


@router.post("/claims/{candidate_id}/approve", response_model=None)
async def approve_claim(
    candidate_id: str,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Approve a claim candidate and emit_audit (action=llm_claim_approved)."""
    payload = await _json_payload(request)
    reason = str(payload.get("reason") or "llm_claim_approve")
    try:
        item = await approve_claim_candidate(
            session,
            candidate_id=candidate_id,
            admin_id=operator.id,
            reason=reason,
        )
    except LLMExtractionError as error:
        _raise_for_error(error)
    await emit_audit(
        session,
        operator=operator,
        action="llm_claim_approved",
        severity="med",
        resource_type="llm_claim_candidate",
        resource_id=candidate_id,
        after={"status": "approved"},
        reason=reason,
        request=request,
    )
    return {"success": True, "item": item}


@router.post("/claims/{candidate_id}/reject", response_model=None)
async def reject_claim(
    candidate_id: str,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Reject a claim candidate and emit_audit (action=llm_claim_rejected)."""
    payload = await _json_payload(request)
    reason = str(payload.get("reason") or "llm_claim_reject")
    try:
        item = await reject_claim_candidate(
            session,
            candidate_id=candidate_id,
            admin_id=operator.id,
            reason=reason,
        )
    except LLMExtractionError as error:
        _raise_for_error(error)
    await emit_audit(
        session,
        operator=operator,
        action="llm_claim_rejected",
        severity="med",
        resource_type="llm_claim_candidate",
        resource_id=candidate_id,
        after={"status": "rejected"},
        reason=reason,
        request=request,
    )
    return {"success": True, "item": item}


@router.post("/backfill", response_model=None)
async def backfill_candidates(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> dict[str, Any]:
    """Backfill extraction candidates from snapshots and emit_audit."""
    payload = await _json_payload(request)
    brand_id_raw = payload.get("brand_id") or payload.get("brandId")
    brand_id: int | None = None
    if brand_id_raw not in (None, ""):
        brand_id = int(str(brand_id_raw))
    version_raw = payload.get("brand_context_version") or payload.get("brandContextVersion")
    version: str | None = str(version_raw).strip() if version_raw not in (None, "") else None
    limit = int(payload.get("limit") or 50)
    summary = await backfill_extraction_candidates(
        session,
        brand_id=brand_id,
        brand_context_version=version,
        limit=limit,
    )
    await emit_audit(
        session,
        operator=operator,
        action="llm_extraction_backfill",
        severity="med",
        resource_type="llm_extraction",
        resource_id=str(brand_id or version or ""),
        after=summary,
        reason=str(payload.get("reason") or "llm_extraction_backfill"),
        request=request,
    )
    return {"success": True, "summary": summary}
