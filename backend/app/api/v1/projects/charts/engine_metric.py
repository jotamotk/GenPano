"""Engine-metric domain chart helpers.

Phase 5a of splitting `_charts_service.py` (Epic #885, design #886). Hosts
the engine-metric contract wrapper, evidence-based blocking helper, and the
per-engine rollup from fact rows. The public-API `get_engine_metrics` builder
remains in `_charts_service.py`.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from genpano_models import Project
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._analytics_contract import metric_blocking_inputs_from_evidence
from app.api.v1.projects._charts_dto import EngineMetricRow, EngineMetricsOut
from app.api.v1.projects._topic_analysis_service import (
    _as_float,
    _as_int,
    _fact_all_mention_count,
    _fact_target_mention_count,
)
from app.api.v1.projects.charts._contracts import (
    _chart_contract_update,
    _metric_evidence_dict,
)


def _apply_engine_metric_contract(
    items: list[EngineMetricRow],
    update: dict[str, Any],
) -> list[EngineMetricRow]:
    evidence = update.get("metric_formula_evidence") or {}

    return [
        item.model_copy(
            update={
                "mention_rate": None
                if metric_blocking_inputs_from_evidence(
                    "mention_rate", _metric_evidence_dict(evidence, "coverage")
                )
                else item.mention_rate,
                "sov": None
                if metric_blocking_inputs_from_evidence(
                    "sov", _metric_evidence_dict(evidence, "sov")
                )
                else item.sov,
                "citation_rate": None
                if metric_blocking_inputs_from_evidence(
                    "citation", _metric_evidence_dict(evidence, "citation")
                )
                else item.citation_rate,
                "sentiment": None
                if metric_blocking_inputs_from_evidence(
                    "sentiment", _metric_evidence_dict(evidence, "sentiment")
                )
                else item.sentiment,
            }
        )
        for item in items
    ]


async def _with_engine_metric_contract(
    out: EngineMetricsOut,
    session: AsyncSession,
    project: Project,
    from_d: date,
    to_d: date,
    *,
    source_provenance: list[str],
    brand_id: int | None = None,
) -> EngineMetricsOut:
    update = await _chart_contract_update(
        session,
        project,
        from_d,
        to_d,
        out,
        metric_keys=["mention_rate", "sov", "citation", "sentiment"],
        source_provenance=source_provenance,
        brand_id=brand_id,
        require_analyzer_package=True,
    )
    if not update:
        return out
    update["items"] = _apply_engine_metric_contract(out.items, update)
    return out.model_copy(update=update)


def _engine_metric_rows_from_facts(
    fact_rows: list[dict[str, Any]],
) -> tuple[list[EngineMetricRow], int]:
    engine_bucket: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "responses": set(),
            "denominator_response_ids": set(),
            "target_response_ids": set(),
            "cited_target_response_ids": set(),
            "has_citation_input": False,
            "target_mentions": 0,
            "all_mentions": 0,
            "sentiment": [],
        }
    )
    seen: set[int] = set()
    for row in fact_rows:
        rid = _as_int(row.get("response_id"))
        if rid is None or rid in seen:
            continue
        seen.add(rid)
        engine = str(row.get("target_llm") or row.get("response_target_llm") or "unknown")
        target_mentions = _fact_target_mention_count(row)
        all_mentions = _fact_all_mention_count(row, target_mentions)
        engine_bucket[engine]["responses"].add(rid)
        engine_bucket[engine]["denominator_response_ids"].add(rid)
        if row.get("citation_count") is not None:
            engine_bucket[engine]["has_citation_input"] = True
        if target_mentions > 0:
            engine_bucket[engine]["target_response_ids"].add(rid)
            if int(row.get("citation_count") or 0) > 0:
                engine_bucket[engine]["cited_target_response_ids"].add(rid)
        engine_bucket[engine]["target_mentions"] += target_mentions
        engine_bucket[engine]["all_mentions"] += all_mentions
        target_mentions = _fact_target_mention_count(row)
        sentiment = (
            _as_float(row.get("target_sentiment_score"))
            if target_mentions > 0
            else _as_float(row.get("sentiment_score"))
        )
        if sentiment is not None:
            engine_bucket[engine]["sentiment"].append(sentiment)
    items = [
        EngineMetricRow(
            engine=engine,
            mention_rate=round(
                len(values["target_response_ids"]) / len(values["denominator_response_ids"]),
                4,
            )
            if values["denominator_response_ids"]
            else None,
            sov=round(values["target_mentions"] / values["all_mentions"], 4)
            if values["all_mentions"] and values["all_mentions"] > values["target_mentions"]
            else None,
            citation_rate=round(
                len(values["cited_target_response_ids"]) / len(values["target_response_ids"]),
                4,
            )
            if values["target_response_ids"] and values["has_citation_input"]
            else None,
            sentiment=round(sum(values["sentiment"]) / len(values["sentiment"]), 3)
            if values["sentiment"]
            else None,
        )
        for engine, values in sorted(engine_bucket.items())
        if values["responses"]
    ]
    return items, len(seen)
