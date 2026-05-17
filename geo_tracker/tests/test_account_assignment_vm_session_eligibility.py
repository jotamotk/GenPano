"""Refs Epic #1110 / Issue #1116 (Codex review on PR #1122).

Unit-level eligibility checks for ``_has_cookies`` and the public
``is_account_executable_for_query`` wrapper that consumes it. Companion
to ``geo_tracker/tests/pool/test_account_pool_vm_session_selectable.py``
which exercises the same fix at the SQL / dispatcher integration layer.

Why both layers:

  - The Codex review found two independent sites that block vm_session
    accounts from selection: the Python helper in ``account_assignment``
    and the SQL filter in ``account_pool``. A test that only covers the
    integration path could mask a Python-helper regression because the
    pool's SQL would still surface the row. These unit tests pin
    ``_has_cookies`` semantics directly so a future edit to the helper
    that drops the vm_session bypass surfaces at the unit layer, not in
    an opaque end-to-end failure.
"""
from __future__ import annotations

from geo_tracker.db.models import AccountStatus, LLMAccount
from geo_tracker.tasks.account_assignment import (
    _has_cookies,
    account_unavailable_reason_from_accounts,
    is_account_executable_for_query,
)


def _vm_session_account_no_cookies(account_id: int = 1) -> LLMAccount:
    return LLMAccount(
        id=account_id,
        llm_name="doubao",
        email=f"vm{account_id}@local",
        cookies_json=None,
        status=AccountStatus.ACTIVE.value,
        execution_mode="vm_session",
        vm_id=f"vm-{account_id:03d}",
        daily_limit=20,
        query_count_today=0,
        consecutive_fails=0,
        cooldown_until=None,
    )


def _local_cookie_account_no_cookies(account_id: int = 2) -> LLMAccount:
    return LLMAccount(
        id=account_id,
        llm_name="doubao",
        email=f"local{account_id}@local",
        cookies_json=None,
        status=AccountStatus.ACTIVE.value,
        execution_mode="local_cookie",
        vm_id=None,
        daily_limit=20,
        query_count_today=0,
        consecutive_fails=0,
        cooldown_until=None,
    )


def _local_cookie_account_with_cookies(account_id: int = 3) -> LLMAccount:
    return LLMAccount(
        id=account_id,
        llm_name="doubao",
        email=f"good{account_id}@local",
        cookies_json='[{"name":"sessionid","value":"abc"}]',
        status=AccountStatus.ACTIVE.value,
        execution_mode="local_cookie",
        vm_id=None,
        daily_limit=20,
        query_count_today=0,
        consecutive_fails=0,
        cooldown_until=None,
    )


# --- _has_cookies direct semantics -------------------------------------------


def test_has_cookies_true_for_vm_session_with_null_cookies() -> None:
    """Headline: a vm_session account with cookies=NULL must be treated
    as eligible. Pre-fix the helper returned False because it called
    ``bool((account.cookies_json or "").strip())`` unconditionally.
    Post-fix it short-circuits to True for execution_mode=='vm_session'.
    Without this short-circuit, the dispatcher's scheduler-pre-assigned
    branch (``acquire_query_account``) silently falls back to the pool
    for every vm_session query."""
    assert _has_cookies(_vm_session_account_no_cookies()) is True


def test_has_cookies_false_for_local_cookie_with_null_cookies() -> None:
    """REGRESSION GUARD. A legacy local_cookie account with NULL cookies
    is broken (the cookies-import flow never populated it, or the row
    was clobbered). The pre-existing cookies filter MUST keep rejecting
    these rows; the vm_session exception is the only loophole."""
    assert _has_cookies(_local_cookie_account_no_cookies()) is False


def test_has_cookies_true_for_local_cookie_with_real_cookies() -> None:
    """Sanity check that the legacy happy path still works (cookies
    present → eligible)."""
    assert _has_cookies(_local_cookie_account_with_cookies()) is True


def test_has_cookies_true_for_vm_session_even_if_cookies_accidentally_set() -> None:
    """Defensive: vm_session is determined by ``execution_mode``, not by
    cookies presence. If a future bug somehow lets cookies leak onto a
    vm_session row (the DB CHECK would normally forbid this), the
    helper still treats it as eligible — the bug surfaces elsewhere
    (e.g. the connector router would log the contradiction), not in
    selection. This keeps the helper's contract narrowly defined."""
    acc = _vm_session_account_no_cookies(account_id=99)
    acc.cookies_json = '[{"name":"leaked"}]'
    assert _has_cookies(acc) is True


# --- is_account_executable_for_query (the public eligibility gate) ----------


def test_is_account_executable_for_query_accepts_vm_session_null_cookies() -> None:
    """End-to-end Python eligibility: vm_session with cookies=NULL
    passes the executable check, so ``acquire_query_account`` honors
    the scheduler-assigned account instead of fallback-to-pool."""
    acc = _vm_session_account_no_cookies()
    assert is_account_executable_for_query(acc, target_llm="doubao") is True


def test_is_account_executable_for_query_rejects_local_cookie_null_cookies() -> None:
    """REGRESSION GUARD at the eligibility-wrapper layer."""
    acc = _local_cookie_account_no_cookies()
    assert is_account_executable_for_query(acc, target_llm="doubao") is False


def test_is_account_executable_for_query_target_llm_mismatch_still_rejects_vm() -> None:
    """The vm_session cookies-bypass MUST NOT bypass the LLM-match
    predicate. A doubao vm_session account is not eligible for a
    chatgpt query."""
    acc = _vm_session_account_no_cookies()
    assert is_account_executable_for_query(acc, target_llm="chatgpt") is False


# --- account_unavailable_reason_from_accounts (diagnostic classifier) -------


def test_unavailable_reason_does_not_call_pool_empty_for_vm_session_only() -> None:
    """If the only available account is a vm_session row (cookies=NULL),
    the diagnostic must NOT report ``account_no_cookies`` —— the pool
    would actually return the account. Reporting a misleading reason
    here would send operators chasing a phantom cookies-import problem
    when the pool is actually healthy."""
    accounts = [_vm_session_account_no_cookies()]
    assert account_unavailable_reason_from_accounts(accounts) == "no_account_available"


def test_unavailable_reason_still_reports_no_cookies_for_local_only() -> None:
    """REGRESSION GUARD: a pool of only broken local_cookie rows
    still classifies as ``account_no_cookies`` so operators get the
    legacy diagnostic and re-run the cookies-import job."""
    accounts = [_local_cookie_account_no_cookies()]
    assert account_unavailable_reason_from_accounts(accounts) == "account_no_cookies"
