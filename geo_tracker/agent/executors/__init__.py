"""Browser-context acquisition strategies for ``GuestQueryExecutor``.

Refs Epic #1110 / Issue #1113: this package splits "how do we obtain a
Playwright ``BrowserContext`` for an LLM + account" from "what do we do
with that context to execute a query". The split lets future work
(Issue #1114) add a ``RemoteCDPConnector`` for VM-per-account without
touching the query execution logic in ``guest_executor.py``.

Public surface:
    - ``BrowserConnector``         -- abstract base class (see ``base.py``)
    - ``LocalLaunchConnector``     -- the production default (see ``local.py``);
                                      preserves the existing Camoufox /
                                      Playwright launch + cookie-injection
                                      behavior exactly.
"""
from geo_tracker.agent.executors.base import BrowserConnector
from geo_tracker.agent.executors.local import LocalLaunchConnector

__all__ = ["BrowserConnector", "LocalLaunchConnector"]
