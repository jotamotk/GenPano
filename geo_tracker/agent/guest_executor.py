"""
无账号浏览器执行器（Guest Mode）
- 使用 Playwright 直接访问 LLM 网站，无需账号
- 支持 ChatGPT、Gemini、Perplexity、Kimi、Doubao、DeepSeek 等
- Gemini 支持通过 GEMINI_COOKIES_JSON 环境变量注入 Google session cookie
- Doubao 支持通过 DOUBAO_COOKIES_JSON 环境变量注入火山引擎 session cookie
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright, BrowserContext, Page

# Camoufox: 反指纹浏览器，海外 LLM 优先使用以绕过 Cloudflare
try:
    from camoufox.async_api import AsyncCamoufox
    HAS_CAMOUFOX = True
except ImportError:
    HAS_CAMOUFOX = False

from geo_tracker.agent.browser_lifecycle import cleanup_browser_resources
from geo_tracker.agent.captcha import CaptchaSolver, detect_and_solve, CAPSOLVER_API_KEY
from geo_tracker.agent.clash_api import (
    ensure_global_proxy_route,
    get_last_error_reason,
    get_current_node,
    switch_to_next_node,
    CLASH_API_URL,
)
from geo_tracker.agent.citation_extraction import (
    classify_citation_extraction,
    extract_citations_from_html,
    extract_doubao_panel_citations_from_html,
    merge_citations,
)
from geo_tracker.agent.response_validation import (
    chatgpt_auth_state_reason,
    DOUBAO_AUTH_OK_MARKER,
    doubao_auth_state_reason,
    doubao_persistence_auth_reason,
    invalid_response_reason,
)
from geo_tracker.db.models import LLMResponse, Query
from geo_tracker.tasks.query_failure import (
    browser_execution_timeout_reason,
    resolve_execution_failure_reason,
)

logger = logging.getLogger(__name__)

# 重试配置
MAX_RETRY_ON_CF_BLOCK = 3                          # Cloudflare 拦截最大重试次数
CLASH_PROXY_GROUP = os.getenv("CLASH_PROXY_GROUP", "💬 Ai平台")  # Clash 代理组名称（含实际节点）
CF_CHALLENGE_TITLES = [
    "just a moment", "attention required", "checking your browser",
    "unable to load site", "please wait", "access denied",
]
DOUBAO_UNAVAILABLE_MARKERS = (
    "\u8be5\u9875\u9762\u6682\u65f6\u4e0d\u53ef\u7528",
    "\u9875\u9762\u6682\u65f6\u4e0d\u53ef\u7528",
    "\u5237\u65b0\u9875\u9762",
    "\u8fd4\u56de\u9996\u9875",
)
DOUBAO_VISUAL_CHALLENGE_REASON = "doubao_visual_challenge"
DOUBAO_IMAGE_CHALLENGE_LOAD_FAILED_REASON = "doubao_image_challenge_load_failed"
DOUBAO_VISUAL_CHALLENGE_MARKERS = (
    "\u8bf7\u9009\u62e9\u6240\u6709\u7b26\u5408\u4e0a\u6587\u63cf\u8ff0\u7684\u56fe\u7247",
    "\u5e76\u62d6\u62fd\u5230\u4e0b\u65b9",
    "\u62d6\u62fd\u5230\u4e0b\u65b9",
    "\u9009\u62e9\u6240\u6709\u7b26\u5408",
    "\u9700\u8981\u7535\u529b\u9a71\u52a8\u7684\u4e1c\u897f",
)
DOUBAO_IMAGE_CHALLENGE_LOAD_FAILED_MARKERS = (
    "\u56fe\u7247\u52a0\u8f7d\u5931\u8d25",
    "\u8bf7\u5237\u65b0\u91cd\u8bd5",
    "[5202]",
    "5202",
)

SCREENSHOT_DIR = Path(os.getenv("SCREENSHOT_DIR", "/data/screenshots"))
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# Refs #963 follow-up to PR #1008 live evidence (Admin E2E run 25924635842
# query 184968 retry 20, stage=prompt_fill, latency=481115ms): each
# ``_fill_plain_text_input`` step is individually bounded so a page in a
# degenerate state (overlay covering input, focus stolen, browser context
# dead-but-not-yet-collected) cannot burn the outer execute_query budget.
# Bounds are kept generous vs. the expected work (typical 30-char query
# completes in ~3s) so legitimate slow renders still succeed; they exist to
# fail fast on a stuck page. Exposed as module constants so the regression
# test can monkeypatch them down for sub-second CI runs (Codex review on
# PR #1009, P2). Production values must not change.
PROMPT_FILL_CLEAR_TIMEOUT_S = 10
PROMPT_FILL_INJECT_TIMEOUT_S = 15
PROMPT_FILL_KEYBOARD_TYPE_TIMEOUT_S = 60
PROMPT_FILL_VALUE_READ_TIMEOUT_S = 10

# Refs #963 follow-up to PR #1010 live evidence (Admin E2E run 25927727628
# query 184968 retry 22, stage=response_wait, latency=480972ms): after
# PR #1010 unblocked prompt_fill, the next bottleneck surfaced as
# response_wait at the full 480s budget. The wait_total counter inside
# the loop is bounded to wait_after_submit (60s) + extension_max (120s)
# = 180s, so additional time is being burned by unbounded calls inside
# the wait loop and the post-loop response extraction. Each individual
# call is bounded so a single hung page op cannot eat the budget.
RESPONSE_WAIT_GENERATING_EVAL_TIMEOUT_S = 3
RESPONSE_EXTRACT_SELECTOR_TIMEOUT_S = 10

# Refs #963 follow-up to PR #1013 live evidence (Admin E2E run 25928885380
# query 184968 retry 23, stage=response_wait, latency=480897ms): the
# per-call 10s bound on still_generating evaluate was too loose — a
# degenerate page tripping the bound every iteration burned ~15s per
# iteration × ~24 extensions = ~360s in the loop alone, plus earlier
# stages = full 480s budget. Tighter eval bound (3s) AND a hard outer
# stage budget guarantee response_wait cannot exceed this regardless
# of how many wait_total extensions happen or how each inner call
# behaves.
RESPONSE_WAIT_STAGE_BUDGET_S = 240


_SENSITIVE_TEXT_PATTERNS = [
    (
        re.compile(
            r'("(?:access|refresh|id|session)?token"\s*:\s*")[^"]+(")',
            re.IGNORECASE,
        ),
        r'\1[redacted]\2',
    ),
    (
        re.compile(
            r'("(?:authorization|cookie|set-cookie)"\s*:\s*")[^"]+(")',
            re.IGNORECASE,
        ),
        r'\1[redacted]\2',
    ),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE), "Bearer [redacted]"),
    (re.compile(r"(https?://)[^/@\s:]+:[^/@\s]+@", re.IGNORECASE), r"\1[redacted]@"),
]


def _is_doubao_unavailable_page_text(body_text: str | None) -> bool:
    return any(marker in (body_text or "") for marker in DOUBAO_UNAVAILABLE_MARKERS)


def _doubao_visual_challenge_state_from_text(text: str | None) -> dict:
    """Return sanitized Doubao visual challenge evidence from page/dialog text."""
    raw_text = _redact_sensitive_text(text or "")
    if not raw_text:
        return {}

    matched_markers = [
        marker for marker in DOUBAO_VISUAL_CHALLENGE_MARKERS if marker in raw_text
    ]
    button_markers = [
        marker for marker in ("\u5237\u65b0", "\u53cd\u9988", "\u63d0\u4ea4") if marker in raw_text
    ]
    image_load_failed = any(
        marker in raw_text for marker in DOUBAO_IMAGE_CHALLENGE_LOAD_FAILED_MARKERS
    )
    if len(matched_markers) < 2 and not (
        matched_markers and image_load_failed and len(button_markers) >= 2
    ):
        return {}

    reason = (
        DOUBAO_IMAGE_CHALLENGE_LOAD_FAILED_REASON
        if image_load_failed
        else DOUBAO_VISUAL_CHALLENGE_REASON
    )
    return {
        "reason": reason,
        "imageLoadFailed": image_load_failed,
        "matchedMarkers": matched_markers[:6],
        "buttonMarkers": button_markers[:3],
        "modalText": raw_text[:1000],
    }


async def _doubao_visual_challenge_state_from_page(page: Page | None) -> dict:
    if page is None:
        return {}
    body_text = ""
    html = ""
    try:
        body_text = await page.evaluate("document.body?.innerText || ''")
    except Exception:
        pass
    try:
        html = await page.content()
    except Exception:
        pass
    return _doubao_visual_challenge_state_from_text(f"{body_text}\n{html}")


def _redact_sensitive_text(text: str | None) -> str:
    if not text:
        return ""
    redacted = str(text)
    for pattern, replacement in _SENSITIVE_TEXT_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _redact_runtime_data(value):
    if isinstance(value, str):
        return _redact_sensitive_text(value)
    if isinstance(value, list):
        return [_redact_runtime_data(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_runtime_data(item) for key, item in value.items()}
    return value


def _chatgpt_session_log_summary(body: str | None) -> str:
    """Return metadata-only session diagnostics without user/token values."""
    body = body or ""
    try:
        data = json.loads(body)
    except Exception:
        return f"json=False body_len={len(body)}"

    data = data if isinstance(data, dict) else {}
    user = data.get("user")
    return (
        "json=True "
        f"body_len={len(body)} "
        f"access_token_present={bool(data.get('accessToken'))} "
        f"user_present={bool(user)} "
        f"expires_present={bool(data.get('expires'))}"
    )


def _debug_query_id(query_id: int | None) -> int:
    return query_id if isinstance(query_id, int) and query_id > 0 else -1

# 从环境变量加载各 LLM 的 cookies（JSON 数组格式）
def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return default


def _block_heavy_resources() -> bool:
    return _env_flag("BROWSER_BLOCK_HEAVY_RESOURCES", True)


def _force_global_proxy_route() -> bool:
    return _env_flag("CLASH_FORCE_GLOBAL_PROXY_ROUTE", True)


def _doubao_proxy_enabled() -> bool:
    return _env_flag("DOUBAO_USE_PROXY", True)


def _should_use_proxy_for_llm(llm_name: str, proxy_url: str | None) -> bool:
    if not proxy_url:
        return False
    if llm_name == "doubao":
        return _doubao_proxy_enabled()
    return llm_name not in DOMESTIC_LLMS


def _requires_global_proxy_route(llm_name: str) -> bool:
    return llm_name in {"chatgpt", "doubao"} and _force_global_proxy_route()


def _proxy_runtime_diagnostic(llm_name: str, proxy_url: str | None, use_proxy: bool) -> dict:
    return {
        "llm": llm_name,
        "proxyConfigured": bool(proxy_url),
        "useProxy": bool(use_proxy),
        "proxyUrl": _redact_sensitive_text(proxy_url or ""),
        "forceGlobalRoute": _force_global_proxy_route(),
        "doubaoUseProxy": _doubao_proxy_enabled() if llm_name == "doubao" else None,
    }


async def _install_resource_blocker(context: BrowserContext) -> None:
    """Drop non-essential assets to keep browser workers inside cgroup limits."""
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

# 各 LLM 的浏览器操作配置（无账号 guest 模式）
def _local_storage_from_storage_state(
    storage_state: dict | None,
    target_url: str,
) -> dict:
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


GUEST_LLM_CONFIG = {
    "chatgpt": {
        "url":              "https://chatgpt.com",
        # #prompt-textarea 是 ProseMirror contenteditable div，不是 textarea
        "input_selector":   "#prompt-textarea, div[contenteditable='true'][role='textbox'], [data-testid='prompt-textarea'], textarea, [role='textbox']",
        # 走 JS 注入路径（contenteditable=True 会启用 execCommand/paste/innerHTML 三段兜底）
        "contenteditable":  True,
        # 发送按钮：composer-submit-button-color 是稳定 class，aria-label="Send prompt" 是文案
        # 排除语音按钮（aria-label 含 Voice/dictation）
        "submit_button":    "button[aria-label='Send prompt'], button[data-testid='send-button'], button.composer-submit-button-color[aria-label*='Send'], #composer-submit-button",
        "submit_key":       "Enter",
        "response_selector": "[data-message-author-role='assistant'] .markdown, [data-message-author-role='assistant']",
        "wait_after_submit": 25000,
        "load_wait":        15000,
        # ChatGPT 有账号模式：确保登录态以获取精准 GEO 数据和 citation
        "requires_login":   True,
        "cookies_env":      "CHATGPT_COOKIES_JSON",
        "dismiss_selectors": [
            "button:has-text('Dismiss')",
            "button:has-text('Stay logged out')",
            "button:has-text('Reject')",
            "button:has-text('Decline')",
            "[aria-label='Close']",
            "[aria-label='Dismiss']",
            "button:has-text('No thanks')",
            "button:has-text('Maybe later')",
        ],
        "login_redirect_domains": [
            "appleid.apple.com",
            "auth0.openai.com",
            "auth.openai.com",
            "login.openai.com",
        ],
    },
    "gemini": {
        "url":              "https://gemini.google.com/app",
        "input_selector":   "rich-textarea .ql-editor, rich-textarea, [contenteditable='true'], textarea",
        "submit_button":    "button.send-button, button[aria-label='Send message'], button[aria-label='Send']",
        "submit_key":       "Enter",
        # Gemini uses Angular custom elements; try specific tags first, then broad fallbacks
        "response_selector": "model-response message-content, model-response .response-content, model-response, message-content, .model-response-text, .response-content, div[class*='model-response'], div[class*='response-text'], .markdown, .prose",
        "wait_after_submit": 60000,
        "load_wait":        15000,
        # requires_login 在运行时动态判断：有 GEMINI_COOKIES_JSON 则 False，否则 True
        "requires_login":   not bool(os.getenv("GEMINI_COOKIES_JSON", "").strip()),
        "cookies_env":      "GEMINI_COOKIES_JSON",  # 注入 cookie 用的环境变量名
        "contenteditable":  True,
        "visit_google_first": False,
        # Domains that indicate a login redirect (response is invalid if we land here)
        "login_redirect_domains": ["accounts.google.com", "signin.google.com"],
    },
    "perplexity": {
        "url":              "https://www.perplexity.ai",
        "input_selector":   "textarea, [placeholder*='Ask'], input[type='text']",
        "submit_key":       "Enter",
        "response_selector": ".prose, [class*='answer'], [class*='response']",
        "wait_after_submit": 15000,
        "load_wait":        4000,
        "requires_login":   False,
    },
    "kimi": {
        "url":              "https://kimi.moonshot.cn",
        "input_selector":   ".chat-input-editor, textarea, [contenteditable='true']",
        "submit_key":       "Enter",
        "response_selector": "[class*='segment-content'], [class*='message-content'], .chat-message",
        "wait_after_submit": 20000,
        "load_wait":        8000,
        "requires_login":   False,
        "contenteditable":  True,
    },
    "doubao": {
        "url":              "https://www.doubao.com/chat",
        # 豆包 2026 版 UI 不再使用 data-testid；改用稳定的 id / class：
        #   #input-engine-container 包裹整个输入区
        #   textarea.semi-input-textarea 是实际输入框（Semi Design）
        #   页面上还有一个 aria-hidden 的隐藏 textarea 用于自动撑高，需排除
        "input_selector":   "#input-engine-container textarea.semi-input-textarea:not([aria-hidden='true']), textarea.semi-input-textarea:not([aria-hidden='true']), textarea:not([aria-hidden='true']), [contenteditable='true']",
        # 发送按钮的稳定标识：id="flow-end-msg-send"；旧版用 testid，新版 UI 已不再使用
        # 禁用态通过 aria-disabled / data-disabled 属性表达，HTML disabled 属性并未设置，
        # 因此 :not([disabled]) 不能区分禁用态——必须显式排除这两个属性。
        "submit_button":    "#flow-end-msg-send:not([aria-disabled='true']):not([data-disabled='true']), button[id='flow-end-msg-send'], .send-btn-wrapper button:not([aria-disabled='true']):not([data-disabled='true']), button[class*='send-msg-btn']:not([aria-disabled='true']):not([data-disabled='true']):not([disabled]), button[data-testid='chat_input_send_button'], button[aria-label*='发送'], button[aria-label*='send' i], button[data-testid*='send']",
        "submit_key":       "Enter",
        # receive_message testid 已移除；用 .flow-markdown-body 作为 AI 响应容器的主 selector
        "response_selector": ".flow-markdown-body, [data-testid='receive_message'], [data-testid='receive_message'] [data-testid='message_text_content'], [data-testid='receive_message'] .flow-markdown-body, [class*='message-content'], [class*='chat-message-content']",
        "wait_after_submit": 60000,
        # Refs #963: when "深度思考" / "正在搜索" is still visible at 60s, or
        # the response is actively streaming/growing, allow response_wait to
        # extend up to this many additional milliseconds. 120s gives a 3-min
        # effective ceiling for slow Doubao responses while still leaving
        # the worker's 480s outer budget room for page_load + cleanup.
        "wait_after_submit_max_extension": 120000,
        "load_wait":        10000,
        # 动态判断：有 DOUBAO_COOKIES_JSON 则可免登录，否则需要登录
        "requires_login":   not bool(os.getenv("DOUBAO_COOKIES_JSON", "").strip()),
        "cookies_env":      "DOUBAO_COOKIES_JSON",
        # 豆包登录页域名检测
        "login_redirect_domains": ["passport.volcengine.com", "sso.volcengine.com", "passport.douyin.com"],
    },
    "deepseek": {
        "url":              "https://chat.deepseek.com",
        "input_selector":   "textarea, [contenteditable=true], input[type=text]",
        "submit_key":       "Enter",
        "response_selector": ".ds-markdown, [class*='message-content'] .markdown, [class*='message'] .markdown",
        "wait_after_submit": 90000,
        "load_wait":        8000,
        "requires_login":   True,
        "login_redirect_domains": ["login.deepseek.com", "deepseek.com/sign_in"],
        "stream_check_selector": "[class*='loading'], [class*='ds-loading'], .ds-icon-stop, button:has-text('Stop'), button:has-text('停止')",
    },
    "claude": {
        "url":              "https://claude.ai",
        "input_selector":   '[contenteditable="true"], textarea',
        "submit_key":       "Enter",
        "response_selector": ".claude-message .prose, [class*='message'], [class*='content']",
        "wait_after_submit": 20000,
        "load_wait":        8000,
        "requires_login":   True,
    },
    "grok": {
        "url":              "https://x.com/i/grok",
        "input_selector":   "textarea",
        "submit_key":       "Enter",
        "response_selector": "[data-testid='grok-response'] .prose, [class*='message']",
        "wait_after_submit": 20000,
        "load_wait":        8000,
        "requires_login":   True,
    },
    "zhipu": {
        "url":              "https://chatglm.cn",
        "input_selector":   "textarea",
        "submit_key":       "Enter",
        "response_selector": ".chat-message.assistant .content, [class*='message']",
        "wait_after_submit": 20000,
        "load_wait":        8000,
        "requires_login":   True,
    },
}

# 国内 LLM 列表（直连，不走代理）
DOMESTIC_LLMS = {"kimi", "doubao", "deepseek", "zhipu"}


class GuestQueryExecutor:
    """无账号查询执行器"""

    def __init__(self, proxy_url: Optional[str] = None, account_cookies: Optional[str] = None):
        """
        Args:
            proxy_url: 代理 URL，用于访问国际 LLM
            account_cookies: JSON string of cookies from LLMAccount (DB), 优先于环境变量
        """
        self.proxy_url = proxy_url or os.getenv("CLASH_PROXY_URL") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
        self.account_cookies = account_cookies
        self.last_error_reason: str | None = None
        self.execution_stage: str | None = None
        # Refs #963: when an outer asyncio.wait_for cancels execute(), the page
        # is cleaned up inside _execute_once's finally before the caller can
        # see TimeoutError. Track the active page + last-known URL/title/body
        # so the caller can attach operator-visible evidence even after
        # cancellation, and so the cancellation handler can save a snapshot
        # before cleanup runs.
        self.current_page: Page | None = None
        self.last_page_url: str | None = None
        self.last_page_title: str | None = None
        self.last_page_body_snippet: str | None = None
        self.last_snapshot_path: str | None = None
        # Refs #963 follow-up to PR #1005: ``execution_stage`` is clobbered to
        # ``"cleanup"`` by the inner _execute_once finally before the outer
        # ``asyncio.wait_for`` in ``celery_tasks._execute_with_timeout`` reads
        # it on TimeoutError, so failures classify as
        # ``doubao_browser_timeout:cleanup`` regardless of where execution was
        # actually stuck. Latch the real stage at cancellation / exception
        # time so callers can read past the finally-block overwrite.
        self.stage_at_failure: str | None = None

    def _set_execution_stage(self, stage: str) -> None:
        self.execution_stage = stage

    def _record_page_pointer(self, page: "Page | None") -> None:
        """Track the active page so cancellation handlers can preserve evidence."""
        self.current_page = page
        if page is not None:
            try:
                self.last_page_url = page.url
            except Exception:
                pass

    async def execute(self, query: Query) -> Optional[LLMResponse]:
        """
        执行单条查询（无账号模式）
        遇到 Cloudflare 拦截时自动切换 Clash 代理节点并重试

        Args:
            query: Query 对象

        Returns:
            LLMResponse 对象，如果失败返回 None
        """
        self.last_error_reason = None
        self._set_execution_stage("start")
        llm = query.target_llm
        config = GUEST_LLM_CONFIG.get(llm)
        if not config:
            logger.error(f"Unknown LLM: {llm}")
            self.last_error_reason = "unknown_llm"
            return None

        use_proxy = _should_use_proxy_for_llm(llm, self.proxy_url)

        # 国内 LLM 或不使用代理时，直接执行一次，无需重试换节点
        if not use_proxy:
            self._set_execution_stage("browser_session")
            return await self._execute_once(query, config, use_proxy=False)

        if _requires_global_proxy_route(llm):
            self._set_execution_stage("proxy_route_preflight")
            route = await ensure_global_proxy_route(CLASH_API_URL, CLASH_PROXY_GROUP)
            if not route.ok:
                self.last_error_reason = route.reason or "proxy_global_route_unavailable"
                logger.error(
                    "[%s] proxy route preflight failed: reason=%s global=%s:%s source=%s:%s",
                    llm,
                    self.last_error_reason,
                    route.global_group,
                    route.global_now,
                    route.source_group,
                    route.source_now,
                )
                return None
            logger.info(
                "[%s] proxy route preflight ok: global=%s selected=%s source=%s:%s changed=%s",
                llm,
                route.global_group,
                route.selected_node,
                route.source_group,
                route.source_now,
                route.changed,
            )

        # 海外 LLM：支持 Cloudflare 拦截后切换节点重试
        failed_nodes: set[str] = set()

        for attempt in range(MAX_RETRY_ON_CF_BLOCK):
            if attempt > 0:
                new_node = await switch_to_next_node(
                    CLASH_API_URL, CLASH_PROXY_GROUP, exclude=failed_nodes
                )
                if not new_node:
                    proxy_reason = get_last_error_reason() or "proxy_unavailable"
                    self.last_error_reason = proxy_reason
                    logger.error(
                        "[%s] proxy rotation stopped: %s (api=%s group=%s)",
                        llm,
                        proxy_reason,
                        CLASH_API_URL,
                        CLASH_PROXY_GROUP,
                    )
                    break
                logger.info(f"[{llm}] 第 {attempt + 1} 次重试，已切换到节点: {new_node}")

            self._set_execution_stage("browser_session")
            result = await self._execute_once(query, config, use_proxy=True)
            if result is not None:
                return result

            # 执行失败，记录当前节点
            current = await get_current_node(CLASH_API_URL, CLASH_PROXY_GROUP)
            if current:
                failed_nodes.add(current)
                logger.warning(f"[{llm}] 节点 {current} 失败，加入黑名单 (已排除 {len(failed_nodes)} 个)")

        logger.error(f"[{llm}] 所有重试均失败")
        self.last_error_reason = self.last_error_reason or "no_response"
        return None

    async def _execute_once(
        self, query: Query, config: dict, *, use_proxy: bool
    ) -> Optional[LLMResponse]:
        """执行一次查询尝试（可能因 Cloudflare 拦截返回 None）"""
        # Refs PR #933 review (Codex P2): execute() retries _execute_once in a
        # proxy-rotation loop without clearing self.last_error_reason between
        # attempts. resolve_execution_failure_reason() preserves any prior value,
        # so without this per-attempt reset, attempt N would inherit attempt
        # N-1's stale reason and mask the real exception of attempt N. Scope
        # the preservation to within a single _execute_once invocation.
        self.last_error_reason = None
        self._set_execution_stage("browser_launch")
        llm = query.target_llm
        proxy_cfg = {"server": self.proxy_url} if use_proxy else None
        proxy_diagnostic = _proxy_runtime_diagnostic(llm, self.proxy_url, bool(use_proxy))

        if use_proxy:
            logger.info(f"[{llm}] 使用代理: {self.proxy_url}")

        page_obj = None
        context = None
        browser = None
        _camoufox_ctx = None
        _playwright = None
        runtime_events: list[dict] = []

        def _record_runtime_event(kind: str, text: object) -> None:
            runtime_events.append(
                {
                    "ts": datetime.utcnow().isoformat() + "Z",
                    "kind": kind,
                    "text": _redact_sensitive_text(str(text))[:1000],
                }
            )
            if len(runtime_events) > 120:
                del runtime_events[: len(runtime_events) - 120]

        def _attach_runtime_debug(page: Page) -> None:
            page.on(
                "console",
                lambda msg: _record_runtime_event(
                    "console",
                    f"{getattr(msg, 'type', '')}: {getattr(msg, 'text', '')}",
                ),
            )
            page.on("pageerror", lambda exc: _record_runtime_event("pageerror", exc))

        try:
            # Camoufox 反指纹浏览器：海外 LLM 绕 Cloudflare，国内需登录的 LLM 绕反爬
            needs_stealth = config.get("requires_login") or bool(self.account_cookies)
            use_camoufox = HAS_CAMOUFOX and (use_proxy or needs_stealth)

            if use_camoufox:
                logger.info(f"[{llm}] 启动 Camoufox 浏览器...")
                is_domestic = llm in DOMESTIC_LLMS
                camoufox_kwargs = {
                    "headless": True,
                    "humanize": True,
                    "block_images": _block_heavy_resources(),
                    "os": "windows",
                    "locale": "zh-CN" if is_domestic else "en-US",
                }
                if use_proxy:
                    camoufox_kwargs["proxy"] = {"server": self.proxy_url}

                _camoufox_ctx = AsyncCamoufox(**camoufox_kwargs)
                browser = await _camoufox_ctx.__aenter__()
                logger.info(f"[{llm}] Camoufox 启动成功")

                context = await browser.new_context()
                await _install_resource_blocker(context)
            else:
                # 国内 LLM 或无 Camoufox 时用普通 Playwright
                logger.info(f"[{llm}] 启动 Playwright 浏览器...")
                _playwright = await async_playwright().start()
                browser = await _playwright.chromium.launch(
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
                    ],
                )
                logger.info(f"[{llm}] Playwright 启动成功")

                is_domestic = llm in DOMESTIC_LLMS
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    locale="zh-CN" if is_domestic else "en-US",
                    timezone_id="Asia/Shanghai" if is_domestic else "America/New_York",
                    ignore_https_errors=True,
                    bypass_csp=True,
                    reduced_motion="reduce",
                )
                await _install_resource_blocker(context)

            # 注入 LLM 专属 cookies + localStorage
            # 支持两种格式:
            #   旧格式: [cookie1, cookie2, ...]  (纯 cookies 数组)
            #   新格式: {"cookies": [...], "localStorage": {"key": "val", ...}}
            injected_cookies = []
            local_storage_data = {}
            if self.account_cookies:
                try:
                    parsed = json.loads(self.account_cookies)
                    if isinstance(parsed, dict) and "cookies" in parsed:
                        # 新格式: cookies + localStorage
                        injected_cookies = parsed.get("cookies", [])
                        local_storage_data = parsed.get("localStorage", {})
                        if not local_storage_data:
                            local_storage_data = _local_storage_from_storage_state(
                                parsed.get("storageState"),
                                config.get("url", ""),
                            )
                        logger.info(
                            f"[{llm}] 使用 AccountPool cookies ({len(injected_cookies)} 个) "
                            f"+ localStorage ({len(local_storage_data)} 项)"
                        )
                    elif isinstance(parsed, list):
                        # 旧格式: 纯 cookies 数组
                        injected_cookies = parsed
                        logger.info(f"[{llm}] 使用 AccountPool cookies ({len(injected_cookies)} 个)")
                except Exception as e:
                    logger.warning(
                        f"[{llm}] 解析 account_cookies 失败: "
                        f"{_redact_sensitive_text(str(e))}"
                    )

            if not injected_cookies:
                cookies_env = config.get("cookies_env")
                if cookies_env:
                    injected_cookies = _load_cookies_from_env(cookies_env)

            if injected_cookies:
                await context.add_cookies(injected_cookies)
                logger.info(f"[{llm}] 已注入 {len(injected_cookies)} 个 cookies")

            page_obj = await context.new_page()
            _attach_runtime_debug(page_obj)
            self._record_page_pointer(page_obj)

            # 注入 localStorage（必须在页面打开后、导航前）
            if local_storage_data:
                # 先导航到目标域名（空页面），才能设置 localStorage
                target_url = config.get("url", "")
                if target_url:
                    try:
                        await page_obj.goto(target_url, wait_until="commit", timeout=15000)
                    except Exception:
                        pass  # 只需要到达域名就够，不需要完全加载
                    await page_obj.evaluate("""
                        (data) => {
                            for (const [key, value] of Object.entries(data)) {
                                localStorage.setItem(key, typeof value === 'object' ? JSON.stringify(value) : value);
                            }
                        }
                    """, local_storage_data)
                    # 验证注入结果
                    verify = await page_obj.evaluate("""
                        (keys) => {
                            const result = {};
                            for (const k of keys) {
                                result[k] = Boolean(localStorage.getItem(k));
                            }
                            return result;
                        }
                    """, list(local_storage_data.keys()))
                    verified_count = sum(1 for present in verify.values() if present)
                    logger.info(
                        f"[{llm}] 已注入 {len(local_storage_data)} 项 localStorage, "
                        f"verified_keys={verified_count}"
                    )
                    # 不 reload，后续主流程会重新 goto 加载页面

            # Playwright 需要手动隐藏自动化特征（Camoufox 自带，不需要）
            if not use_camoufox:
                domestic_langs = "['zh-CN', 'zh']" if is_domestic else "['en-US', 'en']"
                await page_obj.add_init_script(f"""
                    const _origUA = navigator.userAgent;
                    Object.defineProperty(navigator, 'userAgent', {{
                        get: () => _origUA.replace('HeadlessChrome', 'Chrome')
                    }});
                    Object.defineProperty(navigator, 'webdriver', {{get: () => undefined}});
                    delete navigator.__proto__.webdriver;
                    Object.defineProperty(navigator, 'plugins', {{
                        get: () => {{
                            const p = [
                                {{name:'Chrome PDF Plugin', filename:'internal-pdf-viewer', description:'Portable Document Format'}},
                                {{name:'Chrome PDF Viewer', filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai', description:''}},
                                {{name:'Native Client', filename:'internal-nacl-plugin', description:''}}
                            ];
                            p.length = 3;
                            return p;
                        }}
                    }});
                    Object.defineProperty(navigator, 'languages', {{get: () => {domestic_langs}}});
                    Object.defineProperty(navigator, 'hardwareConcurrency', {{get: () => 8}});
                    Object.defineProperty(navigator, 'deviceMemory', {{get: () => 8}});
                    window.chrome = {{
                        runtime: {{ onMessage: {{addListener:()=>{{}},removeListener:()=>{{}}}}, sendMessage:()=>{{}} }},
                        loadTimes: () => ({{}}), csi: () => ({{}})
                    }};
                    Object.defineProperty(navigator, 'maxTouchPoints', {{get: () => 1}});
                    Object.defineProperty(navigator, 'platform', {{get: () => 'Win32'}});
                    Object.defineProperty(screen, 'colorDepth', {{get: () => 24}});
                    Object.defineProperty(screen, 'pixelDepth', {{get: () => 24}});
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.query = (params) =>
                        params.name === 'notifications'
                            ? Promise.resolve({{state: Notification.permission}})
                            : originalQuery(params);
                """)

            # 对于 Gemini，先访问 google.com 建立 cookie
            if config.get("visit_google_first"):
                try:
                    logger.info(f"[{llm}] 先访问 google.com 建立 cookie...")
                    await page_obj.goto("https://www.google.com", wait_until="domcontentloaded", timeout=30000)
                    await page_obj.wait_for_timeout(2000)
                    for sel in ['button:has-text("Accept all")', 'button:has-text("I agree")', 'button:has-text("Accept")']:
                        try:
                            btn = await page_obj.query_selector(sel)
                            if btn and await btn.is_visible():
                                await btn.click()
                                await page_obj.wait_for_timeout(2000)
                                break
                        except Exception:
                            continue
                except Exception as e:
                    logger.warning(f"[{llm}] google.com 预访问失败（非致命）: {e}")

            # 打开目标页面
            logger.info(f"[{llm}] 打开: {config['url']} (proxy: {self.proxy_url if use_proxy else 'none'})")
            try:
                self._set_execution_stage("page_load")
                await page_obj.goto(config["url"], wait_until="domcontentloaded", timeout=90000)
                title = await page_obj.title()
                logger.info(f"[{llm}] 页面标题 (domcontentloaded): {title}")

                # ── Cloudflare 挑战等待 ──
                cf_waited = 0
                cf_max_wait = 30000
                while cf_waited < cf_max_wait:
                    page_title = (await page_obj.title() or "").strip().lower()
                    is_cf = any(t in page_title for t in CF_CHALLENGE_TITLES)
                    is_empty = len(page_title) == 0

                    if is_cf or (is_empty and cf_waited < 10000):
                        if is_cf:
                            logger.info(f"[{llm}] Cloudflare 挑战检测中 (title='{page_title}'), 等待...")
                        else:
                            logger.info(f"[{llm}] 页面标题为空，等待加载...")
                        await page_obj.wait_for_timeout(2000)
                        cf_waited += 2000
                    else:
                        if cf_waited > 0:
                            logger.info(f"[{llm}] 页面就绪 (title='{page_title}', waited={cf_waited}ms)")
                        break

                if cf_waited >= cf_max_wait:
                    if CAPSOLVER_API_KEY:
                        logger.info(f"[{llm}] Cloudflare 挑战未自动通过，尝试 CapSolver...")
                        solver = CaptchaSolver()
                        try:
                            solved = await detect_and_solve(page_obj, solver)
                            if solved:
                                logger.info(f"[{llm}] CapSolver 解码成功，等待页面跳转...")
                                await page_obj.wait_for_timeout(5000)
                                new_title = (await page_obj.title() or "").strip().lower()
                                if not any(t in new_title for t in CF_CHALLENGE_TITLES):
                                    logger.info(f"[{llm}] Cloudflare 挑战已通过 (title='{new_title}')")
                                else:
                                    logger.warning(f"[{llm}] CapSolver token 已注入但页面未跳转")
                                    await _save_screenshot(page_obj, query.id, f"{llm}_cf_blocked")
                                    return None
                            else:
                                logger.warning(f"[{llm}] CapSolver 解码失败")
                                await _save_screenshot(page_obj, query.id, f"{llm}_cf_blocked")
                                return None
                        except Exception as e:
                            logger.error(f"[{llm}] CapSolver 异常: {e}")
                            await _save_screenshot(page_obj, query.id, f"{llm}_cf_blocked")
                            return None
                        finally:
                            await solver.close()
                    else:
                        logger.warning(f"[{llm}] Cloudflare 挑战未通过且无 CAPSOLVER_API_KEY，换节点重试")
                        await _save_screenshot(page_obj, query.id, f"{llm}_cf_blocked")
                        return None

                # ── ChatGPT: Cloudflare 通过后刷新 session token ──
                if llm == "chatgpt" and injected_cookies:
                    try:
                        logger.info(f"[{llm}] CF 已通过，刷新 session token...")
                        resp = await page_obj.goto(
                            "https://chatgpt.com/api/auth/session",
                            wait_until="domcontentloaded", timeout=30000
                        )
                        if resp:
                            body = await page_obj.inner_text("body")
                            logger.info(
                                f"[{llm}] session endpoint HTTP {resp.status}, "
                                f"{_chatgpt_session_log_summary(body)}"
                            )
                            if resp.ok:
                                try:
                                    session_data = json.loads(body)
                                    if session_data.get("accessToken"):
                                        logger.info(
                                            f"[{llm}] session refresh succeeded"
                                        )
                                    else:
                                        logger.warning(f"[{llm}] session 响应无 accessToken，cookie 可能已过期")
                                        await _save_runtime_snapshot(
                                            page_obj,
                                            query.id,
                                            f"{llm}_session_no_token",
                                            config=config,
                                            runtime_events=runtime_events,
                                        )
                                        return None
                                except json.JSONDecodeError:
                                    # 可能返回了 CF 挑战页面 HTML
                                    logger.warning(
                                        f"[{llm}] session response was not JSON "
                                        f"({_chatgpt_session_log_summary(body)})"
                                    )
                                    await _save_screenshot(page_obj, query.id, f"{llm}_session_cf_block")
                                    return None
                            else:
                                logger.warning(f"[{llm}] session 刷新 HTTP {resp.status}")
                                await _save_runtime_snapshot(
                                    page_obj,
                                    query.id,
                                    f"{llm}_session_http_error",
                                    config=config,
                                    runtime_events=runtime_events,
                                )
                                return None
                        else:
                            logger.warning(f"[{llm}] session 刷新无响应")
                            return None

                        # 刷新后关闭旧页面，开新页面（清除客户端缓存的 expired 状态）
                        logger.info(f"[{llm}] session 刷新完成，重新打开新页面...")
                        await page_obj.close()
                        page_obj = await context.new_page()
                        _attach_runtime_debug(page_obj)
                        self._record_page_pointer(page_obj)
                        try:
                            await page_obj.goto(config["url"], wait_until="domcontentloaded", timeout=60000)
                        except Exception as reopen_error:
                            matched_selector, visible = await _find_attached_selector(
                                page_obj,
                                config.get("input_selector", ""),
                                timeout=5000,
                            )
                            await _save_runtime_snapshot(
                                page_obj,
                                query.id,
                                f"{llm}_session_reopen_error",
                                config=config,
                                error=reopen_error,
                                matched_selector=matched_selector,
                                runtime_events=runtime_events,
                            )
                            if matched_selector:
                                logger.warning(
                                    "[%s] session reopen raised but input selector is present "
                                    "(%s visible=%s); continuing",
                                    llm,
                                    matched_selector,
                                    visible,
                                )
                            else:
                                raise
                        await page_obj.wait_for_timeout(3000)
                        # 新页面再过一次 CF
                        cf_waited2 = 0
                        while cf_waited2 < 15000:
                            pt = (await page_obj.title() or "").strip().lower()
                            if any(t in pt for t in CF_CHALLENGE_TITLES) or (not pt and cf_waited2 < 5000):
                                await page_obj.wait_for_timeout(2000)
                                cf_waited2 += 2000
                            else:
                                break
                    except Exception as e:
                        logger.warning(f"[{llm}] session 刷新异常: {e}")
                        if page_obj and "/api/auth/session" in page_obj.url:
                            await _save_runtime_snapshot(
                                page_obj,
                                query.id,
                                f"{llm}_session_exception",
                                config=config,
                                error=e,
                                runtime_events=runtime_events,
                            )
                        else:
                            await _save_screenshot(page_obj, query.id, f"{llm}_session_exception")
                        return None

                # 检测是否被重定向到登录页（cookie 过期或未注入）
                if llm == "chatgpt":
                    auth_reason = await self._prefer_chatgpt_auth_failure_reason(
                        llm,
                        page_obj,
                        runtime_events=runtime_events,
                    )
                    if auth_reason:
                        logger.warning(
                            "[%s] UI auth gate blocked execution before prompt submit: %s",
                            llm,
                            auth_reason,
                        )
                        await _save_runtime_snapshot(
                            page_obj,
                            query.id,
                            auth_reason,
                            config=config,
                            runtime_events=runtime_events,
                        )
                        await _save_screenshot(page_obj, query.id, auth_reason)
                        return None

                current_url = page_obj.url
                login_domains = config.get("login_redirect_domains", [])
                if any(d in current_url for d in login_domains):
                    logger.warning(
                        f"[{llm}] 被重定向到登录页: {current_url}，"
                        f"请更新 {config.get('cookies_env', '')} 环境变量中的 cookies"
                    )
                    await _save_screenshot(page_obj, query.id, f"{llm}_login_redirect")
                    return None

                # 检测页面内的登录弹窗（豆包等国内 LLM 可能在页面内弹出登录框）
                login_modal = await page_obj.query_selector(
                    "[class*='login-modal'], [class*='login-dialog'], "
                    "[class*='sign-in'], [class*='login-panel'], "
                    "[class*='passport-container']"
                )
                if login_modal:
                    is_visible = False
                    try:
                        is_visible = await login_modal.is_visible()
                    except Exception:
                        pass
                    if is_visible:
                        logger.warning(
                            f"[{llm}] 检测到页面内登录弹窗，"
                            f"请更新 {config.get('cookies_env', '')} 环境变量中的 cookies"
                        )
                        await _save_screenshot(page_obj, query.id, f"{llm}_login_modal")
                        return None

                # 豆包特殊处理：登录页可能不跳转也不弹窗，而是直接在 doubao.com/chat 渲染登录表单
                # 检测页面内容中是否包含登录相关关键词
                if llm == "doubao":
                    try:
                        body_text = await page_obj.evaluate("document.body?.innerText || ''")
                        login_keywords = ["登录后免费使用", "用户协议", "隐私政策", "抖音一键登录", "豆包账号服务须知", "下载豆包电脑版", "你好，我是豆包"]
                        matched = [kw for kw in login_keywords if kw in body_text]
                        if len(matched) >= 2:
                            logger.warning(
                                f"[{llm}] 页面内容检测到登录表单（匹配关键词: {matched}），"
                                f"cookies 可能已过期，请更新 cookies"
                            )
                            await _save_screenshot(page_obj, query.id, f"{llm}_login_page")
                            return None
                    except Exception as e:
                        logger.debug(f"[{llm}] 登录页内容检测异常: {e}")

                # ── 关闭弹窗 (cookie banner, login modal, Google One Tap 等) ──
                dismiss_sels = config.get("dismiss_selectors", [])
                if dismiss_sels:
                    await page_obj.wait_for_timeout(2000)  # 等弹窗渲染
                    for dsel in dismiss_sels:
                        try:
                            btn = await page_obj.query_selector(dsel)
                            if btn and await btn.is_visible():
                                await btn.click()
                                logger.info(f"[{llm}] 关闭弹窗: {dsel}")
                                await page_obj.wait_for_timeout(1000)
                        except Exception:
                            continue
                    # 关闭 Google One Tap iframe
                    try:
                        onetap = await page_obj.query_selector("#credential_picker_container")
                        if onetap:
                            await page_obj.evaluate("document.getElementById('credential_picker_container')?.remove()")
                            logger.info(f"[{llm}] 移除 Google One Tap")
                    except Exception:
                        pass

                # 优先等待输入框出现
                load_wait = config.get("load_wait", 8000)
                input_selectors = [s.strip() for s in config["input_selector"].split(",")]
                input_ready = False
                try:
                    for sel in input_selectors:
                        if not sel:
                            continue
                        try:
                            await page_obj.wait_for_selector(sel, timeout=load_wait, state="attached")
                            logger.info(f"[{llm}] 输入框就绪（提前完成等待）: {sel}")
                            input_ready = True
                            break
                        except Exception:
                            continue
                except Exception:
                    pass
                if not input_ready:
                    await page_obj.wait_for_timeout(min(load_wait, 5000))

                title = await page_obj.title()
                logger.info(f"[{llm}] 页面最终标题: {title}")
            except Exception as e:
                logger.error(f"[{llm}] 页面加载失败: {e}")
                recovered_after_load_error = False
                matched_selector = None
                if page_obj:
                    try:
                        matched_selector, visible = await _find_attached_selector(
                            page_obj,
                            config.get("input_selector", ""),
                            timeout=5000,
                        )
                        await _save_runtime_snapshot(
                            page_obj,
                            query.id,
                            f"{llm}_load_error",
                            config=config,
                            error=e,
                            matched_selector=matched_selector,
                            runtime_events=runtime_events,
                        )
                        if matched_selector:
                            recovered_after_load_error = True
                            logger.warning(
                                "[%s] page load raised but input selector is present "
                                "(%s visible=%s); continuing",
                                llm,
                                matched_selector,
                                visible,
                            )
                            await _save_screenshot(page_obj, query.id, f"{llm}_load_error_recovered")
                        else:
                            await _save_screenshot(page_obj, query.id, f"{llm}_load_error")
                    except Exception as probe_error:
                        logger.warning(f"[{llm}] runtime probe after load error failed: {probe_error}")
                if not recovered_after_load_error:
                    if page_obj:
                        await self._prefer_chatgpt_auth_failure_reason(
                            llm, page_obj, runtime_events=runtime_events
                        )
                        doubao_reason = await self._prefer_doubao_load_failure_reason(
                            llm, page_obj
                        )
                        if doubao_reason:
                            try:
                                await _save_html(page_obj, query.id, doubao_reason)
                            except Exception as artifact_error:
                                logger.warning(
                                    "[%s] failed to save %s load-failure html: %s",
                                    llm,
                                    doubao_reason,
                                    artifact_error,
                                )
                            try:
                                await _save_screenshot(page_obj, query.id, doubao_reason)
                            except Exception as artifact_error:
                                logger.warning(
                                    "[%s] failed to save %s load-failure screenshot: %s",
                                    llm,
                                    doubao_reason,
                                    artifact_error,
                                )
                            try:
                                await _save_runtime_snapshot(
                                    page_obj,
                                    query.id,
                                    doubao_reason,
                                    config=config,
                                    error=e,
                                    matched_selector=matched_selector,
                                    runtime_events=runtime_events,
                                )
                            except Exception as artifact_error:
                                logger.warning(
                                    "[%s] failed to save %s load-failure runtime snapshot: %s",
                                    llm,
                                    doubao_reason,
                                    artifact_error,
                                )
                    self.last_error_reason = self.last_error_reason or "page_load_failed"
                    return None

            # 页面加载后检查是否被重定向到登录页
            current_url = page_obj.url
            if llm == "chatgpt":
                auth_reason = await self._prefer_chatgpt_auth_failure_reason(
                    llm,
                    page_obj,
                    runtime_events=runtime_events,
                )
                if auth_reason:
                    logger.warning(
                        "[%s] UI auth gate blocked execution before prompt submit: %s",
                        llm,
                        auth_reason,
                    )
                    await _save_runtime_snapshot(
                        page_obj,
                        query.id,
                        auth_reason,
                        config=config,
                        runtime_events=runtime_events,
                    )
                    await _save_screenshot(page_obj, query.id, auth_reason)
                    return None

            login_domains = config.get("login_redirect_domains", [])
            if any(d in current_url for d in login_domains):
                logger.warning(f"[{llm}] 页面加载后仍在登录页: {current_url}，cookies/token 已失效")
                self.last_error_reason = "cookies_expired"
                await _save_screenshot(page_obj, query.id, f"{llm}_login_after_load")
                if self.account_cookies:
                    return None  # 让上层标记 cookies_expired
                return None

            # 尝试找输入框
            self._set_execution_stage("input_wait")
            input_el = None
            selectors = [s.strip() for s in config["input_selector"].split(",")]
            logger.info(f"[{llm}] 尝试选择器: {selectors}")

            for sel in selectors:
                if not sel:
                    continue
                try:
                    logger.debug(f"[{llm}] 尝试选择器: {sel}")
                    input_el = await page_obj.wait_for_selector(sel, timeout=10000, state="attached")
                    if input_el:
                        is_visible = await input_el.is_visible()
                        if is_visible:
                            logger.info(f"[{llm}] 输入框找到且可见: {sel}")
                            break
                        else:
                            logger.info(f"[{llm}] 输入框找到但报告为不可见，仍尝试使用: {sel}")
                            break
                except Exception as e:
                    logger.debug(f"[{llm}] 选择器失败: {sel} - {e}")
                    continue

            if not input_el and llm == "doubao":
                input_el = await self._recover_from_doubao_unavailable_page(
                    page_obj,
                    query=query,
                    config=config,
                    selectors=selectors,
                    runtime_events=runtime_events,
                    proxy_diagnostic=proxy_diagnostic,
                )

            if not input_el:
                logger.error(f"[{llm}] 找不到输入框")
                if page_obj:
                    await self._prefer_chatgpt_auth_failure_reason(
                        llm, page_obj, runtime_events=runtime_events
                    )
                    await self._prefer_doubao_auth_failure_reason(llm, page_obj)
                self.last_error_reason = self.last_error_reason or "no_input"
                if page_obj:
                    await _save_screenshot(page_obj, query.id, f"{llm}_no_input")
                    await _save_runtime_snapshot(
                        page_obj,
                        query.id,
                        f"{llm}_no_input",
                        config=config,
                        runtime_events=runtime_events,
                        proxy_diagnostic=proxy_diagnostic,
                    )
                    try:
                        content = await page_obj.content()
                        content_path = SCREENSHOT_DIR / f"query_{query.id}_{llm}_content.html"
                        content_path.write_text(content[:50000], encoding='utf-8')
                        logger.info(f"[{llm}] 页面内容已保存: {content_path}")
                    except Exception as e:
                        logger.warning(f"保存页面内容失败: {e}")
                return None

            # 执行查询
            self._set_execution_stage("browser_query")
            resp_text, resp_html, citations = await self._browser_query(
                page_obj,
                config,
                query.query_text,
                llm,
                input_el,
                query_id=query.id,
                runtime_events=runtime_events,
            )

            if resp_text:
                self.last_error_reason = None
                self._set_execution_stage("artifact_save")
                screenshot_path = await _save_screenshot(page_obj, query.id, llm)
                return LLMResponse(
                    query_id=query.id,
                    raw_text=resp_text,
                    response_html=resp_html if resp_html else None,
                    citations_json=citations if citations else None,
                    screenshot_path=str(screenshot_path) if screenshot_path else None,
                    response_time_ms=0,
                    llm_version=f"{'camoufox' if use_camoufox else 'guest'}_{llm}",
                    collected_at=datetime.utcnow(),
                )
            else:
                logger.error(f"[{llm}] 未能获取响应")
                if page_obj:
                    await self._prefer_chatgpt_auth_failure_reason(
                        llm, page_obj, runtime_events=runtime_events
                    )
                    await self._prefer_doubao_visual_challenge_reason(llm, page_obj)
                    await self._prefer_doubao_auth_failure_reason(llm, page_obj)
                self.last_error_reason = self.last_error_reason or "no_response"
                if page_obj:
                    self._set_execution_stage("artifact_save")
                    # Refs #963: unbounded artifact saves on a half-broken
                    # page (CF challenge, login redirect, SPA stuck mid-
                    # render) used to be able to burn the rest of the outer
                    # execute_query budget — including pushing the worker
                    # over its Celery soft_time_limit when other Doubao
                    # rows had already used most of the 480s. Bound each
                    # save call so a hung page cannot prevent the rest of
                    # the worker (cleanup, DB writeback) from running.
                    try:
                        await asyncio.wait_for(
                            _save_screenshot(
                                page_obj, query.id, f"{llm}_no_response"
                            ),
                            timeout=15,
                        )
                    except Exception as save_err:
                        logger.warning(
                            "[%s] no_response screenshot save failed: %s",
                            llm,
                            _redact_sensitive_text(str(save_err))[:200],
                        )
                    try:
                        await asyncio.wait_for(
                            _save_runtime_snapshot(
                                page_obj,
                                query.id,
                                f"{llm}_no_response",
                                config=config,
                                runtime_events=runtime_events,
                            ),
                            timeout=15,
                        )
                    except Exception as save_err:
                        logger.warning(
                            "[%s] no_response runtime snapshot save failed: %s",
                            llm,
                            _redact_sensitive_text(str(save_err))[:200],
                        )
                return None

        except asyncio.CancelledError:
            # Refs #963: outer asyncio.wait_for cancelling execute() must not
            # discard browser-level evidence. Capture the active page state
            # (URL/title/body) and persist a runtime snapshot before the
            # finally-block cleanup tears the page down, so future
            # `doubao_browser_timeout:<stage>` failures land with operator-
            # readable context instead of a bare reason code.
            stage_at_cancel = self.execution_stage or "unknown"
            # Latch the real stage BEFORE the finally block sets stage="cleanup".
            self.stage_at_failure = stage_at_cancel
            self.last_error_reason = self.last_error_reason or "browser_timeout"
            if page_obj is not None:
                try:
                    await asyncio.shield(
                        self._preserve_active_page_evidence(
                            page_obj,
                            query.id,
                            llm,
                            config=config,
                            runtime_events=runtime_events,
                            proxy_diagnostic=proxy_diagnostic,
                            stage=stage_at_cancel,
                            suffix_prefix="browser_timeout",
                        )
                    )
                except BaseException as snap_err:
                    logger.warning(
                        "[%s] cancellation evidence save failed (stage=%s): %s",
                        llm,
                        stage_at_cancel,
                        _redact_sensitive_text(str(snap_err))[:200],
                    )
            raise
        except Exception as e:
            stage_at_exc = self.execution_stage or "unknown"
            # Latch the real stage BEFORE the finally block sets stage="cleanup".
            self.stage_at_failure = stage_at_exc
            logger.exception(f"[{llm}] 执行异常: {e}")
            reason = resolve_execution_failure_reason(e, self.last_error_reason)
            # Refs #963 follow-up: a Playwright TimeoutError bubbling out of an
            # inner await previously landed as generic ``browser_timeout``, with
            # no stage info and only a bare screenshot. The latest live
            # diagnostics for #963 (query 184968) show this is the actual
            # current failure mode — latency ~157s on a 480s outer budget — so
            # operators were left guessing which inner stage hung. For Doubao,
            # upgrade ``browser_timeout`` to ``doubao_browser_timeout:<stage>``
            # so the retry_reason carries the same stage info as the outer
            # cancellation path and routes through the same infrastructure
            # bucket in INFRASTRUCTURE_FAILURE_REASONS.
            if (
                (llm or "").lower() == "doubao"
                and (
                    reason == "browser_timeout"
                    or (reason or "").lower() == "browser_timeout"
                )
            ):
                reason = browser_execution_timeout_reason(llm, stage=stage_at_exc)
            self.last_error_reason = reason
            if page_obj:
                # Save full evidence (URL/title/body/snapshot + screenshot) so
                # the next inner-timeout failure leaves on-disk artifacts the
                # operator can read, instead of relying on a bare screenshot
                # whose failure used to be silently swallowed.
                try:
                    await self._preserve_active_page_evidence(
                        page_obj,
                        query.id,
                        llm,
                        config=config,
                        runtime_events=runtime_events,
                        proxy_diagnostic=proxy_diagnostic,
                        stage=stage_at_exc,
                        suffix_prefix="exception",
                    )
                except Exception as snap_err:
                    logger.warning(
                        "[%s] exception evidence save failed (stage=%s): %s",
                        llm,
                        stage_at_exc,
                        _redact_sensitive_text(str(snap_err))[:200],
                    )
            return None
        finally:
            self._set_execution_stage("cleanup")
            # 生产事故 2026-04-27 根因修复:
            # 原代码 try/except: pass 捕不了 await hang, 浏览器 close 卡死时
            # 后续 camoufox/playwright 清理永不执行, 进程泄漏到 458 PIDs.
            # 统一走 browser_lifecycle.cleanup_browser_resources, 每段独立超时.
            await cleanup_browser_resources(
                page=page_obj,
                context=context,
                browser=browser,
                camoufox_ctx=_camoufox_ctx,
                playwright=_playwright,
            )
            self.current_page = None

    async def _preserve_active_page_evidence(
        self,
        page_obj: "Page",
        query_id: int,
        llm: str,
        *,
        config: dict,
        runtime_events: list[dict],
        proxy_diagnostic: dict,
        stage: str,
        suffix_prefix: str,
    ) -> None:
        """Capture page URL/title/body + runtime snapshot + screenshot when
        the executor leaves ``_execute_once`` without a successful response.

        Refs #963 handoff: each step is best-effort and individually bounded
        by ``asyncio.wait_for`` so a half-broken page (CF challenge, login
        redirect, SPA stuck mid-render) cannot block cancellation propagation
        or hide other failures behind a hanging snapshot. Callers in the
        cancellation path should additionally wrap this in ``asyncio.shield``
        so its awaits are not torn down by a second cancellation while
        evidence is still being written.

        ``suffix_prefix`` is "browser_timeout" for the outer-cancellation
        path and "exception" for the inner-exception path; the resulting
        artifact suffix is ``{llm}_{suffix_prefix}_{stage}`` so artifacts
        from the two paths stay distinguishable on disk.
        """
        try:
            self.last_page_url = page_obj.url
        except Exception:
            pass
        try:
            self.last_page_title = await asyncio.wait_for(
                page_obj.title(), timeout=5
            )
        except Exception:
            pass
        try:
            body = await asyncio.wait_for(
                page_obj.evaluate("document.body?.innerText || ''"),
                timeout=5,
            )
            if isinstance(body, str):
                self.last_page_body_snippet = _redact_sensitive_text(body)[:1000]
        except Exception:
            pass
        suffix = f"{llm}_{suffix_prefix}_{stage}"
        try:
            snapshot_path = await asyncio.wait_for(
                _save_runtime_snapshot(
                    page_obj,
                    query_id,
                    suffix,
                    config=config,
                    runtime_events=runtime_events,
                    proxy_diagnostic=proxy_diagnostic,
                ),
                timeout=15,
            )
            if snapshot_path is not None:
                self.last_snapshot_path = str(snapshot_path)
        except Exception as e:
            logger.warning(
                "[%s] %s snapshot save failed (stage=%s): %s",
                llm,
                suffix_prefix,
                stage,
                _redact_sensitive_text(str(e))[:200],
            )
        try:
            await asyncio.wait_for(
                _save_screenshot(page_obj, query_id, suffix),
                timeout=15,
            )
        except Exception as e:
            logger.warning(
                "[%s] %s screenshot save failed (stage=%s): %s",
                llm,
                suffix_prefix,
                stage,
                _redact_sensitive_text(str(e))[:200],
            )

    async def _recover_from_doubao_unavailable_page(
        self,
        page_obj,
        *,
        query: Query,
        config: dict,
        selectors: list[str],
        runtime_events,
        proxy_diagnostic,
    ):
        # Refs #958: a single reload + 5s wait is often not enough for the
        # transient "该页面暂时不可用" page to clear, and the 12-hour cooldown
        # the caller applies on `page_unavailable` quickly drains the pool. Try
        # reload-then-probe in a bounded loop with growing backoff, re-checking
        # the marker each round so we keep paying the selector-wait cost only
        # while it is justified. On exhaustion, tag the failure and save an
        # informative artifact so operators stop chasing a `no_input` screenshot
        # for a page_unavailable failure.
        llm = "doubao"
        try:
            body_text = await page_obj.evaluate("document.body?.innerText || ''")
        except Exception as exc:
            logger.warning("[%s] unavailable-page probe failed: %s", llm, exc)
            return None

        if not _is_doubao_unavailable_page_text(body_text):
            return None

        reload_max = max(1, _env_int("DOUBAO_UNAVAILABLE_RELOAD_MAX", 3))
        reload_wait_base_ms = max(
            1000, _env_int("DOUBAO_UNAVAILABLE_RELOAD_WAIT_MS", 8000)
        )

        try:
            await _save_runtime_snapshot(
                page_obj,
                query.id,
                f"{llm}_page_unavailable_before_reload",
                config=config,
                runtime_events=runtime_events,
                proxy_diagnostic=proxy_diagnostic,
            )
        except Exception as exc:
            logger.debug(
                "[%s] failed to save page_unavailable_before_reload snapshot: %s",
                llm,
                exc,
            )

        for attempt in range(1, reload_max + 1):
            logger.warning(
                "[%s] detected transient unavailable page; reload %s/%s",
                llm,
                attempt,
                reload_max,
            )
            try:
                await page_obj.reload(wait_until="domcontentloaded", timeout=60000)
            except Exception as exc:
                logger.warning(
                    "[%s] reload attempt %s failed: %s", llm, attempt, exc
                )

            try:
                await page_obj.wait_for_timeout(reload_wait_base_ms * attempt)
            except Exception:
                pass

            try:
                body_text_after = await page_obj.evaluate(
                    "document.body?.innerText || ''"
                )
            except Exception:
                body_text_after = ""

            if _is_doubao_unavailable_page_text(body_text_after):
                logger.info(
                    "[%s] page still unavailable after reload %s/%s; will retry",
                    llm,
                    attempt,
                    reload_max,
                )
                continue

            for sel in selectors:
                if not sel:
                    continue
                try:
                    input_el = await page_obj.wait_for_selector(
                        sel,
                        timeout=10000,
                        state="attached",
                    )
                    if input_el:
                        logger.info(
                            "[%s] input found after unavailable-page reload %s/%s: %s",
                            llm,
                            attempt,
                            reload_max,
                            sel,
                        )
                        return input_el
                except Exception:
                    continue

        self.last_error_reason = "page_unavailable"
        try:
            await _save_screenshot(
                page_obj, query.id, f"{llm}_page_unavailable_final"
            )
        except Exception as exc:
            logger.debug(
                "[%s] failed to save page_unavailable_final screenshot: %s",
                llm,
                exc,
            )
        try:
            await _save_runtime_snapshot(
                page_obj,
                query.id,
                f"{llm}_page_unavailable_final",
                config=config,
                runtime_events=runtime_events,
                proxy_diagnostic=proxy_diagnostic,
            )
        except Exception as exc:
            logger.debug(
                "[%s] failed to save page_unavailable_final snapshot: %s",
                llm,
                exc,
            )
        return None

    async def _prefer_doubao_visual_challenge_reason(
        self, llm_name: str, page: Page | None
    ) -> str | None:
        """Promote Doubao image-selection challenge over generic no-response/homepage reasons."""
        if llm_name != "doubao" or page is None:
            return None
        state = await _doubao_visual_challenge_state_from_page(page)
        reason = state.get("reason")
        if not reason:
            return None
        if self.last_error_reason in (
            None,
            "",
            "no_response",
            "no_input",
            "browser_timeout",
            "page_load_failed",
            "submit_failed",
            "doubao_homepage_content",
        ):
            self.last_error_reason = str(reason)
        logger.warning(
            "[doubao] visual challenge detected (%s); failing without challenge solving",
            reason,
        )
        return str(reason)

    async def _prefer_doubao_auth_failure_reason(
        self, llm_name: str, page: Page | None
    ) -> str | None:
        """Promote Doubao login/auth chrome over generic no-response reasons."""
        if llm_name != "doubao" or page is None:
            return None
        auth_reason = await _doubao_auth_state_reason_from_page(page)
        if not auth_reason:
            return None
        if self.last_error_reason in (
            None,
            "",
            "no_response",
            "no_input",
            "browser_timeout",
            "page_load_failed",
            "submit_failed",
            DOUBAO_VISUAL_CHALLENGE_REASON,
            DOUBAO_IMAGE_CHALLENGE_LOAD_FAILED_REASON,
        ):
            self.last_error_reason = auth_reason
        return auth_reason

    async def _prefer_doubao_load_failure_reason(
        self, llm_name: str, page: Page | None
    ) -> str | None:
        """Promote inspectable Doubao page state over generic load failures."""
        if llm_name != "doubao" or page is None:
            return None
        auth_reason = await _doubao_auth_state_reason_from_page(page)
        if auth_reason == "doubao_not_logged_in":
            return await self._prefer_doubao_auth_failure_reason(llm_name, page)
        challenge_reason = await self._prefer_doubao_visual_challenge_reason(
            llm_name, page
        )
        if challenge_reason:
            return challenge_reason
        if auth_reason:
            return await self._prefer_doubao_auth_failure_reason(llm_name, page)
        return None

    async def _prefer_chatgpt_auth_failure_reason(
        self,
        llm_name: str,
        page: Page | None,
        *,
        runtime_events: list[dict] | None = None,
    ) -> str | None:
        """Promote ChatGPT token/session failures over generic scraper reasons."""
        if llm_name != "chatgpt" or page is None:
            return None
        body_text = ""
        page_title = ""
        try:
            body_text = await page.evaluate("document.body?.innerText || ''")
        except Exception:
            pass
        try:
            page_title = await page.title()
        except Exception:
            pass
        auth_reason = chatgpt_auth_state_reason(
            body_text,
            url=getattr(page, "url", None),
            title=page_title,
            runtime_events=runtime_events,
        )
        if not auth_reason:
            return None
        if self.last_error_reason in (
            None,
            "",
            "no_response",
            "no_input",
            "page_load_failed",
            "browser_timeout",
            "submit_failed",
        ):
            self.last_error_reason = auth_reason
        return auth_reason

    async def _extract_citations(self, page: Page, cfg: dict, llm_name: str) -> tuple[list, dict]:
        """从响应区域提取引用链接"""
        citations = []
        metadata: dict = {}
        try:
            response_selectors = [s.strip() for s in cfg["response_selector"].split(",") if s.strip()]

            # 豆包使用独立的引用面板，需要专门提取
            if llm_name == "doubao":
                citations = await self._extract_doubao_citations(page)
                if citations:
                    logger.info(f"[{llm_name}] 从引用面板提取到 {len(citations)} 个引用链接")
                    return citations, metadata

            # 通用提取：在响应区域内查找所有链接
            if llm_name == "chatgpt":
                chatgpt_result = await self._extract_chatgpt_citations(page)
                metadata.update(chatgpt_result.get("metadata") or {})
                citations = chatgpt_result.get("citations") or []
                if citations:
                    logger.info(
                        "[%s] extracted %s source links from ChatGPT Sources UI",
                        llm_name,
                        len(citations),
                    )
                    return citations, metadata

            js_citations = await page.evaluate("""
                (selectors) => {
                    const skipDomains = [
                        'chatgpt.com', 'gemini.google.com', 'accounts.google.com',
                        'cdn.oaistatic.com', 'gstatic.com', 'googleapis.com',
                        'google.com/gsi', 'statsig', 'sentry', 'intercom',
                        'cdn-cgi', 'oaiusercontent.com',
                    ];
                    function isSkipped(url) {
                        return skipDomains.some(d => url.includes(d));
                    }
                    const citations = [];
                    const seen = new Set();

                    function collectFromContainers(containers) {
                        for (const container of containers) {
                            const links = container.querySelectorAll('a[href]');
                            for (const a of links) {
                                const url = a.href;
                                if (!url || seen.has(url)) continue;
                                if (url.startsWith('javascript:') || url === '#' || url.startsWith('#')) continue;
                                if (!url.startsWith('http')) continue;
                                if (isSkipped(url)) continue;
                                seen.add(url);
                                citations.push({
                                    url: url,
                                    title: (a.textContent || '').trim().slice(0, 200),
                                    index: citations.length + 1
                                });
                            }
                        }
                    }

                    // 先从响应区域提取
                    for (const sel of selectors) {
                        try {
                            collectFromContainers(document.querySelectorAll(sel));
                        } catch(e) {}
                    }

                    // 若响应区域没有，尝试从 article、main 等语义区域提取
                    if (citations.length === 0) {
                        const fallbacks = document.querySelectorAll('article, main, [role="main"]');
                        collectFromContainers(fallbacks);
                    }

                    return citations;
                }
            """, response_selectors)
            if js_citations:
                citations = js_citations
                logger.info(f"[{llm_name}] 提取到 {len(citations)} 个引用链接")
            else:
                logger.info(f"[{llm_name}] 页面无引用链接")
        except Exception as e:
            logger.warning(f"[{llm_name}] 引用提取失败: {e}")
        return citations, metadata

    async def _extract_chatgpt_citations(self, page: Page) -> dict:
        """Open ChatGPT's collapsed Sources UI and extract external links."""
        result = {
            "citations": [],
            "metadata": {
                "source_ui_seen": False,
                "source_ui_clicked": False,
            },
        }
        try:
            clicked = False
            try:
                buttons = page.locator(
                    "button[aria-label*='Source'], "
                    "button[aria-label*='source'], "
                    "button[aria-label*='Citation'], "
                    "button[aria-label*='citation']"
                )
                count = await buttons.count()
                if count:
                    result["metadata"]["source_ui_seen"] = True
                    button = buttons.nth(count - 1)
                    await button.scroll_into_view_if_needed(timeout=2000)
                    await button.click(timeout=3000)
                    clicked = True
            except Exception as e:
                logger.debug("[chatgpt] source button locator click failed: %s", e)

            if not clicked:
                try:
                    handle = await page.evaluate_handle(
                        """
                        () => {
                            const buttons = [...document.querySelectorAll('button')].reverse();
                            return buttons.find((button) => {
                                const label = [
                                    button.getAttribute('aria-label') || '',
                                    button.getAttribute('title') || '',
                                    button.textContent || '',
                                ].join(' ');
                                return /sources?|citations?/i.test(label);
                            }) || null;
                        }
                        """
                    )
                    element = handle.as_element() if handle else None
                    if element:
                        result["metadata"]["source_ui_seen"] = True
                        await element.scroll_into_view_if_needed(timeout=2000)
                        await element.click(timeout=3000)
                        clicked = True
                except Exception as e:
                    logger.debug("[chatgpt] source button JS click failed: %s", e)

            if clicked:
                result["metadata"]["source_ui_clicked"] = True
                await page.wait_for_timeout(1200)

            citations = await page.evaluate(
                """
                () => {
                    const skipDomains = [
                        'chatgpt.com', 'gemini.google.com', 'accounts.google.com',
                        'cdn.oaistatic.com', 'persistent.oaistatic.com',
                        'oaiusercontent.com', 'cdn.openai.com',
                        'openaiassets.blob.core.windows.net',
                        'gstatic.com', 'googleapis.com', 'google.com/gsi',
                        'statsig', 'sentry', 'intercom', 'cdn-cgi',
                    ];
                    function isSkipped(url) {
                        try {
                            const parsed = new URL(url);
                            const host = parsed.hostname.toLowerCase();
                            const lowered = url.toLowerCase();
                            return skipDomains.some(d => host.includes(d) || lowered.includes(d));
                        } catch(e) {
                            return true;
                        }
                    }
                    const panelSelectors = [
                        '[role="dialog"]',
                        '[data-radix-popper-content-wrapper]',
                        '[popover]',
                        '[data-testid*="source" i]',
                        '[data-testid*="citation" i]',
                        '[class*="source" i]',
                        '[class*="citation" i]',
                    ];
                    const roots = [];
                    for (const sel of panelSelectors) {
                        try {
                            document.querySelectorAll(sel).forEach(el => roots.push(el));
                        } catch(e) {}
                    }
                    const citations = [];
                    const seen = new Set();
                    function push(url, title) {
                        if (!url || !url.startsWith('http') || seen.has(url)) return;
                        if (isSkipped(url)) return;
                        seen.add(url);
                        citations.push({
                            url,
                            title: (title || '').trim().slice(0, 200),
                            index: citations.length + 1,
                        });
                    }
                    for (const root of roots) {
                        root.querySelectorAll('a[href]').forEach(a => {
                            push(a.href, a.textContent || a.getAttribute('aria-label') || '');
                        });
                        root.querySelectorAll('[data-url], [data-href], [cite]').forEach(el => {
                            push(
                                el.getAttribute('data-url')
                                  || el.getAttribute('data-href')
                                  || el.getAttribute('cite')
                                  || '',
                                el.textContent || el.getAttribute('aria-label') || ''
                            );
                        });
                    }
                    return citations;
                }
                """
            )
            result["citations"] = citations or []
            return result
        except Exception as e:
            logger.warning("[chatgpt] source panel extraction failed: %s", e)
            return result

    async def _extract_doubao_citations(self, page: Page) -> list:
        """从豆包引用面板提取引用链接。

        豆包 2026 UI 引用结构（线上 DOM 验证）：
        - 触发器: <div class="entry-btn-v3-XXXX"> 内含 <span class="entry-btn-title-v3-XXXX">参考 N 篇资料</span>
        - 面板根: <div class="container-outer-XXXX" data-visible="true">
        - 面板头: <span class="page-search-XXXX">参考资料</span>
        - 每条引用容器: <div class="search-item-XXXX">（hash 后缀变化，前缀稳定）
        - 标题: [class*="search-item-title"]
        - 摘要: [class*="search-item-summary"]
        - 来源: [class*="footer-title"]
        - 编号: [class*="footer-citation"]
        """
        try:
            citations = await page.evaluate("""
                () => {
                    const citations = [];
                    const seen = new Set();

                    // 判断 class 是否是"引用项主容器"——前缀是 search-item-X 而不是
                    // search-item-title-X / search-item-footer-X / search-item-summary-X /
                    // search-item-transition-X 这类内层 class
                    const INNER_PREFIXES = ['search-item-title', 'search-item-footer',
                        'search-item-summary', 'search-item-transition'];
                    const isItemContainer = (el) => {
                        const cls = el.className || '';
                        if (typeof cls !== 'string') return false;
                        const classes = cls.split(/\\s+/);
                        return classes.some(c => {
                            if (!c.startsWith('search-item-')) return false;
                            return !INNER_PREFIXES.some(p => c.startsWith(p));
                        });
                    };

                    const pushFromItem = (item) => {
                        const link = item.querySelector('a[href]');
                        if (!link) return;
                        const url = link.href;
                        if (!url || !url.startsWith('http') || seen.has(url)) return;
                        // 过滤掉豆包自身的链接
                        if (url.includes('doubao.com') || url.includes('bytedance.com')) return;
                        seen.add(url);

                        const titleEl = item.querySelector('[class*="search-item-title"]');
                        const title = titleEl
                            ? (titleEl.textContent || '').trim()
                            : (link.textContent || '').trim();

                        const citationEl = item.querySelector('[class*="footer-citation"]');
                        const citationNum = citationEl
                            ? parseInt(citationEl.textContent, 10)
                            : 0;

                        const sourceEl = item.querySelector('[class*="footer-title"]');
                        const source = sourceEl ? (sourceEl.textContent || '').trim() : '';

                        citations.push({
                            url: url,
                            title: (title || '').slice(0, 200),
                            source: source,
                            index: citationNum || (citations.length + 1)
                        });
                    };

                    // 策略1：找到处于打开态的引用面板（container-outer + data-visible="true"），
                    // 从面板内提取所有引用项
                    const panels = document.querySelectorAll(
                        '[class*="container-outer"][data-visible="true"], '
                        + '[class*="container-outer"]:not([data-visible="false"])'
                    );
                    for (const panel of panels) {
                        // 仅当面板内含"参考资料"标题或 search-item-* 时才算引用面板
                        const isRefPanel = panel.querySelector('[class*="page-search"]')
                            || panel.querySelector('[class*="search-item-title"]');
                        if (!isRefPanel) continue;
                        const candidates = panel.querySelectorAll('[class*="search-item-"]');
                        for (const c of candidates) {
                            if (isItemContainer(c)) pushFromItem(c);
                        }
                    }

                    // 策略2：老版 testid（兼容性兜底）
                    if (citations.length === 0) {
                        const items = document.querySelectorAll('[data-testid="search-text-item"]');
                        for (const item of items) pushFromItem(item);
                    }

                    // 策略3：全文档兜底 —— 任意主容器形态的 search-item-*
                    if (citations.length === 0) {
                        const all = document.querySelectorAll('[class*="search-item-"]');
                        for (const c of all) {
                            if (isItemContainer(c)) pushFromItem(c);
                        }
                    }

                    // 策略4：通用面板兜底（popover / dialog / drawer）
                    if (citations.length === 0) {
                        const panelSelectors = [
                            '[data-testid*="search-reference"] a[href]',
                            '[class*="reference-panel"] a[href]',
                            '[class*="search-panel"] a[href]',
                            '[class*="citation-panel"] a[href]',
                            '[data-radix-popper-content-wrapper] a[href]',
                            '[role="dialog"] a[href]',
                        ];
                        for (const sel of panelSelectors) {
                            try {
                                const links = document.querySelectorAll(sel);
                                for (const link of links) {
                                    const url = link.href;
                                    if (!url || !url.startsWith('http') || seen.has(url)) continue;
                                    if (url.includes('doubao.com') || url.includes('bytedance.com')) continue;
                                    seen.add(url);
                                    citations.push({
                                        url: url,
                                        title: (link.textContent || '').trim().slice(0, 200),
                                        source: '',
                                        index: citations.length + 1
                                    });
                                }
                            } catch(e) {}
                        }
                    }

                    citations.sort((a, b) => a.index - b.index);
                    return citations;
                }
            """)

            return citations or []
        except Exception as e:
            logger.warning(f"[doubao] 引用面板提取失败: {e}")
            return []
        finally:
            # 关闭引用面板（按 Escape），避免影响后续操作
            try:
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(300)
            except Exception:
                pass

    async def _inject_controlled_textarea_value(self, input_el, query_text: str) -> str:
        """Set a controlled textarea/input value and return the observed value."""
        try:
            actual = await input_el.evaluate(
                """
                (el, text) => {
                    el.focus();

                    const proto = el instanceof HTMLTextAreaElement
                        ? HTMLTextAreaElement.prototype
                        : HTMLInputElement.prototype;
                    const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');

                    try {
                        el.dispatchEvent(new InputEvent('beforeinput', {
                            bubbles: true,
                            cancelable: true,
                            inputType: 'insertText',
                            data: text
                        }));
                    } catch (e) {}

                    if (descriptor && descriptor.set) {
                        descriptor.set.call(el, text);
                    } else {
                        el.value = text;
                    }

                    try {
                        el.setSelectionRange(text.length, text.length);
                    } catch (e) {}

                    const events = [
                        new InputEvent('input', {
                            bubbles: true,
                            inputType: 'insertText',
                            data: text
                        }),
                        new Event('change', { bubbles: true }),
                    ];
                    for (const event of events) {
                        el.dispatchEvent(event);
                    }

                    try {
                        el.dispatchEvent(new CompositionEvent('compositionend', {
                            bubbles: true,
                            data: text
                        }));
                    } catch (e) {
                        el.dispatchEvent(new Event('compositionend', { bubbles: true }));
                    }

                    try {
                        el.dispatchEvent(new KeyboardEvent('keyup', {
                            bubbles: true,
                            key: 'Process'
                        }));
                    } catch (e) {}

                    return el.value ?? el.textContent ?? '';
                }
                """,
                query_text,
            )
            return str(actual or "")
        except Exception as e:
            logger.debug(f"controlled textarea injection failed: {e}")
            return ""

    async def _fill_plain_text_input(
        self,
        page: Page,
        input_el,
        query_text: str,
        llm_name: str,
    ) -> bool:
        """Fill a textarea/input, using JS first for Doubao's controlled input.

        Refs #963 follow-up to PR #1008 live evidence (E2E run 25924635842 +
        Server Diagnostics run 25925187531): query 184968 retry 20 on a
        fresh active account 44 hung at ``stage=prompt_fill`` for the full
        480s soft-time-limit. The prior implementation called
        ``input_el.fill("")``, ``self._inject_controlled_textarea_value(...)``,
        ``input_el.evaluate(...)``, and ``page.keyboard.type(...)`` with no
        timeout — if the page sits in a degenerate state where the input
        node is attached but does not accept events (overlay covering the
        input, focus stolen, browser context dead-but-not-yet-collected),
        any of these awaits hangs indefinitely. Bound each step
        individually so a hung input cannot burn the outer execute_query
        budget. Each bound is generous compared to the expected work
        (~3s for a typical 30-char query) so legitimate slow renders still
        succeed; the bounds exist to fail fast on a stuck page.
        """
        try:
            await asyncio.wait_for(
                input_el.fill(""), timeout=PROMPT_FILL_CLEAR_TIMEOUT_S
            )
        except Exception:
            pass
        await page.wait_for_timeout(random.randint(200, 500))

        if llm_name == "doubao":
            try:
                actual = await asyncio.wait_for(
                    self._inject_controlled_textarea_value(input_el, query_text),
                    timeout=PROMPT_FILL_INJECT_TIMEOUT_S,
                )
            except (asyncio.TimeoutError, Exception) as inject_err:
                logger.warning(
                    f"[{llm_name}] JS 注入受控 textarea 超时/异常: "
                    f"{_redact_sensitive_text(str(inject_err))[:200]}"
                )
                actual = ""
            if actual.strip() == query_text.strip():
                logger.info(f"[{llm_name}] 通过 JS 注入受控 textarea")
                return True
            logger.warning(
                f"[{llm_name}] JS 注入后输入值与期望不一致"
                f"（len={len(actual or '')} vs {len(query_text)}），回退到键盘输入"
            )

        try:
            await asyncio.wait_for(
                page.keyboard.type(query_text, delay=random.randint(50, 120)),
                timeout=PROMPT_FILL_KEYBOARD_TYPE_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"[{llm_name}] keyboard.type 超时 "
                f"({PROMPT_FILL_KEYBOARD_TYPE_TIMEOUT_S}s)，回退到 JS 注入"
            )
            try:
                actual = await asyncio.wait_for(
                    self._inject_controlled_textarea_value(input_el, query_text),
                    timeout=PROMPT_FILL_INJECT_TIMEOUT_S,
                )
                return actual.strip() == query_text.strip()
            except (asyncio.TimeoutError, Exception) as fallback_err:
                logger.warning(
                    f"[{llm_name}] 键盘超时后 JS 注入兜底失败: "
                    f"{_redact_sensitive_text(str(fallback_err))[:200]}"
                )
                return False

        try:
            actual = await asyncio.wait_for(
                input_el.evaluate("el => el.value ?? el.textContent ?? ''"),
                timeout=PROMPT_FILL_VALUE_READ_TIMEOUT_S,
            )
        except Exception:
            actual = None
        if actual is not None and actual.strip() != query_text.strip():
            logger.warning(
                f"[{llm_name}] 输入值与期望不一致（len={len(actual or '')} vs {len(query_text)}），"
                "改用 JS 注入并触发 React input 事件"
            )
            try:
                actual = await asyncio.wait_for(
                    self._inject_controlled_textarea_value(input_el, query_text),
                    timeout=PROMPT_FILL_INJECT_TIMEOUT_S,
                )
                return actual.strip() == query_text.strip()
            except (asyncio.TimeoutError, Exception):
                return False
        return True

    async def _browser_query(
        self, page: Page, cfg: dict, query_text: str, llm_name: str, input_el=None,
        _retry_count: int = 0,
        query_id: int | None = None,
        runtime_events: list[dict] | None = None,
    ) -> tuple:
        """在已打开的页面里输入 query，等待响应，抓取文本和引用
        Returns: (response_text, response_html, citations_list)"""
        debug_query_id = _debug_query_id(query_id)
        self._set_execution_stage("prompt_fill")
        if input_el is None:
            input_el = await page.wait_for_selector(cfg["input_selector"].split(",")[0], timeout=10000)

        # 模拟人类行为：随机延迟 + 鼠标移动到输入框
        # Refs #963 follow-up to PR #1009 live evidence (run 25926214958):
        # ``bounding_box()`` and ``mouse.move(...)`` had no timeout and a
        # degenerate page state could hang either of them for the full
        # outer budget. Each is best-effort (caller's try/except already
        # tolerates failure) so a tight 5s bound is fine; production
        # values complete in <100ms when the browser is healthy.
        await page.wait_for_timeout(random.randint(800, 2000))
        try:
            # 先模拟鼠标移动到输入框附近
            box = await asyncio.wait_for(input_el.bounding_box(), timeout=5)
            if box:
                await asyncio.wait_for(
                    page.mouse.move(
                        box["x"] + box["width"] * random.uniform(0.2, 0.8),
                        box["y"] + box["height"] * random.uniform(0.2, 0.8),
                        steps=random.randint(5, 15),
                    ),
                    timeout=5,
                )
                await page.wait_for_timeout(random.randint(200, 500))
        except Exception:
            pass

        # 点击输入框（force=True 绕开可见性检查）
        try:
            await input_el.click(force=True, timeout=5000)
        except Exception:
            pass
        await page.wait_for_timeout(random.randint(300, 800))

        # 对于 contenteditable（如 Gemini 的 Quill 编辑器），键盘事件依赖真实 focus
        # 在 headless 下元素常常报告"不可见"，导致 keyboard.type() 打到 body 而非编辑器
        # 改用 JS 直接注入文字并触发 Quill/Angular 所需的 input 事件
        if cfg.get("contenteditable"):
            # 把 LLM 自己的选择器列表传给 JS，避免硬编码 Gemini 的 Quill 选择器
            # Refs #963 follow-up to PR #1009: bound the JS evaluate so a
            # hung page cannot turn this branch into a full-budget timeout.
            input_selectors = [s.strip() for s in cfg.get("input_selector", "").split(",")]
            try:
                injected = await asyncio.wait_for(page.evaluate("""
                ([text, selectors]) => {
                    // 依次尝试各选择器，找第一个 contenteditable 元素
                    let editor = null;
                    for (const sel of selectors) {
                        try {
                            const el = document.querySelector(sel);
                            if (el && (el.isContentEditable || el.getAttribute('contenteditable') !== null)) {
                                editor = el;
                                break;
                            }
                        } catch(e) {}
                    }
                    // 兜底：任意 contenteditable
                    if (!editor) editor = document.querySelector('[contenteditable="true"]') || document.querySelector('[contenteditable]');
                    if (!editor) return false;

                    editor.focus();

                    // 方法1: execCommand（旧版 Chrome 可用）
                    editor.innerHTML = '';
                    document.execCommand('insertText', false, text);
                    if ((editor.textContent || '').trim().length > 0) return true;

                    // 方法2: 模拟粘贴事件（Quill 支持）
                    try {
                        const dt = new DataTransfer();
                        dt.setData('text/plain', text);
                        editor.dispatchEvent(new ClipboardEvent('paste', {
                            clipboardData: dt, bubbles: true, cancelable: true
                        }));
                        if ((editor.textContent || '').trim().length > 0) return true;
                    } catch(e) {}

                    // 方法3: 直接设置 innerHTML + 触发事件（最终兜底）
                    const escaped = text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
                    editor.innerHTML = '<p>' + escaped + '</p>';
                    editor.classList.remove('ql-blank');
                    ['input', 'keyup', 'change', 'compositionend'].forEach(type => {
                        editor.dispatchEvent(new Event(type, { bubbles: true }));
                    });
                    return (editor.textContent || '').trim().length > 0;
                }
            """, [query_text, input_selectors]), timeout=PROMPT_FILL_INJECT_TIMEOUT_S)
            except (asyncio.TimeoutError, Exception) as ce_err:
                logger.warning(
                    f"[{llm_name}] contenteditable JS 注入超时/异常: "
                    f"{_redact_sensitive_text(str(ce_err))[:200]}"
                )
                injected = False
            logger.info(f"[{llm_name}] JS 注入文字: {'成功' if injected else '失败'}")
            # 保存注入后的 HTML，确认文字是否真的进了编辑器
            await _save_html(page, debug_query_id, f"{llm_name}_after_inject")
            # Refs Codex PR #1010 review (P2): a timed-out or failed
            # contenteditable injection used to fall through to the submit
            # logic and burn the response_wait budget on an empty/stale
            # prompt. Mirror the textarea path — on injection failure,
            # mark last_error_reason="no_input" and bail.
            if not injected:
                logger.warning(
                    f"[{llm_name}] contenteditable 注入失败，放弃本次提交"
                )
                self.last_error_reason = "no_input"
                return "", "", []
        else:
            filled = await self._fill_plain_text_input(page, input_el, query_text, llm_name)
            if not filled:
                logger.warning(f"[{llm_name}] 输入框填充失败，放弃本次提交")
                self.last_error_reason = "no_input"
                await _save_html(page, debug_query_id, f"{llm_name}_input_fill_failed")
                return "", "", []

        # 模拟人类"思考"后再提交
        await page.wait_for_timeout(random.randint(500, 1500))

        # 提交：优先点击 submit_button 里配的 selector，失败时 JS 找 input 附近的 enabled 按钮，
        # 再失败才 fallback 到 Enter
        async def _find_submit_button_js():
            """豆包新 UI 无 testid，通过稳定 id / class + 位置 + 图标找 send 按钮。"""
            return await page.evaluate_handle(
                """
                () => {
                    const isEnabled = (b) => {
                        if (!b) return false;
                        if (b.disabled) return false;
                        if (b.getAttribute('data-disabled') === 'true') return false;
                        if (b.getAttribute('aria-disabled') === 'true') return false;
                        const cls = b.className || '';
                        if (typeof cls === 'string' && /send-msg-btn-disabled-bg/.test(cls)) return false;
                        return true;
                    };

                    // 最优先：稳定的 id（线上 DOM 验证）
                    const byId = document.getElementById('flow-end-msg-send');
                    if (byId && isEnabled(byId)) return byId;

                    const all = [...document.querySelectorAll('button, [role="button"]')];

                    // 其次：按 class 匹配（稳定的 Tailwind/业务类名）
                    const byClass = all.find(b => {
                        if (!isEnabled(b)) return false;
                        const cls = b.className || '';
                        if (typeof cls !== 'string') return false;
                        return /send-msg-btn/.test(cls);
                    });
                    if (byClass) return byClass;

                    // 然后：.send-btn-wrapper（不含 !hidden）内的 button
                    const wrappers = [...document.querySelectorAll('.send-btn-wrapper')];
                    for (const w of wrappers) {
                        const wcls = w.className || '';
                        if (typeof wcls === 'string' && /!hidden/.test(wcls)) continue;
                        const b = w.querySelector('button');
                        if (isEnabled(b)) return b;
                    }

                    // 然后：aria-label / title 含 send/发送
                    const byAria = all.find(b => {
                        if (!isEnabled(b)) return false;
                        const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                        const title = (b.getAttribute('title') || '').toLowerCase();
                        return /send|发送|提交/.test(aria) || /send|发送|提交/.test(title);
                    });
                    if (byAria) return byAria;

                    // 次选：input 附近、含 svg 图标、文本为空或极短、enabled 的按钮
                    const input = document.querySelector(
                        'textarea:not([aria-hidden="true"]), [contenteditable="true"]'
                    );
                    if (!input) return null;
                    const ir = input.getBoundingClientRect();
                    let best = null, bestScore = -Infinity;
                    for (const b of all) {
                        if (!isEnabled(b)) continue;
                        const cls = b.className || '';
                        if (typeof cls === 'string' && /toggle-button/.test(cls)) continue;
                        const r = b.getBoundingClientRect();
                        if (r.width === 0 || r.height === 0) continue;
                        const txt = (b.textContent || '').trim();
                        if (txt.length > 0) continue;  // avoid mode/search toggles
                        if (!b.querySelector('svg, img, i')) continue;  // 必须有图标
                        // 限制在 input 正下方/右侧附近 150px 以内
                        const dx = Math.max(0, r.left - ir.right, ir.left - r.right);
                        const dy = Math.max(0, r.top - ir.bottom, ir.top - r.bottom);
                        if (dx > 300 || dy > 200) continue;
                        if ((r.left + r.width / 2) < (ir.left + ir.width * 0.55)) continue;
                        const verticalPenalty = Math.abs((r.top + r.bottom) / 2 - (ir.top + ir.bottom) / 2);
                        const score = (r.left + r.width) - verticalPenalty - dx - dy;
                        if (score > bestScore) { bestScore = score; best = b; }
                    }
                    return best;
                }
                """
            )

        self._set_execution_stage("prompt_submit")
        submitted = False
        if cfg.get("submit_button"):
            for btn_sel in [s.strip() for s in cfg["submit_button"].split(",")]:
                try:
                    btn = await page.query_selector(btn_sel)
                    if not btn or not await btn.is_visible():
                        continue
                    # 二次校验：豆包等使用 aria-disabled / data-disabled / class 表达禁用态，
                    # CSS :not([disabled]) 抓不到，会误点禁用按钮变成 no-op，导致后面 JS 兜底被跳过。
                    is_disabled = await btn.evaluate(
                        """
                        b => b.disabled
                          || b.getAttribute('aria-disabled') === 'true'
                          || b.getAttribute('data-disabled') === 'true'
                          || /send-msg-btn-disabled-bg/.test(b.className || '')
                        """
                    )
                    if is_disabled:
                        logger.debug(f"[{llm_name}] 跳过禁用按钮: {btn_sel}")
                        continue
                    await btn.click()
                    submitted = True
                    logger.info(f"[{llm_name}] 通过按钮提交: {btn_sel}")
                    break
                except Exception:
                    continue
        if not submitted and llm_name in ("doubao", "deepseek"):
            # JS 兜底：找 input 附近的 send 图标按钮
            try:
                handle = await _find_submit_button_js()
                as_element = handle.as_element() if handle else None
                if as_element:
                    await as_element.click()
                    submitted = True
                    logger.info(f"[{llm_name}] 通过 JS 兜底按钮提交")
            except Exception as e:
                logger.debug(f"[{llm_name}] JS 找 submit 按钮失败: {e}")
        if not submitted:
            await page.keyboard.press("Enter")
            logger.info(f"[{llm_name}] 通过 Enter 键提交")

        # 验证提交成功：依据各 LLM 的稳定标记判断"用户消息已上屏"
        # 共用标记 + 各 LLM 特化（豆包: send-msg-bubble-bg；chatgpt: [data-message-author-role="user"]）
        async def _submit_confirmed() -> bool:
            try:
                return await page.evaluate(
                    r"""
                    ([queryText, llmName]) => {
                        // 1) ChatGPT: 出现 user 消息气泡
                        if (llmName === 'chatgpt') {
                            const userMsgs = document.querySelectorAll(
                                '[data-message-author-role="user"]'
                            );
                            const needle = queryText.slice(0, 30).trim();
                            for (const el of userMsgs) {
                                if ((el.textContent || '').includes(needle)) return true;
                            }
                            // URL 从 / 变成 /c/{id} 也算
                            if (/\/c\/[a-zA-Z0-9-]+/.test(location.pathname)) return true;
                            return false;
                        }
                        if (llmName === 'deepseek') {
                            const needle = queryText.slice(0, 24).trim();
                            if (!needle) return true;
                            const textareas = [...document.querySelectorAll('textarea')];
                            const stillInInput = textareas.some(el =>
                                ((el.value || el.textContent || '').includes(needle))
                            );
                            const messageCandidates = document.querySelectorAll(
                                '[class*="message"], [class*="chat"], [class*="markdown"], main'
                            );
                            for (const el of messageCandidates) {
                                if (textareas.some(input => input === el || el.contains(input))) continue;
                                if ((el.textContent || '').includes(needle)) return true;
                            }
                            return !stillInInput && (document.body.innerText || '').includes(needle);
                        }
                        // 2) Doubao: 老 UI send_message testid
                        if (document.querySelector('[data-testid="send_message"]')) return true;
                        // 3) Doubao 2026 稳定 class: send-msg-bubble-bg（用户消息气泡），
                        //    以及其他用户消息相关 class（兜底）
                        const candidates = document.querySelectorAll(
                            '[class*="send-msg-bubble-bg"], [class*="user-message"], [class*="send-message"], [class*="message-item"], [class*="chat-item"], [class*="message-list"]'
                        );
                        const needle = queryText.slice(0, 20).trim();
                        for (const el of candidates) {
                            if ((el.textContent || '').includes(needle)) return true;
                        }
                        return false;
                    }
                    """,
                    [query_text, llm_name],
                )
            except Exception:
                return False

        self._set_execution_stage("submit_confirm")
        # Refs PR #1006 review (Codex P1): initialize ``confirmed`` before the
        # engine-gated submit-confirmation block. Otherwise engines outside
        # the (doubao, chatgpt, deepseek) set (e.g. gemini, kimi, claude,
        # grok, zhipu, perplexity) would raise UnboundLocalError when the
        # response_wait extension passes ``confirmed`` into
        # ``_maybe_extend_wait_total``. Default ``False`` matches the
        # semantics for unconfirmed/non-applicable engines: the
        # awaiting_answer extension trigger only fires when submit was
        # explicitly confirmed.
        confirmed = False
        if llm_name in ("doubao", "chatgpt", "deepseek"):
            # Refs #963: the original ~5s window (10 iterations × 500ms) was
            # too short for Doubao's 2026 SPA on a slow render: the click
            # could land successfully and the request fire upstream, but the
            # user-message bubble was not yet in the DOM when we polled, so
            # the code "retried" the submit by clicking again, occasionally
            # producing a duplicate request and confusing the upstream
            # response routing. Widen the wait for Doubao specifically
            # (~15s, 30 × 500ms) so a slow-but-correct first submit is
            # detected before we kick off the retry path. Other engines
            # keep the original budget.
            confirm_iters = 30 if llm_name == "doubao" else 10
            for _ in range(confirm_iters):
                if await _submit_confirmed():
                    confirmed = True
                    break
                await page.wait_for_timeout(500)

            if confirmed:
                logger.info(f"[{llm_name}] 已确认消息发送成功")
            else:
                logger.warning(f"[{llm_name}] 提交后未检测到发送的消息，尝试重新提交")
                try:
                    if llm_name == "doubao":
                        input_retry = await page.query_selector(
                            "#input-engine-container textarea.semi-input-textarea:not([aria-hidden='true']), "
                            "textarea.semi-input-textarea:not([aria-hidden='true']), "
                            "textarea:not([aria-hidden='true']), [contenteditable='true']"
                        )
                        if input_retry:
                            await input_retry.click(force=True)
                            await page.wait_for_timeout(300)
                            await self._fill_plain_text_input(
                                page, input_retry, query_text, llm_name
                            )

                    # 先再点一次发送按钮（id 是稳定标识），失败再退化到 Enter
                    clicked_again = False
                    try:
                        retry_handle = await _find_submit_button_js()
                        retry_el = retry_handle.as_element() if retry_handle else None
                        if retry_el:
                            await retry_el.click()
                            clicked_again = True
                            logger.info(f"[{llm_name}] 重试通过 JS 兜底按钮提交")
                    except Exception as e:
                        logger.debug(f"[{llm_name}] 重试 JS 兜底按钮失败: {e}")

                    if not clicked_again:
                        input_retry = await page.query_selector(
                            "#input-engine-container textarea.semi-input-textarea:not([aria-hidden='true']), "
                            "textarea.semi-input-textarea:not([aria-hidden='true']), "
                            "textarea:not([aria-hidden='true']), [contenteditable='true']"
                        )
                        if input_retry:
                            await input_retry.click(force=True)
                            await page.wait_for_timeout(300)
                        await page.keyboard.press("Enter")
                        logger.info(f"[{llm_name}] 重试 Enter 提交")
                    for _ in range(10):
                        if await _submit_confirmed():
                            confirmed = True
                            break
                        await page.wait_for_timeout(500)
                    if confirmed:
                        logger.info(f"[{llm_name}] 重试后消息发送成功")
                    else:
                        logger.warning(f"[{llm_name}] 重试后仍未检测到发送的消息")
                        await _save_html(page, debug_query_id, f"{llm_name}_submit_failed")
                        await self._prefer_doubao_auth_failure_reason(llm_name, page)
                        self.last_error_reason = self.last_error_reason or "no_response"
                        return "", "", []
                except Exception as e:
                    logger.warning(f"[{llm_name}] 重试提交异常: {e}")

        # 等待响应生成（分段等待，每隔一段检查是否已有内容）
        wait_total = cfg["wait_after_submit"]
        wait_interval = 5000  # 每 5 秒检查一次
        elapsed = 0
        response_selectors = [s.strip() for s in cfg["response_selector"].split(",") if s.strip()]

        prev_resp_len = 0       # 上一轮检测到的响应文本长度
        stable_rounds = 0       # 文本长度连续不变的轮数
        STABLE_THRESHOLD = 2    # 连续 N 轮不变才认为生成完毕

        # Refs #963: when Doubao is in "深度思考" or "正在搜索" mode the answer
        # can take significantly longer than ``wait_after_submit`` to start
        # streaming. The previous loop only RESET the stability counter when
        # the still-generating indicator was visible — it never extended
        # ``wait_total``, so the loop bailed at the original budget and the
        # row landed as ``no_response`` (or, when the answer arrived just
        # past the cutoff, ``response_too_short``). Allow a bounded extension
        # in those two situations:
        #   1. answer hasn't started yet but the still-generating sign is up;
        #   2. answer is streaming and length is still growing.
        # Per-call hard cap is ``wait_after_submit_max_extension`` (default:
        # 2x ``wait_after_submit``) so a permanently-stuck UI cannot burn
        # the entire outer execution budget here.
        extension_max = cfg.get("wait_after_submit_max_extension")
        if extension_max is None:
            extension_max = int(wait_total) * 2
        extension_used = 0
        extension_step = wait_interval

        def _maybe_extend_wait_total(
            current_elapsed: int,
            current_wait_total: int,
            still_generating_flag: bool,
            resp_ready_flag: bool,
            resp_growing: bool,
            extension_used_so_far: int,
            submit_was_confirmed: bool,
        ) -> tuple[int, int]:
            """Extend wait_total when there is concrete evidence the model is
            still working. Returns ``(new_wait_total, new_extension_used)``.

            Refs #963 PR #1005 deploy live evidence (E2E run 25920221085 +
            Server Diagnostics): query 184968 ran end-to-end on the fresh
            account 44 but the AI answer wasn't ready inside the configured
            ``wait_after_submit`` window. Doubao 2026's SPA does not always
            keep the "深度思考" / "正在搜索" indicator visible while the
            answer is in flight, so the original ``still_generating``-only
            extension trigger missed this case, the loop exited at base
            budget, the JS fallback then picked up homepage placeholder
            text, and the executor correctly discarded the row as
            ``doubao_homepage_content``. Extend whenever submit was
            confirmed AND we have no response yet — that is concrete
            evidence the user message went through but the answer is
            still in flight."""
            if extension_max <= 0:
                return current_wait_total, extension_used_so_far
            if extension_used_so_far >= extension_max:
                return current_wait_total, extension_used_so_far
            # Only extend when we are about to exit the loop AND we have a
            # real reason to wait longer.
            if current_elapsed + wait_interval < current_wait_total:
                return current_wait_total, extension_used_so_far
            awaiting_answer = submit_was_confirmed and not resp_ready_flag
            should_extend = (
                still_generating_flag
                or (resp_ready_flag and resp_growing)
                or awaiting_answer
            )
            if not should_extend:
                return current_wait_total, extension_used_so_far
            step = min(extension_step, extension_max - extension_used_so_far)
            if step <= 0:
                return current_wait_total, extension_used_so_far
            logger.info(
                "[%s] response_wait extended (+%dms, total +%dms / max +%dms): "
                "still_generating=%s, resp_growing=%s, resp_ready=%s, awaiting_answer=%s",
                llm_name,
                step,
                extension_used_so_far + step,
                extension_max,
                still_generating_flag,
                resp_growing,
                resp_ready_flag,
                awaiting_answer,
            )
            return current_wait_total + step, extension_used_so_far + step

        self._set_execution_stage("response_wait")
        # Refs #963 follow-up to PR #1013 live evidence (run 25928885380):
        # track consecutive timeouts on the still_generating evaluate so a
        # dead page bails out of the loop fast instead of grinding through
        # all extensions. A page that cannot respond to a 3s evaluate is
        # not going to render a response — break out and let the no_response
        # path persist evidence.
        dead_page_eval_streak = 0
        DEAD_PAGE_EVAL_THRESHOLD = 3
        # Codex PR #1014 review (P2): RESPONSE_WAIT_STAGE_BUDGET_S was
        # defined but never enforced — the elapsed counter ticks 5s per
        # iteration regardless of wall-clock cost, so a degenerate page
        # where each loop iteration spends e.g. 15s wall (3s eval timeout
        # + 5s sleep + selectors hitting their 10s timeouts) can still
        # exceed the 180s nominal cap. Track wall-clock since stage
        # entry and bail out if it exceeds the documented stage budget,
        # giving the stage a hard outer cap regardless of what each
        # inner call costs.
        response_wait_started_at = asyncio.get_event_loop().time()
        while elapsed < wait_total:
            wall_elapsed = asyncio.get_event_loop().time() - response_wait_started_at
            if wall_elapsed >= RESPONSE_WAIT_STAGE_BUDGET_S:
                logger.error(
                    f"[{llm_name}] response_wait wall-clock budget exceeded "
                    f"({wall_elapsed:.1f}s >= {RESPONSE_WAIT_STAGE_BUDGET_S}s); bailing"
                )
                self.last_error_reason = self.last_error_reason or "no_response"
                break
            await page.wait_for_timeout(min(wait_interval, wait_total - elapsed))
            elapsed += wait_interval

            # 检测是否跳转到登录页
            current_url = page.url
            login_domains = cfg.get("login_redirect_domains", [])
            if any(d in current_url for d in login_domains):
                logger.warning(f"[{llm_name}] 检测到跳转到登录页: {current_url}，中止等待")
                self.last_error_reason = (
                    "doubao_not_logged_in" if llm_name == "doubao" else "cookies_expired"
                )
                await _save_screenshot(page, debug_query_id, f"{llm_name}_login_redirect")
                await _save_runtime_snapshot(
                    page,
                    debug_query_id,
                    f"{llm_name}_login_redirect",
                    config=cfg,
                    runtime_events=runtime_events,
                )
                return "", "", []

            # 检查是否仍在生成中（豆包"深度思考"等状态）
            # Refs #963 follow-up to PR #1010 live evidence (run 25927727628):
            # this evaluate runs every 5s inside the response_wait loop with
            # no per-call timeout. On a degenerate page it can hang for the
            # full outer budget. Bound it so a single hung evaluate cannot
            # eat the response_wait stage.
            still_generating = False
            if llm_name == "doubao":
                try:
                    generating = await asyncio.wait_for(page.evaluate("""
                        () => {
                            const body = document.body.innerText || '';
                            // 豆包生成中的标志
                            const signs = ['深度思考', '正在搜索', '正在思考', '正在生成'];
                            const has_sign = signs.some(s => body.includes(s));
                            // 检查是否有 receive_message（已有回复）
                            const has_resp = document.querySelector("[data-testid='receive_message']");
                            // 有生成标志且无完整回复 → 仍在生成
                            return has_sign && !has_resp;
                        }
                    """), timeout=RESPONSE_WAIT_GENERATING_EVAL_TIMEOUT_S)
                    still_generating = bool(generating)
                    dead_page_eval_streak = 0
                except asyncio.TimeoutError:
                    dead_page_eval_streak += 1
                    logger.warning(
                        f"[{llm_name}] still_generating evaluate timed out "
                        f"(streak={dead_page_eval_streak}/{DEAD_PAGE_EVAL_THRESHOLD})"
                    )
                    if dead_page_eval_streak >= DEAD_PAGE_EVAL_THRESHOLD:
                        logger.error(
                            f"[{llm_name}] response_wait bailing out — page evaluate "
                            f"has timed out {dead_page_eval_streak} times in a row; "
                            f"page is unresponsive"
                        )
                        self.last_error_reason = "no_response"
                        break
                except Exception:
                    pass

            # 提前检查是否已有响应内容（避免浪费剩余等待时间）
            # Refs #963 follow-up to PR #1010: bound each per-selector
            # check inside the response_wait loop so a single hung selector
            # or inner_text() cannot burn the budget.
            resp_ready = False
            current_resp_len = 0
            for sel in response_selectors:
                try:
                    el = await asyncio.wait_for(
                        page.query_selector(sel),
                        timeout=RESPONSE_EXTRACT_SELECTOR_TIMEOUT_S,
                    )
                    if el:
                        txt = await asyncio.wait_for(
                            el.inner_text(),
                            timeout=RESPONSE_EXTRACT_SELECTOR_TIMEOUT_S,
                        )
                        if txt and len(txt.strip()) > 20:
                            resp_ready = True
                            current_resp_len = len(txt.strip())
                            break
                except Exception:
                    continue

            if resp_ready:
                # 检查是否仍在流式输出
                # 方式1: stream_check_selector（loading/stop 按钮）
                stream_sel = cfg.get("stream_check_selector", "")
                still_streaming = False
                if stream_sel:
                    try:
                        stream_el = await page.query_selector(stream_sel)
                        if stream_el and await stream_el.is_visible():
                            still_streaming = True
                    except Exception:
                        pass

                # 方式2: 文本长度稳定性检测（连续 N 轮长度不变 → 完成）
                if current_resp_len > prev_resp_len:
                    stable_rounds = 0
                    logger.info(
                        f"[{llm_name}] 响应仍在增长（{elapsed}ms, {current_resp_len} chars）"
                    )
                else:
                    stable_rounds += 1

                prev_resp_len = current_resp_len

                if still_streaming or still_generating:
                    stable_rounds = 0  # 有明确的生成指示符时重置稳定计数
                    logger.info(f"[{llm_name}] 检测到响应但仍在生成中（{elapsed}ms），继续等待...")
                elif stable_rounds >= STABLE_THRESHOLD:
                    logger.info(
                        f"[{llm_name}] 响应内容就绪（{elapsed}ms, {current_resp_len} chars, "
                        f"连续 {stable_rounds} 轮稳定）"
                    )
                    break

            # ``stable_rounds == 0`` after the resp_ready block means the
            # response was actively growing this round (it gets reset to 0
            # both on length growth and on still_streaming/still_generating).
            # ``confirmed`` is the submit-was-confirmed flag from the earlier
            # submit_confirm stage; passing it lets the extension keep
            # waiting for the answer when the user message did make it onto
            # the page but Doubao hasn't surfaced an explicit progress
            # indicator yet (Refs #963 / 184968 retry 17 evidence).
            wait_total, extension_used = _maybe_extend_wait_total(
                elapsed,
                wait_total,
                still_generating,
                resp_ready,
                resp_ready and stable_rounds == 0,
                extension_used,
                confirmed,
            )

        # 抓取响应文本 + HTML
        # Refs #963 follow-up to PR #1014 live evidence (run 25930179463):
        # the response_wait stage label covers BOTH the wait loop AND this
        # extraction block. PR #1014's wall-clock check inside the loop
        # only catches loop-internal hangs; the extraction phase has its
        # own per-call bounds but no aggregate cap, so a busy page where
        # each inner_html / inner_text trips the 10s bound can still burn
        # 100s+ at this stage. Check the same wall-clock budget here so
        # the whole stage is hard-capped regardless of where time is being
        # spent.
        resp_text = ""
        resp_html = ""
        wall_elapsed_at_extract = asyncio.get_event_loop().time() - response_wait_started_at
        if wall_elapsed_at_extract >= RESPONSE_WAIT_STAGE_BUDGET_S:
            logger.error(
                f"[{llm_name}] response_wait wall-clock budget exhausted "
                f"({wall_elapsed_at_extract:.1f}s >= {RESPONSE_WAIT_STAGE_BUDGET_S}s) "
                f"before extraction; skipping extraction"
            )
            self.last_error_reason = self.last_error_reason or "no_response"
            return "", "", []
        try:
            # 保存完整页面 HTML 用于调试 selector
            await _save_html(page, debug_query_id, f"{llm_name}_response_page")

            # 优先尝试配置的 selectors
            # Refs #963 follow-up to PR #1010: bound each extraction call
            # so a single hung selector / inner_text() / inner_html() cannot
            # turn the response_wait stage into a full-budget timeout.
            # Refs PR #1014 follow-up: wall-clock check at each selector
            # iteration too — if 5 selectors each spend N seconds, the
            # aggregate could still exceed the stage budget.
            for sel in response_selectors:
                wall_elapsed_inner = (
                    asyncio.get_event_loop().time() - response_wait_started_at
                )
                if wall_elapsed_inner >= RESPONSE_WAIT_STAGE_BUDGET_S:
                    logger.warning(
                        f"[{llm_name}] response_wait wall-clock budget exhausted "
                        f"({wall_elapsed_inner:.1f}s) inside extraction loop; bailing "
                        f"with partial result"
                    )
                    break
                try:
                    elements = await asyncio.wait_for(
                        page.query_selector_all(sel),
                        timeout=RESPONSE_EXTRACT_SELECTOR_TIMEOUT_S,
                    )
                    if elements:
                        texts = []
                        htmls = []
                        for el in elements:
                            try:
                                txt = await asyncio.wait_for(
                                    el.inner_text(),
                                    timeout=RESPONSE_EXTRACT_SELECTOR_TIMEOUT_S,
                                )
                                if txt and txt.strip():
                                    texts.append(txt.strip())
                                # 同时保存 innerHTML（保留 <a href> 等标签）
                                html = await asyncio.wait_for(
                                    el.inner_html(),
                                    timeout=RESPONSE_EXTRACT_SELECTOR_TIMEOUT_S,
                                )
                                if html:
                                    htmls.append(html)
                            except Exception:
                                pass
                        combined = "\n".join(texts)
                        if len(combined) > 20:
                            logger.info(f"[{llm_name}] 通过 selector 提取响应: {sel} ({len(combined)} chars)")
                            resp_text = combined[-5000:]
                            resp_html = "\n".join(htmls)[-50000:]  # HTML 保留更多
                            # 豆包：同时保存引用面板 HTML 以便后续 backfill
                            if llm_name == "doubao":
                                try:
                                    ref_panel = await asyncio.wait_for(
                                        page.query_selector('[data-testid="search-reference-ui-v3"]'),
                                        timeout=RESPONSE_EXTRACT_SELECTOR_TIMEOUT_S,
                                    )
                                    if ref_panel:
                                        ref_html = await asyncio.wait_for(
                                            ref_panel.inner_html(),
                                            timeout=RESPONSE_EXTRACT_SELECTOR_TIMEOUT_S,
                                        )
                                        if ref_html:
                                            resp_html += "\n<!-- doubao-references -->\n" + ref_html
                                except Exception:
                                    pass
                            break
                except Exception:
                    continue

            # 在做 <p>/<li>/main 兜底之前，先确认用户消息真的上屏了——
            # 否则可能爬到首页 UI（比如 ChatGPT "What are you working on?" 文案）
            user_msg_present = False
            try:
                user_msg_present = await page.evaluate(
                    r"""
                    ([queryText, llmName]) => {
                        const needle = queryText.slice(0, 30).trim();
                        if (!needle) return true;  // 空 query 不做校验
                        // 通用：所有 LLM 都用的 user message marker
                        const sels = [
                            '[data-message-author-role="user"]',
                            '[class*="send-msg-bubble-bg"]',  // doubao
                            '[class*="user-message"]',
                            '[class*="send-message"]',
                            '[class*="message-item"]',
                            '[class*="chat-item"]',
                            // Refs #963: Doubao 2026 Semi Design 偶尔把用户气泡的
                            // class 改成 user-bubble / my-bubble / semi-message-user 类。
                            // 加更宽松的兜底，避免因为 class 改名导致 user_msg_present=false
                            // 进而跳过 JS fallback 抽取，把本来已经渲染出的回答漏掉。
                            '[class*="user-bubble"]',
                            '[class*="my-bubble"]',
                            '[class*="my-message"]',
                            '[class*="semi-message-user"]',
                            '[class*="bubble-user"]',
                            '[data-role="user"]',
                            '[data-author="user"]',
                        ];
                        for (const sel of sels) {
                            const els = document.querySelectorAll(sel);
                            for (const el of els) {
                                if ((el.textContent || '').includes(needle)) return true;
                            }
                        }
                        // 进入 /c/{id} 路径也算（chatgpt 等）
                        if (/\/c\/[a-zA-Z0-9-]+/.test(location.pathname)) return true;
                        // Refs #963: Doubao 提交后 URL 通常会变成
                        //   /chat/{id}, /chat?conversation=..., /chat/conversation/...
                        // 都属于"已经进入会话页"的证据，足以解锁 JS fallback 抽取。
                        if (llmName === 'doubao') {
                            const path = location.pathname || '';
                            const search = location.search || '';
                            if (/\/chat\/[a-zA-Z0-9_-]+/.test(path)) return true;
                            if (/[?&](conversation|chatId|conv_id|cid)=/.test(search)) return true;
                        }
                        return false;
                    }
                    """,
                    [query_text, llm_name],
                )
            except Exception:
                user_msg_present = False

            if not resp_text and not user_msg_present:
                # 没有响应也没有用户消息气泡 = 提交根本没成功，禁止抽取首页 UI
                logger.warning(
                    f"[{llm_name}] 未检测到用户消息气泡，提交可能未成功——"
                    "跳过通用兜底抽取，避免误抓首页内容"
                )
                await _save_html(page, debug_query_id, f"{llm_name}_submit_failed_no_user_msg")

            if llm_name == "doubao" and not resp_text:
                auth_reason = await self._prefer_doubao_auth_failure_reason(llm_name, page)
                if auth_reason:
                    await _save_html(page, debug_query_id, auth_reason)
                    await _save_screenshot(page, debug_query_id, auth_reason)
                    await _save_runtime_snapshot(
                        page,
                        debug_query_id,
                        auth_reason,
                        config=cfg,
                        runtime_events=runtime_events,
                    )
                    return "", "", []
                challenge_reason = await self._prefer_doubao_visual_challenge_reason(
                    llm_name, page
                )
                if challenge_reason:
                    await _save_html(page, debug_query_id, challenge_reason)
                    await _save_screenshot(page, debug_query_id, challenge_reason)
                    await _save_runtime_snapshot(
                        page,
                        debug_query_id,
                        challenge_reason,
                        config=cfg,
                        runtime_events=runtime_events,
                    )
                    return "", "", []

            if not resp_text and user_msg_present:
                # fallback 1：拼接所有 <p> 标签文本
                logger.warning(f"[{llm_name}] 响应选择器未匹配，使用 JS fallback 提取")
                await _save_html(page, debug_query_id, f"{llm_name}_extract_fail")
                js_text = await page.evaluate("""
                    () => {
                        // 排除侧边栏/导航区域
                        const excludeSelectors = [
                            'nav', 'aside', '[class*="sidebar"]', '[class*="side-bar"]',
                            '[class*="history"]', '[class*="conversation-list"]',
                            '[data-testid="conversation_list"]', '[class*="nav"]',
                        ];
                        const excludeEls = new Set();
                        for (const sel of excludeSelectors) {
                            try {
                                document.querySelectorAll(sel).forEach(el => excludeEls.add(el));
                            } catch(e) {}
                        }
                        function isExcluded(el) {
                            for (const ex of excludeEls) {
                                if (ex.contains(el)) return true;
                            }
                            return false;
                        }
                        const paras = [...document.querySelectorAll('p, li')].filter(p => !isExcluded(p));
                        const paraText = paras
                            .map(p => (p.textContent || '').trim())
                            .filter(t => t.length > 5)
                            .join('\\n');
                        if (paraText.length > 50) return paraText;

                        // body fallback：移除侧边栏后取 main/article 区域
                        const main = document.querySelector('main, [role="main"], article');
                        if (main) {
                            const mainText = (main.innerText || '').trim();
                            if (mainText.length > 100) return mainText.slice(-4000);
                        }
                        const bodyText = (document.body.innerText || '').trim();
                        if (bodyText.length > 100) return bodyText.slice(-4000);
                        return '';
                    }
                """)
                if js_text and len(js_text) > 20:
                    logger.info(f"[{llm_name}] JS fallback 提取成功 ({len(js_text)} chars)")
                    resp_text = js_text[:5000]

            if llm_name == "doubao" and resp_text:
                auth_reason = await _doubao_response_auth_reason_from_page(
                    page, resp_text, resp_html
                )
                if auth_reason:
                    self.last_error_reason = auth_reason
                    await _save_html(page, debug_query_id, auth_reason)
                    await _save_screenshot(page, debug_query_id, auth_reason)
                    await _save_runtime_snapshot(
                        page,
                        debug_query_id,
                        auth_reason,
                        config=cfg,
                        runtime_events=runtime_events,
                    )
                    return "", "", []
                challenge_reason = await self._prefer_doubao_visual_challenge_reason(
                    llm_name, page
                )
                if challenge_reason:
                    await _save_html(page, debug_query_id, challenge_reason)
                    await _save_screenshot(page, debug_query_id, challenge_reason)
                    await _save_runtime_snapshot(
                        page,
                        debug_query_id,
                        challenge_reason,
                        config=cfg,
                        runtime_events=runtime_events,
                    )
                    return "", "", []

            if not resp_text:
                try:
                    page_text = await page.evaluate("document.body?.innerText || ''")
                    invalid_page_reason = invalid_response_reason(llm_name, page_text)
                    if invalid_page_reason:
                        logger.warning(
                            "[%s] page content indicates invalid session/content (%s)",
                            llm_name,
                            invalid_page_reason,
                        )
                        self.last_error_reason = invalid_page_reason
                        await _save_html(page, debug_query_id, f"{llm_name}_{invalid_page_reason}")
                        return "", "", []
                except Exception as e:
                    logger.debug("[%s] invalid page probe failed: %s", llm_name, e)
                logger.warning(f"[{llm_name}] 所有提取方式均失败，当前 URL: {page.url}")

            # 检测是否误抓了首页内容（而非真正的 AI 响应）
            homepage_indicators_by_llm = {
                "doubao": ["有什么我能帮你的吗", "写一段早上", "PPT 生成", "超能模式", "图像生成"],
                "chatgpt": [
                    "What are you working on?",
                    "How can I help you today?",
                    "Examples", "Capabilities", "Limitations",
                    "Stay logged out", "Log in", "Sign up",
                ],
            }
            indicators = homepage_indicators_by_llm.get(llm_name, [])
            if indicators and resp_text:
                matched_indicators = [kw for kw in indicators if kw in resp_text]
                if len(matched_indicators) >= 2:
                    logger.warning(
                        f"[{llm_name}] 提取到的内容疑似首页而非 AI 响应"
                        f"（匹配首页关键词: {matched_indicators}），丢弃"
                    )
                    await _save_html(page, debug_query_id, f"{llm_name}_homepage_content")
                    self.last_error_reason = f"{llm_name}_homepage_content"
                    resp_text = ""
                    resp_html = ""

            # Reject known app/login/error pages before saving a response.
            invalid_reason = invalid_response_reason(llm_name, resp_text)
            if invalid_reason:
                logger.warning(
                    "[%s] extracted invalid response content (%s), discarding",
                    llm_name,
                    invalid_reason,
                )
                self.last_error_reason = invalid_reason
                await _save_html(page, debug_query_id, f"{llm_name}_{invalid_reason}")

                # ChatGPT's SPA occasionally crashes mid-render and surfaces a
                # JS stack trace where the answer should be. A single page
                # reload + resubmit usually clears it; switching proxy nodes
                # (the upstream retry path) does not, since the bug is
                # client-side. Retry once and only once.
                if invalid_reason == "chatgpt_application_error" and _retry_count == 0:
                    logger.info(
                        "[%s] reloading page and retrying once after application error",
                        llm_name,
                    )
                    try:
                        await page.reload(wait_until="domcontentloaded", timeout=30000)
                        await page.wait_for_timeout(2000)
                        new_input = None
                        for sel in [
                            s.strip() for s in cfg.get("input_selector", "").split(",")
                        ]:
                            if not sel:
                                continue
                            try:
                                new_input = await page.wait_for_selector(
                                    sel, timeout=8000, state="attached"
                                )
                                if new_input:
                                    break
                            except Exception:
                                continue
                        if new_input:
                            return await self._browser_query(
                                page, cfg, query_text, llm_name, new_input,
                                _retry_count=1,
                                query_id=query_id,
                                runtime_events=runtime_events,
                            )
                        logger.warning(
                            "[%s] retry aborted: no input element after reload",
                            llm_name,
                        )
                    except Exception as e:
                        logger.warning("[%s] reload+retry failed: %s", llm_name, e)

                return "", "", []

            if llm_name == "doubao":
                auth_reason = await _doubao_response_auth_reason_from_page(
                    page, resp_text, resp_html
                )
                if auth_reason:
                    logger.warning(
                        "[doubao] rejecting response because auth state is not proven (%s)",
                        auth_reason,
                    )
                    self.last_error_reason = auth_reason
                    await _save_html(page, debug_query_id, auth_reason)
                    await _save_screenshot(page, debug_query_id, auth_reason)
                    await _save_runtime_snapshot(
                        page,
                        debug_query_id,
                        auth_reason,
                        config=cfg,
                        runtime_events=runtime_events,
                    )
                    return "", "", []
                resp_html = (resp_html or "") + f"\n<!-- {DOUBAO_AUTH_OK_MARKER} -->"

            # 豆包引用面板：2026 UI 触发器从 [data-testid=...] 换成
            # <div class="entry-btn-v3-XXXX"> 包裹 <span class="entry-btn-title-v3-XXXX">参考 N 篇资料</span>
            # 必须点击触发器才能渲染右侧面板（container-outer-XXXX[data-visible="true"]）。
            #
            # Refs #570 / #904 — Q-185003 evidence (workflow run 25851188421)
            # showed citations_json_count=0 while the screenshot proved 8
            # visible reference cards. Root cause: ``resp_html`` was captured
            # via ``inner_html()`` of the response-message selector BEFORE
            # this entry-btn-v3 click fired, so the drawer DOM never reached
            # ``llm_responses.response_html`` and downstream HTML extraction
            # had nothing to read. We now (1) open the drawer, (2) snapshot
            # the opened ``container-outer[data-visible="true"]`` outerHTML
            # and append it to ``resp_html``, and (3) feed the snapshot
            # through the dedicated Doubao panel extractor as a defense-in-
            # depth fallback for the live ``page.evaluate`` extractor.
            doubao_panel_html = ""
            if llm_name == "doubao":
                try:
                    ref_btn = await page.wait_for_selector(
                        '[class*="entry-btn-v3"], [data-testid="search-reference-ui-v3"]',
                        timeout=8000,
                    )
                    await page.wait_for_timeout(500)
                    if ref_btn:
                        try:
                            await ref_btn.click()
                        except Exception:
                            # entry-btn-v3 是个 div，可能需要走 JS click
                            try:
                                await ref_btn.evaluate("el => el.click()")
                            except Exception as e:
                                logger.debug(f"[doubao] 引用触发器点击失败: {e}")
                        logger.debug("[doubao] 已点击引用面板按钮，等待展开")
                        try:
                            await page.wait_for_selector(
                                '[class*="container-outer"][data-visible="true"] [class*="search-item-title"], '
                                '[data-testid="search-text-item"]',
                                timeout=5000,
                            )
                            await page.wait_for_timeout(800)
                        except Exception:
                            logger.debug("[doubao] 引用面板展开后未找到 search-item")

                    # Re-capture the opened drawer DOM. This MUST run after the
                    # click + wait above so the DOM contains the rendered
                    # search-item-* cards. We grab the panel root's outerHTML
                    # (not the entire page) to keep the persisted bytes bounded
                    # but include enough markup for fallback extraction.
                    try:
                        doubao_panel_html = await page.evaluate(
                            """
                            () => {
                                const panels = document.querySelectorAll(
                                    '[class*="container-outer"][data-visible="true"], '
                                    + '[class*="container-outer"]:not([data-visible="false"])'
                                );
                                const out = [];
                                for (const panel of panels) {
                                    const isRefPanel = panel.querySelector('[class*="page-search"]')
                                        || panel.querySelector('[class*="search-item-title"]');
                                    if (!isRefPanel) continue;
                                    out.push(panel.outerHTML);
                                }
                                // 兜底：未匹配 container-outer 时退回老 testid
                                if (!out.length) {
                                    const legacy = document.querySelector(
                                        '[data-testid="search-reference-ui-v3"]'
                                    );
                                    if (legacy) out.push(legacy.outerHTML);
                                }
                                return out.join('\\n');
                            }
                            """
                        ) or ""
                        if doubao_panel_html:
                            # Cap the captured drawer to a sane budget. 200KB is
                            # well above the largest observed Doubao drawer
                            # snapshot (~30KB) and keeps the existing
                            # ``response_html[-50000:]`` budget honest.
                            doubao_panel_html = doubao_panel_html[:200000]
                            resp_html = (
                                (resp_html or "")
                                + "\n<!-- doubao-references-opened -->\n"
                                + doubao_panel_html
                            )
                            logger.info(
                                "[doubao] captured opened reference panel HTML (%s bytes)",
                                len(doubao_panel_html),
                            )
                    except Exception as e:
                        logger.debug(f"[doubao] 引用面板 outerHTML 抓取失败: {e}")
                except Exception:
                    logger.debug("[doubao] 未检测到引用面板（可能无引用）")

            # 提取引用链接
            citations, citation_metadata = await self._extract_citations(page, cfg, llm_name)
            html_citations = extract_citations_from_html(resp_html, llm_name=llm_name)
            if html_citations:
                citations = merge_citations(citations, html_citations)

            # Defense in depth for Doubao: when the live page.evaluate path
            # missed the drawer (timing race, click rejected, etc.) but we
            # successfully captured the drawer HTML above, re-extract from
            # the persisted HTML so DB ↔ live extraction can't diverge.
            doubao_panel_html_citations: list[dict] = []
            if llm_name == "doubao":
                doubao_panel_html_citations = (
                    extract_doubao_panel_citations_from_html(resp_html) or []
                )
                if doubao_panel_html_citations and not citations:
                    citations = merge_citations(citations, doubao_panel_html_citations)
                    logger.info(
                        "[doubao] recovered %s citations from opened panel HTML "
                        "after live extractor returned none",
                        len(doubao_panel_html_citations),
                    )
                elif doubao_panel_html_citations:
                    citations = merge_citations(citations, doubao_panel_html_citations)

            if llm_name in ("chatgpt", "doubao"):
                citation_state = classify_citation_extraction(
                    llm_name,
                    raw_text=resp_text,
                    response_html=resp_html,
                    citations=citations,
                    source_ui_seen=bool(citation_metadata.get("source_ui_seen")),
                    source_ui_clicked=bool(citation_metadata.get("source_ui_clicked")),
                )
                logger.info(
                    "[%s] citation extraction status=%s reason=%s "
                    "citations=%s html_candidates=%s "
                    "doubao_panel_candidates=%s source_markers=%s "
                    "source_ui_seen=%s source_ui_clicked=%s",
                    llm_name,
                    citation_state["status"],
                    citation_state["reason"],
                    citation_state["citation_count"],
                    citation_state["html_candidate_count"],
                    citation_state.get("doubao_panel_candidate_count", 0),
                    citation_state["source_marker_count"],
                    citation_state["source_ui_seen"],
                    citation_state["source_ui_clicked"],
                )
            return resp_text, resp_html, citations
        except Exception as e:
            logger.warning(f"[{llm_name}] 提取响应异常: {e}")
            return "", "", []


async def _doubao_auth_state_reason_from_page(page: Page) -> str | None:
    """Inspect the full Doubao page chrome before accepting an answer."""
    body_text = ""
    html = ""
    try:
        body_text = await page.evaluate("document.body?.innerText || ''")
    except Exception:
        pass
    try:
        html = await page.content()
    except Exception:
        pass
    return doubao_auth_state_reason(body_text, html)


async def _doubao_response_auth_reason_from_page(
    page: Page,
    raw_text: str | None,
    response_html: str | None,
) -> str | None:
    """Inspect full Doubao page chrome after a candidate answer was extracted."""
    body_text = ""
    html = ""
    try:
        body_text = await page.evaluate("document.body?.innerText || ''")
    except Exception:
        pass
    try:
        html = await page.content()
    except Exception:
        pass
    combined_text = "\n".join(part for part in (raw_text or "", body_text) if part)
    combined_html = "\n".join(part for part in (response_html or "", html) if part)
    return doubao_persistence_auth_reason("doubao", combined_text, combined_html)


async def _save_html(page: Page, query_id: int, suffix: str = "") -> Optional[Path]:
    """保存页面 HTML 供调试（比截图更容易分析 DOM 结构）

    Refs #963 follow-up to PR #1009 live evidence (Admin E2E run
    25926214958 query 184968 retry 21, stage=prompt_fill,
    latency=480856ms): PR #1009 bounded each step inside
    ``_fill_plain_text_input`` but the production retry still spent
    the full 480s budget at stage=prompt_fill. The post-fix code path
    on a "no_input" failure is: bounded fill returns False →
    ``_save_html(page, ..., "{llm}_input_fill_failed")`` → ``await
    page.content()`` — and that ``page.content()`` call is unbounded.
    On a dead/hung page it can wait indefinitely. Bound the
    ``page.content()`` call so a hung page cannot turn a fast fill
    failure into a full-budget timeout. 15s is plenty for the
    real call (returns in <100ms when the page is healthy).
    """
    try:
        timestamp = int(datetime.utcnow().timestamp())
        filename = f"query_{query_id}_{suffix}_{timestamp}.html" if suffix else f"query_{query_id}_{timestamp}.html"
        path = SCREENSHOT_DIR / filename
        html = await asyncio.wait_for(page.content(), timeout=PROMPT_FILL_VALUE_READ_TIMEOUT_S)
        path.write_text(html, encoding="utf-8")
        logger.info(f"HTML 已保存: {path} ({len(html)} bytes)")
        return path
    except asyncio.TimeoutError:
        logger.warning(
            f"保存 HTML 超时 ({PROMPT_FILL_VALUE_READ_TIMEOUT_S}s) "
            f"page.content() did not return for query_{query_id}_{suffix}"
        )
        return None
    except Exception as e:
        logger.warning(f"保存 HTML 失败: {e}")
        return None


async def _find_attached_selector(
    page: Page,
    selector_csv: str,
    *,
    timeout: int = 5000,
) -> tuple[str | None, bool]:
    """Return the first selector that exists on a partially loaded page."""
    selectors = [s.strip() for s in selector_csv.split(",") if s.strip()]
    for selector in selectors:
        try:
            element = await page.wait_for_selector(
                selector,
                timeout=timeout,
                state="attached",
            )
            if element:
                visible = False
                try:
                    visible = await element.is_visible()
                except Exception:
                    pass
                return selector, visible
        except Exception:
            continue
    return None, False


async def _save_runtime_snapshot(
    page: Page,
    query_id: int,
    suffix: str,
    *,
    config: dict | None = None,
    error: BaseException | str | None = None,
    matched_selector: str | None = None,
    runtime_events: list[dict] | None = None,
    proxy_diagnostic: dict | None = None,
) -> Optional[Path]:
    """Save a redacted DOM/runtime snapshot for scraper triage."""
    try:
        timestamp = int(datetime.utcnow().timestamp())
        filename = f"query_{query_id}_{suffix}_{timestamp}.json" if suffix else f"query_{query_id}_{timestamp}.json"
        path = SCREENSHOT_DIR / filename
        selector_payload = {
            "input": config.get("input_selector", "") if config else "",
            "response": config.get("response_selector", "") if config else "",
        }
        page_state = await page.evaluate(
            """
            (selectors) => {
                const inspect = (selectorCsv) => {
                    return (selectorCsv || '')
                        .split(',')
                        .map(s => s.trim())
                        .filter(Boolean)
                        .map(selector => {
                            try {
                                const nodes = [...document.querySelectorAll(selector)];
                                const first = nodes[0] || null;
                                return {
                                    selector,
                                    count: nodes.length,
                                    visibleCount: nodes.filter(n => {
                                        const r = n.getBoundingClientRect();
                                        const style = getComputedStyle(n);
                                        return r.width > 0 && r.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                                    }).length,
                                    firstText: first ? (first.innerText || first.textContent || first.value || '').slice(0, 500) : '',
                                    firstHtml: first ? first.outerHTML.slice(0, 1000) : '',
                                };
                            } catch (e) {
                                return {selector, error: String(e).slice(0, 300)};
                            }
                        });
                };
                return {
                    url: location.href,
                    title: document.title,
                    readyState: document.readyState,
                    activeElement: document.activeElement ? {
                        tagName: document.activeElement.tagName,
                        id: document.activeElement.id || '',
                        className: String(document.activeElement.className || '').slice(0, 200),
                    } : null,
                    bodyText: (document.body?.innerText || '').slice(0, 3000),
                    inputSelectors: inspect(selectors.input),
                    responseSelectors: inspect(selectors.response),
                    loginLikeNodes: inspect("[class*='login'], [class*='sign-in'], [class*='passport'], [role='dialog']"),
                    challengeLikeNodes: inspect("[role='dialog'], [class*='captcha'], [class*='verify'], [class*='challenge'], [class*='modal']"),
                };
            }
            """,
            selector_payload,
        )
        is_doubao_snapshot = "doubao" in suffix.lower() or "doubao" in (
            config.get("url", "") if config else ""
        ).lower()
        doubao_auth_reason = (
            doubao_auth_state_reason(
                page_state.get("bodyText", "") if isinstance(page_state, dict) else "",
                json.dumps(page_state.get("loginLikeNodes", []), ensure_ascii=False)
                if isinstance(page_state, dict)
                else "",
            )
            if is_doubao_snapshot
            else None
        )
        doubao_visual_challenge = None
        if is_doubao_snapshot and isinstance(page_state, dict):
            doubao_visual_challenge = _doubao_visual_challenge_state_from_text(
                "\n".join(
                    [
                        str(page_state.get("bodyText", "")),
                        json.dumps(
                            page_state.get("challengeLikeNodes", []),
                            ensure_ascii=False,
                        ),
                    ]
                )
            ) or None
        snapshot = {
            "savedAt": datetime.utcnow().isoformat() + "Z",
            "queryId": query_id,
            "suffix": suffix,
            "matchedSelector": matched_selector,
            "error": _redact_sensitive_text(f"{type(error).__name__}: {error}") if error else None,
            "proxy": proxy_diagnostic,
            "doubaoAuthStateReason": doubao_auth_reason,
            "doubaoVisualChallenge": doubao_visual_challenge,
            "runtimeEvents": runtime_events[-80:] if runtime_events else [],
            "page": page_state,
        }
        raw = json.dumps(_redact_runtime_data(snapshot), ensure_ascii=True, indent=2)
        path.write_text(raw, encoding="utf-8")
        logger.info(f"Runtime snapshot saved: {path} ({len(raw)} bytes)")
        return path
    except Exception as e:
        logger.warning(f"Failed to save runtime snapshot: {e}")
        return None


async def _save_screenshot(page: Page, query_id: int, suffix: str = "") -> Optional[Path]:
    """保存截图"""
    try:
        timestamp = int(datetime.utcnow().timestamp())
        filename = f"query_{query_id}_{suffix}_{timestamp}.png" if suffix else f"query_{query_id}_{timestamp}.png"
        path = SCREENSHOT_DIR / filename
        await page.screenshot(path=str(path), full_page=True)
        logger.info(f"截图已保存: {path}")
        return path
    except Exception as e:
        logger.warning(f"保存截图失败: {e}")
        return None
