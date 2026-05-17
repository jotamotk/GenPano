"""Refs Epic #1110 / Issue #1114.

Unit tests for ``RemoteCDPConnector``. The connector is the only module
that talks to a VM, so the tests stub both Playwright (no real Chrome
launched) and ``VmRegistry`` (no env var dependence). Coverage targets:

  - Happy path: connect_over_cdp(endpoint) is awaited with the
    registry-resolved endpoint for the requested engine, and the
    returned context is the VM's default context (NOT a new context).
  - ``add_cookies`` and ``new_context`` are NEVER called: the VM owns
    session state; if either is called we have re-introduced the R2.5
    self-cloning-device failure mode that the DB CHECK constraint
    ``chk_exec_mode_cookies`` is supposed to prevent.
  - PROXY_DEAD is raised when the registry has no entry for vm_id.
  - PROXY_DEAD is raised when the registry has the entry but status
    is 'down' (Phase 1 only emits 'alive', but the contract must hold
    for the Phase 2 watchdog integration).
  - PROXY_DEAD is raised when ``connect_over_cdp`` itself raises (VM
    in registry, TCP socket refused).
  - PAGE_CRASHED is raised when the VM-side Chrome has no default
    context (process crash, profile wiped).
  - NO_ACCOUNT_AVAILABLE is raised when the account has no vm_id at
    all (DB schema bug rather than VM bug).
  - ``release_context`` calls ``browser.close()`` (CDP detach) and
    does NOT raise even when the underlying detach fails.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest


def _install_fake_playwright(monkeypatch):
    """Replace ``playwright.async_api`` with a stub before importing
    ``remote_vm``. The stub provides the symbols the module imports at
    load time. Connector tests override ``playwright_factory`` so the
    stubbed module's ``async_playwright`` is never actually awaited."""
    playwright = types.ModuleType("playwright")
    playwright_async = types.ModuleType("playwright.async_api")
    playwright_async.async_playwright = MagicMock()
    playwright_async.BrowserContext = object
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.async_api", playwright_async)


def _fake_account(vm_id: str | None):
    """Stand-in for ``LLMAccount``. Only ``id`` and ``vm_id`` are read."""
    account = MagicMock()
    account.id = 7
    account.vm_id = vm_id
    return account


def _stub_playwright_factory(*, contexts: list, connect_raises: Exception | None = None):
    """Build a (factory, browser_mock, stop_mock) tuple. ``factory()`` is
    what ``RemoteCDPConnector`` calls in place of the real
    ``async_playwright``. ``factory().start()`` returns the playwright
    handle whose ``chromium.connect_over_cdp`` produces a browser whose
    ``contexts`` attribute is the supplied list (or raises
    ``connect_raises``)."""
    browser = MagicMock()
    browser.contexts = contexts
    browser.close = AsyncMock()

    if connect_raises is not None:
        connect = AsyncMock(side_effect=connect_raises)
    else:
        connect = AsyncMock(return_value=browser)

    pw_handle = MagicMock()
    pw_handle.chromium = MagicMock()
    pw_handle.chromium.connect_over_cdp = connect
    pw_handle.stop = AsyncMock()

    pw_obj = MagicMock()
    pw_obj.start = AsyncMock(return_value=pw_handle)
    factory = MagicMock(return_value=pw_obj)
    return factory, browser, pw_handle, connect


@pytest.mark.asyncio
async def test_acquire_returns_default_vm_context_without_mutating_state(monkeypatch):
    """Happy path: the connector resolves vm_id → endpoint via the
    registry, calls connect_over_cdp on the resolved ws:// URL, and
    returns the VM's default ``BrowserContext``. It must NOT call
    ``new_context`` or ``add_cookies`` — the VM owns session state.
    """
    _install_fake_playwright(monkeypatch)

    from geo_tracker.agent.executors.registry import VmInfo
    from geo_tracker.agent.executors.remote_vm import RemoteCDPConnector

    default_context = MagicMock(name="default_context")
    # ``add_cookies`` and ``new_context`` are spies so we can prove
    # they were never awaited (the test's load-bearing invariant).
    default_context.add_cookies = AsyncMock()
    factory, browser, _pw_handle, connect = _stub_playwright_factory(
        contexts=[default_context]
    )
    browser.new_context = AsyncMock()

    # Stub registry: vm-001 maps to host with Doubao on port 9222.
    registry = MagicMock()
    registry.lookup = AsyncMock(
        return_value=VmInfo(
            vm_id="vm-001",
            hostname="10.0.0.5",
            ports={"doubao": 9222},
            status="alive",
        )
    )

    connector = RemoteCDPConnector(
        vm_registry=registry,
        playwright_factory=factory,
    )
    context = await connector.acquire_context("doubao", _fake_account(vm_id="vm-001"))

    assert context is default_context
    registry.lookup.assert_awaited_once_with("vm-001")
    connect.assert_awaited_once_with("ws://10.0.0.5:9222")
    # The two invariants the comment block at the top of this test
    # file pins:
    default_context.add_cookies.assert_not_awaited()
    browser.new_context.assert_not_awaited()


