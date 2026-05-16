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

import importlib
import sys
import types
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


def _install_fake_playwright(monkeypatch: pytest.MonkeyPatch) -> None:
    """`geo_tracker.tasks.celery_tasks` imports `geo_tracker.agent.guest_executor`
    transitively, which hard-imports `playwright.async_api`. The backend
    test env doesn't have playwright installed, so we stub it the same
    way `test_issue_588_pipeline_profile_analyzer.py:53-61` does.
    """
    playwright = types.ModuleType("playwright")
    playwright_async = types.ModuleType("playwright.async_api")
    playwright_async.async_playwright = object
    playwright_async.BrowserContext = object
    playwright_async.ElementHandle = object
    playwright_async.Page = object
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.async_api", playwright_async)


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


def test_beat_schedule_includes_aggregate_daily_scores_when_auto_enabled(monkeypatch):
    """Issue #1040 — when ``ANALYZER_AUTO_SCHEDULE=true``, the beat schedule
    must include an ``aggregate-daily-scores`` entry alongside the existing
    ``daily-analysis`` entry, both pointing at the analysis queue."""
    _install_fake_playwright(monkeypatch)
    monkeypatch.setenv("ANALYZER_AUTO_SCHEDULE", "true")
    monkeypatch.setenv("HOTSPOT_AUTO_SCHEDULE", "false")

    # Re-import the celery_tasks module so the module-level
    # `_beat_schedule` dict is rebuilt with the env var set.
    if "geo_tracker.tasks.celery_tasks" in sys.modules:
        celery_tasks = importlib.reload(sys.modules["geo_tracker.tasks.celery_tasks"])
    else:
        celery_tasks = importlib.import_module("geo_tracker.tasks.celery_tasks")

    schedule = celery_tasks._beat_schedule
    assert "daily-analysis" in schedule, (
        "sanity check failed — daily-analysis should be present when ANALYZER_AUTO_SCHEDULE=true"
    )
    assert "aggregate-daily-scores" in schedule, (
        "Issue #1040 regression: ANALYZER_AUTO_SCHEDULE=true must add an "
        "aggregate-daily-scores beat entry so product_score_daily is "
        "populated daily."
    )
    entry = schedule["aggregate-daily-scores"]
    assert entry["task"] == "geo_tracker.tasks.celery_tasks.aggregate_daily_scores"
    # `schedule` is a celery.schedules.crontab instance — just verify it
    # exists (and isn't, e.g., a plain int seconds value that would
    # collide with the every-N-seconds API).
    assert "schedule" in entry


def test_beat_schedule_omits_aggregate_when_auto_disabled(monkeypatch):
    """Disabled env var must NOT register either daily-analysis or
    aggregate-daily-scores — both are opt-in together."""
    _install_fake_playwright(monkeypatch)
    monkeypatch.setenv("ANALYZER_AUTO_SCHEDULE", "false")
    monkeypatch.setenv("HOTSPOT_AUTO_SCHEDULE", "false")

    if "geo_tracker.tasks.celery_tasks" in sys.modules:
        celery_tasks = importlib.reload(sys.modules["geo_tracker.tasks.celery_tasks"])
    else:
        celery_tasks = importlib.import_module("geo_tracker.tasks.celery_tasks")

    schedule = celery_tasks._beat_schedule
    assert "daily-analysis" not in schedule
    assert "aggregate-daily-scores" not in schedule


def test_beat_schedule_routes_aggregate_to_analysis_queue(monkeypatch):
    """Already-existing task_routes entry must remain (so the new beat
    entry actually queues onto the analysis worker)."""
    _install_fake_playwright(monkeypatch)
    monkeypatch.setenv("ANALYZER_AUTO_SCHEDULE", "true")

    if "geo_tracker.tasks.celery_tasks" in sys.modules:
        celery_tasks = importlib.reload(sys.modules["geo_tracker.tasks.celery_tasks"])
    else:
        celery_tasks = importlib.import_module("geo_tracker.tasks.celery_tasks")

    routes = celery_tasks.app.conf.task_routes or {}
    assert "geo_tracker.tasks.celery_tasks.aggregate_daily_scores" in routes, (
        "task_routes lost the aggregate_daily_scores entry"
    )
    assert routes["geo_tracker.tasks.celery_tasks.aggregate_daily_scores"]["queue"] == "analysis"
