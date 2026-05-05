"""Phase D — registry membership tests for the fourth rule batch.

Adds smoke checks ensuring the five new rules are wired into REGISTRY
and that the registry has reached the 23+ rule milestone (within 2 of
the 25+ PRD target).
"""

from __future__ import annotations

from app.diagnostics.rules import (
    REGISTRY,
    AttributionAnchorLowRule,
    ContentGapRule,
    LlmEngineAnomalyRule,
    PersonaKeywordChangeRule,
    ProductFeatureNegativeRule,
)


def test_batch4_rules_registered() -> None:
    assert LlmEngineAnomalyRule in REGISTRY
    assert AttributionAnchorLowRule in REGISTRY
    assert ContentGapRule in REGISTRY
    assert ProductFeatureNegativeRule in REGISTRY
    assert PersonaKeywordChangeRule in REGISTRY


def test_registry_size_milestone() -> None:
    # 18 prior rules + 5 new = 23; within 2 of the 25+ PRD target.
    assert len(REGISTRY) >= 23


def test_batch4_metadata_consistent() -> None:
    for cls in (
        LlmEngineAnomalyRule,
        AttributionAnchorLowRule,
        ContentGapRule,
        ProductFeatureNegativeRule,
        PersonaKeywordChangeRule,
    ):
        assert cls.rule_id, f"{cls.__name__} missing rule_id"
        assert cls.category, f"{cls.__name__} missing category"
        assert cls.rule_id.endswith("_v1"), f"{cls.__name__} rule_id should end _v1"
