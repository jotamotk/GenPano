"""Topic-heatmap domain chart helpers.

Phase 5c of splitting `_charts_service.py` (Epic #885, design #886). Hosts
the brand/topic heatmap matrix builder. The public-API `get_topic_heatmap`
builder remains in `_charts_service.py`.
"""

from __future__ import annotations

from typing import Any

from genpano_models import Project
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._charts_dto import HeatmapCell, HeatmapRow
from app.api.v1.projects._legacy_lookups import resolve_brand_names, resolve_topic_names
from app.api.v1.projects._topic_analysis_service import (
    _as_float,
    _as_int,
    _fact_target_mention_count,
)


async def _topic_heatmap_from_facts(
    session: AsyncSession,
    project: Project,
    fact_rows: list[dict[str, Any]],
    *,
    brand_id: int,
    metric: str,
    compare_with: list[int],
    top_n: int,
) -> tuple[list[HeatmapRow], int]:
    primary = brand_id

    topic_buckets: dict[int, dict[str, Any]] = {}
    seen: set[int] = set()
    for row in fact_rows:
        tid = _as_int(row.get("topic_id"))
        rid = _as_int(row.get("response_id"))
        if tid is None or rid is None or rid in seen:
            continue
        seen.add(rid)
        bucket = topic_buckets.setdefault(
            tid,
            {
                "name": row.get("topic_name") or f"topic-{tid}",
                "responses": set(),
                "target_responses": set(),
                "sentiments": [],
            },
        )
        bucket["responses"].add(rid)
        if _fact_target_mention_count(row) > 0:
            bucket["target_responses"].add(rid)
        target_mentions = _fact_target_mention_count(row)
        sentiment = (
            _as_float(row.get("target_sentiment_score"))
            if target_mentions > 0
            else _as_float(row.get("sentiment_score"))
        )
        if sentiment is not None:
            bucket["sentiments"].append(sentiment)

    top_topics = sorted(
        topic_buckets,
        key=lambda tid: (
            -len(topic_buckets[tid]["target_responses"]),
            -len(topic_buckets[tid]["responses"]),
            tid,
        ),
    )[:top_n]
    if not top_topics:
        return [], len(seen)

    topic_names = await resolve_topic_names(session, top_topics)
    brand_ids = [primary, *compare_with]
    brand_names = await resolve_brand_names(session, brand_ids)
    cells: list[HeatmapCell] = []
    for tid in top_topics:
        bucket = topic_buckets[tid]
        sample = len(bucket["responses"])
        value = None
        if metric == "sentiment":
            sentiments = bucket["sentiments"]
            if sentiments:
                value = round(sum(sentiments) / len(sentiments), 4)
        elif sample:
            value = round(len(bucket["target_responses"]) / sample, 4)
        cells.append(
            HeatmapCell(
                topic_id=tid,
                topic_label=topic_names.get(tid) or bucket["name"],
                value=value,
                sample=sample,
            )
        )
    rows = [HeatmapRow(brand_id=primary, brand_name=brand_names.get(primary), values=cells)]
    for bid in compare_with:
        rows.append(
            HeatmapRow(
                brand_id=bid,
                brand_name=brand_names.get(bid),
                values=[
                    HeatmapCell(
                        topic_id=cell.topic_id,
                        topic_label=cell.topic_label,
                        value=None,
                        sample=0,
                    )
                    for cell in cells
                ],
            )
        )
    return rows, len(seen)
