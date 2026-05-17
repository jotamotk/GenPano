"""Refs Epic #1110 / Issue #1114.

Unit tests for the env-driven ``VmRegistryFromEnv``. The registry is
parsed once and cached on the instance; tests target the parse +
cdp_endpoint behavior plus the malformed-input warnings.
"""
from __future__ import annotations

import logging
import sys
import types
from unittest.mock import MagicMock

import pytest


def _install_fake_playwright():
    """Sibling modules (``local.py`` / ``remote_vm.py``) imported by the
    package ``__init__.py`` pull in playwright at import time. Tests run
    in any env that has pytest-asyncio installed, so we stub the
    Playwright module before the registry test imports anything from
    the package. Idempotent — re-imports just reuse the stub."""
    if "playwright" in sys.modules and "playwright.async_api" in sys.modules:
        return
    playwright = types.ModuleType("playwright")
    playwright_async = types.ModuleType("playwright.async_api")
    playwright_async.async_playwright = MagicMock()
    playwright_async.BrowserContext = object
    sys.modules["playwright"] = playwright
    sys.modules["playwright.async_api"] = playwright_async


_install_fake_playwright()


@pytest.mark.asyncio
async def test_empty_env_yields_no_lookups():
    """No VM_REGISTRY set → every lookup returns None. Confirms the
    "no VMs configured" case does not crash and does not pretend a VM
    exists."""
    from geo_tracker.agent.executors.registry import VmRegistryFromEnv

    registry = VmRegistryFromEnv(env={})
    assert await registry.lookup("vm-anything") is None


@pytest.mark.asyncio
async def test_single_vm_two_engines_round_trip():
    """The canonical happy path: one CSV entry with both ports parses
    into a VmInfo whose cdp_endpoint produces the correct ws:// URL
    for each engine."""
    from geo_tracker.agent.executors.registry import VmRegistryFromEnv

    registry = VmRegistryFromEnv(
        env={"VM_REGISTRY": "vm-001:10.0.0.5:9222:9223"},
    )
    info = await registry.lookup("vm-001")
    assert info is not None
    assert info.vm_id == "vm-001"
    assert info.hostname == "10.0.0.5"
    assert info.status == "alive"
    assert info.cdp_endpoint("doubao") == "ws://10.0.0.5:9222"
    assert info.cdp_endpoint("deepseek") == "ws://10.0.0.5:9223"


@pytest.mark.asyncio
async def test_multiple_vms_independent_lookup():
    """Two CSV entries → two VmInfo records, each independently
    addressable. Confirms the parser doesn't conflate entries."""
    from geo_tracker.agent.executors.registry import VmRegistryFromEnv

    registry = VmRegistryFromEnv(
        env={
            "VM_REGISTRY": (
                "vm-001:10.0.0.5:9222:9223,"
                "vm-002:10.0.0.6:9224:9225"
            )
        },
    )
    a = await registry.lookup("vm-001")
    b = await registry.lookup("vm-002")
    assert a is not None
    assert b is not None
    assert a.hostname == "10.0.0.5"
    assert b.hostname == "10.0.0.6"
    assert a.cdp_endpoint("doubao") == "ws://10.0.0.5:9222"
    assert b.cdp_endpoint("deepseek") == "ws://10.0.0.6:9225"


@pytest.mark.asyncio
async def test_missing_engine_port_skips_that_engine():
    """`` vm-001:host::9223 `` (doubao port empty, deepseek port set)
    → the resulting VmInfo only knows about deepseek. Asking for
    doubao raises KeyError so the connector translates to PROXY_DEAD."""
    from geo_tracker.agent.executors.registry import VmRegistryFromEnv

    registry = VmRegistryFromEnv(
        env={"VM_REGISTRY": "vm-001:10.0.0.5::9223"},
    )
    info = await registry.lookup("vm-001")
    assert info is not None
    assert "deepseek" in info.ports
    assert "doubao" not in info.ports
    assert info.cdp_endpoint("deepseek") == "ws://10.0.0.5:9223"
    with pytest.raises(KeyError):
        info.cdp_endpoint("doubao")


