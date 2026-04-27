"""Rate limiter — 7 cases.

Covers email + IP capacity ceilings, normalisation discipline, denied
attempts counting toward the window, and post-window release.
"""

from __future__ import annotations

import pytest

from app.admin.auth.rate_limiter import (
    EMAIL_LIMIT_CAPACITY,
    IP_LIMIT_CAPACITY,
    LIMIT_WINDOW_SECONDS,
    SlidingWindowLimiter,
    check_email_limit,
    check_ip_limit,
    reset_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_limiter() -> None:
    reset_for_tests()


def test_email_capacity_5_within_window() -> None:
    email = "Frank@Example.com"
    # Capacity is 5; the 6th call must be rejected.
    for i in range(EMAIL_LIMIT_CAPACITY):
        assert check_email_limit(email, now=100.0 + i) is True, f"call {i+1}"
    assert check_email_limit(email, now=100.0 + EMAIL_LIMIT_CAPACITY) is False


def test_email_normalisation_collapses_case_and_whitespace() -> None:
    # All four spellings must hit the same bucket.
    for variant in ("frank@x.com", "FRANK@X.COM", " frank@x.com ", "Frank@X.com"):
        check_email_limit(variant, now=200.0)
    # 4 attempts already; the next 1 fits, the one after exceeds.
    assert check_email_limit("frank@x.com", now=200.0) is True
    assert check_email_limit("frank@x.com", now=200.0) is False


def test_denied_attempts_still_count_toward_window() -> None:
    """Once over the cap, every additional call must keep returning False
    until entries age out. A limiter that didn't count denied attempts
    would let an attacker bombard at infinite rate after the first 5."""

    email = "abuser@x.com"
    for i in range(EMAIL_LIMIT_CAPACITY):
        check_email_limit(email, now=300.0 + i)
    # 10 more denied attempts within the same window
    for i in range(10):
        assert check_email_limit(email, now=305.0 + i) is False


def test_window_releases_after_expiry() -> None:
    email = "victim@x.com"
    base = 1000.0
    for i in range(EMAIL_LIMIT_CAPACITY):
        check_email_limit(email, now=base + i)
    # Cap exceeded
    assert check_email_limit(email, now=base + EMAIL_LIMIT_CAPACITY) is False
    # Jump past the window — old entries must evict.
    later = base + LIMIT_WINDOW_SECONDS + 10
    assert check_email_limit(email, now=later) is True


def test_ip_capacity_20_within_window() -> None:
    ip = "203.0.113.42"
    for i in range(IP_LIMIT_CAPACITY):
        assert check_ip_limit(ip, now=2000.0 + i) is True
    assert check_ip_limit(ip, now=2000.0 + IP_LIMIT_CAPACITY) is False


def test_ip_none_or_empty_normalises_to_default_bucket() -> None:
    # `None` and empty share the same bucket as `0.0.0.0` literal — so an
    # attacker who hides the X-Forwarded-For header still gets rate-limited
    # against the same shared key.
    for v in (None, "", "0.0.0.0"):
        check_ip_limit(v, now=3000.0)
    # 3 attempts on the shared bucket so far. Fill to cap (20 total) — 17 more.
    for i in range(IP_LIMIT_CAPACITY - 3):
        assert check_ip_limit("0.0.0.0", now=3000.0 + i) is True
    assert check_ip_limit(None, now=3000.0 + 20) is False


def test_separate_limiters_dont_share_buckets() -> None:
    # Custom limiters with isolated buckets — using both does not leak.
    a = SlidingWindowLimiter(capacity=2, window_seconds=60)
    b = SlidingWindowLimiter(capacity=2, window_seconds=60)
    assert a.check("k", now=10.0) is True
    assert a.check("k", now=11.0) is True
    assert a.check("k", now=12.0) is False
    # b is untouched, still has full capacity.
    assert b.check("k", now=13.0) is True
    assert b.check("k", now=14.0) is True
    assert b.check("k", now=15.0) is False
