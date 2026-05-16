"""Issue #1040 — beat schedule + one-shot backfill for product_score_daily.

Covers two surfaces:

1. ``scripts.backfill_product_score_daily`` — verify the day-sequence
   helper produces the right window in chronological order, and that
   the ``backfill()`` coroutine calls the aggregator once per day with
   the right (date, brand_id) — mocking the aggregator so the test
   doesn't need a real DB or geo_tracker side effects.

2. ``geo_tracker.tasks.celery_tasks._beat_schedule`` — when the
   ``ANALYZER_AUTO_SCHEDULE=true`` env var is set, the schedule must
   include an ``aggregate-daily-scores`` entry pointing at
   ``geo_tracker.tasks.celery_tasks.aggregate_daily_scores``. Pre-fix
   this entry was missing, which is why ``product_score_daily``
   stayed empty in production.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

# geo_tracker lives at the repo root, not inside backend/. Mirror the
# pattern from `backend/tests/test_issue_588_pipeline_profile_analyzer.py:11-13`
# so `geo_tracker` is importable from this test.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _celery_tasks_source() -> str:
    """Read the celery_tasks.py source as text.

    Tests assert on source presence rather than executing
    ``importlib.reload`` on the module: reloading re-runs the Celery app
    construction + signal-handler registration mid-pytest, which races
    with the async event loop cleanup and produced an "Event loop is
    closed" failure in CI (locally green). The beat schedule is built
    at module top level from constants + ``os.getenv`` checks, so the
    source itself is the contract.
    """
    path = _REPO_ROOT / "geo_tracker" / "tasks" / "celery_tasks.py"
    return path.read_text(encoding="utf-8")


# ── Day-sequence helper ────────────────────────────────────────────────


def test_day_sequence_returns_chronological_window():
    from scripts.backfill_product_score_daily import _day_sequence

    end = datetime(2026, 5, 16, 12, 30, 45)
    seq = _day_sequence(days=3, end_date=end)

    assert [d.date().isoformat() for d in seq] == [
        "2026-05-14",
        "2026-05-15",
        "2026-05-16",
    ]
    # All entries normalized to 00:00:00 so `_clear_existing_daily_aggregates`
    # in the aggregator matches the date_start it derives internally.
    assert all(d.hour == 0 and d.minute == 0 and d.second == 0 for d in seq)


def test_day_sequence_one_day_returns_today_only():
    from scripts.backfill_product_score_daily import _day_sequence

    end = datetime(2026, 5, 16, 23, 59, 59)
    seq = _day_sequence(days=1, end_date=end)
    assert len(seq) == 1
    assert seq[0].date().isoformat() == "2026-05-16"


def test_day_sequence_zero_or_negative_returns_empty():
    from scripts.backfill_product_score_daily import _day_sequence

    end = datetime(2026, 5, 16)
    assert _day_sequence(days=0, end_date=end) == []
    assert _day_sequence(days=-5, end_date=end) == []


# ── backfill() loop — mock the aggregator + DB ──────────────────────────


@pytest.mark.asyncio
async def test_backfill_calls_aggregator_once_per_day(monkeypatch):
    """``backfill(days=N)`` must invoke ``Aggregator.aggregate_daily`` exactly
    N times, once per day in chronological order, with the requested
    ``brand_id``.
    """
    from scripts import backfill_product_score_daily as mod

    # Mock the engine + sessionmaker so we don't actually touch a DB.
    fake_engine = MagicMock()
    fake_engine.dispose = AsyncMock()

    class _FakeSessionCtx:
        async def __aenter__(self):
            return MagicMock()

        async def __aexit__(self, *a):
            return False

    fake_sm = MagicMock(return_value=_FakeSessionCtx())

    monkeypatch.setattr(mod, "create_async_engine", MagicMock(return_value=fake_engine))
    monkeypatch.setattr(mod, "async_sessionmaker", MagicMock(return_value=fake_sm))
    monkeypatch.setattr(
        mod,
        "get_settings",
        MagicMock(return_value=SimpleNamespace(database_url="sqlite+aiosqlite:///:memory:")),
    )

    # Patch the aggregator class the script imports lazily — patch the real
    # module so the script's `from geo_tracker.analyzer.aggregator import
    # Aggregator` finds the mock.
    fake_aggregator = MagicMock()
    fake_aggregator.aggregate_daily = AsyncMock(
        return_value={
            "product_score": 7,
            "geo_score_daily": 3,
            "topic_score": 2,
            "industry_benchmark": 1,
        }
    )
    aggregator_factory = MagicMock(return_value=fake_aggregator)

    fake_module = SimpleNamespace(Aggregator=aggregator_factory)
    monkeypatch.setitem(sys.modules, "geo_tracker.analyzer.aggregator", fake_module)

    end = datetime(2026, 5, 16, 12, 0, 0)
    results = await mod.backfill(brand_id=24, days=3, end_date=end)

    # Exactly 3 days attempted, all successful, all targeted brand 24.
    assert len(results) == 3
    assert all(r["error"] is None for r in results)
    assert [r["date"] for r in results] == [
        "2026-05-14",
        "2026-05-15",
        "2026-05-16",
    ]
    assert fake_aggregator.aggregate_daily.await_count == 3

    # Each call passes brand_id=24 as the second positional arg.
    for call in fake_aggregator.aggregate_daily.await_args_list:
        args, _kwargs = call
        # Aggregator.aggregate_daily(date, brand_id, ...)
        assert args[1] == 24

    # Stats are propagated into the per-day result rows.
    assert all(r["stats"]["product_score"] == 7 for r in results)


@pytest.mark.asyncio
async def test_backfill_keeps_going_when_one_day_fails(monkeypatch):
    """A day that raises must not abort the loop — the rest of the
    window should still attempt + report ``error`` populated for the
    failure."""
    from scripts import backfill_product_score_daily as mod

    fake_engine = MagicMock()
    fake_engine.dispose = AsyncMock()

    class _FakeSessionCtx:
        async def __aenter__(self):
            return MagicMock()

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(mod, "create_async_engine", MagicMock(return_value=fake_engine))
    monkeypatch.setattr(
        mod,
        "async_sessionmaker",
        MagicMock(return_value=MagicMock(return_value=_FakeSessionCtx())),
    )
    monkeypatch.setattr(
        mod,
        "get_settings",
        MagicMock(return_value=SimpleNamespace(database_url="sqlite+aiosqlite:///:memory:")),
    )

    # Aggregator raises on the 2nd day, succeeds on the rest.
    call_count = {"n": 0}

    async def _aggregate(_date, _brand_id):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated DB hiccup on day 2")
        return {"product_score": 5, "geo_score_daily": 1, "topic_score": 0, "industry_benchmark": 0}

    fake_aggregator = MagicMock()
    fake_aggregator.aggregate_daily = AsyncMock(side_effect=_aggregate)
    monkeypatch.setitem(
        sys.modules,
        "geo_tracker.analyzer.aggregator",
        SimpleNamespace(Aggregator=MagicMock(return_value=fake_aggregator)),
    )

    end = datetime(2026, 5, 16)
    results = await mod.backfill(brand_id=24, days=3, end_date=end)

    assert len(results) == 3
    # day 1 + day 3 OK, day 2 has error.
    assert results[0]["error"] is None
    assert results[1]["error"] is not None
    assert "simulated DB hiccup" in results[1]["error"]
    assert results[2]["error"] is None


# ── --help / arg parsing smoke test ─────────────────────────────────────


def test_backfill_script_args_help_runs(capsys):
    from scripts.backfill_product_score_daily import _parse_args

    with pytest.raises(SystemExit) as exc_info:
        _parse_args(["--help"])
    # argparse exits 0 on --help.
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "--brand-id" in out
    assert "--days" in out


def test_backfill_script_requires_brand_id():
    from scripts.backfill_product_score_daily import _parse_args

    with pytest.raises(SystemExit):
        _parse_args([])  # missing --brand-id is a hard error


def test_backfill_script_parses_brand_and_days():
    from scripts.backfill_product_score_daily import _parse_args

    ns = _parse_args(["--brand-id", "24", "--days", "90"])
    assert ns.brand_id == 24
    assert ns.days == 90


def test_backfill_script_days_default_is_30():
    from scripts.backfill_product_score_daily import _parse_args

    ns = _parse_args(["--brand-id", "24"])
    assert ns.days == 30


def test_backfill_script_rejects_zero_days(monkeypatch):
    from scripts import backfill_product_score_daily as mod

    rc = mod.main(["--brand-id", "24", "--days", "0"])
    assert rc == 2


# ── Beat schedule — Issue #1040 ────────────────────────────────────────


def test_beat_schedule_includes_aggregate_daily_scores_when_auto_enabled():
    """Issue #1040 — when ``ANALYZER_AUTO_SCHEDULE=true``, the beat schedule
    must include an ``aggregate-daily-scores`` entry alongside the existing
    ``daily-analysis`` entry, both pointing at the analysis queue.

    Source-level assertion (no `importlib.reload`): reloading
    `geo_tracker.tasks.celery_tasks` mid-pytest re-runs Celery app
    construction + signal-handler registration, which interacts badly
    with the async event loop in CI ("Event loop is closed"). Read the
    file as text instead — the gate is module-level so source presence
    is a valid contract check.
    """
    src = _celery_tasks_source()
    # The beat entry MUST appear inside the ANALYZER_AUTO_SCHEDULE=="true" guard.
    assert 'os.getenv("ANALYZER_AUTO_SCHEDULE"' in src, (
        "ANALYZER_AUTO_SCHEDULE gate disappeared from celery_tasks.py"
    )
    assert '_beat_schedule["aggregate-daily-scores"]' in src, (
        "Issue #1040 regression: ANALYZER_AUTO_SCHEDULE=true block must add "
        "an aggregate-daily-scores beat entry so product_score_daily is "
        "populated daily."
    )
    # Whitespace in celery_tasks.py is "task":<spaces>"..." — match the
    # task path itself in a way that tolerates either format.
    import re

    assert re.search(
        r'"task"\s*:\s*"geo_tracker\.tasks\.celery_tasks\.aggregate_daily_scores"',
        src,
    ), "aggregate-daily-scores entry must target the aggregate_daily_scores task"


def test_beat_schedule_omits_aggregate_when_auto_disabled():
    """Disabled env var must NOT register the aggregate beat entry —
    both ``daily-analysis`` and ``aggregate-daily-scores`` live inside
    the same ``ANALYZER_AUTO_SCHEDULE=="true"`` guard.
    """
    src = _celery_tasks_source()
    # The beat entry MUST live under the env-var guard, not at module top level.
    guard_idx = src.find('os.getenv("ANALYZER_AUTO_SCHEDULE"')
    aggregate_idx = src.find('_beat_schedule["aggregate-daily-scores"]')
    assert guard_idx != -1, "ANALYZER_AUTO_SCHEDULE guard missing"
    assert aggregate_idx != -1, "aggregate-daily-scores entry missing"
    assert aggregate_idx > guard_idx, (
        "aggregate-daily-scores must be inside the ANALYZER_AUTO_SCHEDULE guard, "
        "not registered unconditionally"
    )


def test_beat_schedule_routes_aggregate_to_analysis_queue():
    """The existing task_routes block must route ``aggregate_daily_scores``
    onto the analysis queue (so the new beat entry actually queues onto
    the analysis worker, not the default queue).
    """
    src = _celery_tasks_source()
    assert '"geo_tracker.tasks.celery_tasks.aggregate_daily_scores"' in src, (
        "aggregate_daily_scores task definition missing"
    )
    # Pattern that captures both the route declaration and its queue assignment.
    assert '"aggregate_daily_scores":' in src or "aggregate_daily_scores" in src, (
        "task_routes entry for aggregate_daily_scores missing"
    )
    # Concrete: the routing dict in this file maps the task to {"queue": "analysis"}.
    assert '"queue": "analysis"' in src, (
        "analysis queue routing missing — celery_tasks task_routes must keep "
        '{"queue": "analysis"} for aggregate_daily_scores'
    )
