"""Legacy profile router — Phase 9 slice 9d.

Mounted at the legacy ``/api/profiles*`` paths. admin_console served
these without auth; the FastAPI port adds ``Depends(current_admin)``
(security hardening).

Routes:
- GET    /api/profiles                  list (geo_tracker schema)
- POST   /api/profiles                  create + emit_audit (med)
- PUT    /api/profiles/{id}             update + emit_audit (med)
- DELETE /api/profiles/{id}             delete + emit_audit (high)
- GET    /api/profiles/lite             schema-aware picker
- GET    /api/profiles/{id}/similar     heuristic similar profiles

Note: segment-attached profiles (with code / segment_id) are owned by
slice 6b at /api/admin/segments/{id}/profiles. This slice is the
geo_tracker-flavor profiles table used by the admin.html attempt
tracker; admin_console served both flavors at /api/profiles.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from genpano_models import AdminUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.profiles_legacy import db as profiles_db
from app.admin.profiles_legacy.lib import (
    ProfileValidationError,
    parse_profile_payload,
)
from app.api.admin.auth.router import current_admin
from app.core.errors import not_found
from app.core.security import _DependsDb

router = APIRouter(tags=["Profiles (legacy)"])


def _validation_400(error: ProfileValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"success": False, "error": error.code, "message": error.message},
    )


@router.get("/profiles", response_model=None)
async def list_profiles(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> Any:
    return await profiles_db.list_profiles(session)


@router.post("/profiles", response_model=None)
async def create_profile(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        normalized = parse_profile_payload(payload)
    except ProfileValidationError as error:
        return _validation_400(error)

    profile_id = await profiles_db.create_profile(session, payload=normalized)
    if profile_id is None:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "profiles_unavailable",
                "message": "profiles table is not available; run migrations first.",
            },
        )
    await emit_audit(
        session,
        operator=operator,
        action="create_profile",
        severity="med",
        resource_type="profile",
        resource_id=str(profile_id),
        after={
            "name": normalized["name"],
            "country_code": normalized["country_code"],
            "language": normalized["language"],
            "device_type": normalized["device_type"],
            "trait_keys": sorted((normalized.get("persona_traits") or {}).keys()),
        },
        reason="create_profile",
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={"success": True, "profile_id": profile_id},
    )


@router.put("/profiles/{profile_id}", response_model=None)
async def update_profile(
    profile_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        normalized = parse_profile_payload(payload)
    except ProfileValidationError as error:
        return _validation_400(error)

    ok = await profiles_db.update_profile(session, profile_id=profile_id, payload=normalized)
    if not ok:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "Profile not found"},
        )
    await emit_audit(
        session,
        operator=operator,
        action="update_profile",
        severity="med",
        resource_type="profile",
        resource_id=str(profile_id),
        after={
            "name": normalized["name"],
            "country_code": normalized["country_code"],
            "language": normalized["language"],
            "device_type": normalized["device_type"],
            "trait_keys": sorted((normalized.get("persona_traits") or {}).keys()),
        },
        reason="update_profile",
        request=request,
    )
    return JSONResponse(status_code=200, content={"success": True})


@router.delete("/profiles/{profile_id}", response_model=None)
async def delete_profile(
    profile_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    deleted, unlinked = await profiles_db.delete_profile(session, profile_id)
    if not deleted:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "Profile not found"},
        )
    await emit_audit(
        session,
        operator=operator,
        action="delete_profile",
        severity="high",
        resource_type="profile",
        resource_id=str(profile_id),
        after={"deleted": True, "unlinked_query_count": unlinked},
        reason="delete_profile",
        request=request,
    )
    return JSONResponse(status_code=200, content={"success": True})


# ── lite + similar ──────────────────────────────────────────


@router.get("/profiles/lite", response_model=None)
async def profiles_lite(
    operator: Annotated[AdminUser, Depends(current_admin)],
    q: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    session: AsyncSession = _DependsDb,
) -> Any:
    return await profiles_db.list_profiles_lite(session, q=q, limit=limit)


@router.get("/profiles/{profile_id}/similar", response_model=None)
async def profiles_similar(
    profile_id: str,
    operator: Annotated[AdminUser, Depends(current_admin)],
    limit: int = Query(20, ge=1, le=200),
    session: AsyncSession = _DependsDb,
) -> Any:
    result = await profiles_db.find_similar_profiles(session, profile_id=profile_id, limit=limit)
    if result is None:
        raise not_found("profile not found")
    return result


__all__ = ["router"]
