"""`diagnostics` router (Phase 0 skeleton)."""

from fastapi import APIRouter, status

from app.api.v1.diagnostics._dto import PlaceholderResponse

router = APIRouter(tags=["Diagnostics"])


@router.get("/", status_code=status.HTTP_501_NOT_IMPLEMENTED, response_model=PlaceholderResponse)
async def stub() -> PlaceholderResponse:
    """Phase 0 placeholder — real implementation lands in Phase 1+."""
    return PlaceholderResponse()
