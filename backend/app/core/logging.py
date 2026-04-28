"""Application logging backbone — closes A0' Bug 4 (info-level gap).

Centralized dictConfig that:
- Sets the root logger to INFO so `admin_email.skipped`,
  `admin_audit.stub`, etc. reach stdout.
- Pipes everything through a single JSON formatter so structured
  `extra={...}` payloads survive into log aggregators.
- Reuses uvicorn's existing access / error loggers so we don't lose
  request lines when the app reconfigures logging.

Wired from FastAPI's lifespan in `app/main.py` so configuration runs
once at startup, before any router emits a log event.
"""

from __future__ import annotations

import json
import logging
import logging.config
from typing import Any

_SAFE_LOGRECORD_FIELDS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """Render records as one JSON document per line.

    Anything passed via `extra={...}` lands as a top-level key in the
    rendered object so structured payloads (e.g. the audit envelope
    in `admin_audit.stub`) stay introspectable downstream.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _SAFE_LOGRECORD_FIELDS or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def _logging_config() -> dict[str, Any]:
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": "app.core.logging.JsonFormatter",
            }
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "json",
            }
        },
        "root": {
            "level": "INFO",
            "handlers": ["stdout"],
        },
        "loggers": {
            "uvicorn": {"level": "INFO", "handlers": ["stdout"], "propagate": False},
            "uvicorn.error": {
                "level": "INFO",
                "handlers": ["stdout"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": "INFO",
                "handlers": ["stdout"],
                "propagate": False,
            },
        },
    }


def configure_logging() -> None:
    """Apply the dictConfig. Idempotent — safe to call from lifespan."""
    logging.config.dictConfig(_logging_config())
