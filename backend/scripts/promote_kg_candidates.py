"""One-shot CLI for KG candidate promotion.

Usage:
    cd backend
    uv run python scripts/promote_kg_candidates.py [--limit N] [--dry-run]

Idempotent. Safe to re-run. The Celery task `app.tasks.kg.promote_candidates`
calls the same function on a 15-min cadence; this script is for ops to
force a drain or to verify behaviour after an admin bulk-approve.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.kg.promote import promote_approved_candidates


async def _main(limit: int, dry_run: bool) -> int:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, future=True)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        summary = await promote_approved_candidates(session, limit=limit, dry_run=dry_run)
    await engine.dispose()
    print(json.dumps(summary, indent=2))
    return 0


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=500, help="max candidates per run")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would happen without persisting",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(_main(args.limit, args.dry_run)))


if __name__ == "__main__":
    main()
