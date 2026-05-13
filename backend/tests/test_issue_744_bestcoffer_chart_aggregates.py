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


def test_admin_fact_citation_rate_uses_cited_target_response_set() -> None:
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
    }

    assert _fact_metric_value("citation", bucket) == 0.5


@pytest.mark.asyncio
async def test_admin_fact_metric_series_uses_cited_target_response_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    day = date(2026, 5, 13)

    async def fact_rows(*args: object, **kwargs: object) -> list[dict[str, object]]:
        return [
            {
                "response_id": 101,
                "response_created_at": day,
                "target_mention_count": 1,
                "all_mention_count": 1,
                "citation_count": 5,
            },
            {
                "response_id": 102,
                "response_created_at": day,
                "target_mention_count": 1,
                "all_mention_count": 1,
                "citation_count": 0,
            },
            {
                "response_id": 103,
                "response_created_at": day,
                "target_mention_count": 0,
                "all_mention_count": 1,
                "citation_count": 9,
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