@pytest.mark.asyncio
async def test_acquire_raises_no_account_available_when_vm_id_missing(monkeypatch):
    """A vm_session account that somehow ended up without a vm_id
    (DB-write bug — admin UI from #1116 should always set one). We
    raise NO_ACCOUNT_AVAILABLE to match docs/ADAPTER_CONTRACT.md
    §6.1 — that error code signals "this account can't be used right
    now, mark Query PENDING" rather than "VM is broken"."""
    _install_fake_playwright(monkeypatch)
    from geo_tracker.agent.executors.remote_vm import AdapterError, RemoteCDPConnector

    factory, _browser, _pw_handle, _connect = _stub_playwright_factory(contexts=[])
    registry = MagicMock()
    registry.lookup = AsyncMock(return_value=None)

    connector = RemoteCDPConnector(
        vm_registry=registry,
        playwright_factory=factory,
    )

    with pytest.raises(AdapterError) as exc:
        await connector.acquire_context("doubao", _fake_account(vm_id=None))

    assert exc.value.code == "NO_ACCOUNT_AVAILABLE"
    # We did not even try to look up the registry — we know upfront the
    # account is unusable. Saves a network round trip.
    registry.lookup.assert_not_called()


@pytest.mark.asyncio
async def test_acquire_raises_proxy_dead_when_vm_not_in_registry(monkeypatch):
    """The account is consistent (has a vm_id) but the registry has no
    entry for it. Operator config drift; map to PROXY_DEAD so the
    retry layer spends a different VM next attempt."""
    _install_fake_playwright(monkeypatch)
    from geo_tracker.agent.executors.remote_vm import AdapterError, RemoteCDPConnector

    factory, _browser, _pw_handle, _connect = _stub_playwright_factory(contexts=[])
    registry = MagicMock()
    registry.lookup = AsyncMock(return_value=None)

    connector = RemoteCDPConnector(
        vm_registry=registry,
        playwright_factory=factory,
    )

    with pytest.raises(AdapterError) as exc:
        await connector.acquire_context("doubao", _fake_account(vm_id="vm-missing"))

    assert exc.value.code == "PROXY_DEAD"
    assert getattr(exc.value, "proxyId", None) == "vm-missing"


@pytest.mark.asyncio
async def test_acquire_raises_proxy_dead_when_vm_status_is_down(monkeypatch):
    """Issue #1115 watchdog will set status='down' when heartbeats stop.
    The connector must treat that the same as a registry miss."""
    _install_fake_playwright(monkeypatch)
    from geo_tracker.agent.executors.registry import VmInfo
    from geo_tracker.agent.executors.remote_vm import AdapterError, RemoteCDPConnector

    factory, _browser, _pw_handle, _connect = _stub_playwright_factory(contexts=[])
    registry = MagicMock()
    registry.lookup = AsyncMock(
        return_value=VmInfo(
            vm_id="vm-001",
            hostname="10.0.0.5",
            ports={"doubao": 9222},
            status="down",
        )
    )

    connector = RemoteCDPConnector(
        vm_registry=registry,
        playwright_factory=factory,
    )

    with pytest.raises(AdapterError) as exc:
        await connector.acquire_context("doubao", _fake_account(vm_id="vm-001"))

    assert exc.value.code == "PROXY_DEAD"


@pytest.mark.asyncio
async def test_acquire_raises_proxy_dead_when_cdp_connect_fails(monkeypatch):
    """Registry says the VM is alive but the TCP socket refuses
    (transient: VM Chrome restarting). Map to PROXY_DEAD."""
    _install_fake_playwright(monkeypatch)
    from geo_tracker.agent.executors.registry import VmInfo
    from geo_tracker.agent.executors.remote_vm import AdapterError, RemoteCDPConnector

    factory, _browser, pw_handle, _connect = _stub_playwright_factory(
        contexts=[],
        connect_raises=ConnectionRefusedError("nope"),
    )
    registry = MagicMock()
    registry.lookup = AsyncMock(
        return_value=VmInfo(
            vm_id="vm-001",
            hostname="10.0.0.5",
            ports={"doubao": 9222},
            status="alive",
        )
    )

    connector = RemoteCDPConnector(
        vm_registry=registry,
        playwright_factory=factory,
    )

    with pytest.raises(AdapterError) as exc:
        await connector.acquire_context("doubao", _fake_account(vm_id="vm-001"))

    assert exc.value.code == "PROXY_DEAD"
    # Playwright handle should have been stopped so we don't leak the
    # subprocess after a failed connect attempt.
    pw_handle.stop.assert_awaited()


