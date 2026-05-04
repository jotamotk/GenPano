"""DTOs for Meta (Phase 0 skeleton — Pydantic v2)."""

from pydantic import BaseModel


class PlaceholderResponse(BaseModel):
    """Phase 0 stub. Real schemas land per Phase 1+ implementation."""

    state: str = "phase_0_stub"
    message: str = "List registered routes — endpoint not yet implemented"
