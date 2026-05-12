from __future__ import annotations

from typing import Any


INFRASTRUCTURE_FAILURE_REASONS = frozenset(
    {
        "browser_epipe",
        "browser_exception",
        "browser_launch_timeout",
        "browser_timeout",
        "exception",
        "no_input",
        "no_response",
        "page_load_failed",
        "page_unavailable",
        "proxy_unavailable",
        "soft_time_limit",
    }
)


def classify_execution_failure(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}".lower()
    if "browsertype.launch" in text and "timeout" in text:
        return "browser_launch_timeout"
    if "write epipe" in text or " epipe" in text:
        return "browser_epipe"
    if "timeout" in text:
        return "browser_timeout"
    return "browser_exception"


def _empty_response_failure_reason(
    response: Any,
    *,
    executor: Any,
    account_cookies: str | None,
) -> str:
    if response is not None:
        return "response_too_short"
    reason = getattr(executor, "last_error_reason", None)
    if reason:
        return str(reason)
    return "cookies_expired" if account_cookies else "no_response"


def _should_report_account_failure(reason: str | None) -> bool:
    if not reason:
        return True
    return reason not in INFRASTRUCTURE_FAILURE_REASONS
