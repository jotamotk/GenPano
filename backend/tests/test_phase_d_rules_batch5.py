"""Phase D — registry membership tests for the fifth (final) rule batch.

Adds smoke checks ensuring the four new rules are wired into REGISTRY
and that the registry has reached the 25+ PRD target. Also asserts
PLANNED_CATEGORIES is now empty (all PRD §4.7.1.1 categories shipped).
"""

from __future__ import annotations

from app.diagnostics.rules import (
    PLANNED_CATEGORIES,
    REGISTRY,
    NarrativeDriftRule,
    ProductRemissionRule,
    SameGroupShareLowRule,
    TopicEmergingMissedRule,
)


def test_batch5_rules_registered() -> None:
    assert NarrativeDriftRule in REGISTRY
    assert TopicEmergingMissedRule in REGISTRY
    assert ProductRemissionRule in REGISTRY
    assert SameGroupShareLowRule in REGISTRY


def test_registry_meets_prd_target() -> None:
    # 23 prior rules + 4 new = 27 — exceeds the PRD §4.7.1.1 25+ target.
    assert len(REGISTRY) >= 25


def test_planned_categories_empty() -> None:
    assert PLANNED_CATEGORIES == [], "All PRD §4.7.1.1 categories shipped; queue should be empty."


def test_batch5_metadata_consistent() -> None:
    for cls in (
        NarrativeDriftRule,
        TopicEmergingMissedRule,
        ProductRemissionRule,
        SameGroupShareLowRule,
    ):
        assert cls.rule_id, f"{cls.__name__} missing rule_id"
        assert cls.category, f"{cls.__name__} missing category"
        assert cls.rule_id.endswith("_v1"), f"{cls.__name__} rule_id should end _v1"
