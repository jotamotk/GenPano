from __future__ import annotations

from typing import Any


INFRASTRUCTURE_FAILURE_REASONS = frozenset(
    {
        "browser_epipe",
        "browser_exception",
        "browser_launch_timeout",
        "browser_timeout",
        "doubao_image_challenge_load_failed",
        "doubao_visual_challenge",
        "exception",
        "no_input",
        "no_response",
        "page_load_failed",
        "page_unavailable",
        "proxy_api_unauthorized",
        "proxy_api_unreachable",
        "proxy_global_group_unavailable",
        "proxy_global_no_candidate",
        "proxy_global_route_unavailable",
        "proxy_global_switch_failed",
        "proxy_group_not_found",
        "proxy_no_available_nodes",
        "proxy_source_group_unavailable",
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


def resolve_execution_failure_reason(exc: BaseException, prior: str | None) -> str:
    # Refs #928: an artifact-save call (e.g. _save_runtime_snapshot, page.content)
    # in a specific failure branch can raise a Playwright TimeoutError after the
    # inner branch already set a precise reason like "no_input" / "page_unavailable".
    # The outer except must not overwrite that precise reason with "browser_timeout".
    if prior:
        return prior
    return classify_execution_failure(exc)


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
