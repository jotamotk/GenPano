"""Issue #1225: citation_share denominator revised to ALL window citations.

PRD-APP-ANALYTICS-003 was revised 2026-05-18 (AI Leader decision in the
#1225 thread): the citation_share denominator is no longer the
target-mentioning responses' citation_count sum (which degenerated to 100%
whenever LLM responses for a project failed to cite competitor official
domains — the captured bestCoffer evidence shape from probe run
26026560992). The new denominator is the window-cumulative count of every
citation_sources row, regardless of brand attribution, surfaced via
``AnalyticsContractContext.evidence_counts["total_citation_count_window"]``.

Captured bestCoffer evidence shape (probe run 26026560992):

- target-attributed citation_sources in window: 127
- unresolved citation_sources in window: 1243
- window total: 1370

Pre-#1234 (the citation_mapper symmetry fix landing on the parent branch):
``127 / 1370 ≈ 0.0927`` — a meaningful share instead of the previous 1.0.

Post-#1234 (200 bestcoffer.com rows move from unresolved → target):
``327 / 1370 ≈ 0.2387``. The window total is unchanged because the same
citation rows are merely re-attributed.
"""

from __future__ import annotations

import pytest

from app.api.v1.projects._analytics_contract import (
    FORMULA_OK_STATUS,
    AnalyticsContractContext,
    ProjectScope,
)
from app.api.v1.projects._metrics_service import _fact_metric_value


def _bestcoffer_context(window_total: int) -> AnalyticsContractContext:
    return AnalyticsContractContext(
        project_scope=ProjectScope(
            project_id="project-1225",
            primary_brand_id=24,
            requested_brand_id=24,
        ),
        state="ok",
        state_reason="data_available",
        formula_status=FORMULA_OK_STATUS,
        # PRD-APP-ANALYTICS-003 revised denominator. The other evidence
        # count is preserved because adjacent code paths still read it
        # (per the dispatch's forbidden-scope note).
        evidence_counts={
            "total_citation_count_window": window_total,
            "citation_source_count": 127,
        },
        source_provenance=["admin_facts"],
    )


def _bucket(target_citation_count_sum: int, citation_count_sum: int) -> dict:
    return {
        "response_ids": set(),
        "mention_denominator_response_ids": set(),
        "target_mention_response_ids": set(),
        "citation_target_response_ids": set(),
        "cited_target_response_ids": set(),
        "has_citation_input": True,
        "has_target_mention_input": True,
        "has_all_mention_input": True,
        "target_mentions": 0,
        "all_mentions": 0,
        "ranks": [],
        "sentiment_scores": [],
        "sentiment_label_count": 0,
        # `citation_count_sum` is the legacy per-day sum that the
        # pre-#1225 formula divided by. Retained on the bucket so other
        # code paths can still read it; not used as the denominator any
        # more.
        "citation_count_sum": citation_count_sum,
        "target_citation_count_sum": target_citation_count_sum,
    }


def test_citation_share_pre_1234_window_denominator() -> None:
    """Pre-#1234 attribution: 127 target-attributed / 1370 window total
    ≈ 0.0927. Before #1225 this would have rendered as 1.0 because the old
    denominator was bucket["citation_count_sum"] = 127.
    """
    context = _bestcoffer_context(window_total=1370)
    bucket = _bucket(target_citation_count_sum=127, citation_count_sum=127)

    assert _fact_metric_value("citation", bucket, context=context) == 0.0927


def test_citation_share_post_1234_attribution_lift() -> None:
    """Post-#1234 citation_mapper symmetry fix: 200 bestcoffer.com rows
    move from unresolved → target. Window total is unchanged (same rows,
    different attribution); numerator rises from 127 to 327. Resulting
    share ≈ 0.2387.
    """
    context = _bestcoffer_context(window_total=1370)
    bucket = _bucket(target_citation_count_sum=327, citation_count_sum=327)

    assert _fact_metric_value("citation", bucket, context=context) == 0.2387


def test_citation_share_empty_window_returns_none() -> None:
    """Empty window (no citations captured anywhere in the time window):
    the metric must return ``None`` so the contract can render as
    ``partial``/``empty`` rather than a misleading zero.
    """
    context = _bestcoffer_context(window_total=0)
    bucket = _bucket(target_citation_count_sum=0, citation_count_sum=0)

    assert _fact_metric_value("citation", bucket, context=context) is None


def test_citation_share_target_positive_window_zero_returns_none() -> None:
    """Defensive: target-attributed > 0 but window total = 0 should never
    happen (the window total is a superset of target-attributed), but if
    it ever does we must return ``None`` rather than divide by zero.
    """
    context = _bestcoffer_context(window_total=0)
    bucket = _bucket(target_citation_count_sum=5, citation_count_sum=5)

    assert _fact_metric_value("citation", bucket, context=context) is None


@pytest.mark.parametrize(
    "target_citations,window_total,expected",
    [
        (127, 1370, 0.0927),
        (327, 1370, 0.2387),
    ],
)
def test_citation_share_matches_captured_bestcoffer_shape(
    target_citations: int, window_total: int, expected: float
) -> None:
    """Pin the two captured-evidence ratios in one parametrized check so
    a future regression can't quietly shift either anchor."""
    context = _bestcoffer_context(window_total=window_total)
    bucket = _bucket(
        target_citation_count_sum=target_citations,
        citation_count_sum=target_citations,
    )

    assert _fact_metric_value("citation", bucket, context=context) == expected
