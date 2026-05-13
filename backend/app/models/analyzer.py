"""Backward-compat shim — see `genpano_models.analyzer` (ADR-004)."""

from genpano_models.analyzer import (
    AnalysisFactLink,
    AnalyzerQualityFlag,
    AnalyzerRun,
    BrandMention,
    CitationSource,
    GeoScoreDaily,
    IndustryBenchmarkDaily,
    ProductFeatureMention,
    ProductScoreDaily,
    ResponseAnalysis,
    ResponseEntity,
    ResponseRelationFact,
    SentimentDriver,
)

__all__ = [
    "AnalysisFactLink",
    "AnalyzerQualityFlag",
    "AnalyzerRun",
    "BrandMention",
    "CitationSource",
    "GeoScoreDaily",
    "IndustryBenchmarkDaily",
    "ProductFeatureMention",
    "ProductScoreDaily",
    "ResponseAnalysis",
    "ResponseEntity",
    "ResponseRelationFact",
    "SentimentDriver",
]