@pytest.mark.asyncio
async def test_malformed_entry_is_dropped_with_warning(caplog):
    """An entry that does not match the schema is dropped (with a
    WARNING) — we don't want an operator typo to crash the worker
    process at import time."""
    from geo_tracker.agent.executors.registry import VmRegistryFromEnv

    caplog.set_level(logging.WARNING)
    registry = VmRegistryFromEnv(
        env={
            "VM_REGISTRY": (
                "this-is-not-valid,"
                "vm-001:10.0.0.5:9222:9223"
            )
        },
    )

    # Valid entry still works.
    assert (await registry.lookup("vm-001")) is not None
    # Invalid entry surfaced a warning.
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("malformed entry" in w.getMessage() for w in warnings)


@pytest.mark.asyncio
async def test_non_integer_port_is_dropped_for_that_engine(caplog):
    """A non-integer port (e.g. ``"abc"``) is dropped for that engine
    only. The other engine on the same entry must still parse.
    Catches a regression where the parser would discard the whole
    entry on a single bad column."""
    from geo_tracker.agent.executors.registry import VmRegistryFromEnv

    caplog.set_level(logging.WARNING)
    registry = VmRegistryFromEnv(
        env={"VM_REGISTRY": "vm-001:10.0.0.5:abc:9223"},
    )
    info = await registry.lookup("vm-001")
    assert info is not None
    assert "deepseek" in info.ports
    assert "doubao" not in info.ports
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("non-integer port" in w.getMessage() for w in warnings)


@pytest.mark.asyncio
async def test_entry_with_only_invalid_ports_is_dropped(caplog):
    """Entry with no usable ports → entry is dropped entirely (we won't
    register a VM that can't serve any engine)."""
    from geo_tracker.agent.executors.registry import VmRegistryFromEnv

    caplog.set_level(logging.WARNING)
    registry = VmRegistryFromEnv(env={"VM_REGISTRY": "vm-001:10.0.0.5::"})
    assert (await registry.lookup("vm-001")) is None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("no usable engine ports" in w.getMessage() for w in warnings)


@pytest.mark.asyncio
async def test_duplicate_vm_id_later_wins(caplog):
    """If the operator pastes the same vm_id twice, the second entry
    wins. We warn but don't crash."""
    from geo_tracker.agent.executors.registry import VmRegistryFromEnv

    caplog.set_level(logging.WARNING)
    registry = VmRegistryFromEnv(
        env={
            "VM_REGISTRY": (
                "vm-001:host-a:9222:9223,"
                "vm-001:host-b:9222:9223"
            )
        },
    )
    info = await registry.lookup("vm-001")
    assert info is not None
    assert info.hostname == "host-b"
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("duplicate vm_id" in w.getMessage() for w in warnings)


@pytest.mark.asyncio
async def test_lookup_returns_none_for_unknown_vm_id():
    """Asking for a vm_id that was never registered → None (the
    connector translates this to PROXY_DEAD)."""
    from geo_tracker.agent.executors.registry import VmRegistryFromEnv

    registry = VmRegistryFromEnv(
        env={"VM_REGISTRY": "vm-001:10.0.0.5:9222:9223"},
    )
    assert (await registry.lookup("vm-missing")) is None


@pytest.mark.asyncio
async def test_refresh_re_parses_env():
    """``refresh()`` is the hook the future Issue #1115 watchdog will
    use to push heartbeat-changed state into the registry. Today it
    just clears the cache so the next lookup re-reads from the
    mapping the registry was constructed with."""
    from geo_tracker.agent.executors.registry import VmRegistryFromEnv

    env: dict[str, str] = {"VM_REGISTRY": "vm-001:host-a:9222:9223"}
    registry = VmRegistryFromEnv(env=env)
    first = await registry.lookup("vm-001")
    assert first is not None and first.hostname == "host-a"

    env["VM_REGISTRY"] = "vm-001:host-b:9222:9223"
    # Without refresh, the cached value still wins.
    assert (await registry.lookup("vm-001")).hostname == "host-a"
    # After refresh, the new value is picked up.
    registry.refresh()
    assert (await registry.lookup("vm-001")).hostname == "host-b"


@pytest.mark.asyncio
async def test_default_env_falls_back_to_os_environ(monkeypatch):
    """Constructor with no ``env`` kwarg → reads ``os.environ`` so
    production paths work without dependency injection. We delete the
    var to confirm the default-empty case still returns None."""
    monkeypatch.delenv("VM_REGISTRY", raising=False)
    from geo_tracker.agent.executors.registry import VmRegistryFromEnv

    registry = VmRegistryFromEnv()
    assert (await registry.lookup("vm-anything")) is None
