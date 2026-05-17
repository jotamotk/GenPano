"""Browser-context acquisition strategies for ``GuestQueryExecutor``.

Refs Epic #1110 / Issue #1113 + Issue #1114.

The package splits "how do we obtain a Playwright ``BrowserContext``
for an LLM + account" from "what do we do with that context to execute
a query". The split lets the VM-per-account rollout (Epic #1110) add a
``RemoteCDPConnector`` without touching the query execution logic in
``guest_executor.py``.

Public surface:
    - ``BrowserConnector``         -- abstract base class (see ``base.py``)
    - ``LocalLaunchConnector``     -- production default (see ``local.py``);
                                      Camoufox / Playwright launch + cookie
                                      injection. Identical to pre-#1113
                                      production behavior.
    - ``RemoteCDPConnector``       -- VM-per-account CDP connector (Issue
                                      #1114, ``remote_vm.py``). Default-off;
                                      requires the ``VM_EXECUTOR_ENABLED``
                                      feature flag.
    - ``select_executor``          -- per-account router (see ``router.py``);
                                      picks Local vs Remote based on the
                                      three feature gates.
    - ``VmRegistry``/``VmRegistryFromEnv``/``VmInfo``
                                   -- env-driven VM lookup (see ``registry.py``).
"""
from geo_tracker.agent.executors.base import BrowserConnector
from geo_tracker.agent.executors.local import LocalLaunchConnector
from geo_tracker.agent.executors.registry import (
    PHASE1_VM_ENGINES,
    VmInfo,
    VmRegistry,
    VmRegistryFromEnv,
)
from geo_tracker.agent.executors.remote_vm import AdapterError, RemoteCDPConnector
from geo_tracker.agent.executors.router import select_executor

__all__ = [
    "AdapterError",
    "BrowserConnector",
    "LocalLaunchConnector",
    "PHASE1_VM_ENGINES",
    "RemoteCDPConnector",
    "VmInfo",
    "VmRegistry",
    "VmRegistryFromEnv",
    "select_executor",
]
