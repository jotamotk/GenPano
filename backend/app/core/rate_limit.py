"""Phase 5 — request-level sliding-window rate limiter.

Generic counterpart to `app.user_auth.rate_limiter.SlidingWindowLimiter`
intended for `/api/v1/*` traffic gating. The auth limiter stays for
login/register since it has email-keyed semantics.

Limits (PRD §7.1):
  - Authenticated calls:  60 / minute / user
  - Anonymous calls:      30 / minute / IP

Backend strategy:
  - Try Redis-backed sliding window first (Sorted Set + ZADD/ZREMRANGEBYSCORE).
    Survives multiple uvicorn workers and pod restarts.
  - Fall back to in-memory sliding window when Redis is unreachable —
    do *not* 500 the request. Multi-tenant + e2e tests rely on this.

Integration: ``setup_rate_limit(app)`` adds a starlette middleware. The
middleware is a no-op in test environments (set ``GENPANO_RATE_LIMIT_DISABLED=1``)
to keep multi-tenant + e2e tests deterministic.
"""

from __future__ import annotations

import logging
import os
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

DEFAULT_AUTHED_PER_MINUTE = 60
DEFAULT_ANON_PER_MINUTE = 30

logger = logging.getLogger(__name__)


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
_redis_client: Any | None = None
_redis_unreachable_until: float = 0.0


def reset_for_tests() -> None:
    _limiter.reset()
    global _redis_client, _redis_unreachable_until
    _redis_client = None
    _redis_unreachable_until = 0.0


async def _get_redis_client() -> Any | None:
    """Return a connected redis.asyncio client or None if unreachable.

    Cached. After a connection failure we back off for 30s to avoid
    hammering the network on every request.
    """
    global _redis_client, _redis_unreachable_until
    if _redis_client is not None:
        return _redis_client
    if time.monotonic() < _redis_unreachable_until:
        return None
    if os.environ.get("GENPANO_RATE_LIMIT_NO_REDIS") == "1":
        return None
    try:
        from redis.asyncio import from_url

        url = os.environ.get("GENPANO_REDIS_URL") or os.environ.get(
            "REDIS_URL", "redis://localhost:6379/0"
        )
        client = from_url(  # type: ignore[no-untyped-call]
            url, encoding="utf-8", decode_responses=True
        )
        await client.ping()
        _redis_client = client
        return client
    except Exception as exc:
        logger.info("rate_limit Redis unreachable, falling back to in-memory: %s", exc)
        _redis_unreachable_until = time.monotonic() + 30.0
        return None


async def _check_redis(
    key: str, *, capacity: int, window_seconds: int = 60
) -> tuple[bool, int] | None:
    """Redis-backed sliding window via ZSET. Returns None on failure.

    Strategy: ZADD score=now, ZREMRANGEBYSCORE up to now - window,
    ZCARD to count remaining. Atomic via pipeline.
    """
    client = await _get_redis_client()
    if client is None:
        return None
    try:
        now_ms = int(time.time() * 1000)
        cutoff = now_ms - window_seconds * 1000
        rkey = f"rl:{key}"
        # Atomic 4-step: trim, count, add, expire.
        async with client.pipeline(transaction=True) as pipe:
            await pipe.zremrangebyscore(rkey, 0, cutoff)
            await pipe.zcard(rkey)
            await pipe.zadd(rkey, {f"{now_ms}-{os.urandom(4).hex()}": now_ms})
            await pipe.expire(rkey, window_seconds + 5)
            results = await pipe.execute()
        prior_count = int(results[1])
        if prior_count >= capacity:
            # Roll back our ZADD so future window has accurate count
            try:
                await client.zremrangebyrank(rkey, -1, -1)
            except Exception:
                pass
            # Compute retry_after from oldest remaining timestamp
            try:
                oldest = await client.zrange(rkey, 0, 0, withscores=True)
                if oldest:
                    oldest_ms = int(oldest[0][1])
                    retry_after = max(1, int((oldest_ms + window_seconds * 1000 - now_ms) / 1000))
                else:
                    retry_after = window_seconds
            except Exception:
                retry_after = window_seconds
            return False, retry_after
        return True, 0
    except Exception as exc:
        logger.info("rate_limit Redis op failed; falling back to in-memory: %s", exc)
        global _redis_client, _redis_unreachable_until
        _redis_client = None
        _redis_unreachable_until = time.monotonic() + 30.0
        return None


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
        bucket_key = f"{path[:64]}:{key}"
        # Try Redis-backed first; fall back to in-memory on failure.
        redis_result = await _check_redis(bucket_key, capacity=capacity, window_seconds=60)
        if redis_result is not None:
            allowed, retry_after = redis_result
        else:
            allowed, retry_after = _limiter.check(bucket_key, capacity=capacity, window_seconds=60)
        if not allowed:
            from app.core.request_id import REQUEST_ID_HEADER, current_request_id

            rid = current_request_id() or ""
            return JSONResponse(
                status_code=429,
                content={
                    "detail": {
                        "type": "about:blank",
                        "title": "Rate limit exceeded",
                        "status": 429,
                        "code": "rate_limit_exceeded",
                        "detail": "Try again later",
                        "retry_after": retry_after,
                        "retry_after_seconds": retry_after,
                        "request_id": rid,
                        "instance": path,
                    }
                },
                headers={
                    "Retry-After": str(retry_after),
                    REQUEST_ID_HEADER: rid,
                },
            )
        return await call_next(request)
