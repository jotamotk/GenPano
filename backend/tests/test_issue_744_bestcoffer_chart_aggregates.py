"""Issue #744: BestCoffer analyzer chart aggregate regressions."""

from __future__ import annotations

from app.api.v1.projects._metrics_service import _fact_metric_value


def test_admin_fact_citation_share_is_capped_to_response_share() -> None:
    bucket = {
        "response_ids": {101, 102},
        "mention_denominator_response_ids": set(),
        "target_mention_response_ids": set(),
        "has_target_mention_input": True,
        "has_all_mention_input": True,
        "target_mentions": 0,
        "all_mentions": 0,
        "ranks": [],
        "sentiment_scores": [],
        "sentiment_label_count": 0,
        "citation_count": 3,
    }

    assert _fact_metric_value("citation", bucket) == 1.0
