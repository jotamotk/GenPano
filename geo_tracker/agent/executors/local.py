"""``LocalLaunchConnector`` — launch a local Camoufox/Chromium and inject cookies.

Refs Epic #1110 / Issue #1113.

This is the production default and the only ``BrowserConnector`` shipped
in this PR. It mirrors the exact launch + cookie-injection sequence that
previously lived inline in
``geo_tracker.agent.guest_executor.GuestQueryExecutor._execute_once``:

  1. Decide ``use_camoufox`` (HAS_CAMOUFOX and (use_proxy or
     needs_stealth or qg_active_for_doubao)).
  2. Build ``camoufox_kwargs`` (Doubao timezone/geo pinning, qg lease
     proxy, persisted fingerprint reuse), or build plain Chromium
     ``launch`` args (ADAPTER_CONTRACT.md §4.1 flags).
  3. Open a new ``BrowserContext`` with the correct locale / timezone /
     viewport for domestic vs. international LLMs.
  4. Install the resource blocker.
  5. Parse ``account.cookies_json`` (new format ``{"cookies": [...],
     "localStorage": {...}}`` or legacy plain list) and inject cookies
     via ``context.add_cookies``. ``localStorage`` is returned via
     :attr:`local_storage_data` so the caller can apply it after
     ``context.new_page()`` (localStorage requires a Page, which is
     created on the executor side of the boundary).

This is **structural refactor only** — no behavior change. Every
launch arg, env-var read, fingerprint path, qg lease flow, and cookie
format is preserved verbatim. The corresponding RemoteCDPConnector
(Issue #1114) will replace this class without touching the executor.
"""
from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright

from geo_tracker.agent.browser_fingerprint import (
    extract_fingerprint_from_account_cookies,
)
from geo_tracker.agent.browser_lifecycle import cleanup_browser_resources
from geo_tracker.agent.executors.base import BrowserConnector

try:
    from camoufox.async_api import AsyncCamoufox

    HAS_CAMOUFOX = True
except ImportError:
    HAS_CAMOUFOX = False

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext

    from geo_tracker.agent.qg_proxy import QGProxyClient

logger = logging.getLogger(__name__)


# Mirrors guest_executor.DOMESTIC_LLMS. The connector keeps its own copy
# rather than importing the symbol to avoid a circular import — both
# modules independently need the set and the membership is part of the
# product taxonomy, not a per-call configuration. If the set drifts the
# test suite catches it (the connector test imports both).
_DOMESTIC_LLMS = {"kimi", "doubao", "deepseek", "zhipu"}


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _block_heavy_resources() -> bool:
    return _env_flag("BROWSER_BLOCK_HEAVY_RESOURCES", True)


async def _install_resource_blocker(context: "BrowserContext") -> None:
    """Drop non-essential assets to keep browser workers inside cgroup limits.

    Behavior-identical copy of ``guest_executor._install_resource_blocker``
    — kept here so the launch path is self-contained for the
    Connector boundary. Both functions read the same env flag.
    """
    if not _block_heavy_resources():
        return

    async def _route(route):
        if route.request.resource_type in {"image", "media", "font"}:
            await route.abort()
            return
        await route.continue_()

    await context.route("**/*", _route)


def _load_cookies_from_env(env_var: str) -> list:
    raw = os.getenv(env_var, "").strip()
    if not raw:
        return []
    try:
        cookies = json.loads(raw)
        logger.info(f"Loaded {len(cookies)} cookies from {env_var}")
        return cookies
    except Exception as e:
        logger.warning(f"Failed to parse {env_var}: {e}")
        return []


def _local_storage_from_storage_state(
    storage_state: dict | None,
    target_url: str,
) -> dict:
    """Extract ``localStorage`` items for ``target_url`` from a Playwright
    ``storageState`` payload. Behavior-identical to the helper of the same
    name in ``guest_executor``."""
    if not isinstance(storage_state, dict):
        return {}
    try:
        target = urlparse(target_url)
        target_origin = f"{target.scheme}://{target.netloc}".rstrip("/")
    except Exception:
        target_origin = ""
    origins = storage_state.get("origins") or []
    if not isinstance(origins, list):
        return {}
    for origin in origins:
        if not isinstance(origin, dict):
            continue
        if target_origin and str(origin.get("origin", "")).rstrip("/") != target_origin:
            continue
        items = origin.get("localStorage") or []
        if isinstance(items, list):
            return {
                str(item.get("name")): item.get("value")
                for item in items
                if isinstance(item, dict) and item.get("name") and item.get("value")
            }
    return {}


