"""Backward-compat shim — ORM models now live in `genpano_models` (ADR-004).

Existing `from app.models import User, BrandMention, ...` imports continue to
work via this re-export. New code should import directly from `genpano_models`.
"""

from genpano_models import (
    Base,
    BrandMention,
    CitationSource,
    GeoScoreDaily,
    IndustryBenchmarkDaily,
    ProductFeatureMention,
    ProductScoreDaily,
    ResponseAnalysis,
    SentimentDriver,
    User,
    UserAuthToken,
)

__all__ = [
    "Base",
    "BrandMention",
    "CitationSource",
    "GeoScoreDaily",
    "IndustryBenchmarkDaily",
    "ProductFeatureMention",
    "ProductScoreDaily",
    "ResponseAnalysis",
    "SentimentDriver",
    "User",
    "UserAuthToken",
]
