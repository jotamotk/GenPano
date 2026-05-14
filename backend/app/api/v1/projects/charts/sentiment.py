"""Sentiment-domain helpers and contract wrappers.

Phase 3 of splitting `_charts_service.py` (Epic #885, design #886). This
module currently hosts the dependency-light sentiment functions: contract
wrappers, missing-output factories, polarity classification, and the SQL
sentiment-label expression. The heavier builders (`_sentiment_by_engine_*`,
`get_sentiment_*`) remain in `_charts_service.py` for now because they depend
on the shared fact-rollup helpers (`_admin_fact_rows`, `_fact_response_ids`,
...) that are moved separately in a later phase.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from genpano_models import Project
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._analytics_contract import (
    FORMULA_MISSING_INPUTS_STATUS,
    formula_diagnostics_for,
)
from app.api.v1.projects._charts_dto import (
    SentimentByEngineOut,
    SentimentTrendByEngineOut,
)
from app.api.v1.projects._topic_analysis_service import _as_float, _as_int
from app.api.v1.projects.charts._contracts import (
    _chart_contract_update,
    _contract_metric_blocked,
)


async def _with_sentiment_by_engine_contract(
    out: SentimentByEngineOut,
    session: AsyncSession,
    project: Project,
    from_d: date,
    to_d: date,
    *,
    source_provenance: list[str],
    brand_id: int | None = None,
) -> SentimentByEngineOut:
    update = await _chart_contract_update(
        session,
        project,
        from_d,
        to_d,
        out,
        metric_keys=["sentiment"],
        source_provenance=source_provenance,
        brand_id=brand_id,
        require_analyzer_package=True,
    )
    if not update:
        return out
    if _contract_metric_blocked(update, "sentiment"):
        update["items"] = []
    return out.model_copy(update=update)


async def _with_sentiment_trend_contract(
    out: SentimentTrendByEngineOut,
    session: AsyncSession,
    project: Project,
    from_d: date,
    to_d: date,
    *,
    source_provenance: list[str],
    brand_id: int | None = None,
) -> SentimentTrendByEngineOut:
    update = await _chart_contract_update(
        session,
        project,
        from_d,
        to_d,
        out,
        metric_keys=["sentiment"],
        source_provenance=source_provenance,
        brand_id=brand_id,
        require_analyzer_package=True,
        allow_geo_score_daily_without_analyzer=True,
    )
    if not update:
        return out
    if _contract_metric_blocked(update, "sentiment"):
        update["items"] = []
    else:
        update.update(
            {
                "state": out.state,
                "state_reason": out.state_reason,
                "missing_inputs": out.missing_inputs,
                "missing_sources": out.missing_sources,
                "missing_reasons": out.missing_reasons,
                "formula_status": out.formula_status,
                "formula_diagnostics": out.formula_diagnostics,
            }
        )
    return out.model_copy(update=update)


def _sentiment_label_sql() -> str:
    return "LOWER(TRIM(COALESCE(bm.sentiment, '')))"


def _fact_sentiment_score_response_count(rows: list[dict[str, Any]]) -> int:
    ids = {
        _as_int(row.get("response_id"))
        for row in rows
        if _as_int(row.get("response_id")) is not None
        and (
            _as_float(row.get("target_sentiment_score")) is not None
            or _as_float(row.get("sentiment_score")) is not None
        )
    }
    return len({rid for rid in ids if rid is not None})


def _sentiment_by_engine_missing_out(
    *,
    project_id: str,
    period: dict[str, str],
    evidence_count: int,
    evidence_counts: dict[str, int],
    missing_inputs: list[str] | None = None,
) -> SentimentByEngineOut:
    missing_inputs = missing_inputs or [
        "brand_mentions.sentiment_score",
        "brand_mentions.sentiment",
    ]
    return SentimentByEngineOut(
        project_id=project_id,
        period=period,
        items=[],
        state="partial",
        state_reason="missing_formula_inputs",
        evidence_count=evidence_count,
        evidence_counts=evidence_counts,
        missing_inputs=missing_inputs,
        missing_sources=missing_inputs,
        formula_status=FORMULA_MISSING_INPUTS_STATUS,
        formula_diagnostics=formula_diagnostics_for(
            FORMULA_MISSING_INPUTS_STATUS,
            missing_inputs=missing_inputs,
        ),
        source_provenance=["brand_mentions", "llm_responses", "geo_score_daily"],
    )


def _sentiment_missing_out(
    *,
    project_id: str,
    period: dict[str, str],
    engines: list[str],
    evidence_count: int,
    evidence_counts: dict[str, int],
) -> SentimentTrendByEngineOut:
    missing_inputs = ["brand_mentions.sentiment_score", "brand_mentions.sentiment"]
    return SentimentTrendByEngineOut(
        project_id=project_id,
        period=period,
        engines=engines,
        items=[],
        state="partial",
        state_reason="missing_formula_inputs",
        evidence_count=evidence_count,
        evidence_counts=evidence_counts,
        missing_inputs=missing_inputs,
        missing_sources=missing_inputs,
        formula_status=FORMULA_MISSING_INPUTS_STATUS,
        formula_diagnostics=formula_diagnostics_for(
            FORMULA_MISSING_INPUTS_STATUS,
            missing_inputs=missing_inputs,
        ),
        source_provenance=["brand_mentions", "geo_score_daily"],
    )


def _polarity_from_score(score: object) -> str:
    value = _as_float(score)
    if value is None:
        return "neutral"
    if value > 0.05:
        return "positive"
    if value < -0.05:
        return "negative"
    return "neutral"


def _label_for_polarity(polarity: str) -> str:
    return {"positive": "Positive", "negative": "Negative", "neutral": "Neutral"}.get(
        polarity, "Neutral"
    )
