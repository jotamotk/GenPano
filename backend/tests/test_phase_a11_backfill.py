"""Phase A.11 — backfill script unit tests.

Tests exercise the helper functions directly against the test SQLite
fixture (db_session). The full main() script entry point is smoke-tested
separately by parsing args.
"""

from __future__ import annotations

import os

import pytest
from genpano_models import DomainAuthority, EngineHealthDaily, ProxyHealthDaily
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


# ── domain authority backfill ────────────────────────────


@pytest.mark.asyncio
async def test_backfill_domain_authorities_inserts_seeds(db_session: AsyncSession):
    from scripts.backfill_phase_a import (
        DEFAULT_AUTHORITIES,
        backfill_domain_authorities,
    )

    inserted = await backfill_domain_authorities(db_session, dry_run=False)
    assert inserted == len(DEFAULT_AUTHORITIES)

    # All seeds present
    rows = list((await db_session.execute(select(DomainAuthority))).scalars().all())
    assert len(rows) == len(DEFAULT_AUTHORITIES)
    domains = {r.domain for r in rows}
    assert "wikipedia.org" in domains
    assert "zhihu.com" in domains


@pytest.mark.asyncio
async def test_backfill_domain_authorities_idempotent(db_session: AsyncSession):
    from scripts.backfill_phase_a import backfill_domain_authorities

    first = await backfill_domain_authorities(db_session, dry_run=False)
    second = await backfill_domain_authorities(db_session, dry_run=False)
    assert first > 0
    assert second == 0


@pytest.mark.asyncio
async def test_backfill_domain_authorities_dry_run_no_writes(
    db_session: AsyncSession,
):
    from scripts.backfill_phase_a import backfill_domain_authorities

    inserted = await backfill_domain_authorities(db_session, dry_run=True)
    assert inserted > 0  # would-insert count

    # But no actual rows committed
    rows = (await db_session.execute(select(DomainAuthority))).scalars().all()
    assert list(rows) == []


# ── engine health backfill ───────────────────────────────


@pytest.mark.asyncio
async def test_backfill_engine_health_creates_zero_rows(db_session: AsyncSession):
    from scripts.backfill_phase_a import (
        DEFAULT_ENGINES,
        backfill_engine_health,
    )

    inserted = await backfill_engine_health(db_session, days=7, dry_run=False)
    expected = 7 * len(DEFAULT_ENGINES)
    assert inserted == expected

    rows = list((await db_session.execute(select(EngineHealthDaily))).scalars().all())
    assert len(rows) == expected
    # All engines covered
    engines = {r.engine for r in rows}
    assert engines == set(DEFAULT_ENGINES)
    # All rows are zero-attempt
    for r in rows:
        assert r.total_attempts == 0


@pytest.mark.asyncio
async def test_backfill_engine_health_idempotent(db_session: AsyncSession):
    from scripts.backfill_phase_a import backfill_engine_health

    first = await backfill_engine_health(db_session, days=3, dry_run=False)
    second = await backfill_engine_health(db_session, days=3, dry_run=False)
    assert first > 0
    assert second == 0


# ── proxy health backfill ────────────────────────────────


@pytest.mark.asyncio
async def test_backfill_proxy_health_creates_zero_rows(db_session: AsyncSession):
    from scripts.backfill_phase_a import backfill_proxy_health

    inserted = await backfill_proxy_health(db_session, days=5, dry_run=False, proxy_ids=[10, 20])
    assert inserted == 5 * 2  # 5 days x 2 proxies

    rows = list((await db_session.execute(select(ProxyHealthDaily))).scalars().all())
    assert len(rows) == 10
    proxy_ids = {r.proxy_id for r in rows}
    assert proxy_ids == {10, 20}


@pytest.mark.asyncio
async def test_backfill_proxy_health_idempotent(db_session: AsyncSession):
    from scripts.backfill_phase_a import backfill_proxy_health

    first = await backfill_proxy_health(db_session, days=3, dry_run=False, proxy_ids=[1])
    second = await backfill_proxy_health(db_session, days=3, dry_run=False, proxy_ids=[1])
    assert first > 0
    assert second == 0


# ── arg parsing ──────────────────────────────────────────


def test_arg_parser_defaults():
    from scripts.backfill_phase_a import _parse_args

    args = _parse_args([])
    assert args.days == 30
    assert args.dry_run is False
    assert args.proxy_ids == [1, 2, 3]


def test_arg_parser_dry_run_flag():
    from scripts.backfill_phase_a import _parse_args

    args = _parse_args(["--dry-run", "--days", "7", "--proxy-ids", "5", "10"])
    assert args.days == 7
    assert args.dry_run is True
    assert args.proxy_ids == [5, 10]
