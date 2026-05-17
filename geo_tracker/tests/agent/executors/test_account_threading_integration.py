"""Integration trace: account flows from celery_tasks call site through to
``RemoteCDPConnector.acquire_context`` with its ``vm_id`` intact.

Refs Epic #1110 / Issue #1114. Refs Codex review on PR #1121 (Bug 1).

Why this file exists (Evidence-First Shipping):

Bug 1 in PR #1121 was a contract break invisible to unit tests:

  - ``GuestQueryExecutor._execute_once`` was calling
    ``active_connector.acquire_context(llm, query)``.
  - ``LocalLaunchConnector.acquire_context(llm, account)`` ignores the
    second arg (``del account``) so all 53 existing unit tests passed.
  - ``RemoteCDPConnector.acquire_context(llm, account)`` reads
    ``getattr(account, "vm_id", None)`` from it. Passing a ``Query``
    (no ``vm_id``) makes that return ``None`` → raises
    ``AdapterError("NO_ACCOUNT_AVAILABLE")``, breaking every
    ``vm_session`` query in production.

Per AGENTS.md ``### Evidence-First Shipping``: changing a value that
crosses a boundary (here: the seam between executor and connector)
requires tracing one real value through the consumer end-to-end. This
test does exactly that — it spins up ``select_executor`` with a real
``vm_session`` account through the real router path, runs
``_execute_once`` against a mocked ``RemoteCDPConnector``, and asserts
the connector receives an object with a ``vm_id`` attribute matching
the account.

If this test fails, the production vm_session path is broken even if
every other test is green. That's the property the unit tests missed.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest


def _install_fake_playwright(monkeypatch):
    """Stub ``playwright.async_api`` so importing the executor/router/connector
    modules works without a real Playwright install. Mirrors the helper used
    in ``test_browser_connector.py`` / ``test_router.py``."""
    playwright = types.ModuleType("playwright")
    playwright_async = types.ModuleType("playwright.async_api")
    playwright_async.async_playwright = MagicMock()
    playwright_async.BrowserContext = object
    playwright_async.ElementHandle = object
    playwright_async.Page = object
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.async_api", playwright_async)


def _make_vm_session_account(*, vm_id: str, account_id: int = 42, llm_name: str = "doubao"):
    """Build a stand-in for an ORM ``LLMAccount`` row that the router's
    ``execution_mode == 'vm_session'`` branch will accept."""
    account = MagicMock(name=f"LLMAccount(id={account_id}, vm_id={vm_id})")
    account.id = account_id
    account.llm_name = llm_name
    account.execution_mode = "vm_session"
    account.vm_id = vm_id
    return account


@pytest.mark.asyncio
async def test_account_threads_through_select_executor_to_remote_connector_acquire(monkeypatch):
    """End-to-end account-threading trace (Codex review on PR #1121, Bug 1).

    This is the integration trace the unit-test layer missed. We run the
    REAL ``select_executor`` (no mock router), feed it a real
    ``vm_session`` account, then drive the resulting
    ``GuestQueryExecutor`` through one ``_execute_once`` cycle against a
    spy ``RemoteCDPConnector``. The spy records the second positional
    arg passed to ``acquire_context``; we assert it is an object
    carrying the account's ``vm_id``.

    Before the Bug 1 fix this assertion would fail with the spy seeing
    a ``Query`` object (whose ``vm_id`` is missing → AttributeError-as-
    None), which is the exact failure mode that broke production
    vm_session queries.
    """
    _install_fake_playwright(monkeypatch)

    # Import AFTER the playwright stub is installed; ``router.py`` lazily
    # imports ``guest_executor`` inside ``select_executor`` so this
    # ordering matters.
    from geo_tracker.agent.executors import BrowserConnector
    from geo_tracker.agent.executors.router import select_executor
    from geo_tracker.agent.guest_executor import GUEST_LLM_CONFIG

    account = _make_vm_session_account(vm_id="vm-prod-007", account_id=11823)

    # Spy connector: stand-in for the production ``RemoteCDPConnector``
    # the router would build. Records every call to ``acquire_context``
    # so we can prove the account threaded through correctly. The spy
    # raises after recording so we don't have to mock the rest of
    # ``_execute_once``'s downstream code path.
    acquire_calls: list = []
    release_calls: list = []

    class _SpyRemoteConnector(BrowserConnector):
        # Attributes the executor reads off the connector after acquire
        # (mirrors the production ``RemoteCDPConnector`` surface).
        local_storage_data: dict = {}
        use_camoufox: bool = False
        active_qg_lease = None
        injected_cookies_count: int = 0

        async def acquire_context(self, llm, acct):
            acquire_calls.append({"llm": llm, "arg": acct})
            # Raise so the executor short-circuits into its failure-return
            # path; we only care that ``acquire_context`` got the right arg.
            raise RuntimeError("spy: stop here")

        async def release_context(self, context):
            release_calls.append(context)

    spy_remote = _SpyRemoteConnector()

    # Drive the REAL router with the THREE-gate vm_session config so it
    # routes to our spy (substituted via ``remote_connector_factory``).
    executor = select_executor(
        account,
        env={
            "VM_EXECUTOR_ENABLED": "true",
            "VM_EXECUTOR_ENGINES": "doubao,deepseek",
        },
        remote_connector_factory=lambda: spy_remote,
    )

    # The executor that came out of select_executor MUST have the
    # account stashed on it; that's the plumbing fix.
    assert executor.account is account, (
        "select_executor did not forward account to GuestQueryExecutor — "
        "Bug 1 plumbing regression."
    )

    # Build a query for the same engine the account is configured for
    # (doubao is in GUEST_LLM_CONFIG; we only need the dict-shape to
    # exist for _execute_once's launch path).
    fake_query = MagicMock(name="Query(id=99001)")
    fake_query.target_llm = "doubao"
    fake_query.id = 99001

    # Run one execute cycle. The spy raises inside acquire_context,
    # _execute_once swallows it via its generic except and returns None.
    result = await executor._execute_once(
        fake_query, GUEST_LLM_CONFIG["doubao"], use_proxy=False
    )
    assert result is None

    # --- The acceptance claim of this integration trace ---------------
    assert len(acquire_calls) == 1, (
        "spy connector did not receive an acquire_context call — "
        "_execute_once is not routing through the injected connector."
    )
    call = acquire_calls[0]
    assert call["llm"] == "doubao"

    # The arg ``RemoteCDPConnector.acquire_context`` will read
    # ``account.vm_id`` off MUST be the account (carries vm_id), NOT the
    # query (would carry id/target_llm only). This is the load-bearing
    # assertion — it would FAIL on the pre-fix code that passed
    # ``query`` here.
    passed_arg = call["arg"]
    assert passed_arg is account, (
        f"acquire_context received {passed_arg!r} instead of the account. "
        "This is the Bug 1 contract break: passing ``query`` instead of "
        "``account`` makes ``RemoteCDPConnector`` see no vm_id."
    )
    assert getattr(passed_arg, "vm_id", None) == "vm-prod-007", (
        "account threaded through but vm_id attribute is missing/wrong — "
        "Bug 1 plumbing fix regressed somewhere."
    )

    # release_context still runs in the finally so the connector cleanup
    # contract holds even on the spy-raised path.
    assert len(release_calls) == 1


@pytest.mark.asyncio
async def test_remote_proxy_dead_propagates_to_executor_last_error_reason(monkeypatch):
    """Bug 2 acceptance trace: AdapterError(PROXY_DEAD) raised by
    RemoteCDPConnector.acquire_context MUST surface as
    ``executor.last_error_reason == "PROXY_DEAD"`` after _execute_once
    completes.

    The celery_tasks failure path reads ``executor.last_error_reason``
    via ``_empty_response_failure_reason`` and feeds it to
    ``quota_settlement.settle_failure(reason=...)`` → which calls
    ``AccountPool.report_failure(..., reason="PROXY_DEAD")``. That last
    call is what activates the vm_session 30-minute cooldown branch
    (account_pool.py:624). The fix in this PR (Bug 2) wires
    ``resolve_execution_failure_reason`` to propagate AdapterError.code
    instead of collapsing it to ``browser_exception``.
    """
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.executors import BrowserConnector
    from geo_tracker.agent.executors.remote_vm import AdapterError
    from geo_tracker.agent.executors.router import select_executor
    from geo_tracker.agent.guest_executor import GUEST_LLM_CONFIG

    account = _make_vm_session_account(vm_id="vm-prod-008", account_id=22001)

    class _DeadVmConnector(BrowserConnector):
        """Simulates a vm-unreachable RemoteCDPConnector: acquire_context
        raises AdapterError(PROXY_DEAD) — exactly the case where the
        registry-watchdog from Issue #1115 would mark the VM down or
        the CDP socket would refuse the connect."""

        local_storage_data: dict = {}
        use_camoufox: bool = False
        active_qg_lease = None
        injected_cookies_count: int = 0

        async def acquire_context(self, llm, acct):
            raise AdapterError(
                "PROXY_DEAD",
                detail=f"vm {getattr(acct, 'vm_id', None)!r} unreachable (test)",
                proxyId=getattr(acct, "vm_id", None),
            )

        async def release_context(self, context):
            return None

    dead_connector = _DeadVmConnector()
    executor = select_executor(
        account,
        env={
            "VM_EXECUTOR_ENABLED": "true",
            "VM_EXECUTOR_ENGINES": "doubao,deepseek",
        },
        remote_connector_factory=lambda: dead_connector,
    )

    fake_query = MagicMock()
    fake_query.target_llm = "doubao"
    fake_query.id = 99002

    result = await executor._execute_once(
        fake_query, GUEST_LLM_CONFIG["doubao"], use_proxy=False
    )

    # Acquire raised, _execute_once returned None.
    assert result is None
    # The acceptance assertion: PROXY_DEAD survived the trip from
    # AdapterError.code → resolve_execution_failure_reason →
    # executor.last_error_reason. Before the Bug 2 fix, this was
    # ``browser_exception`` and the AccountPool vm_session cooldown
    # never fired.
    assert executor.last_error_reason == "PROXY_DEAD", (
        f"expected PROXY_DEAD, got {executor.last_error_reason!r}. "
        "Bug 2 regression — resolve_execution_failure_reason did not "
        "propagate AdapterError.code."
    )


@pytest.mark.asyncio
async def test_remote_proxy_dead_calls_account_pool_report_failure_with_proxy_dead(
    monkeypatch,
):
    """End-to-end Bug 2 trace: simulate the executor → settle_failure →
    AccountPool.report_failure chain with a mocked AccountPool. Asserts
    ``report_failure(account_id, reason="PROXY_DEAD", ...)`` is invoked,
    which is the exact precondition for the vm_session 30-minute
    cooldown branch (account_pool.py:624) — the line the original PR
    #1121 review pointed at as never being hit in production."""
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.executors import BrowserConnector
    from geo_tracker.agent.executors.remote_vm import AdapterError
    from geo_tracker.agent.executors.router import select_executor
    from geo_tracker.agent.guest_executor import GUEST_LLM_CONFIG
    from geo_tracker.tasks.account_quota_settlement import AccountQuotaSettlement
    from geo_tracker.tasks.query_failure import _empty_response_failure_reason

    account = _make_vm_session_account(vm_id="vm-prod-009", account_id=33001)

    class _DeadVmConnector(BrowserConnector):
        local_storage_data: dict = {}
        use_camoufox: bool = False
        active_qg_lease = None
        injected_cookies_count: int = 0

        async def acquire_context(self, llm, acct):
            raise AdapterError("PROXY_DEAD", detail="cdp refused", proxyId="vm-prod-009")

        async def release_context(self, context):
            return None

    executor = select_executor(
        account,
        env={
            "VM_EXECUTOR_ENABLED": "true",
            "VM_EXECUTOR_ENGINES": "doubao,deepseek",
        },
        remote_connector_factory=lambda: _DeadVmConnector(),
    )

    fake_query = MagicMock()
    fake_query.target_llm = "doubao"
    fake_query.id = 99003

    await executor._execute_once(
        fake_query, GUEST_LLM_CONFIG["doubao"], use_proxy=False
    )

    # Replay the slice of celery_tasks.execute_query that maps an
    # empty/failed response into a settle_failure call. We mirror the
    # production sequence so the trace covers the actual call site, not
    # an artificial wrapper.
    failure_reason = _empty_response_failure_reason(
        None,
        executor=executor,
        account_cookies=None,
    )
    # _empty_response_failure_reason returns ``executor.last_error_reason``
    # verbatim when set — so this must be PROXY_DEAD after Bug 2 fix.
    assert failure_reason == "PROXY_DEAD"

    # settle_failure with a mocked pool. The assertion below is the
    # acceptance gate: report_failure(reason="PROXY_DEAD") MUST be the
    # call that reaches AccountPool — that's the only way the
    # vm_session cooldown branch fires.
    pool = MagicMock()
    pool.report_failure = AsyncMock()

    settlement = AccountQuotaSettlement()
    settlement.reserve(account.id)
    await settlement.settle_failure(
        db=MagicMock(),
        pool=pool,
        reason=failure_reason,
        query_id=fake_query.id,
    )

    pool.report_failure.assert_awaited_once()
    call_kwargs = pool.report_failure.call_args.kwargs
    call_args = pool.report_failure.call_args.args
    # account_id is first positional, reason is keyword.
    assert call_args[0] == 33001
    assert call_kwargs.get("reason") == "PROXY_DEAD", (
        f"expected PROXY_DEAD, got {call_kwargs!r}. "
        "Bug 2 regression — AccountPool.report_failure did not receive "
        "the canonical code, so the vm_session cooldown branch will "
        "not fire."
    )


@pytest.mark.asyncio
async def test_local_path_also_receives_account_uniformly(monkeypatch):
    """The router forwards ``account`` on both the local and remote
    branches. ``LocalLaunchConnector`` ignores it today (per its
    docstring) but the contract should be uniform so a future connector
    that wires the account in cannot silently see ``None`` on the local
    path. Codex review on PR #1121 explicitly called out this asymmetry
    as the root cause masker — fix it once, fix it for both branches.
    """
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.executors import BrowserConnector
    from geo_tracker.agent.executors.router import select_executor
    from geo_tracker.agent.guest_executor import GUEST_LLM_CONFIG

    # local_cookie account → router takes the default branch.
    account = MagicMock(name="LLMAccount(local_cookie)")
    account.id = 55
    account.llm_name = "perplexity"
    account.execution_mode = "local_cookie"
    account.vm_id = None

    acquire_calls: list = []

    class _SpyLocalConnector(BrowserConnector):
        local_storage_data: dict = {}
        use_camoufox: bool = False
        active_qg_lease = None
        injected_cookies_count: int = 0
        # Mirror the LocalLaunchConnector's runtime attributes the
        # executor's ``isinstance`` guard reads to decide whether to
        # rebuild a per-call connector. We set them to non-None so the
        # executor uses our spy directly.
        _browser = object()
        _camoufox_ctx = object()

        async def acquire_context(self, llm, acct):
            acquire_calls.append(acct)
            raise RuntimeError("spy: stop here")

        async def release_context(self, context):
            return None

    spy_local = _SpyLocalConnector()

    executor = select_executor(
        account,
        env={},  # flag off → local branch
        local_connector_factory=lambda: spy_local,
    )

    # Same account-threading invariant on the local path.
    assert executor.account is account

    fake_query = MagicMock()
    fake_query.target_llm = "perplexity"
    fake_query.id = 7

    await executor._execute_once(
        fake_query, GUEST_LLM_CONFIG["perplexity"], use_proxy=False
    )

    assert len(acquire_calls) == 1
    assert acquire_calls[0] is account
