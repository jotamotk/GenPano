"""``RemoteCDPConnector`` — connect to a VM-side browser over Playwright CDP.

Refs Epic #1110 / Issue #1114.

Phase 1 of the VM-per-account architecture. Where ``LocalLaunchConnector``
(PR #1120 / Issue #1113) launches a fresh Camoufox/Chromium and injects
cookies per query, ``RemoteCDPConnector`` connects via CDP to a long-lived
browser process running on a dedicated VM that already holds the
account's logged-in session state.

Boundary contract (this module is the only one that talks to a VM):

  - The VM owns the browser process AND the session state. We connect
    over CDP, grab the default context (whose cookies + localStorage are
    those that the VM-side login flow established), and return it. We
    NEVER call ``new_context`` (would lose the warm session) and NEVER
    call ``add_cookies`` (would conflict with the constraint on
    ``llm_accounts.chk_exec_mode_cookies``; ``vm_session`` rows by DB
    invariant have no cookies to inject).
  - On release we ONLY detach the CDP client (``browser.close()`` on a
    CDP-connected ``Browser`` performs ``Browser.close`` which detaches
    rather than killing the VM-side Chrome — see Playwright's
    ``BrowserType.connect_over_cdp`` docs).
  - Errors map to the canonical taxonomy in ADAPTER_CONTRACT.md §6.1:
      * No ``vm_id`` on the account               → NO_ACCOUNT_AVAILABLE
      * VM not in registry or status != 'alive'   → PROXY_DEAD
      * VM reachable but no default browser ctx   → PAGE_CRASHED

Production gating: this connector is only constructed by
``select_executor`` when ALL of the following hold:

  * ``VM_EXECUTOR_ENABLED=true`` is set in the environment.
  * The account's ``llm_name`` is in ``VM_EXECUTOR_ENGINES`` (CSV).
  * ``account.execution_mode == 'vm_session'``.

The default for all three gates is "off" so production behavior is
unchanged until the operator opts in per-engine.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from playwright.async_api import async_playwright

from geo_tracker.agent.executors.base import BrowserConnector
from geo_tracker.agent.executors.registry import VmInfo, VmRegistry, VmRegistryFromEnv

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext

logger = logging.getLogger(__name__)


@dataclass
class AdapterError(Exception):
    """Lightweight error wrapper matching the ADAPTER_CONTRACT.md §6.1 taxonomy.

    ``code`` MUST be one of the enum values from §6.1 so the retry / cooldown
    / pool side-effect machinery (``account_pool.report_failure``,
    ``executeWithRetry``) can react without string parsing. ``detail`` is
    free-form operator-readable context appended to the log line.

    A dedicated module-local class (rather than reusing one from
    ``agent/error_codes.py`` or similar) keeps this connector's dependency
    surface minimal — the VM rollout will inevitably move this into a
    shared ``adapter_errors`` module once #1115 / #1116 land, but
    pre-creating that abstraction before the second consumer exists would
    just be premature factoring.
    """

    code: str
    detail: str = ""
    # Optional structured fields. Kept as keyword-only attrs (not dataclass
    # fields) so the error can be raised with just ``code=`` for the common
    # path; the side-effect handler reads getattr(..., default=None).

    def __init__(self, code: str, *, detail: str = "", **extras):
        self.code = code
        self.detail = detail
        for key, value in extras.items():
            setattr(self, key, value)
        super().__init__(f"{code}: {detail}" if detail else code)


class RemoteCDPConnector(BrowserConnector):
    """Connect over CDP to a long-lived VM-side browser.

    Args:
        vm_registry: Source of truth for "which hostname:port serves this
            ``vm_id``". Defaults to env-driven registry
            (``VM_REGISTRYzehd``) so existing single-process deploys can wire it
            without dependency injection plumbing. Tests pass a stub.
        playwright_factory: Override the Playwright entry point. Tests pass
            ``lambda: fake_async_playwright_module`` so they can drive the
            CDP connect call without a real Playwright install. Production
            paths use the imported ``async_playwright`` directly.

    Lifetime: one connector instance per query, matching the
    ``LocalLaunchConnector`` contract. The CDP ``Browser`` handle returned
    by ``connect_over_cdp`` is tracked on ``self._browser`` so
    ``release_context`` can detach cleanly even when the caller has lost
    the ``BrowserContext`` reference (e.g. cancellation).
    """

    def __init__(
        self,
        vm_registry: Optional[VmRegistry] = None,
        *,
        playwright_factory=None,
    ) -> None:
        self.vm_registry: VmRegistry = vm_registry or VmRegistryFromEnv()
        self._playwright_factory = playwright_factory or async_playwright

        # Resources owned by the most recent acquire_context call.
        self._playwright = None
        self._browser = None
        # Attributes the executor (post-#1113 refactor) reads off any
        # connector after acquire. We expose stub values so the caller's
        # post-acquire code path stays identical to LocalLaunchConnector.
        self.local_storage_data: dict = {}
        self.use_camoufox: bool = False
        self.active_qg_lease = None
        self.injected_cookies_count: int = 0

    async def acquire_context(self, llm: str, account) -> "BrowserContext":
        """Connect to the VM's CDP endpoint and return its default context.

        Failures are mapped to the canonical error code taxonomy so the
        upstream retry / cooldown machinery can react. NEVER calls
        ``new_context`` (would lose the warm session) and NEVER calls
        ``add_cookies`` (the ``chk_exec_mode_cookies`` DB constraint
        guarantees ``vm_session`` rows carry no cookies — there is nothing
        to inject).
        """
        vm_id = getattr(account, "vm_id", None)
        if not vm_id:
            raise AdapterError(
                "NO_ACCOUNT_AVAILABLE",
                detail="vm_session account without vm_id",
                accountId=getattr(account, "id", None),
            )

        vm: VmInfo | None = await self.vm_registry.lookup(vm_id)
        if vm is None or vm.status != "alive":
            raise AdapterError(
                "PROXY_DEAD",
                detail=(
                    f"vm {vm_id!r} unreachable "
                    f"(registry={'missing' if vm is None else vm.status})"
                ),
                proxyId=vm_id,
            )

        endpoint = vm.cdp_endpoint(llm)
        logger.info(
            "[%s] RemoteCDPConnector connecting account=%s vm=%s endpoint=%s",
            llm,
            getattr(account, "id", None),
            vm_id,
            endpoint,
        )

        self._playwright = await self._playwright_factory().start()
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(endpoint)
        except Exception as exc:
            # VM was in registry but the actual CDP TCP socket refused.
            # Map to PROXY_DEAD so retries can spend a different VM (the
            # registry watchdog from Issue #1115 will down-mark this VM
            # within a beat). Detail captures the underlying error so the
            # operator log shows the real cause without leaking
            # endpoint:port to the analytics surface.
            await self._safe_stop_playwright()
            raise AdapterError(
                "PROXY_DEAD",
                detail=f"cdp connect failed for vm={vm_id!r}: {exc!r}",
                proxyId=vm_id,
            ) from exc

        contexts = list(getattr(self._browser, "contexts", []) or [])
        if not contexts:
            # The VM-side Chrome lost its persistent profile (process
            # crash, OOM, profile dir wiped). Map to PAGE_CRASHED so the
            # retry layer triggers a context restart rather than burning
            # an account ricochet strike.
            raise AdapterError(
                "PAGE_CRASHED",
                detail="vm chrome has no default context",
                consoleDump=f"vm={vm_id!r} contexts=0",
            )

        # The VM owns session state. Return the warm default context
        # directly — do NOT call new_context (would land in a blank
        # incognito-style context with no cookies) and do NOT call
        # add_cookies (DB constraint forbids cookies_json on vm_session
        # rows; nothing to inject anyway).
        return contexts[0]

    async def release_context(self, context: "BrowserContext") -> None:
        """Detach the CDP client; the VM-side Chrome stays running.

        Per Playwright docs, calling ``Browser.close()`` on a Browser
        returned by ``connect_over_cdp`` performs a CDP detach rather
        than terminating the remote Chrome — exactly the semantics this
        connector needs (the VM's warm session must persist across
        queries; only #1115's watchdog or admin teardown should kill
        the VM-side process).
        """
        # ``context`` argument is documented in the ABC; we accept it for
        # symmetry but do nothing with it — Browser.close() is the CDP
        # detach in Playwright, and per-context close on a CDP browser
        # has no effect on the VM side.
        del context

        try:
            if self._browser is not None:
                await self._browser.close()
        except Exception as exc:
            # Detach failures are logged but do not propagate — we are in
            # a cleanup path and the connector instance is about to be
            # discarded. Aborting cleanup would leave the playwright
            # process handle leaking.
            logger.warning(
                "RemoteCDPConnector release: browser.close() raised %r "
                "(treating as detach-complete)",
                exc,
            )
        finally:
            self._browser = None
            await self._safe_stop_playwright()

    async def _safe_stop_playwright(self) -> None:
        if self._playwright is None:
            return
        try:
            await self._playwright.stop()
        except Exception as exc:
            logger.warning(
                "RemoteCDPConnector release: playwright.stop() raised %r",
                exc,
            )
        finally:
            self._playwright = None
