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
from unittest.mock import MagicMock

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
