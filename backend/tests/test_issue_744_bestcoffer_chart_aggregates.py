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
    """Issue #948 follow-up + Issue #1225 revision (2026-05-18): the per-day
    citation metric must compute ``target_attributed_citations /
    all_window_citations``, NOT ``(any target-mentioning response has any
    citation) / (target-mentioning responses)``. The old set-identity
    formula collapsed to 1.0 the moment the LLM emitted citations on a
    target-mentioning response. The interim #948 denominator
    (target-mentioning responses' citation_count_sum) ALSO degenerated to
    100% when LLM responses did not cite competitor official domains —
    fixed in #1225 by moving the denominator to the window-total citation
    count provided by ``context.evidence_counts["total_citation_count_window"]``.

    This test pins the corrected formula: 5 target-attributed citations
    out of 10 window-total → 0.5.
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
        # Issue #1225: per-day target sum is the numerator; the window
        # total comes from the analytics contract context below.
        "citation_count_sum": 10,
        "target_citation_count_sum": 5,
    }
    context = AnalyticsContractContext(
        project_scope=ProjectScope(
            project_id="project-744",
            primary_brand_id=24,
            requested_brand_id=24,
        ),
        state="ok",
        state_reason="data_available",
        formula_status=FORMULA_OK_STATUS,
        evidence_counts={"total_citation_count_window": 10},
        source_provenance=["admin_facts"],
    )

    assert _fact_metric_value("citation", bucket, context=context) == 0.5


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
            # Issue #1225: per the new citation_share definition the
            # denominator is the window-total citation count surfaced by
            # the contract context. 5 + 0 + 5 = 10 citations across the
            # three fixture responses.
            evidence_counts={
                "geo_score_daily_rows": 1,
                "total_citation_count_window": 10,
            },
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