class LocalLaunchConnector(BrowserConnector):
    """Launch a local Camoufox or Chromium and inject cookies.

    Constructor args mirror the inputs previously read inline by
    ``GuestQueryExecutor._execute_once``:

    Args:
        proxy_url: Outbound proxy URL (Clash). ``None`` means direct.
        account_cookies: JSON string from ``LLMAccount.cookies_json``.
            Either the legacy plain-list shape or the
            ``{"cookies": [...], "localStorage": {...},
            "storageState": {...}}`` shape.
        use_proxy: Whether the caller has decided this query should
            actually use ``proxy_url`` (Doubao-direct vs. ChatGPT-proxied,
            see ``guest_executor._should_use_proxy_for_llm``). The
            connector does NOT re-decide this — it just consumes the
            decision so its own ``camoufox_kwargs`` reflect it.
        target_url: The page URL the executor will navigate to after
            ``acquire_context``. Used only to extract per-origin
            ``localStorage`` items from a Playwright ``storageState``
            payload (mirrors the old inline call).
        config: The ``GUEST_LLM_CONFIG`` entry for the LLM. Used to look
            up ``cookies_env`` for env-cookie fallback. The connector
            otherwise treats it as opaque data.
        qg_proxy_client: Doubao rotating-IP proxy client, or ``None``.
            When provided AND the LLM is Doubao, ``acquire_context``
            reserves a fresh IP and pins the Camoufox launch to it. The
            lease is exposed via :attr:`active_qg_lease` so the caller
            can ``report_failure`` on it when Doubao serves an
            IP-level block.

    The connector also exposes the parsed payload via attributes so the
    caller (which still owns the Page and the post-launch stealth +
    localStorage injection) can pick up where ``acquire_context``
    leaves off without re-parsing ``account_cookies``:

        - :attr:`local_storage_data`     -- dict of items to write via
          ``page.evaluate`` after ``context.new_page()``.
        - :attr:`use_camoufox`           -- True if the launch went via
          Camoufox; the caller skips the manual stealth init script when
          this is True (Camoufox already covers it).
        - :attr:`active_qg_lease`        -- qg lease used by the current
          launch, or ``None``. Caller is responsible for calling
          ``qg_proxy_client.report_failure(lease.ip_port)`` when
          appropriate (IP-block failure modes).
        - :attr:`injected_cookies_count` -- int. Number of cookies the
          connector added to the context via ``add_cookies``. The
          ChatGPT session-refresh block in ``guest_executor`` reads
          this to decide whether to attempt the post-launch refresh.
    """

    def __init__(
        self,
        *,
        proxy_url: Optional[str] = None,
        account_cookies: Optional[str] = None,
        use_proxy: bool = False,
        target_url: str = "",
        config: Optional[dict] = None,
        qg_proxy_client: "Optional[QGProxyClient]" = None,
    ) -> None:
        self.proxy_url = proxy_url
        self.account_cookies = account_cookies
        self.use_proxy = use_proxy
        self.target_url = target_url
        self.config = config or {}
        self.qg_proxy_client = qg_proxy_client

        # Resources owned by the most recent acquire_context call. Cleared
        # by release_context. Multiple concurrent acquires per connector
        # instance are NOT supported (one connector per executor per
        # query, same as the inline behavior).
        self._browser: Any = None
        self._camoufox_ctx: Any = None
        self._playwright: Any = None

        # Exposed to caller (see class docstring).
        self.local_storage_data: dict = {}
        self.use_camoufox: bool = False
        self.active_qg_lease: Any = None
        # Refs #1113: ChatGPT post-launch session-refresh in
        # ``guest_executor._execute_once`` gates on whether any cookies
        # were actually injected. Surfaced as an int rather than the
        # raw list so the inner cookie payload (which may contain
        # sensitive session tokens) does not leak across the connector
        # boundary; truthiness alone is enough for the gate.
        self.injected_cookies_count: int = 0

    async def acquire_context(self, llm: str, account) -> "BrowserContext":
        """Launch the browser and return a cookie-injected ``BrowserContext``.

        ``account`` is currently unused by this connector (account state
        flows through ``account_cookies`` set on the constructor). It is
        kept in the signature so ``RemoteCDPConnector`` (#1114) can use
        it to pick the correct VM without breaking the ABC.
        """
        del account  # see docstring; reserved for #1114

        # Step 1: pick launch strategy. Camoufox is preferred whenever
        # the LLM needs login / cookies / proxy or whenever the qg
        # rotating-IP path is active (Doubao + qg client configured),
        # because Camoufox is the only path that disables WebRTC at
        # the Firefox level — the Chromium fallback only has the
        # policy flag, which is weaker.
        needs_stealth = self.config.get("requires_login") or bool(self.account_cookies)
        qg_active_for_doubao = llm == "doubao" and self.qg_proxy_client is not None
        use_camoufox = HAS_CAMOUFOX and (
            self.use_proxy or needs_stealth or qg_active_for_doubao
        )
        self.use_camoufox = use_camoufox

        if use_camoufox:
            context = await self._launch_camoufox(llm)
        else:
            context = await self._launch_plain_playwright(llm)

        await _install_resource_blocker(context)

        # Step 2: parse account cookies (new format or legacy list) and
        # inject into the context. localStorage is captured for the
        # caller to apply after page creation.
        injected_cookies: list = []
        local_storage_data: dict = {}
        if self.account_cookies:
            from geo_tracker.agent.guest_executor import _redact_sensitive_text

            try:
                parsed = json.loads(self.account_cookies)
                if isinstance(parsed, dict) and "cookies" in parsed:
                    injected_cookies = parsed.get("cookies", [])
                    local_storage_data = parsed.get("localStorage", {})
                    if not local_storage_data:
                        local_storage_data = _local_storage_from_storage_state(
                            parsed.get("storageState"),
                            self.config.get("url", ""),
                        )
                    logger.info(
                        f"[{llm}] 使用 AccountPool cookies ({len(injected_cookies)} 个) "
                        f"+ localStorage ({len(local_storage_data)} 项)"
                    )
                elif isinstance(parsed, list):
                    injected_cookies = parsed
                    logger.info(
                        f"[{llm}] 使用 AccountPool cookies ({len(injected_cookies)} 个)"
                    )
            except Exception as e:
                logger.warning(
                    f"[{llm}] 解析 account_cookies 失败: "
                    f"{_redact_sensitive_text(str(e))}"
                )

        if not injected_cookies:
            cookies_env = self.config.get("cookies_env")
            if cookies_env:
                injected_cookies = _load_cookies_from_env(cookies_env)

        if injected_cookies:
            await context.add_cookies(injected_cookies)
            logger.info(f"[{llm}] 已注入 {len(injected_cookies)} 个 cookies")

        self.local_storage_data = local_storage_data
        # Number of cookies actually injected into the context.
        # ``guest_executor`` reads this in its ChatGPT post-launch
        # session-refresh block (the block gates on "did we inject
        # cookies?"); preserving the truthiness signal across the
        # extraction is part of the zero-behavior-change contract.
        self.injected_cookies_count = len(injected_cookies)
        return context

    async def release_context(self, context: "BrowserContext") -> None:
        """Close the browser context and the entire browser stack.

        Routes through ``cleanup_browser_resources`` so a single hung
        Chromium close cannot prevent the rest of the stack from being
        torn down (production incident 2026-04-27 root cause). ``page``
        is ``None`` here because the caller owns the page and is
        expected to close it via its own cleanup chain BEFORE calling
        ``release_context`` (or to pass ``page=None`` to its own
        ``cleanup_browser_resources`` and let this connector handle
        the rest — both orderings are safe because ``cleanup_browser``
        is idempotent).

        Future ``RemoteCDPConnector`` will override this to ``detach``
        the CDP client without closing the VM-side browser.
        """
        await cleanup_browser_resources(
            page=None,
            context=context,
            browser=self._browser,
            camoufox_ctx=self._camoufox_ctx,
            playwright=self._playwright,
        )
        self._browser = None
        self._camoufox_ctx = None
        self._playwright = None
        # active_qg_lease is intentionally NOT cleared here: the caller
        # reads it in its own failure-handling finally block to decide
        # whether to report_failure() on the IP. The caller clears it.

    async def _launch_camoufox(self, llm: str) -> "BrowserContext":
        """Camoufox launch path. Verbatim port of the inline block in
        ``guest_executor._execute_once``."""
        logger.info(f"[{llm}] 启动 Camoufox 浏览器...")
        is_domestic = llm in _DOMESTIC_LLMS
        camoufox_kwargs: dict = {
            "headless": True,
            "humanize": True,
            "block_images": _block_heavy_resources(),
            "os": "windows",
            "locale": "zh-CN" if is_domestic else "en-US",
            # Refs #963 Q-184988 follow-up: WebRTC STUN bypasses HTTP
            # proxies and leaks the worker's static egress IP. Disabling
            # WebRTC entirely (media.peerconnection.enabled = false)
            # closes the leak so Doubao only ever sees the qg IP.
            # ``disable_coop`` lets cross-origin captcha iframes be
            # interacted with when one does fire.
            "block_webrtc": True,
            "disable_coop": True,
            "i_know_what_im_doing": True,
        }
        # Refs #963 doubao_homepage_content follow-up: pin Camoufox to
        # Shanghai geo + timezone for Doubao so JS geo matches qg
        # exit-IP geo. The Dockerfile installs tzdata so Firefox can
        # actually resolve Asia/Shanghai.
        if llm == "doubao":
            camoufox_kwargs["config"] = {
                "timezone": "Asia/Shanghai",
                "geolocation:longitude": 121.4737,
                "geolocation:latitude": 31.2304,
                "geolocation:accuracy": 100,
            }
            camoufox_kwargs["env"] = {**os.environ, "TZ": "Asia/Shanghai"}

        # Refs #963: qg.net rotating-IP proxy for Doubao. Reserve a fresh
        # residential / mobile IP per query so the worker's native egress
        # IP doesn't get fingerprinted by Doubao risk control.
        qg_lease = None
        if llm == "doubao" and self.qg_proxy_client is not None:
            try:
                qg_lease = await self.qg_proxy_client.reserve()
            except Exception as exc:
                from geo_tracker.agent.guest_executor import _redact_sensitive_text

                logger.warning(
                    "[%s] qg proxy reserve failed (%s); "
                    "falling back to default proxy path",
                    llm,
                    _redact_sensitive_text(str(exc))[:200],
                )
        if qg_lease is not None:
            self.active_qg_lease = qg_lease
            camoufox_kwargs["proxy"] = {
                "server": qg_lease.server_url,
                "username": qg_lease.auth_key,
                "password": qg_lease.auth_password,
            }
            logger.info(
                "[%s] using qg.net rotating proxy IP %s",
                llm,
                qg_lease.ip_port.split(":")[0] + ":[port-redacted]",
            )
        elif self.use_proxy:
            camoufox_kwargs["proxy"] = {"server": self.proxy_url}

        # Refs #963: reuse the Camoufox fingerprint that auto_login
        # captured for this account so the query opens with the exact
        # same UA/screen/Canvas seed Doubao saw when the cookies were
        # issued.
        saved_fp = extract_fingerprint_from_account_cookies(self.account_cookies)
        if saved_fp is not None:
            camoufox_kwargs["fingerprint"] = saved_fp
            logger.info(
                "[%s] reusing persisted Camoufox fingerprint for account",
                llm,
            )

        self._camoufox_ctx = AsyncCamoufox(**camoufox_kwargs)
        self._browser = await self._camoufox_ctx.__aenter__()
        logger.info(f"[{llm}] Camoufox 启动成功")

        context = await self._browser.new_context()
        return context

    async def _launch_plain_playwright(self, llm: str) -> "BrowserContext":
        """Plain Chromium launch path. Verbatim port of the inline block in
        ``guest_executor._execute_once``."""
        logger.info(f"[{llm}] 启动 Playwright 浏览器...")
        proxy_cfg = {"server": self.proxy_url} if self.use_proxy else None
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            proxy=proxy_cfg,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu",
                "--use-gl=swiftshader",
                "--no-zygote",
                "--window-size=1920,1080",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                # Refs #963: force WebRTC through the proxy (or none) so
                # the worker's static egress IP doesn't leak via STUN.
                # The Camoufox path disables WebRTC entirely via
                # media.peerconnection.enabled=false; the Chromium
                # fallback uses the Chromium-equivalent policy flag so
                # symmetric behaviour holds either way.
                "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            ],
        )
        logger.info(f"[{llm}] Playwright 启动成功")

        is_domestic = llm in _DOMESTIC_LLMS
        context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN" if is_domestic else "en-US",
            timezone_id="Asia/Shanghai" if is_domestic else "America/New_York",
            ignore_https_errors=True,
            bypass_csp=True,
            reduced_motion="reduce",
        )
        return context
