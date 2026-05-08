"""X-Request-ID propagation middleware + logging filter.

Goal: every API request gets a stable correlation ID, surfaced as
`X-Request-ID` response header, embedded into RFC 7807 error bodies, and
attached to every log record produced under that request.

Usage:

    from app.core.request_id import (
        RequestIDMiddleware,
        current_request_id,
        install_logging_filter,
    )

    app.add_middleware(RequestIDMiddleware)
    install_logging_filter()

The middleware reads incoming `X-Request-ID` (so trusted upstreams like an
ingress can propagate IDs end-to-end) and falls back to a fresh uuid4 hex.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"

_current_request_id: ContextVar[str | None] = ContextVar("genpano_request_id", default=None)


def current_request_id() -> str | None:
    """Return the request_id for the in-flight request, if any."""
    return _current_request_id.get()


def _new_request_id() -> str:
    return uuid.uuid4().hex[:24]


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Generate / propagate `X-Request-ID` for every request."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming if incoming else _new_request_id()
        request.state.request_id = request_id
        token = _current_request_id.set(request_id)
        try:
            response = await call_next(request)
        finally:
            _current_request_id.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


class _RequestIDLogFilter(logging.Filter):
    """Inject `request_id` attribute onto every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = current_request_id() or "-"
        return True


def install_logging_filter(logger: logging.Logger | None = None) -> None:
    """Attach the request_id filter to the given logger (root by default).

    Idempotent — calling twice will not duplicate the filter.
    """
    target = logger if logger is not None else logging.getLogger()
    for existing in target.filters:
        if isinstance(existing, _RequestIDLogFilter):
            return
    target.addFilter(_RequestIDLogFilter())
