"""Tests for geo_tracker.tasks._loop_utils.safe_dispose_engine."""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import MagicMock

import pytest

from geo_tracker.tasks._loop_utils import safe_dispose_engine


def _engine_returning(coro_result):
    engine = MagicMock()

    async def _dispose():
        return coro_result

    engine.dispose = _dispose
    return engine


def _engine_raising(exc: BaseException):
    engine = MagicMock()

    async def _dispose():
        raise exc

    engine.dispose = _dispose
    return engine


def test_safe_dispose_engine_clean(caplog: pytest.LogCaptureFixture) -> None:
    """Happy path: dispose returns cleanly; nothing is logged."""
    loop = asyncio.new_event_loop()
    try:
        engine = _engine_returning(None)
        logger = logging.getLogger("test.safe_dispose.clean")
        with caplog.at_level(logging.DEBUG, logger=logger.name):
            safe_dispose_engine(loop, engine, logger)
    finally:
        loop.close()
    assert caplog.records == []


def test_safe_dispose_engine_runtimeerror_logged_at_debug(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Expected RuntimeError (loop closed / engine disposed) -> DEBUG only."""
    loop = asyncio.new_event_loop()
    try:
        engine = _engine_raising(RuntimeError("Event loop is closed"))
        logger = logging.getLogger("test.safe_dispose.runtime")
        with caplog.at_level(logging.DEBUG, logger=logger.name):
            safe_dispose_engine(loop, engine, logger)
    finally:
        loop.close()
    records = [r for r in caplog.records if r.name == "test.safe_dispose.runtime"]
    assert len(records) == 1
    assert records[0].levelno == logging.DEBUG
    assert "Event loop is closed" in records[0].getMessage()


def test_safe_dispose_engine_unexpected_logged_at_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Any non-RuntimeError -> WARNING with stack trace (exc_info attached)."""
    loop = asyncio.new_event_loop()
    try:
        engine = _engine_raising(ValueError("boom"))
        logger = logging.getLogger("test.safe_dispose.warning")
        with caplog.at_level(logging.WARNING, logger=logger.name):
            safe_dispose_engine(loop, engine, logger)
    finally:
        loop.close()
    records = [r for r in caplog.records if r.name == "test.safe_dispose.warning"]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert records[0].exc_info is not None
    assert "boom" in records[0].getMessage()
