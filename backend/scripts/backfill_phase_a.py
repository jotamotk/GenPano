"""Phase A.11 — 30-day analyzer-extension backfill script.

Populates the Phase A extension tables (BrandOfficialDomain stub seeds,
DomainAuthority defaults, EngineHealthDaily / ProxyHealthDaily zero rows
for active brands and engines) so the admin dashboards have non-empty
fixtures from day one.

This is a one-shot operator script — NOT a test, NOT a Celery task. Run
it once after a fresh deployment:

    cd backend
    uv run python scripts/backfill_phase_a.py [--days 30] [--dry-run]

Idempotent: re-running won't create duplicate rows because we check
existence first. Use --dry-run to see what would be inserted without
committing.

What it does NOT do:
  - Backfill brand_mentions / sentiment_drivers — those need the
    actual analyzer pipeline (geo_tracker.analyzer) which is its own
    Celery workflow.
  - Run the full 30-day analyzer over historical llm_responses — that's
    Phase A.11 production-side per ADR-008. This script only seeds the
    Phase A extension tables we own in genpano_models so the admin views
    have data.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from genpano_models import (
    DomainAuthority,
    EngineHealthDaily,
    ProxyHealthDaily,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("backfill_phase_a")


# Default tier-1 official domain seeds (admin can edit later via UI).
DEFAULT_AUTHORITIES: list[dict[str, Any]] = [
    {"domain": "wikipedia.org", "tier": 1, "site_type": "encyclopedia", "confidence": 0.99},
    {"domain": "baike.baidu.com", "tier": 1, "site_type": "encyclopedia", "confidence": 0.95},
    {"domain": "zhihu.com", "tier": 2, "site_type": "qa", "confidence": 0.85},
    {"domain": "xiaohongshu.com", "tier": 2, "site_type": "social", "confidence": 0.80},
    {"domain": "weibo.com", "tier": 2, "site_type": "social", "confidence": 0.80},
    {"domain": "douyin.com", "tier": 2, "site_type": "social", "confidence": 0.78},
    {"domain": "bilibili.com", "tier": 2, "site_type": "social", "confidence": 0.75},
    {"domain": "wired.com", "tier": 1, "site_type": "news", "confidence": 0.90},
    {"domain": "techcrunch.com", "tier": 1, "site_type": "news", "confidence": 0.88},
    {"domain": "theverge.com", "tier": 1, "site_type": "news", "confidence": 0.88},
    {"domain": "36kr.com", "tier": 2, "site_type": "news", "confidence": 0.82},
]


# Engines to seed health rows for (matches Tracker adapter set).
DEFAULT_ENGINES = ["chatgpt", "doubao", "deepseek"]


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def backfill_domain_authorities(session: Any, *, dry_run: bool) -> int:
    """Insert default tier-1/2 authorities. Idempotent on `domain` PK."""
    inserted = 0
    for entry in DEFAULT_AUTHORITIES:
        existing = (
            await session.execute(
                select(DomainAuthority).where(DomainAuthority.domain == entry["domain"])
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        if dry_run:
            log.info(
                "[dry-run] would insert DomainAuthority %s tier=%d", entry["domain"], entry["tier"]
            )
        else:
            session.add(DomainAuthority(**entry))
        inserted += 1
    if not dry_run:
        await session.commit()
    return inserted


async def backfill_engine_health(session: Any, *, days: int, dry_run: bool) -> int:
    """Insert zero-attempt EngineHealthDaily rows for past `days` days x engines.

    These act as ground-zero fixtures so the admin engine-health page
    isn't empty until the real Celery aggregator starts writing.
    """
    inserted = 0
    today = _now().date()
    for engine in DEFAULT_ENGINES:
        for i in range(days):
            d = datetime.combine(today - timedelta(days=i), datetime.min.time())
            existing = (
                await session.execute(
                    select(EngineHealthDaily).where(
                        EngineHealthDaily.engine == engine,
                        EngineHealthDaily.date == d,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            if dry_run:
                log.info(
                    "[dry-run] would insert EngineHealthDaily engine=%s date=%s",
                    engine,
                    d.date().isoformat(),
                )
            else:
                session.add(
                    EngineHealthDaily(
                        engine=engine,
                        date=d,
                        total_attempts=0,
                        success_count=0,
                        failed_count=0,
                        success_rate=None,
                    )
                )
            inserted += 1
    if not dry_run:
        await session.commit()
    return inserted


async def backfill_proxy_health(
    session: Any, *, days: int, dry_run: bool, proxy_ids: list[int]
) -> int:
    """Same as engine_health but for proxies."""
    inserted = 0
    today = _now().date()
    for proxy_id in proxy_ids:
        for i in range(days):
            d = datetime.combine(today - timedelta(days=i), datetime.min.time())
            existing = (
                await session.execute(
                    select(ProxyHealthDaily).where(
                        ProxyHealthDaily.proxy_id == proxy_id,
                        ProxyHealthDaily.date == d,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            if dry_run:
                log.info(
                    "[dry-run] would insert ProxyHealthDaily proxy=%d date=%s",
                    proxy_id,
                    d.date().isoformat(),
                )
            else:
                session.add(
                    ProxyHealthDaily(
                        proxy_id=proxy_id,
                        date=d,
                        total_requests=0,
                        success_count=0,
                        success_rate=None,
                        is_blocked=False,
                    )
                )
            inserted += 1
    if not dry_run:
        await session.commit()
    return inserted


async def main(*, days: int, dry_run: bool, proxy_ids: list[int]) -> dict[str, int]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, future=True)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    log.info(
        "Backfill starting: days=%d dry_run=%s proxy_ids=%s db=%s",
        days,
        dry_run,
        proxy_ids,
        settings.database_url.split("@")[-1],  # don't log creds
    )
    async with sm() as session:
        d_count = await backfill_domain_authorities(session, dry_run=dry_run)
        e_count = await backfill_engine_health(session, days=days, dry_run=dry_run)
        p_count = await backfill_proxy_health(
            session, days=days, dry_run=dry_run, proxy_ids=proxy_ids
        )
    await engine.dispose()

    summary = {
        "domain_authorities_inserted": d_count,
        "engine_health_rows_inserted": e_count,
        "proxy_health_rows_inserted": p_count,
    }
    log.info("Backfill complete: %s", summary)
    return summary


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--days", type=int, default=30, help="Days of history (default 30)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be inserted without committing.",
    )
    parser.add_argument(
        "--proxy-ids",
        nargs="*",
        type=int,
        default=[1, 2, 3],
        help="Proxy IDs to seed (default: 1 2 3)",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    summary = asyncio.run(
        main(
            days=args.days,
            dry_run=args.dry_run,
            proxy_ids=args.proxy_ids,
        )
    )
    # Always exit 0 — the script is informational; missing data is reported
    # via the summary dict, not via exit code.
    sys.exit(0)
