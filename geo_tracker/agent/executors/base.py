"""Abstract base class for browser-context acquisition strategies.

Refs Epic #1110 / Issue #1113.

This module defines the contract that ``GuestQueryExecutor`` uses to
obtain a Playwright ``BrowserContext`` for a given LLM + account. Two
concrete implementations are planned:

  - ``LocalLaunchConnector`` (this PR, Issue #1113): launches a fresh
    Camoufox or Playwright Chromium and injects cookies. This is the
    current production behavior, just relocated.

  - ``RemoteCDPConnector`` (Issue #1114, NOT in this PR): connects via
    CDP to an already-logged-in browser running inside a VM that owns
    a single account's session state.

The split keeps query-execution code (selectors, response wait, DOM
extract, error classification, screenshot capture, stage tracking)
inside ``guest_executor.py`` so the VM rollout (Epic #1110) can change
the connector without touching the well-tested query logic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Import only at type-check time so test environments without
    # Playwright installed can still import this module for the ABC.
    from playwright.async_api import BrowserContext


class BrowserConnector(ABC):
    """Abstract way to get a Playwright ``BrowserContext`` for a query.

    Two implementations:

    - ``LocalLaunchConnector``: launches a fresh Camoufox / Chromium and
      injects cookies (current production behavior).
    - ``RemoteCDPConnector``: connects via CDP to an already-logged-in
      VM Chrome (Issue #1114, NOT in this PR).
    """

    @abstractmethod
    async def acquire_context(self, llm: str, account) -> "BrowserContext":
        """Acquire a ``BrowserContext`` ready to execute a query.

        Implementations are responsible for:

        - Setting up the browser (launch or connect).
        - Establishing authentication state (cookie injection for the
          local launch path, persistent profile for the VM CDP path).

        Returns a ``BrowserContext`` that the caller MUST clean up via
        ``try/finally`` by calling :meth:`release_context`.
        """
        ...

    @abstractmethod
    async def release_context(self, context: "BrowserContext") -> None:
        """Release the context.

        For ``LocalLaunchConnector`` this closes the browser entirely so
        the worker process does not leak Chromium children (production
        incident 2026-04-27 root cause).

        For ``RemoteCDPConnector`` (#1114) this only detaches the CDP
        client; the VM-side browser MUST stay running so the next query
        reuses the warm session.
        """
        ...
