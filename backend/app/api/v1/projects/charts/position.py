"""Position-distribution domain chart helpers.

Phase 5b of splitting `_charts_service.py` (Epic #885, design #886). Hosts
the per-fact-row rank bucketization. The public-API `get_position_distribution`
builder remains in `_charts_service.py`.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from app.api.v1.projects._charts_dto import PositionBucketRow
from app.api.v1.projects._topic_analysis_service import _as_int, _fact_target_mention_count


def _position_distribution_from_facts(
    fact_rows: list[dict[str, Any]],
) -> tuple[list[PositionBucketRow], int, int]:
    buckets: OrderedDict[str, int] = OrderedDict(
        [("Top1", 0), ("Top3", 0), ("Top5", 0), ("Top10", 0), ("11+", 0), ("Unmentioned", 0)]
    )
    seen: set[int] = set()
    for row in fact_rows:
        rid = _as_int(row.get("response_id"))
        if rid is None or rid in seen:
            continue
        seen.add(rid)
        if _fact_target_mention_count(row) <= 0:
            continue
        rank = _as_int(row.get("min_position_rank") or row.get("target_brand_rank"))
        if rank is None:
            buckets["Unmentioned"] += 1
        elif rank == 1:
            buckets["Top1"] += 1
        elif rank <= 3:
            buckets["Top3"] += 1
        elif rank <= 5:
            buckets["Top5"] += 1
        elif rank <= 10:
            buckets["Top10"] += 1
        else:
            buckets["11+"] += 1
    total = sum(buckets.values())
    return (
        [
            PositionBucketRow(
                bucket=k,
                count=v,
                pct=round((v / total * 100) if total else 0.0, 2),
            )
            for k, v in buckets.items()
        ],
        total,
        len(seen),
    )
