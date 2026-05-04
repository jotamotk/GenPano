"""Backward-compat shim — see `genpano_models.analyzer` (ADR-004)."""

from genpano_models.analyzer import (
    BrandMention,
    CitationSource,
    GeoScoreDaily,
    IndustryBenchmarkDaily,
    ProductFeatureMention,
    ProductScoreDaily,
    ResponseAnalysis,
    SentimentDriver,
)

__all__ = [
    "BrandMention",
    "CitationSource",
    "GeoScoreDaily",
    "IndustryBenchmarkDaily",
    "ProductFeatureMention",
    "ProductScoreDaily",
    "ResponseAnalysis",
    "SentimentDriver",
]
