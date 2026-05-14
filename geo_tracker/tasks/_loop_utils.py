"""Shared utilities for Celery tasks that manage their own asyncio loops."""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncEngine


def safe_dispose_engine(
    loop: asyncio.AbstractEventLoop,
    engine: AsyncEngine,
    logger: logging.Logger,
) -> None:
    """Dispose an async engine inside a finally block; log instead of swallow.

    Expected RuntimeError (event loop already closed, engine already disposed
    during shutdown) is logged at DEBUG so it does not flood production logs.
    Any other exception is logged at WARNING with full stack trace so genuine
    cleanup failures are no longer silently masked.
    """
    try:
        loop.run_until_complete(engine.dispose())
    except RuntimeError as exc:
        logger.debug("task_engine.dispose() skipped: %s", exc)
    except Exception as exc:
        logger.warning("task_engine.dispose() failed: %s", exc, exc_info=True)
