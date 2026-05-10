"""DTOs for Brands."""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class PlaceholderResponse(BaseModel):
    """Phase 0 stub. Real schemas land per Phase 1+ implementation."""

    state: str = "phase_0_stub"
    message: str = "Search brands — endpoint not yet implemented"


class _BaseDto(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class BrandSearchHit(_BaseDto):
    brand_id: int
    brand_name: str
    industry: str | None = None
    is_already_monitoring: bool = False


class BrandSearchResponse(_BaseDto):
    items: list[BrandSearchHit]
