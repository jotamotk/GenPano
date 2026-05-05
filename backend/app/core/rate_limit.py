"""Phase 5 — request-level sliding-window rate limiter.

Generic counterpart to `app.user_auth.rate_limiter.SlidingWindowLimiter`
intended for `/api/v1/*` traffic gating. The auth limiter stays for
login/register since it has email-keyed semantics.

Limits (PRD §7.1):
  - Authenticated calls:  60 / minute / user
  - Anonymous calls:      30 / minute / IP

Backend strategy:
  - In-memory sliding window (default — used by tests and dev).
  - Phase 5+ swap-in: Redis-backed if `REDIS_URL` is reachable, falling
    back to in-memory on connection failure (do not 500 the request).

Integration: ``setup_rate_limit(app)`` adds a starlette middleware. The
middleware is a no-op in test environments (set ``GENPANO_RATE_LIMIT_DISABLED=1``)
to keep multi-tenant + e2e tests deterministic.
"""

from __future__ import annotations

import os
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

DEFAULT_AUTHED_PER_MINUTE = 60
DEFAULT_ANON_PER_MINUTE = 30


@dataclass
class _Bucket:
    timestamps: deque[float] = field(default_factory=deque)


class _SlidingWindow:
    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}

    def check(
        self,
        key: str,
        *,
        capacity: int,
        window_seconds: int = 60,
        now: float | None = None,
    ) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        ts = now if now is not None else time.monotonic()
        bucket = self._buckets.setdefault(key, _Bucket())
        cutoff = ts - window_seconds
        while bucket.timestamps and bucket.timestamps[0] < cutoff:
            bucket.timestamps.popleft()
        if len(bucket.timestamps) >= capacity:
            # Retry-after: oldest sample drops out at + window_seconds
            oldest = bucket.timestamps[0]
            retry_after = max(1, int(oldest + window_seconds - ts))
            return False, retry_after
        bucket.timestamps.append(ts)
        return True, 0

    def reset(self) -> None:
        self._buckets.clear()


_limiter = _SlidingWindow()


def reset_for_tests() -> None:
    _limiter.reset()


def _principal_key(request: Request) -> tuple[str, int]:
    """Return ``(key, capacity)`` based on auth state.

    Authenticated (Bearer / API key): keyed by token. Else IP address.
    """
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        # Token itself is high-entropy; hash-prefix to bound key length
        token = auth[7:].strip()
        return f"u:{token[:24]}", DEFAULT_AUTHED_PER_MINUTE
    ip = request.client.host if request.client else "unknown"
    return f"ip:{ip}", DEFAULT_ANON_PER_MINUTE


def setup_rate_limit(app: FastAPI) -> None:
    """Attach the middleware to ``app``.

    Set ``GENPANO_RATE_LIMIT_DISABLED=1`` to make the middleware a no-op
    (CI / e2e suites use this so tests never trip a flake on quick polling).
    """

    @app.middleware("http")
    async def _rate_limit_mw(
        request: Request,
        call_next: Callable[[Request], Awaitable[JSONResponse]],
    ) -> JSONResponse:
        if os.environ.get("GENPANO_RATE_LIMIT_DISABLED") == "1":
            return await call_next(request)
        # Only rate-limit /api/v1/* and /mcp/* — leave /health, /api/auth,
        # /reports/public unmetered (different limiters or open-by-design).
        path = request.url.path
        if not (path.startswith("/api/v1") or path.startswith("/mcp")):
            return await call_next(request)
        key, capacity = _principal_key(request)
        allowed, retry_after = _limiter.check(
            f"{path[:64]}:{key}", capacity=capacity, window_seconds=60
        )
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": {
                        "code": "rate_limited",
                        "message": "Too Many Requests",
                        "retry_after_seconds": retry_after,
                    }
                },
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)
