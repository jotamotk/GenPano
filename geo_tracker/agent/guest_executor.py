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
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, BrowserContext, Page

# Camoufox: 反指纹浏览器，海外 LLM 优先使用以绕过 Cloudflare
try:
    from camoufox.async_api import AsyncCamoufox
    HAS_CAMOUFOX = True
except ImportError:
    HAS_CAMOUFOX = False

from geo_tracker.agent.captcha import CaptchaSolver, detect_and_solve, CAPSOLVER_API_KEY
from geo_tracker.agent.clash_api import (
    get_current_node,
    switch_to_next_node,
    CLASH_API_URL,
)
from geo_tracker.db.models import LLMResponse, Query, QueryStatus

logger = logging.getLogger(__name__)

# 重试配置
MAX_RETRY_ON_CF_BLOCK = 3                          # Cloudflare 拦截最大重试次数
CLASH_PROXY_GROUP = os.getenv("CLASH_PROXY_GROUP", "💬 Ai平台")  # Clash 代理组名称（含实际节点）
CF_CHALLENGE_TITLES = [
    "just a moment", "attention required", "checking your browser",
    "unable to load site", "please wait", "access denied",
]

SCREENSHOT_DIR = Path(os.getenv("SCREENSHOT_DIR", "/data/screenshots"))
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# 从环境变量加载各 LLM 的 cookies（JSON 数组格式）
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
GUEST_LLM_CONFIG = {
    "chatgpt": {
        "url":              "https://chatgpt.com",
        "input_selector":   "#prompt-textarea, [data-testid='prompt-textarea'], textarea, [role='textbox']",
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
        "input_selector":   "[data-testid='chat_input_input'], textarea[data-testid='chat_input_input'], textarea, [contenteditable='true'], [class*='chat-input']",
        # 豆包 2026 版 UI 不再使用 data-testid，需要多 selector + JS fallback 兜底
        "submit_button":    "button[data-testid='chat_input_send_button'], button[aria-label*='发送'], button[aria-label*='send' i], button[data-testid*='send']",
        "submit_key":       "Enter",
        # receive_message testid 已移除；保留旧 selector + flow-markdown-body / message 类名作为 fallback
        "response_selector": "[data-testid='receive_message'] [data-testid='message_text_content'], [data-testid='receive_message'] .flow-markdown-body, .flow-markdown-body, [class*='message-content'], [class*='chat-message-content']",
        "wait_after_submit": 60000,
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

    async def execute(self, query: Query) -> Optional[LLMResponse]:
        """
        执行单条查询（无账号模式）
        遇到 Cloudflare 拦截时自动切换 Clash 代理节点并重试

        Args:
            query: Query 对象

        Returns:
            LLMResponse 对象，如果失败返回 None
        """
        llm = query.target_llm
        config = GUEST_LLM_CONFIG.get(llm)
        if not config:
            logger.error(f"Unknown LLM: {llm}")
            return None

        use_proxy = self.proxy_url and llm not in DOMESTIC_LLMS

        # 国内 LLM 或不使用代理时，直接执行一次，无需重试换节点
        if not use_proxy:
            return await self._execute_once(query, config, use_proxy=False)

        # 海外 LLM：支持 Cloudflare 拦截后切换节点重试
        failed_nodes: set[str] = set()

        for attempt in range(MAX_RETRY_ON_CF_BLOCK):
            if attempt > 0:
                new_node = await switch_to_next_node(
                    CLASH_API_URL, CLASH_PROXY_GROUP, exclude=failed_nodes
                )
                if not new_node:
                    logger.error(f"[{llm}] 没有更多可用代理节点，放弃重试")
                    break
                logger.info(f"[{llm}] 第 {attempt + 1} 次重试，已切换到节点: {new_node}")

            result = await self._execute_once(query, config, use_proxy=True)
            if result is not None:
                return result

            # 执行失败，记录当前节点
            current = await get_current_node(CLASH_API_URL, CLASH_PROXY_GROUP)
            if current:
                failed_nodes.add(current)
                logger.warning(f"[{llm}] 节点 {current} 失败，加入黑名单 (已排除 {len(failed_nodes)} 个)")

        logger.error(f"[{llm}] 所有重试均失败")
        return None

    async def _execute_once(
        self, query: Query, config: dict, *, use_proxy: bool
    ) -> Optional[LLMResponse]:
        """执行一次查询尝试（可能因 Cloudflare 拦截返回 None）"""
        llm = query.target_llm
        proxy_cfg = {"server": self.proxy_url} if use_proxy else None

        if use_proxy:
            logger.info(f"[{llm}] 使用代理: {self.proxy_url}")

        page_obj = None
        browser = None
        _camoufox_ctx = None
        _playwright = None

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
                    "block_images": False,
                    "os": "windows",
                    "locale": "zh-CN" if is_domestic else "en-US",
                }
                if use_proxy:
                    camoufox_kwargs["proxy"] = {"server": self.proxy_url}

                _camoufox_ctx = AsyncCamoufox(**camoufox_kwargs)
                browser = await _camoufox_ctx.__aenter__()
                logger.info(f"[{llm}] Camoufox 启动成功")

                context = await browser.new_context()
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
                        logger.info(
                            f"[{llm}] 使用 AccountPool cookies ({len(injected_cookies)} 个) "
                            f"+ localStorage ({len(local_storage_data)} 项)"
                        )
                    elif isinstance(parsed, list):
                        # 旧格式: 纯 cookies 数组
                        injected_cookies = parsed
                        logger.info(f"[{llm}] 使用 AccountPool cookies ({len(injected_cookies)} 个)")
                except Exception as e:
                    logger.warning(f"[{llm}] 解析 account_cookies 失败: {e}")

            if not injected_cookies:
                cookies_env = config.get("cookies_env")
                if cookies_env:
                    injected_cookies = _load_cookies_from_env(cookies_env)

            if injected_cookies:
                await context.add_cookies(injected_cookies)
                logger.info(f"[{llm}] 已注入 {len(injected_cookies)} 个 cookies")

            page_obj = await context.new_page()

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
                                const v = localStorage.getItem(k);
                                result[k] = v ? v.substring(0, 80) + (v.length > 80 ? '...' : '') : null;
                            }
                            return result;
                        }
                    """, list(local_storage_data.keys()))
                    logger.info(f"[{llm}] 已注入 {len(local_storage_data)} 项 localStorage, 验证: {verify}")
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
                            logger.info(f"[{llm}] session endpoint HTTP {resp.status}, body: {body[:300]}")
                            if resp.ok:
                                try:
                                    session_data = json.loads(body)
                                    if session_data.get("accessToken"):
                                        logger.info(
                                            f"[{llm}] session 刷新成功，"
                                            f"用户: {session_data.get('user', {}).get('email', 'unknown')}, "
                                            f"expires: {session_data.get('expires', 'unknown')}"
                                        )
                                    else:
                                        logger.warning(f"[{llm}] session 响应无 accessToken，cookie 可能已过期")
                                        await _save_screenshot(page_obj, query.id, f"{llm}_session_no_token")
                                        return None
                                except json.JSONDecodeError:
                                    # 可能返回了 CF 挑战页面 HTML
                                    logger.warning(f"[{llm}] session 响应非 JSON（可能是 CF 页面）: {body[:200]}")
                                    await _save_screenshot(page_obj, query.id, f"{llm}_session_cf_block")
                                    return None
                            else:
                                logger.warning(f"[{llm}] session 刷新 HTTP {resp.status}")
                                await _save_screenshot(page_obj, query.id, f"{llm}_session_http_error")
                                return None
                        else:
                            logger.warning(f"[{llm}] session 刷新无响应")
                            return None

                        # 刷新后关闭旧页面，开新页面（清除客户端缓存的 expired 状态）
                        logger.info(f"[{llm}] session 刷新完成，重新打开新页面...")
                        await page_obj.close()
                        page_obj = await context.new_page()
                        await page_obj.goto(config["url"], wait_until="domcontentloaded", timeout=60000)
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
                        await _save_screenshot(page_obj, query.id, f"{llm}_session_exception")
                        return None

                # 检测是否被重定向到登录页（cookie 过期或未注入）
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
                if page_obj:
                    try:
                        await _save_screenshot(page_obj, query.id, f"{llm}_load_error")
                    except:
                        pass
                return None

            # 页面加载后检查是否被重定向到登录页
            current_url = page_obj.url
            login_domains = config.get("login_redirect_domains", [])
            if any(d in current_url for d in login_domains):
                logger.warning(f"[{llm}] 页面加载后仍在登录页: {current_url}，cookies/token 已失效")
                await _save_screenshot(page_obj, query.id, f"{llm}_login_after_load")
                if self.account_cookies:
                    return None  # 让上层标记 cookies_expired
                return None

            # 尝试找输入框
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

            if not input_el:
                logger.error(f"[{llm}] 找不到输入框")
                if page_obj:
                    await _save_screenshot(page_obj, query.id, f"{llm}_no_input")
                    try:
                        content = await page_obj.content()
                        content_path = SCREENSHOT_DIR / f"query_{query.id}_{llm}_content.html"
                        content_path.write_text(content[:50000], encoding='utf-8')
                        logger.info(f"[{llm}] 页面内容已保存: {content_path}")
                    except Exception as e:
                        logger.warning(f"保存页面内容失败: {e}")
                return None

            # 执行查询
            resp_text, resp_html, citations = await self._browser_query(page_obj, config, query.query_text, llm, input_el)

            if resp_text:
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
                    await _save_screenshot(page_obj, query.id, f"{llm}_no_response")
                return None

        except Exception as e:
            logger.exception(f"[{llm}] 执行异常: {e}")
            if page_obj:
                try:
                    await _save_screenshot(page_obj, query.id, f"{llm}_exception")
                except:
                    pass
            return None
        finally:
            if browser:
                try:
                    await browser.close()
                except:
                    pass
            if _camoufox_ctx:
                try:
                    await _camoufox_ctx.__aexit__(None, None, None)
                except:
                    pass
            if _playwright:
                try:
                    await _playwright.stop()
                except:
                    pass

    async def _extract_citations(self, page: Page, cfg: dict, llm_name: str) -> list:
        """从响应区域提取引用链接"""
        citations = []
        try:
            response_selectors = [s.strip() for s in cfg["response_selector"].split(",") if s.strip()]

            # 豆包使用独立的引用面板，需要专门提取
            if llm_name == "doubao":
                citations = await self._extract_doubao_citations(page)
                if citations:
                    logger.info(f"[{llm_name}] 从引用面板提取到 {len(citations)} 个引用链接")
                    return citations

            # 通用提取：在响应区域内查找所有链接
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
        return citations

    async def _extract_doubao_citations(self, page: Page) -> list:
        """从豆包引用面板提取引用链接。

        豆包的引用不是内嵌在响应正文的 <a> 标签，而是在独立的引用面板中：
        - 触发按钮: [data-testid="search-reference-ui-v3"]（需先点击展开）
        - 每条引用: [data-testid="search-text-item"] 内含 <a href="...">
        - 标题: .search-item-title-* 类名
        - 编号: .footer-citation-* 类名
        """
        try:
            citations = await page.evaluate("""
                () => {
                    const citations = [];
                    const seen = new Set();

                    // 策略1：从展开的引用面板中提取（search-text-item）
                    const items = document.querySelectorAll('[data-testid="search-text-item"]');
                    for (const item of items) {
                        const link = item.querySelector('a[href]');
                        if (!link) continue;
                        const url = link.href;
                        if (!url || !url.startsWith('http') || seen.has(url)) continue;
                        seen.add(url);

                        // 提取标题（优先用 title class，fallback 到链接文本）
                        const titleEl = item.querySelector('[class*="search-item-title"]');
                        const title = titleEl
                            ? (titleEl.textContent || '').trim()
                            : (link.textContent || '').trim();

                        // 提取引用编号
                        const citationEl = item.querySelector('[class*="footer-citation"]');
                        const citationNum = citationEl
                            ? parseInt(citationEl.textContent, 10)
                            : 0;

                        // 提取来源名称
                        const sourceEl = item.querySelector('[class*="footer-title"]');
                        const source = sourceEl ? (sourceEl.textContent || '').trim() : '';

                        citations.push({
                            url: url,
                            title: (title || '').slice(0, 200),
                            source: source,
                            index: citationNum || (citations.length + 1)
                        });
                    }

                    // 策略2：如果 search-text-item 未找到，尝试从弹出面板中的所有链接提取
                    // 豆包的弹出面板可能使用 popover / dialog / drawer 等容器
                    if (citations.length === 0) {
                        const panelSelectors = [
                            '[data-testid*="search-reference"] a[href]',
                            '[class*="reference-panel"] a[href]',
                            '[class*="search-panel"] a[href]',
                            '[class*="citation-panel"] a[href]',
                            // popover / drawer 容器内的链接
                            '[data-radix-popper-content-wrapper] a[href]',
                            '[role="dialog"] a[href]',
                        ];
                        for (const sel of panelSelectors) {
                            try {
                                const links = document.querySelectorAll(sel);
                                for (const link of links) {
                                    const url = link.href;
                                    if (!url || !url.startsWith('http') || seen.has(url)) continue;
                                    // 过滤掉豆包自身的链接
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

                    // 按引用编号排序
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

    async def _browser_query(
        self, page: Page, cfg: dict, query_text: str, llm_name: str, input_el=None
    ) -> tuple:
        """在已打开的页面里输入 query，等待响应，抓取文本和引用
        Returns: (response_text, response_html, citations_list)"""
        if input_el is None:
            input_el = await page.wait_for_selector(cfg["input_selector"].split(",")[0], timeout=10000)

        # 模拟人类行为：随机延迟 + 鼠标移动到输入框
        await page.wait_for_timeout(random.randint(800, 2000))
        try:
            # 先模拟鼠标移动到输入框附近
            box = await input_el.bounding_box()
            if box:
                await page.mouse.move(
                    box["x"] + box["width"] * random.uniform(0.2, 0.8),
                    box["y"] + box["height"] * random.uniform(0.2, 0.8),
                    steps=random.randint(5, 15),
                )
                await page.wait_for_timeout(random.randint(200, 500))
        except Exception:
            pass

        # 点击输入框（force=True 绕开可见性检查）
        try:
            await input_el.click(force=True, timeout=5000)
        except:
            pass
        await page.wait_for_timeout(random.randint(300, 800))

        # 对于 contenteditable（如 Gemini 的 Quill 编辑器），键盘事件依赖真实 focus
        # 在 headless 下元素常常报告"不可见"，导致 keyboard.type() 打到 body 而非编辑器
        # 改用 JS 直接注入文字并触发 Quill/Angular 所需的 input 事件
        if cfg.get("contenteditable"):
            # 把 LLM 自己的选择器列表传给 JS，避免硬编码 Gemini 的 Quill 选择器
            input_selectors = [s.strip() for s in cfg.get("input_selector", "").split(",")]
            injected = await page.evaluate("""
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
            """, [query_text, input_selectors])
            logger.info(f"[{llm_name}] JS 注入文字: {'成功' if injected else '失败'}")
            # 保存注入后的 HTML，确认文字是否真的进了编辑器
            await _save_html(page, -1, f"{llm_name}_after_inject")
        else:
            try:
                await input_el.fill("")
            except:
                pass
            await page.wait_for_timeout(random.randint(200, 500))
            # 模拟人类打字速度（50-120ms/字符）
            await page.keyboard.type(query_text, delay=random.randint(50, 120))

        # 模拟人类"思考"后再提交
        await page.wait_for_timeout(random.randint(500, 1500))

        # 提交：优先点击 submit_button 里配的 selector，失败时 JS 找 input 附近的 enabled 按钮，
        # 再失败才 fallback 到 Enter
        async def _find_submit_button_js():
            """豆包新 UI 无 testid，通过位置 + 图标找 send 按钮。"""
            return await page.evaluate_handle(
                """
                () => {
                    // 优先：aria-label / title 含 send/发送
                    const all = [...document.querySelectorAll('button, [role="button"]')];
                    const byAria = all.find(b => {
                        if (b.disabled) return false;
                        const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                        const title = (b.getAttribute('title') || '').toLowerCase();
                        return /send|发送|提交/.test(aria) || /send|发送|提交/.test(title);
                    });
                    if (byAria) return byAria;

                    // 次选：input 附近、含 svg 图标、文本为空或极短、enabled 的按钮
                    const input = document.querySelector(
                        'textarea, [contenteditable="true"]'
                    );
                    if (!input) return null;
                    const ir = input.getBoundingClientRect();
                    let best = null, bestDist = Infinity;
                    for (const b of all) {
                        if (b.disabled || b.getAttribute('data-disabled') === 'true') continue;
                        const r = b.getBoundingClientRect();
                        if (r.width === 0 || r.height === 0) continue;
                        const txt = (b.textContent || '').trim();
                        if (txt.length > 4) continue;  // 文本按钮跳过
                        if (!b.querySelector('svg, img, i')) continue;  // 必须有图标
                        // 限制在 input 正下方/右侧附近 150px 以内
                        const dx = Math.max(0, r.left - ir.right, ir.left - r.right);
                        const dy = Math.max(0, r.top - ir.bottom, ir.top - r.bottom);
                        if (dx > 300 || dy > 200) continue;
                        const dist = dx + dy;
                        if (dist < bestDist) { bestDist = dist; best = b; }
                    }
                    return best;
                }
                """
            )

        submitted = False
        if cfg.get("submit_button"):
            for btn_sel in [s.strip() for s in cfg["submit_button"].split(",")]:
                try:
                    btn = await page.query_selector(btn_sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        submitted = True
                        logger.info(f"[{llm_name}] 通过按钮提交: {btn_sel}")
                        break
                except Exception:
                    continue
        if not submitted and llm_name == "doubao":
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

        # 验证提交成功：豆包 testid 已删除，改用 textarea 清空 + 出现新消息块判断
        async def _submit_confirmed() -> bool:
            try:
                return await page.evaluate(
                    r"""
                    (queryText) => {
                        // 1) 存在 send_message testid（老 UI）
                        if (document.querySelector('[data-testid="send_message"]')) return true;
                        // 2) 输入框被清空（发送后 doubao 会清空）
                        const inp = document.querySelector(
                            'textarea[data-testid="chat_input_input"], textarea, [contenteditable="true"]'
                        );
                        if (inp) {
                            const v = (inp.value !== undefined ? inp.value : inp.textContent) || '';
                            if (v.trim().length === 0 && queryText.length > 0) return true;
                        }
                        // 3) 页面某个气泡类元素包含 query 文本
                        const candidates = document.querySelectorAll(
                            '[class*="user-message"], [class*="send-message"], [class*="message-item"], [class*="chat-item"]'
                        );
                        const needle = queryText.slice(0, 20).trim();
                        for (const el of candidates) {
                            if ((el.textContent || '').includes(needle)) return true;
                        }
                        return false;
                    }
                    """,
                    query_text,
                )
            except Exception:
                return False

        if llm_name == "doubao":
            confirmed = False
            for _ in range(10):  # 最多 ~5s 轮询
                if await _submit_confirmed():
                    confirmed = True
                    break
                await page.wait_for_timeout(500)

            if confirmed:
                logger.info(f"[{llm_name}] 已确认消息发送成功")
            else:
                logger.warning(f"[{llm_name}] 提交后未检测到发送的消息，尝试重新提交")
                try:
                    input_retry = await page.query_selector(
                        "[data-testid='chat_input_input'], textarea, [contenteditable='true']"
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
                        await _save_html(page, -1, f"{llm_name}_submit_failed")
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

        while elapsed < wait_total:
            await page.wait_for_timeout(min(wait_interval, wait_total - elapsed))
            elapsed += wait_interval

            # 检测是否跳转到登录页
            current_url = page.url
            login_domains = cfg.get("login_redirect_domains", [])
            if any(d in current_url for d in login_domains):
                logger.warning(f"[{llm_name}] 检测到跳转到登录页: {current_url}，中止等待")
                await _save_screenshot(page, -1, f"{llm_name}_login_redirect")
                return "", "", []

            # 检查是否仍在生成中（豆包"深度思考"等状态）
            still_generating = False
            if llm_name == "doubao":
                try:
                    generating = await page.evaluate("""
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
                    """)
                    still_generating = bool(generating)
                except Exception:
                    pass

            # 提前检查是否已有响应内容（避免浪费剩余等待时间）
            resp_ready = False
            current_resp_len = 0
            for sel in response_selectors:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        txt = await el.inner_text()
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

        # 抓取响应文本 + HTML
        resp_text = ""
        resp_html = ""
        try:
            # 保存完整页面 HTML 用于调试 selector
            await _save_html(page, -1, f"{llm_name}_response_page")

            # 优先尝试配置的 selectors
            for sel in response_selectors:
                try:
                    elements = await page.query_selector_all(sel)
                    if elements:
                        texts = []
                        htmls = []
                        for el in elements:
                            try:
                                txt = await el.inner_text()
                                if txt and txt.strip():
                                    texts.append(txt.strip())
                                # 同时保存 innerHTML（保留 <a href> 等标签）
                                html = await el.inner_html()
                                if html:
                                    htmls.append(html)
                            except:
                                pass
                        combined = "\n".join(texts)
                        if len(combined) > 20:
                            logger.info(f"[{llm_name}] 通过 selector 提取响应: {sel} ({len(combined)} chars)")
                            resp_text = combined[-5000:]
                            resp_html = "\n".join(htmls)[-50000:]  # HTML 保留更多
                            # 豆包：同时保存引用面板 HTML 以便后续 backfill
                            if llm_name == "doubao":
                                try:
                                    ref_panel = await page.query_selector('[data-testid="search-reference-ui-v3"]')
                                    if ref_panel:
                                        ref_html = await ref_panel.inner_html()
                                        if ref_html:
                                            resp_html += "\n<!-- doubao-references -->\n" + ref_html
                                except Exception:
                                    pass
                            break
                except Exception:
                    continue

            if not resp_text:
                # fallback 1：拼接所有 <p> 标签文本
                logger.warning(f"[{llm_name}] 响应选择器未匹配，使用 JS fallback 提取")
                await _save_html(page, -1, f"{llm_name}_extract_fail")
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

            if not resp_text:
                logger.warning(f"[{llm_name}] 所有提取方式均失败，当前 URL: {page.url}")

            # 豆包：检测是否误抓了首页内容（而非真正的 AI 响应）
            if llm_name == "doubao" and resp_text:
                homepage_indicators = ["有什么我能帮你的吗", "写一段早上", "PPT 生成", "超能模式", "图像生成"]
                matched_indicators = [kw for kw in homepage_indicators if kw in resp_text]
                if len(matched_indicators) >= 2:
                    logger.warning(
                        f"[{llm_name}] 提取到的内容疑似首页而非 AI 响应"
                        f"（匹配首页关键词: {matched_indicators}），丢弃"
                    )
                    await _save_html(page, -1, f"{llm_name}_homepage_content")
                    resp_text = ""
                    resp_html = ""

            # 豆包引用面板可能在响应完成后异步加载，额外等待
            if llm_name == "doubao":
                try:
                    ref_btn = await page.wait_for_selector(
                        '[data-testid="search-reference-ui-v3"]',
                        timeout=8000,
                    )
                    await page.wait_for_timeout(500)
                    # 引用按钮需要点击才能展开面板，展开后才有 search-text-item
                    if ref_btn:
                        await ref_btn.click()
                        logger.debug("[doubao] 已点击引用面板按钮，等待展开")
                        try:
                            await page.wait_for_selector(
                                '[data-testid="search-text-item"]',
                                timeout=5000,
                            )
                            await page.wait_for_timeout(800)
                        except Exception:
                            logger.debug("[doubao] 引用面板展开后未找到 search-text-item")
                except Exception:
                    logger.debug("[doubao] 未检测到引用面板（可能无引用）")

            # 提取引用链接
            citations = await self._extract_citations(page, cfg, llm_name)
            return resp_text, resp_html, citations
        except Exception as e:
            logger.warning(f"[{llm_name}] 提取响应异常: {e}")
            return "", "", []


async def _save_html(page: Page, query_id: int, suffix: str = "") -> Optional[Path]:
    """保存页面 HTML 供调试（比截图更容易分析 DOM 结构）"""
    try:
        timestamp = int(datetime.utcnow().timestamp())
        filename = f"query_{query_id}_{suffix}_{timestamp}.html" if suffix else f"query_{query_id}_{timestamp}.html"
        path = SCREENSHOT_DIR / filename
        html = await page.content()
        path.write_text(html, encoding="utf-8")
        logger.info(f"HTML 已保存: {path} ({len(html)} bytes)")
        return path
    except Exception as e:
        logger.warning(f"保存 HTML 失败: {e}")
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
