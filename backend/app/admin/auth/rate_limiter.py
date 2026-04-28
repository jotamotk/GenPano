"""In-memory sliding-window rate limiter for /admin/api/v1/auth/login.

Decision #24.B contract:
- Email key: 5 attempts per 15-minute window (locks out a single email under
  brute force without spilling into other accounts).
- IP key: 20 attempts per 15-minute window (catches distributed attempts
  from one origin without blocking a shared corporate egress prematurely).
- Denied attempts STILL count toward the window — otherwise an attacker who
  hits the cap could keep retrying indefinitely after rejection without
  pushing the oldest attempts out of the window.

Email normalisation: trim + lowercase before keying so `Frank@x` and
`frank@x` collapse onto a single bucket. Empty / `None` IP normalises to
`'0.0.0.0'`.

This is the **MVP path** — single-process, single-worker. Multi-worker
deployments need Redis-backed sliding window (Step 4 STOP-Trigger A4 covers
this). The interface here is identical so swapping out the storage layer
later is a one-file change.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

# Window constants (seconds) — separate from constants.py because they are
# limiter-specific tuning, not shared auth constants.
EMAIL_LIMIT_CAPACITY = 5
IP_LIMIT_CAPACITY = 20
LIMIT_WINDOW_SECONDS = 15 * 60  # 15 min


@dataclass
class _Bucket:
    timestamps: deque[float] = field(default_factory=deque)


class SlidingWindowLimiter:
    """One bucket per key; deque of attempt timestamps within the window.

    `check(key)` always records the attempt, then evicts entries older than
    `window_seconds`, then returns True iff the post-record count is ≤
    capacity. The "denied attempts count" rule is enforced by recording
    BEFORE the cap test.
    """

    def __init__(self, *, capacity: int, window_seconds: int) -> None:
        self._capacity = capacity
        self._window = window_seconds
        self._buckets: dict[str, _Bucket] = {}

    def check(self, key: str, *, now: float | None = None) -> bool:
        ts = now if now is not None else time.monotonic()
        bucket = self._buckets.setdefault(key, _Bucket())

        cutoff = ts - self._window
        while bucket.timestamps and bucket.timestamps[0] < cutoff:
            bucket.timestamps.popleft()

        bucket.timestamps.append(ts)
        return len(bucket.timestamps) <= self._capacity

    def reset(self, key: str | None = None) -> None:
        """Test helper: clear one key (or all)."""

        if key is None:
            self._buckets.clear()
        else:
            self._buckets.pop(key, None)


_email_limiter = SlidingWindowLimiter(
    capacity=EMAIL_LIMIT_CAPACITY,
    window_seconds=LIMIT_WINDOW_SECONDS,
)
_ip_limiter = SlidingWindowLimiter(
    capacity=IP_LIMIT_CAPACITY,
    window_seconds=LIMIT_WINDOW_SECONDS,
)


def _normalise_email(raw: str) -> str:
    return raw.strip().lower()


def _normalise_ip(raw: str | None) -> str:
    return raw if (raw is not None and raw != "") else "0.0.0.0"


def check_email_limit(email: str, *, now: float | None = None) -> bool:
    return _email_limiter.check(f"email:{_normalise_email(email)}", now=now)


def check_ip_limit(ip: str | None, *, now: float | None = None) -> bool:
    return _ip_limiter.check(f"ip:{_normalise_ip(ip)}", now=now)


def reset_for_tests() -> None:
    """Drop all in-memory state — pytest fixture entry point."""

    _email_limiter.reset()
    _ip_limiter.reset()
