"""Phase D — registry membership tests for the third rule batch.

Adds smoke checks ensuring the eight new rules are wired into REGISTRY
and that the registry has reached the 18+ rule milestone.
"""

from __future__ import annotations

from app.diagnostics.rules import (
    REGISTRY,
    CategoryRankDropRule,
    CitationAttributionMismatchRule,
    CitationGrowthSurgeRule,
    CompetitorRadicalGrowthRule,
    FirstPlaceLossRule,
    GeoScoreDropSevereRule,
    TopicLossRule,
    WikiMissingRule,
)


def test_batch3_rules_registered() -> None:
    assert GeoScoreDropSevereRule in REGISTRY
    assert CompetitorRadicalGrowthRule in REGISTRY
    assert CategoryRankDropRule in REGISTRY
    assert CitationAttributionMismatchRule in REGISTRY
    assert WikiMissingRule in REGISTRY
    assert TopicLossRule in REGISTRY
    assert FirstPlaceLossRule in REGISTRY
    assert CitationGrowthSurgeRule in REGISTRY


def test_registry_size_milestone() -> None:
    # 10 prior rules + 8 new = 18; the broader 25+ target is multi-PR.
    assert len(REGISTRY) >= 18


def test_batch3_metadata_consistent() -> None:
    for cls in (
        GeoScoreDropSevereRule,
        CompetitorRadicalGrowthRule,
        CategoryRankDropRule,
        CitationAttributionMismatchRule,
        WikiMissingRule,
        TopicLossRule,
        FirstPlaceLossRule,
        CitationGrowthSurgeRule,
    ):
        assert cls.rule_id, f"{cls.__name__} missing rule_id"
        assert cls.category, f"{cls.__name__} missing category"
        assert cls.rule_id.endswith("_v1"), f"{cls.__name__} rule_id should end _v1"
