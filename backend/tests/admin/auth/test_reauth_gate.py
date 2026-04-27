"""Reauth gate — 7 cases.

Covers the three-outcome decision matrix, naive-vs-aware datetime handling,
clock-skew tolerance, and the bool-alias helper.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.admin.auth.constants import REAUTH_WINDOW_MS
from app.admin.auth.reauth_gate import evaluate_reauth, require_recent_auth

_WINDOW_S = REAUTH_WINDOW_MS / 1000.0


def test_none_last_password_returns_never_authenticated() -> None:
    decision = evaluate_reauth(last_password_at=None)
    assert decision.allowed is False
    assert decision.reason == "never_authenticated"


def test_within_window_allowed() -> None:
    now = datetime.now(UTC)
    last = now - timedelta(seconds=_WINDOW_S - 30)  # 30s before the cliff
    decision = evaluate_reauth(last_password_at=last, now=now)
    assert decision.allowed is True
    assert decision.reason is None


def test_just_past_window_stale() -> None:
    now = datetime.now(UTC)
    last = now - timedelta(seconds=_WINDOW_S + 30)  # 30s past the cliff
    decision = evaluate_reauth(last_password_at=last, now=now)
    assert decision.allowed is False
    assert decision.reason == "stale"


def test_naive_datetime_treated_as_utc() -> None:
    now = datetime.now(UTC)
    last_naive = (now - timedelta(seconds=60)).replace(tzinfo=None)
    decision = evaluate_reauth(last_password_at=last_naive, now=now)
    assert decision.allowed is True


def test_future_last_password_clock_skew_allowed() -> None:
    now = datetime.now(UTC)
    last = now + timedelta(seconds=120)  # impossible but happens with skew
    decision = evaluate_reauth(last_password_at=last, now=now)
    assert decision.allowed is True
    assert decision.reason is None


def test_custom_max_age_overrides_default() -> None:
    now = datetime.now(UTC)
    last = now - timedelta(seconds=300)  # 5 min ago
    # Default 30-min window: still allowed.
    assert evaluate_reauth(last_password_at=last, now=now).allowed is True
    # Tightened to 60 s: now stale.
    decision = evaluate_reauth(last_password_at=last, now=now, max_age_ms=60_000)
    assert decision.allowed is False
    assert decision.reason == "stale"


def test_require_recent_auth_returns_bool() -> None:
    now = datetime.now(UTC)
    fresh = now - timedelta(seconds=10)
    stale = now - timedelta(seconds=_WINDOW_S + 60)
    assert require_recent_auth(last_password_at=fresh, now=now) is True
    assert require_recent_auth(last_password_at=stale, now=now) is False
    assert require_recent_auth(last_password_at=None, now=now) is False
