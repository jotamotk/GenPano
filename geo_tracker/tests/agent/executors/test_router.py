"""Refs Epic #1110 / Issue #1114.

Unit tests for ``select_executor``. The router has three orthogonal
feature gates (env flag, env engine allow-list, account.execution_mode).
This suite pins the truth table by exercising every combination that
flips the routing decision:

  1. Flag off                             → Local (regardless of mode)
  2. Flag on, engine NOT in CSV           → Local (engine not opted in)
  3. Flag on, engine in CSV, mode='local_cookie' → Local (DB row opt-out)
  4. Flag on, engine in CSV, mode='vm_session'   → Remote (the only "yes")

The tests use sentinel callables (``local_factory`` / ``remote_factory``)
instead of letting the router build real connectors, because
``RemoteCDPConnector`` imports Playwright at module load and we want the
suite to run in any Python env that has pytest-asyncio.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest


def _install_fake_playwright(monkeypatch):
    """Stub ``playwright.async_api`` so importing ``guest_executor`` (which
    the router lazily imports inside ``select_executor``) does not require
    a real Playwright install. Mirrors the helper in
    ``test_browser_connector.py``."""
    playwright = types.ModuleType("playwright")
    playwright_async = types.ModuleType("playwright.async_api")
    playwright_async.async_playwright = MagicMock()
    playwright_async.BrowserContext = object
    playwright_async.ElementHandle = object
    playwright_async.Page = object
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.async_api", playwright_async)


def _fake_account(*, llm_name: str, execution_mode: str, vm_id: str | None = None):
    """A minimal stand-in for ``LLMAccount``. ``select_executor`` only
    reads ``llm_name``, ``execution_mode``, ``id`` (logging only) and the
    constructor-forwarded ``cookies_json`` attribute is unused here."""
    account = MagicMock()
    account.id = 42
    account.llm_name = llm_name
    account.execution_mode = execution_mode
    account.vm_id = vm_id
    return account


def _make_factories():
    """Return (local_factory, remote_factory, local_calls, remote_calls).

    Each factory is a callable that returns a unique sentinel and appends
    to its calls list so the test can assert which branch the router
    took without constructing a real connector.
    """
    local_calls: list = []
    remote_calls: list = []

    class _LocalSentinel:
        pass

    class _RemoteSentinel:
        pass

    def local_factory():
        local_calls.append(object())
        return _LocalSentinel()

    def remote_factory():
        remote_calls.append(object())
        return _RemoteSentinel()

    return local_factory, remote_factory, local_calls, remote_calls, _LocalSentinel, _RemoteSentinel


# --- The 4 cases the issue body pins ----------------------------------------

def test_flag_off_routes_local_regardless_of_execution_mode(monkeypatch):
    """Default-off behavior: even a vm_session-flagged account in the
    enabled engine list does NOT route remote when the flag is off.

    This is the safety property that lets us ship #1114 as dead-code:
    operators can have ``vm_session`` rows in the DB without taking the
    rollout risk until they explicitly set ``VM_EXECUTOR_ENABLED=true``.
    """
    _install_fake_playwright(monkeypatch)
    from geo_tracker.agent.executors.router import select_executor

    local_factory, remote_factory, local_calls, remote_calls, LocalS, _ = _make_factories()
    account = _fake_account(llm_name="doubao", execution_mode="vm_session", vm_id="vm-1")

    executor = select_executor(
        account,
        env={"VM_EXECUTOR_ENGINES": "doubao,deepseek"},  # flag intentionally absent
        local_connector_factory=local_factory,
        remote_connector_factory=remote_factory,
    )

    assert len(local_calls) == 1
    assert len(remote_calls) == 0
    assert isinstance(executor.connector, LocalS)


def test_flag_on_engine_not_in_csv_routes_local(monkeypatch):
    """Engine-level opt-in: a vm_session account on an engine that is
    NOT in ``VM_EXECUTOR_ENGINES`` keeps the local path. This lets the
    operator stage the rollout per engine."""
    _install_fake_playwright(monkeypatch)
    from geo_tracker.agent.executors.router import select_executor

    local_factory, remote_factory, local_calls, remote_calls, LocalS, _ = _make_factories()
    # chatgpt is NOT in the enabled list; vm_session mode shouldn't matter.
    account = _fake_account(llm_name="chatgpt", execution_mode="vm_session", vm_id="vm-1")

    executor = select_executor(
        account,
        env={
            "VM_EXECUTOR_ENABLED": "true",
            "VM_EXECUTOR_ENGINES": "doubao,deepseek",
        },
        local_connector_factory=local_factory,
        remote_connector_factory=remote_factory,
    )

    assert len(local_calls) == 1
    assert len(remote_calls) == 0
    assert isinstance(executor.connector, LocalS)


def test_flag_on_engine_in_csv_but_local_cookie_mode_routes_local(monkeypatch):
    """Per-account opt-out: even with the global flag on AND the engine
    in the allow-list, an account whose execution_mode is still
    'local_cookie' stays on the legacy path. This is the migration
    safety property — we don't accidentally route legacy accounts to a
    VM they aren't bound to."""
    _install_fake_playwright(monkeypatch)
    from geo_tracker.agent.executors.router import select_executor

    local_factory, remote_factory, local_calls, remote_calls, LocalS, _ = _make_factories()
    account = _fake_account(llm_name="doubao", execution_mode="local_cookie")

    executor = select_executor(
        account,
        env={
            "VM_EXECUTOR_ENABLED": "true",
            "VM_EXECUTOR_ENGINES": "doubao,deepseek",
        },
        local_connector_factory=local_factory,
        remote_connector_factory=remote_factory,
    )

    assert len(local_calls) == 1
    assert len(remote_calls) == 0
    assert isinstance(executor.connector, LocalS)


