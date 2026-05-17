"""Per-account executor router.

Refs Epic #1110 / Issue #1114.

``select_executor(account)`` is the single decision point that picks
between the legacy ``LocalLaunchConnector`` (PR #1120) and the new
``RemoteCDPConnector`` (this PR). Default behavior is identical to
pre-#1114 production: every account routes to ``LocalLaunchConnector``
unless ALL three of the following gates pass:

  1. ``VM_EXECUTOR_ENABLED=true`` is set in the environment.
  2. The account's engine (``llm_name``) is in ``VM_EXECUTOR_ENGINES``
     (a comma-separated allow-list, e.g. ``"doubao,deepseek"``).
  3. The account's ``execution_mode`` column is ``'vm_session'``.

This three-gate design is intentional:

  - Gate 1 is the global kill switch — the operator can roll the
    rollout back in one env var without touching code or DB rows.
  - Gate 2 lets the operator opt in per engine (the docs/ADAPTER_CONTRACT
    §1.1 MVP locks Phase 1 to ``chatgpt / doubao / deepseek-CN``, but the
    actual VM-side runners ship for doubao + deepseek first).
  - Gate 3 lets the operator opt in per account (Admin UI from #1116
    creates ``vm_session`` rows; until then there are none and the
    router is a strict no-op even when gates 1+2 pass).

All three gates default OFF. The router is dead-code on every prod
worker until the operator flips ``VM_EXECUTOR_ENABLED``. Dead-code
deploy validates schema migration + import wiring + no-regression
without taking the rollout risk.
"""
from __future__ import annotations

import logging
import os
from typing import Mapping, Optional

from geo_tracker.agent.executors.local import LocalLaunchConnector
from geo_tracker.agent.executors.remote_vm import RemoteCDPConnector

logger = logging.getLogger(__name__)

# Env-var names. Kept as module constants so tests + operators agree
# on the spelling (no ad-hoc string literals at call sites).
ENV_FLAG = "VM_EXECUTOR_ENABLED"
ENV_ENGINES = "VM_EXECUTOR_ENGINES"
VM_SESSION_MODE = "vm_session"


def _normalize_engines(raw: str) -> frozenset[str]:
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def _flag_enabled(env: Mapping[str, str]) -> bool:
    raw = (env.get(ENV_FLAG) or "false").strip().lower()
    # Accept the standard truthy spellings without surprising the operator.
    # Anything else (including the default 'false') leaves the flag off.
    return raw in {"true", "1", "yes", "on"}


def select_executor(
    account,
    *,
    proxy_url: Optional[str] = None,
    account_cookies: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    local_connector_factory=None,
    remote_connector_factory=None,
):
    """Pick the ``GuestQueryExecutor`` flavor for ``account``.

    Returns a ``GuestQueryExecutor`` instance wrapping either a
    ``LocalLaunchConnector`` (default) or a ``RemoteCDPConnector``
    (when all three feature gates pass). ``proxy_url`` and
    ``account_cookies`` are threaded onto the executor instance the
    same way the inline ``GuestQueryExecutor(proxy_url=..., account_cookies=...)``
    call site does — needed for the LocalLaunchConnector path because
    the executor's ``_execute_once`` builds its per-call connector from
    those attributes (see ``guest_executor.py`` "if isinstance
    self.connector LocalLaunchConnector and _browser is None" block).
    They are harmless on the RemoteCDPConnector path because the remote
    connector ignores both (the VM owns proxy + session state).

    Args:
        account: an ORM ``LLMAccount`` (or any object with the same
            ``llm_name`` + ``execution_mode`` attributes). We avoid
            importing the ORM symbol to keep this module testable
            without spinning up the model package.
        proxy_url: forwarded to ``GuestQueryExecutor`` for LocalLaunchConnector.
        account_cookies: forwarded to ``GuestQueryExecutor`` for LocalLaunchConnector.
        env: environment lookup. Defaults to ``os.environ``. Tests pass
            a dict so they do not have to monkey-patch the process env.
        local_connector_factory / remote_connector_factory: zero-arg
            callables that return a connector. Tests pass sentinels so
            the test can assert which path the router took without
            constructing real connectors (RemoteCDPConnector imports
            Playwright at module-load via remote_vm.py).
    """
    # Imported lazily so the router can be imported in environments
    # where Playwright is not installed (e.g. backend-only unit test).
    # ``GuestQueryExecutor`` imports Playwright at module load via
    # guest_executor.py. The connector factories are passed by tests so
    # this import only triggers in production / integration paths.
    from geo_tracker.agent.guest_executor import GuestQueryExecutor

    env_map = env if env is not None else os.environ

    flag_on = _flag_enabled(env_map)
    enabled_engines = _normalize_engines(env_map.get(ENV_ENGINES) or "")
    llm_name = getattr(account, "llm_name", None) if account is not None else None
    execution_mode = (
        getattr(account, "execution_mode", None) if account is not None else None
    ) or "local_cookie"

    should_route_remote = (
        flag_on
        and llm_name is not None
        and llm_name in enabled_engines
        and execution_mode == VM_SESSION_MODE
    )

    if should_route_remote:
        logger.info(
            "select_executor: routing account_id=%s llm=%s execution_mode=%s "
            "to RemoteCDPConnector (VM_EXECUTOR_ENABLED=true, engines=%s)",
            getattr(account, "id", None),
            llm_name,
            execution_mode,
            sorted(enabled_engines),
        )
        factory = remote_connector_factory or RemoteCDPConnector
        # NOTE: proxy_url / account_cookies are still forwarded to the
        # executor so the executor's bookkeeping (last_error_reason
        # context, log lines) keeps reading them; the RemoteCDPConnector
        # itself does NOT use them (VM owns proxy + session). The DB
        # CHECK ``chk_exec_mode_cookies`` guarantees a vm_session row
        # has no cookies, so account_cookies would be None anyway.
        return GuestQueryExecutor(
            proxy_url=proxy_url,
            account_cookies=account_cookies,
            connector=factory(),
        )

    # Default path: every existing call site keeps the legacy behavior.
    # We do NOT log here on the default path because the per-query
    # logging would flood the operator log with redundant
    # "routed to local" lines for every successful query.
    factory = local_connector_factory or LocalLaunchConnector
    return GuestQueryExecutor(
        proxy_url=proxy_url,
        account_cookies=account_cookies,
        connector=factory(),
    )
