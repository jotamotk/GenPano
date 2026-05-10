"""`brands` router — public brand search for onboarding + watch flows."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth.router import get_current_user
from app.api.v1.brands._dto import BrandSearchHit, BrandSearchResponse, PlaceholderResponse
from app.api.v1.brands.service import search_brands
from app.db.session import get_db
from app.models.user import User

router = APIRouter(tags=["Brands"])


@router.get("/search", response_model=BrandSearchResponse)
async def search(
    q: Annotated[str, Query(min_length=1, max_length=120)],
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> BrandSearchResponse:
    items: list[BrandSearchHit] = await search_brands(db, q=q, limit=limit, user_id=current_user.id)
    return BrandSearchResponse(items=items)


@router.get("/", status_code=status.HTTP_501_NOT_IMPLEMENTED, response_model=PlaceholderResponse)
async def stub() -> PlaceholderResponse:
    """Phase 0 placeholder for the broader brand catalog endpoint."""
    return PlaceholderResponse()