@pytest.mark.asyncio
async def test_acquire_raises_page_crashed_when_no_default_context(monkeypatch):
    """VM Chrome started but has no default context (profile wipe,
    process crash mid-launch). PAGE_CRASHED so the retry layer
    restarts rather than burning an account strike."""
    _install_fake_playwright(monkeypatch)
    from geo_tracker.agent.executors.registry import VmInfo
    from geo_tracker.agent.executors.remote_vm import AdapterError, RemoteCDPConnector

    factory, _browser, _pw_handle, _connect = _stub_playwright_factory(contexts=[])
    registry = MagicMock()
    registry.lookup = AsyncMock(
        return_value=VmInfo(
            vm_id="vm-001",
            hostname="10.0.0.5",
            ports={"doubao": 9222},
            status="alive",
        )
    )

    connector = RemoteCDPConnector(
        vm_registry=registry,
        playwright_factory=factory,
    )

    with pytest.raises(AdapterError) as exc:
        await connector.acquire_context("doubao", _fake_account(vm_id="vm-001"))

    assert exc.value.code == "PAGE_CRASHED"


@pytest.mark.asyncio
async def test_release_context_closes_browser_then_stops_playwright(monkeypatch):
    """``release_context`` is the CDP detach. It must call
    ``browser.close()`` (CDP semantics: detach client, keep VM Chrome
    running) and then stop the local playwright driver subprocess
    so we don't leak handles between queries."""
    _install_fake_playwright(monkeypatch)
    from geo_tracker.agent.executors.registry import VmInfo
    from geo_tracker.agent.executors.remote_vm import RemoteCDPConnector

    default_context = MagicMock(name="default_context")
    factory, browser, pw_handle, _connect = _stub_playwright_factory(
        contexts=[default_context]
    )
    registry = MagicMock()
    registry.lookup = AsyncMock(
        return_value=VmInfo(
            vm_id="vm-001",
            hostname="10.0.0.5",
            ports={"doubao": 9222},
            status="alive",
        )
    )

    connector = RemoteCDPConnector(
        vm_registry=registry,
        playwright_factory=factory,
    )
    context = await connector.acquire_context("doubao", _fake_account(vm_id="vm-001"))
    await connector.release_context(context)

    browser.close.assert_awaited()
    pw_handle.stop.assert_awaited()


@pytest.mark.asyncio
async def test_release_context_swallows_close_errors(monkeypatch):
    """``release_context`` is a finally-block path. A
    ``browser.close()`` failure must NOT propagate — the executor's
    own cleanup chain depends on this path running to completion
    (leaking a playwright subprocess per failed query would exhaust
    the worker's fd table within hours)."""
    _install_fake_playwright(monkeypatch)
    from geo_tracker.agent.executors.registry import VmInfo
    from geo_tracker.agent.executors.remote_vm import RemoteCDPConnector

    default_context = MagicMock(name="default_context")
    factory, browser, pw_handle, _connect = _stub_playwright_factory(
        contexts=[default_context]
    )
    browser.close = AsyncMock(side_effect=RuntimeError("synthetic"))

    registry = MagicMock()
    registry.lookup = AsyncMock(
        return_value=VmInfo(
            vm_id="vm-001",
            hostname="10.0.0.5",
            ports={"doubao": 9222},
            status="alive",
        )
    )

    connector = RemoteCDPConnector(
        vm_registry=registry,
        playwright_factory=factory,
    )
    context = await connector.acquire_context("doubao", _fake_account(vm_id="vm-001"))
    # No exception should escape release_context.
    await connector.release_context(context)

    # Even though browser.close() failed, the playwright handle was
    # still stopped (otherwise the leak above would happen).
    pw_handle.stop.assert_awaited()


@pytest.mark.asyncio
async def test_acquire_per_engine_endpoint_lookup(monkeypatch):
    """If the registry maps a VM with two engines (Doubao + DeepSeek),
    each acquire_context call hits the correct CDP port for its
    engine. Catches a regression where the endpoint lookup ignores
    the ``llm`` argument."""
    _install_fake_playwright(monkeypatch)
    from geo_tracker.agent.executors.registry import VmInfo
    from geo_tracker.agent.executors.remote_vm import RemoteCDPConnector

    default_context = MagicMock(name="default_context")
    factory, browser, _pw_handle, connect = _stub_playwright_factory(
        contexts=[default_context]
    )

    registry = MagicMock()
    registry.lookup = AsyncMock(
        return_value=VmInfo(
            vm_id="vm-001",
            hostname="10.0.0.5",
            ports={"doubao": 9222, "deepseek": 9223},
            status="alive",
        )
    )

    connector = RemoteCDPConnector(
        vm_registry=registry,
        playwright_factory=factory,
    )
    await connector.acquire_context("doubao", _fake_account(vm_id="vm-001"))
    connect.assert_awaited_with("ws://10.0.0.5:9222")

    # Second acquire (different engine) should hit the deepseek port.
    # Reset the connector's internal pw handle for the second acquire
    # so the test exercises the full path again.
    connector._playwright = None
    connector._browser = None
    await connector.acquire_context("deepseek", _fake_account(vm_id="vm-001"))
    connect.assert_awaited_with("ws://10.0.0.5:9223")
