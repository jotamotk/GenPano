"""Unit tests for `app/core/logging.py` (Step 3 v2 / T4 Bug 4 closure).

The logging backbone has two entry points:

  - `JsonFormatter.format(record)` — renders one JSON line per record,
    promoting `extra={...}` payloads to top-level keys, and emitting
    `exc_info` when present.
  - `configure_logging()` — applies the dictConfig, idempotent so the
    FastAPI lifespan can invoke it without side-effects on re-runs.

Both are sync, so coverage's async-trace gap (Windows + coverage 7.13
+ FastAPI route async bodies) does not apply here. Direct unit tests
exercise the lines that endpoint integration tests can't reach.
"""

from __future__ import annotations

import json
import logging

from app.core.logging import JsonFormatter, configure_logging


def _make_record(
    *,
    name: str = "test.logger",
    level: int = logging.INFO,
    msg: str = "hello",
    extra: dict[str, object] | None = None,
    exc_info: tuple | None = None,
) -> logging.LogRecord:
    record = logging.LogRecord(
        name=name,
        level=level,
        pathname="x.py",
        lineno=1,
        msg=msg,
        args=None,
        exc_info=exc_info,
    )
    if extra:
        for k, v in extra.items():
            setattr(record, k, v)
    return record


def test_json_formatter_emits_level_logger_message() -> None:
    formatter = JsonFormatter()
    line = formatter.format(_make_record(name="svc", msg="ok"))
    payload = json.loads(line)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "svc"
    assert payload["message"] == "ok"


def test_json_formatter_promotes_extra_payload_to_top_level() -> None:
    formatter = JsonFormatter()
    line = formatter.format(_make_record(extra={"audit": {"action": "freeze", "user_id": "u-1"}}))
    payload = json.loads(line)
    assert payload["audit"] == {"action": "freeze", "user_id": "u-1"}


def test_json_formatter_skips_safe_logrecord_fields_and_underscored() -> None:
    """Built-in LogRecord attributes (name/msg/...) and any attribute
    whose key starts with `_` must NOT leak into the rendered payload."""
    formatter = JsonFormatter()
    record = _make_record(extra={"_private": "secret", "audit_action": "freeze"})
    line = formatter.format(record)
    payload = json.loads(line)
    assert "_private" not in payload
    # filename / pathname / lineno / funcName etc. are LogRecord built-ins.
    for builtin in ("pathname", "filename", "lineno", "module", "args"):
        assert builtin not in payload
    # User-supplied keys without the underscore prefix DO survive.
    assert payload["audit_action"] == "freeze"


def test_json_formatter_renders_exc_info_when_present() -> None:
    formatter = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = _make_record(exc_info=sys.exc_info())
    line = formatter.format(record)
    payload = json.loads(line)
    assert "exc_info" in payload
    assert "ValueError" in payload["exc_info"]
    assert "boom" in payload["exc_info"]


def test_configure_logging_is_idempotent_and_sets_root_to_info() -> None:
    """The FastAPI lifespan invokes configure_logging() once at startup.
    The function is also exercised here to lift the dictConfig branch
    out of the async-coverage shadow + prove repeated calls don't trip
    the dict assembler."""
    configure_logging()
    configure_logging()
    assert logging.getLogger().level == logging.INFO
