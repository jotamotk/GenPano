from __future__ import annotations

from typing import Any


# Refs Epic #1110 / Issue #1114. Codex review on PR #1121 (Bug 2).
# AdapterError codes raised by ``RemoteCDPConnector`` (see
# ``geo_tracker/agent/executors/remote_vm.py`` AdapterError class and
# ``docs/ADAPTER_CONTRACT.md`` §6.1). The set is duplicated here rather
# than imported because ``geo_tracker.agent.executors.remote_vm`` imports
# Playwright at module load — this module is consumed by
# ``celery_tasks.py`` paths that must remain importable in lightweight
# test environments where Playwright is stubbed. The list is short and
# changes only when the canonical taxonomy in ADAPTER_CONTRACT.md §6.1
# does, so the duplication is bounded.
ADAPTER_ERROR_CODES = frozenset(
    {
        "NO_ACCOUNT_AVAILABLE",
        "PROXY_DEAD",
        "PAGE_CRASHED",
    }
)


INFRASTRUCTURE_FAILURE_REASONS = frozenset(
    {
        "browser_epipe",
        "browser_exception",
        "browser_launch_timeout",
        "browser_timeout",
        "doubao_browser_timeout",
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
        "scraper_session_lock_timeout",
        "soft_time_limit",
    }
)


def _failure_reason_base(reason: str | None) -> str | None:
    if not reason:
        return None
    return str(reason).split(":", 1)[0]


def browser_execution_timeout_reason(
    llm_name: str | None,
    *,
    stage: str | None = None,
    has_existing_response: bool = False,
) -> str:
    if (llm_name or "").lower() == "doubao":
        if has_existing_response:
            return "doubao_browser_timeout:existing_response"
        clean_stage = (stage or "unknown_stage").strip().lower().replace(" ", "_")
        clean_stage = "".join(
            ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in clean_stage
        ).strip("_")
        return f"doubao_browser_timeout:{clean_stage or 'unknown_stage'}"
    return "browser_timeout"


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
    # Refs Epic #1110 / Issue #1114. Codex review on PR #1121 (Bug 2).
    # ``RemoteCDPConnector`` raises ``AdapterError(code=...)`` whose ``code``
    # is the canonical taxonomy string (PROXY_DEAD / NO_ACCOUNT_AVAILABLE /
    # PAGE_CRASHED, per ADAPTER_CONTRACT.md §6.1). Before this branch, those
    # codes were classified as the generic ``browser_exception`` by
    # ``classify_execution_failure`` — which meant ``AccountPool.report_failure``
    # never saw ``reason == "PROXY_DEAD"`` on a vm_session account, so the
    # 30-minute VM-local cooldown branch (account_pool.py:624) was never
    # exercised and the dispatcher kept retrying the dead VM.
    #
    # Propagate the code directly when it matches the known set so the
    # cooldown / pool side-effect machinery can react. We allow-list the
    # codes rather than blindly forwarding ``exc.code`` so an unrelated
    # third-party exception that happens to have a ``code`` attribute
    # (e.g. ``OSError`` subclasses with ``errno`` or some HTTP libs) can't
    # pollute the failure-reason taxonomy.
    exc_code = getattr(exc, "code", None)
    if isinstance(exc_code, str) and exc_code in ADAPTER_ERROR_CODES:
        return exc_code
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
    base_reason = _failure_reason_base(reason)
    if not base_reason:
        return True
    return base_reason not in INFRASTRUCTURE_FAILURE_REASONS