def test_flag_on_engine_in_csv_vm_session_mode_routes_remote(monkeypatch):
    """The one combination where the router crosses into RemoteCDPConnector."""
    _install_fake_playwright(monkeypatch)
    from geo_tracker.agent.executors.router import select_executor

    local_factory, remote_factory, local_calls, remote_calls, _, RemoteS = _make_factories()
    account = _fake_account(llm_name="doubao", execution_mode="vm_session", vm_id="vm-1")

    executor = select_executor(
        account,
        env={
            "VM_EXECUTOR_ENABLED": "true",
            "VM_EXECUTOR_ENGINES": "doubao,deepseek",
        },
        local_connector_factory=local_factory,
        remote_connector_factory=remote_factory,
    )

    assert len(local_calls) == 0
    assert len(remote_calls) == 1
    assert isinstance(executor.connector, RemoteS)


# --- Supporting properties --------------------------------------------------

def test_default_env_is_off(monkeypatch):
    """No env vars set at all → flag is off, router stays on local. This
    matches the ``grep VM_EXECUTOR_ENABLED returns default-false``
    verification in the issue body."""
    _install_fake_playwright(monkeypatch)
    from geo_tracker.agent.executors.router import select_executor

    local_factory, remote_factory, local_calls, remote_calls, LocalS, _ = _make_factories()
    account = _fake_account(llm_name="doubao", execution_mode="vm_session", vm_id="vm-1")

    executor = select_executor(
        account,
        env={},  # nothing set
        local_connector_factory=local_factory,
        remote_connector_factory=remote_factory,
    )

    assert len(local_calls) == 1
    assert len(remote_calls) == 0
    assert isinstance(executor.connector, LocalS)


@pytest.mark.parametrize(
    "raw_flag,expected_remote",
    [
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        ("0", False),
        ("no", False),
        ("", False),
        ("anything_else", False),
    ],
)
def test_flag_truthy_spellings(monkeypatch, raw_flag, expected_remote):
    """The router accepts the standard truthy spellings for
    ``VM_EXECUTOR_ENABLED``. Anything not in the truthy set falls back
    to the safe (local) default — including unrecognized values like
    "yep" so a typo cannot accidentally enable the VM path."""
    _install_fake_playwright(monkeypatch)
    from geo_tracker.agent.executors.router import select_executor

    local_factory, remote_factory, local_calls, remote_calls, _, _ = _make_factories()
    account = _fake_account(llm_name="doubao", execution_mode="vm_session", vm_id="vm-1")

    select_executor(
        account,
        env={
            "VM_EXECUTOR_ENABLED": raw_flag,
            "VM_EXECUTOR_ENGINES": "doubao",
        },
        local_connector_factory=local_factory,
        remote_connector_factory=remote_factory,
    )

    if expected_remote:
        assert len(remote_calls) == 1, f"flag={raw_flag!r} should route remote"
        assert len(local_calls) == 0
    else:
        assert len(local_calls) == 1, f"flag={raw_flag!r} should route local"
        assert len(remote_calls) == 0


def test_engine_csv_strips_whitespace(monkeypatch):
    """`` doubao , deepseek `` (operator-typed with stray spaces) must
    still enable doubao. The CSV split lives in one place
    (``_normalize_engines``) so a regression that drops the strip will
    surface here rather than at the operator's first deploy."""
    _install_fake_playwright(monkeypatch)
    from geo_tracker.agent.executors.router import select_executor

    local_factory, remote_factory, _, remote_calls, _, _ = _make_factories()
    account = _fake_account(llm_name="doubao", execution_mode="vm_session", vm_id="vm-1")

    select_executor(
        account,
        env={
            "VM_EXECUTOR_ENABLED": "true",
            "VM_EXECUTOR_ENGINES": "  doubao , deepseek ,  ",
        },
        local_connector_factory=local_factory,
        remote_connector_factory=remote_factory,
    )

    assert len(remote_calls) == 1
