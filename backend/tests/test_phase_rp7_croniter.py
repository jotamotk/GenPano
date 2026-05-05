"""Phase RP.7 — croniter-based real cron evaluation.

`run_schedules` advances `next_run_at` after firing a schedule. Until
this PR it always added +1 day regardless of the cron expression. Now
the next tick is computed by `croniter` so e.g. a `0 8 * * 1` weekly
cron really fires every Monday morning.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.tasks.reports import _next_cron_tick


def test_weekly_monday_8am_advances_correctly():
    # Tuesday 12:00 → next Monday 08:00
    base = datetime(2026, 5, 5, 12, 0)  # Tuesday
    nxt = _next_cron_tick("0 8 * * 1", base)
    assert nxt == datetime(2026, 5, 11, 8, 0)
    assert nxt.weekday() == 0  # Monday
    assert nxt.hour == 8


def test_daily_3am():
    base = datetime(2026, 5, 5, 12, 0)
    nxt = _next_cron_tick("0 3 * * *", base)
    assert nxt == datetime(2026, 5, 6, 3, 0)


def test_every_5_minutes():
    base = datetime(2026, 5, 5, 12, 3)
    nxt = _next_cron_tick("*/5 * * * *", base)
    assert nxt == datetime(2026, 5, 5, 12, 5)


def test_first_of_month_midnight():
    base = datetime(2026, 5, 5, 12, 0)
    nxt = _next_cron_tick("0 0 1 * *", base)
    assert nxt == datetime(2026, 6, 1, 0, 0)


def test_malformed_cron_falls_back_to_plus_one_day():
    """Operator typo shouldn't wedge the scheduler — fall back to +1 day."""
    base = datetime(2026, 5, 5, 12, 0)
    nxt = _next_cron_tick("nonsense", base)
    # +1 day fallback
    assert nxt == base + timedelta(days=1)


def test_empty_cron_falls_back_to_plus_one_day():
    base = datetime(2026, 5, 5, 12, 0)
    nxt = _next_cron_tick("", base)
    assert nxt == base + timedelta(days=1)


def test_none_cron_falls_back():
    base = datetime(2026, 5, 5, 12, 0)
    nxt = _next_cron_tick(None, base)
    assert nxt == base + timedelta(days=1)


def test_cron_advances_strictly_forward():
    """`get_next` always returns the *next* firing, never `base` itself."""
    base = datetime(2026, 5, 5, 12, 0)
    # base itself matches the cron (every minute), but next must be > base
    nxt = _next_cron_tick("* * * * *", base)
    assert nxt > base
