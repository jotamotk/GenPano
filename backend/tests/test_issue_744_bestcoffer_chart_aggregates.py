"""Issue #744: BestCoffer analyzer chart aggregate regressions."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.api.v1.projects import _charts_service as charts_service
from app.api.v1.projects import _metrics_service as metrics_service
from app.api.v1.projects._analytics_contract import (
    FORMULA_OK_STATUS,
    AnalyticsContractContext,
    ProjectScope,
)
from app.api.v1.projects._metrics_service import _fact_metric_value
from app.api.v1.projects._topic_analysis_service import AnalysisFilters


def test_admin_fact_citation_rate_target_attributed_over_eligible_project() -> None:
    """Issue #948 follow-up: the per-day citation metric must compute
    ``target_attributed_citations / eligible_project_citations``, NOT
    ``(any target-mentioning response has any citation) /
    (target-mentioning responses)``. The old set-identity formula
    collapsed to 1.0 the moment the LLM emitted citations on a
    target-mentioning response (see live bestCoffer evidence: 引用份额
    rendered 100% post-PR #980 deploy while project-level attributed
    was 70/895 ≈ 7.8%).

    This test pins the corrected formula: 5 target-attributed citations
    out of 10 total → 0.5.
    """
    bucket = {
        "response_ids": {101, 102},
        "mention_denominator_response_ids": set(),
        "target_mention_response_ids": set(),
        "citation_target_response_ids": {101, 102},
        "cited_target_response_ids": {101},
        "has_citation_input": True,
        "has_target_mention_input": True,
        "has_all_mention_input": True,
        "target_mentions": 0,
        "all_mentions": 0,
        "ranks": [],
        "sentiment_scores": [],
        "sentiment_label_count": 0,
        # Issue #948 follow-up: per-day attributed + total sums replace
        # the previous set-identity ratio.
        "citation_count_sum": 10,
        "target_citation_count_sum": 5,
    }

    assert _fact_metric_value("citation", bucket) == 0.5


@pytest.mark.asyncio
async def test_admin_fact_metric_series_target_attributed_over_eligible_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end pin of the per-day citation metric series produced by
    ``_metrics_from_admin_facts``. Fixture seeds three responses on one
    day:

    - 101: target_mentioned, 5 citations of which 5 are attributed to target.
    - 102: target_mentioned, 0 citations.
    - 103: not target-mentioned, 5 citations (zero attributed to target by
      construction).

    Old (incorrect) formula: ``(1 with target citation) / (2 target-mentioned)``
    = 0.5 — collapsed when the LLM emitted any citations on a target row.

    Corrected formula: ``5 target-attributed / 10 total = 0.5``. Equal in
    THIS fixture because the numbers were chosen to produce the same
    headline value, but with different semantics. The companion live
    case (bestCoffer 70 attributed / 895 total ≈ 7.8%) now reflects the
    project share correctly instead of the previous 100% artifact.
    """
    day = date(2026, 5, 13)

    async def fact_rows(*args: object, **kwargs: object) -> list[dict[str, object]]:
        return [
            {
                "response_id": 101,
                "response_created_at": day,
                "target_mention_count": 1,
                "all_mention_count": 1,
                "citation_count": 5,
                "target_citation_count": 5,
            },
            {
                "response_id": 102,
                "response_created_at": day,
                "target_mention_count": 1,
                "all_mention_count": 1,
                "citation_count": 0,
                "target_citation_count": 0,
            },
            {
                "response_id": 103,
                "response_created_at": day,
                "target_mention_count": 0,
                "all_mention_count": 1,
                "citation_count": 5,
                "target_citation_count": 0,
            },
        ]

    async def contract_context(*args: object, **kwargs: object) -> AnalyticsContractContext:
        return AnalyticsContractContext(
            project_scope=ProjectScope(
                project_id="project-744",
                primary_brand_id=24,
                requested_brand_id=24,
            ),
            state="ok",
            state_reason="data_available",
            formula_status=FORMULA_OK_STATUS,
            evidence_counts={"geo_score_daily_rows": 1},
            source_provenance=["admin_facts"],
        )

    monkeypatch.setattr(metrics_service, "_fact_rows", fact_rows)
    monkeypatch.setattr(metrics_service, "build_contract_context", contract_context)

    project = SimpleNamespace(id="project-744", primary_brand_id=24)
    out = await metrics_service._metrics_from_admin_facts(
        object(),
        project,  # type: ignore[arg-type]
        brand_id=24,
        brand_id_override=None,
        requested=["citation"],
        from_d=day,
        to_d=day,
        filters=AnalysisFilters(),
    )

    citation_series = out.series[0]
    assert citation_series.metric == "citation"
    # 5 target-attributed / (5 + 0 + 5) total = 0.5
    assert citation_series.points[0].value == 0.5


def test_engine_metric_rows_use_cited_target_response_set() -> None:
    items, evidence_count = charts_service._engine_metric_rows_from_facts(
        [
            {
                "response_id": 201,
                "target_llm": "chatgpt",
                "target_mention_count": 1,
                "all_mention_count": 1,
                "citation_count": 5,
            },
            {
                "response_id": 202,
                "target_llm": "chatgpt",
                "target_mention_count": 1,
                "all_mention_count": 1,
                "citation_count": 0,
            },
            {
                "response_id": 203,
                "target_llm": "chatgpt",
                "target_mention_count": 0,
                "all_mention_count": 1,
                "citation_count": 9,
            },
        ]
    )

    assert evidence_count == 3
    assert len(items) == 1
    assert items[0].engine == "chatgpt"
    assert items[0].citation_rate == 0.5
