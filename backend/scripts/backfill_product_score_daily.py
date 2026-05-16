"""Issue #1040 — Backfill `product_score_daily` for a brand over N days.

Why this exists
---------------
The Celery task ``geo_tracker.tasks.celery_tasks.aggregate_daily_scores``
(which populates ``product_score_daily`` / ``geo_score_daily`` /
``industry_benchmark_daily`` / ``topic_score_daily``) historically had no
beat schedule. As a result, on every deploy where the analyzer was already
producing fresh ``response_analyses`` / ``brand_mentions`` rows, the
``/api/v1/projects/<id>/products`` page still rendered every per-product
metric column (``mention_rate``, ``sov``, ``avg_sentiment``, ``ranking``,
``trend_30d``) as ``--`` because the rollup table the products service
reads from (``product_score_daily``) was empty.

The companion change in this PR adds a daily beat entry that runs the
task at 04:00 UTC, but that only fixes the FUTURE: for any brand whose
analyzer has been writing for N days, we still need to walk those N days
once to populate the table. That's what this script does.

What it does
------------
For a given ``--brand-id``, walks the last ``--days`` days (default 30)
in chronological order and calls ``Aggregator.aggregate_daily(date,
brand_id)`` once per day. The aggregator is idempotent by construction
(``_clear_existing_daily_aggregates`` deletes existing rows for the
(brand_id, date) scope before re-inserting), so re-running this script
is safe.

What it does NOT do
-------------------
- It does NOT analyze any responses — it assumes ``ResponseAnalysis``
  rows already exist for the days you're backfilling. If they don't,
  run the analyzer first (``run_daily_analysis`` Celery task or the
  ``geo_tracker.analyzer.cli run-daily`` CLI).
- It does NOT modify the beat schedule or trigger any Celery work; it
  invokes the aggregator directly in-process against the live DB.

Usage
-----
From the deploy host (where ``DATABASE_URL`` points at the prod DB):

    cd backend
    uv run python -m scripts.backfill_product_score_daily \\
        --brand-id 24 --days 90

For BestCoffer specifically (brand_id=24, per
``geo_tracker/tests/test_issue_827_bestcoffer_v4_coverage.py:188``):

    uv run python -m scripts.backfill_product_score_daily --brand-id 24 --days 90
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Make geo_tracker importable: the backend package and the geo_tracker
# package both live under the repo root, but only `backend/` is on the
# path by default. Mirror the pattern from
# `backend/tests/test_issue_588_pipeline_profile_analyzer.py:11-13`.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("backfill_product_score_daily")


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _day_sequence(*, days: int, end_date: datetime) -> list[datetime]:
    """Return the ``days`` days ending at ``end_date`` (inclusive) in
    chronological (oldest-first) order.

    Each entry is normalized to 00:00:00 UTC so the aggregator's
    ``_clear_existing_daily_aggregates`` matches the date_start it
    derives internally (``date.replace(hour=0, minute=0, second=0,
    microsecond=0)``).
    """
    if days < 1:
        return []
    anchor = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
    return [anchor - timedelta(days=offset) for offset in range(days - 1, -1, -1)]


async def _aggregate_one_day(
    *,
    sessionmaker: async_sessionmaker[Any],
    date: datetime,
    brand_id: int,
) -> dict[str, int]:
    """Run the aggregator for a single (date, brand_id) in its own session.

    Using a fresh session per day keeps transaction scope tight: if one
    day fails the rest can still proceed, and we don't accumulate session
    state across 30/90 day loops.
    """
    # Lazy import: the aggregator pulls in `geo_tracker.db.models` which
    # only resolves once `_REPO_ROOT` is on `sys.path`.
    from geo_tracker.analyzer.aggregator import Aggregator

    async with sessionmaker() as session:
        aggregator = Aggregator(session)
        stats = await aggregator.aggregate_daily(date, brand_id)
    return stats


async def backfill(
    *,
    brand_id: int,
    days: int,
    end_date: datetime | None = None,
) -> list[dict[str, Any]]:
    """Run the aggregator day-by-day for the requested window.

    Returns one summary dict per day with ``date``, ``stats``, and an
    ``error`` field (``None`` on success).
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url, future=True)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    sequence = _day_sequence(days=days, end_date=end_date or _utcnow())
    log.info(
        "Backfill starting: brand_id=%d days=%d window=%s..%s",
        brand_id,
        days,
        sequence[0].date().isoformat() if sequence else "(none)",
        sequence[-1].date().isoformat() if sequence else "(none)",
    )

    results: list[dict[str, Any]] = []
    try:
        for d in sequence:
            try:
                stats = await _aggregate_one_day(sessionmaker=sm, date=d, brand_id=brand_id)
                product_rows = stats.get("product_score", 0)
                log.info(
                    "  %s brand=%d product_score=%d geo=%d topic=%d benchmark=%d",
                    d.date().isoformat(),
                    brand_id,
                    product_rows,
                    stats.get("geo_score_daily", 0),
                    stats.get("topic_score", 0),
                    stats.get("industry_benchmark", 0),
                )
                results.append({"date": d.date().isoformat(), "stats": stats, "error": None})
            except Exception as exc:
                # Don't abort the whole window if one day blows up — the
                # aggregator is idempotent so re-running just that day
                # later (or this whole script) is cheap.
                log.exception("  %s brand=%d FAILED: %s", d.date().isoformat(), brand_id, exc)
                results.append({"date": d.date().isoformat(), "stats": {}, "error": str(exc)})
    finally:
        await engine.dispose()

    successes = sum(1 for r in results if r["error"] is None)
    total_product_rows = sum(int(r["stats"].get("product_score", 0) or 0) for r in results)
    log.info(
        "Backfill complete: brand_id=%d days_attempted=%d days_ok=%d product_score_rows_written=%d",
        brand_id,
        len(results),
        successes,
        total_product_rows,
    )
    return results


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill product_score_daily (and the other daily-aggregate "
            "tables) for a brand over N days. See module docstring for "
            "full context and the Issue #1040 reference."
        )
    )
    parser.add_argument(
        "--brand-id",
        type=int,
        required=True,
        help="Brand ID to aggregate. BestCoffer = 24.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days of history to backfill, ending today (default 30).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.days < 1:
        log.error("--days must be >= 1 (got %d)", args.days)
        return 2
    asyncio.run(backfill(brand_id=args.brand_id, days=args.days))
    return 0


if __name__ == "__main__":
    sys.exit(main())
