"""RFC 7807 application/problem+json helpers.

Per ADR-014 + PRD §4.5.2.6 + Phase P §4.7.3.4: every API 4xx / 5xx response
returns a structured `ProblemDetails` body with stable `code` field for FE
i18n lookup.

Usage:

    from app.core.errors import unauthorized, validation_error
    raise unauthorized()
    raise validation_error("project.name", "must be 1-120 chars")
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.core.request_id import current_request_id


def _problem(
    status_code: int,
    code: str,
    title: str,
    *,
    detail: str | None = None,
    extra: dict[str, Any] | None = None,
) -> HTTPException:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status_code,
        "code": code,
    }
    if detail:
        body["detail"] = detail
    if extra:
        body.update(extra)
    rid = current_request_id()
    if rid:
        body["request_id"] = rid
    return HTTPException(status_code=status_code, detail=body)


def unauthorized(detail: str | None = None) -> HTTPException:
    return _problem(401, "unauthorized", "Authentication required", detail=detail)


def mcp_auth_required(detail: str | None = None) -> HTTPException:
    """MCP-specific 401 — see PRD §4.5.2.1."""
    return _problem(401, "MCP_AUTH_REQUIRED", "MCP API key required", detail=detail)


def forbidden(detail: str | None = None) -> HTTPException:
    return _problem(403, "forbidden", "Access denied", detail=detail)


def not_found(detail: str | None = None) -> HTTPException:
    """404 — also used for cross-tenant access (deny existence info)."""
    return _problem(404, "not_found", "Resource not found", detail=detail)


def conflict(code: str, detail: str | None = None) -> HTTPException:
    """409 — capacity full, unique constraint, status mismatch, etc."""
    return _problem(409, code, "Conflict", detail=detail)


def gone(detail: str | None = None) -> HTTPException:
    """410 — resource expired or revoked (e.g., public share link)."""
    return _problem(410, "gone", "Resource gone", detail=detail)


def validation_error(field: str, reason: str) -> HTTPException:
    return _problem(
        422,
        "validation_error",
        "Invalid input",
        detail=f"{field}: {reason}",
        extra={"field": field, "reason": reason},
    )


def rate_limit_exceeded(retry_after_seconds: int | None = None) -> HTTPException:
    extra = {"retry_after": retry_after_seconds} if retry_after_seconds else None
    return _problem(
        429,
        "rate_limit_exceeded",
        "Rate limit exceeded",
        detail="Try again later",
        extra=extra,
    )


def internal_error(detail: str | None = None) -> HTTPException:
    """500 — never expose stack traces / DB errors directly."""
    return _problem(500, "internal_error", "Internal server error", detail=detail)


def service_degraded(detail: str | None = None) -> HTTPException:
    """503 — upstream LLM unavailable, partial data."""
    return _problem(503, "service_degraded", "Service degraded", detail=detail)
