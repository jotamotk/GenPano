"""Phase 5 — Redis-backed rate limiter fallback semantics.

Verifies that:
  1. When `GENPANO_RATE_LIMIT_NO_REDIS=1` is set the Redis path is
     skipped and the in-memory limiter is used.
  2. The in-memory `_SlidingWindow` continues to enforce capacity.
  3. `reset_for_tests()` clears both buckets and the cached client.
"""

from __future__ import annotations

import time

import pytest

from app.core import rate_limit as rl


@pytest.mark.asyncio
async def test_no_redis_env_disables_redis_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GENPANO_RATE_LIMIT_NO_REDIS", "1")
    rl.reset_for_tests()

    # Even with the env var set, _check_redis returns None promptly.
    result = await rl._check_redis("test-key", capacity=10)
    assert result is None


def test_in_memory_sliding_window_capacity() -> None:
    rl.reset_for_tests()
    limiter = rl._SlidingWindow()
    capacity = 3
    for i in range(capacity):
        ok, _ = limiter.check("k", capacity=capacity, window_seconds=60, now=float(i))
        assert ok, f"call {i} should be allowed"
    ok, retry = limiter.check("k", capacity=capacity, window_seconds=60, now=float(capacity))
    assert not ok
    assert retry > 0


def test_reset_for_tests_clears_redis_cache() -> None:
    rl._redis_unreachable_until = 9999.0
    rl.reset_for_tests()
    assert rl._redis_unreachable_until == 0.0
    assert rl._redis_client is None


def test_redis_unreachable_backoff_window() -> None:
    """After a connection failure we back off so we don't ping Redis on every request."""
    rl.reset_for_tests()
    rl._redis_unreachable_until = time.monotonic() + 9999.0
    # While still in the backoff window, _get_redis_client returns None.
    import asyncio

    result = asyncio.run(rl._get_redis_client())
    assert result is None
