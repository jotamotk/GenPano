"""VM registry for the VM-per-account architecture.

Refs Epic #1110 / Issue #1114.

Phase 1 only — env-driven registry. The ``VM_REGISTRY`` environment
variable carries a CSV of VM descriptors::

    VM_REGISTRY = "<vm_id>:<hostname>:<doubao_port>:<deepseek_port>[,<vm_id>:...]"

For example, two VMs hosting Doubao and DeepSeek::

    VM_REGISTRY = "vm-001:10.0.0.5:9222:9223,vm-002:10.0.0.6:9222:9223"

ChatGPT is intentionally NOT a CDP port column for Phase 1 — the
``docs/ADAPTER_CONTRACT.md`` §1.1 MVP locks the VM rollout to the three
CN-friendly engines (chatgpt / doubao / deepseek-CN). ChatGPT keeps the
local-launch path (which knows how to deal with Cloudflare + proxy
rotation) for the MVP. The router gates per-engine via
``VM_EXECUTOR_ENGINES`` so the operator can opt in only the two engines
the VM rollout actually serves at first.

Issue #1115 will add a watchdog that PUSHES heartbeat state into a small
process-local store; in Phase 1 the ``status`` is always ``'alive'`` if
the env entry is present, so the connector treats "registry miss" and
"registry hit + alive" as the only two states. The same ``VmRegistry``
interface lets #1115 replace the env-only backend without touching
``RemoteCDPConnector``.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Mapping, Optional, Protocol

logger = logging.getLogger(__name__)


# Phase 1 MVP engines per docs/ADAPTER_CONTRACT.md §1.1. ChatGPT is in
# the list but Phase 1 does not actually expose a CDP port for it (see
# module docstring); keeping the constant here so a future Phase change
# is a single-symbol edit.
PHASE1_VM_ENGINES = ("doubao", "deepseek")


@dataclass
class VmInfo:
    """Resolved info for a single VM in the registry.

    Attributes:
        vm_id: opaque registry key; same value stored in
            ``llm_accounts.vm_id`` for ``execution_mode='vm_session'`` rows.
        hostname: DNS name or IP the worker can reach.
        ports: mapping ``llm_name -> cdp_port``. Engines not in the
            mapping will raise ``KeyError`` from :meth:`cdp_endpoint`,
            which ``RemoteCDPConnector`` translates to ``PROXY_DEAD`` so
            an account misconfigured for an unsupported engine cannot
            silently fall through to a connect attempt against port 0.
        status: ``'alive'`` if the env entry exists (Phase 1) or the
            watchdog (Phase 2 / Issue #1115) has heartbeats within window.
            ``'down'`` otherwise.
    """

    vm_id: str
    hostname: str
    ports: dict[str, int] = field(default_factory=dict)
    status: str = "alive"

    def cdp_endpoint(self, llm: str) -> str:
        """Return the Playwright ``ws://...`` CDP endpoint for ``llm``.

        Raises ``KeyError`` if the engine is not configured on this VM —
        the caller (``RemoteCDPConnector``) re-raises as
        ``AdapterError('PROXY_DEAD')`` so the operator log makes the
        misconfiguration visible without the worker hanging on a
        connect to a non-existent port.
        """
        if llm not in self.ports:
            raise KeyError(
                f"vm_id={self.vm_id!r} has no CDP port configured for engine={llm!r}; "
                f"available engines={sorted(self.ports)!r}"
            )
        return f"ws://{self.hostname}:{self.ports[llm]}"


class VmRegistry(Protocol):
    """Lookup interface ``RemoteCDPConnector`` depends on.

    A Protocol (not an ABC) so tests can pass plain stub objects without
    inheriting. The env-driven implementation below satisfies it; future
    watchdog-driven implementations (Issue #1115) will too.
    """

    async def lookup(self, vm_id: str) -> Optional[VmInfo]:
        ...


class VmRegistryFromEnv:
    """Env-driven implementation of :class:`VmRegistry`.

    Parses ``VM_REGISTRY`` once at first lookup (lazy) and caches the
    result on the instance. Re-parsing per lookup would let an operator
    hot-edit ``/etc/environment`` and see new VMs without a restart, but
    Phase 1 only deploys via container restart, so the lazy cache is
    safe. ``refresh()`` is exposed for tests + the future watchdog.

    Each CSV entry is ``vm_id:hostname:doubao_port:deepseek_port``. Empty
    port columns are skipped (e.g. ``vm-001:10.0.0.5::9223`` registers
    deepseek only). Malformed entries are dropped with a WARNING — we
    don't want an operator typo to take the worker process down at
    import time.
    """

    # Column order matches the engines from PHASE1_VM_ENGINES above. The
    # CSV format is intentionally positional rather than k=v so the
    # operator does not need shell-escaping when pasting into a
    # docker-compose env.
    _COLUMN_ENGINES = PHASE1_VM_ENGINES

    def __init__(self, env: Optional[Mapping[str, str]] = None) -> None:
        self._env = env if env is not None else os.environ
        self._cache: Optional[dict[str, VmInfo]] = None

    def refresh(self) -> None:
        """Force a re-parse on the next ``lookup`` call."""
        self._cache = None

    def _ensure_parsed(self) -> dict[str, VmInfo]:
        if self._cache is not None:
            return self._cache
        raw = (self._env.get("VM_REGISTRY") or "").strip()
        result: dict[str, VmInfo] = {}
        if not raw:
            self._cache = result
            return result

        for entry in raw.split(","):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split(":")
            # vm_id + hostname + N engine ports (matching _COLUMN_ENGINES).
            min_parts = 2
            max_parts = 2 + len(self._COLUMN_ENGINES)
            if not (min_parts <= len(parts) <= max_parts):
                logger.warning(
                    "VM_REGISTRY: dropping malformed entry %r "
                    "(expected vm_id:hostname[:doubao_port[:deepseek_port]])",
                    entry,
                )
                continue
            vm_id, hostname, *port_columns = parts
            vm_id = vm_id.strip()
            hostname = hostname.strip()
            if not vm_id or not hostname:
                logger.warning(
                    "VM_REGISTRY: dropping entry with empty vm_id/hostname %r",
                    entry,
                )
                continue

            ports: dict[str, int] = {}
            for engine, raw_port in zip(self._COLUMN_ENGINES, port_columns):
                raw_port = raw_port.strip()
                if not raw_port:
                    # Empty column means "this VM does not serve this
                    # engine" — skip without warning.
                    continue
                try:
                    ports[engine] = int(raw_port)
                except ValueError:
                    logger.warning(
                        "VM_REGISTRY: dropping non-integer port %r for "
                        "engine=%s in entry %r",
                        raw_port,
                        engine,
                        entry,
                    )

            if not ports:
                logger.warning(
                    "VM_REGISTRY: dropping entry %r — no usable engine ports",
                    entry,
                )
                continue

            if vm_id in result:
                logger.warning(
                    "VM_REGISTRY: duplicate vm_id=%s; later entry wins", vm_id
                )

            # Phase 1: status is always 'alive' if the env entry exists.
            # Issue #1115 watchdog will replace this with heartbeat-driven
            # state in a future change.
            result[vm_id] = VmInfo(
                vm_id=vm_id,
                hostname=hostname,
                ports=ports,
                status="alive",
            )

        self._cache = result
        return result

    async def lookup(self, vm_id: str) -> Optional[VmInfo]:
        return self._ensure_parsed().get(vm_id)
