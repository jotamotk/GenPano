"""Small in-memory rate limiter for product auth endpoints."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class _Bucket:
    timestamps: deque[float] = field(default_factory=deque)


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}

    def check(
        self,
        key: str,
        *,
        capacity: int,
        window_seconds: int,
        now: float | None = None,
    ) -> bool:
        ts = now if now is not None else time.monotonic()
        bucket = self._buckets.setdefault(key, _Bucket())
        cutoff = ts - window_seconds
        while bucket.timestamps and bucket.timestamps[0] < cutoff:
            bucket.timestamps.popleft()
        bucket.timestamps.append(ts)
        return len(bucket.timestamps) <= capacity

    def reset(self) -> None:
        self._buckets.clear()


_limiter = SlidingWindowLimiter()


def check_auth_limit(
    scope: str,
    *,
    email: str | None,
    ip_address: str | None,
    capacity: int,
    window_seconds: int = 60,
) -> bool:
    normal_email = (email or "unknown").strip().lower()
    normal_ip = ip_address or "0.0.0.0"
    key = f"{scope}:{normal_ip}:{normal_email}"
    return _limiter.check(key, capacity=capacity, window_seconds=window_seconds)


def reset_for_tests() -> None:
    _limiter.reset()
