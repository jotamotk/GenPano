"""
核心 Agent 执行器
- 使用 Camoufox 规避指纹检测
- 加载账号 cookies 跳过登录
- 注入人类行为
- 失败时上报 AccountPool / ProxyPool
"""
from __future__ import annotations

import json
import logging
import os
import random
from datetime import datetime
from pathlib import Path
from typing import Optional

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import BrowserContext, Page

from geo_tracker.agent.browser_lifecycle import (
    cleanup_browser_resources,
    install_resource_blocker,
    should_block_heavy_resources,
)
from geo_tracker.agent.captcha import CaptchaSolver, detect_and_solve
from geo_tracker.agent.human_behavior import (
    human_type, human_scroll_read, pre_query_pause,
    post_submit_wait, inter_query_delay,
)
from geo_tracker.db.models import LLMAccount, LLMResponse, Query, QueryStatus
from geo_tracker.pool.account_pool import AccountPool
from geo_tracker.pool.proxy_pool import ProxyPool

logger = logging.getLogger(__name__)

SCREENSHOT_DIR = Path(os.getenv("SCREENSHOT_DIR", "/data/screenshots"))
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


# ─── LLM 页面配置 ─────────────────────────────────────────────────────────────

LLM_CONFIG: dict[str, dict] = {
    "chatgpt": {
        "url":              "https://chat.openai.com",
        # #prompt-textarea 现在是 ProseMirror contenteditable div
        "input_selector":   "#prompt-textarea, div[contenteditable='true'][role='textbox']",
        # data-testid 偶尔变；优先稳定的 aria-label + class
        "submit_selector":  "button[aria-label='Send prompt'], button[data-testid='send-button'], button.composer-submit-button-color[aria-label*='Send'], #composer-submit-button",
        "response_selector":"[data-message-author-role='assistant'] .markdown",
        # 流式输出完成信号：停止按钮消失 + 发送按钮重新可用
        "wait_for_done":    "button[aria-label='Send prompt']:not([disabled]), button[data-testid='send-button']:not([disabled])",
        # 额外等待：流式光标消失
        "stream_cursor_selector": ".result-streaming",
        "response_timeout": 90_000,
    },
    "gemini": {
        "url":              "https://gemini.google.com",
        "input_selector":   "rich-textarea .ql-editor",
        "submit_selector":  "button.send-button",
        "response_selector":"message-content .markdown",
        # Gemini有打字动画，等动画结束
        "wait_for_done":    "button.send-button:not([disabled])",
        "stream_cursor_selector": "model-response[pending]",
        "response_timeout": 120_000,
        # Gemini需要Google账号，登录态较重要
        "requires_login":   True,
    },
    "claude": {
        "url":              "https://claude.ai",
        "input_selector":   '[contenteditable="true"]',
        "submit_selector":  'button[aria-label="Send Message"]',
        "response_selector":".claude-message .prose",
        "wait_for_done":    'button[aria-label="Send Message"]:not([disabled])',
        "stream_cursor_selector": ".streaming-indicator",
        "response_timeout": 90_000,
    },
    "perplexity": {
        "url":              "https://www.perplexity.ai",
        "input_selector":   "textarea[placeholder]",
        "submit_selector":  "button[aria-label='Submit']",
        "response_selector":".prose",
        "wait_for_done":    "button[aria-label='Submit']:not([disabled])",
        "response_timeout": 60_000,
        # Perplexity 有 citations，需要额外提取
        "citation_selector":"a.citation",
    },
    "grok": {
        "url":              "https://x.com/i/grok",
        "input_selector":   "textarea",
        "submit_selector":  "button[data-testid='grok-send-button']",
        "response_selector":"[data-testid='grok-response'] .prose",
        "wait_for_done":    "button[data-testid='grok-send-button']:not([disabled])",
        "response_timeout": 90_000,
        # Grok 强依赖 X/Twitter 登录态
        "requires_login":   True,
    },
    "kimi": {
        "url":              "https://kimi.moonshot.cn",
        "input_selector":   ".chat-input textarea",
        "submit_selector":  "button.send-btn",
        "response_selector":".message-content",
        "wait_for_done":    "button.send-btn:not([disabled])",
        "response_timeout": 90_000,
    },
    "doubao": {
        "url":              "https://www.doubao.com/chat",
        # 2026 版 UI 不再使用 data-testid；改用稳定 id / class
        "input_selector":   "#input-engine-container textarea.semi-input-textarea:not([aria-hidden='true']), textarea.semi-input-textarea:not([aria-hidden='true']), textarea.input-area, textarea:not([aria-hidden='true']), [class*='chat-input']",
        "submit_selector":  "#flow-end-msg-send:not([aria-disabled='true']):not([data-disabled='true']), button[id='flow-end-msg-send'], button[data-testid='chat_input_send_button']",
        "response_selector":".flow-markdown-body, [class*='receive-message'] [class*='content'], .bot-message .content, [class*='message-content']",
        "wait_for_done":    "#flow-end-msg-send:not([aria-disabled='true']):not([data-disabled='true']), button[data-testid='chat_input_send_button']:not([disabled])",
        "response_timeout": 90_000,
        "requires_login":   True,
        "cookies_env":      "DOUBAO_COOKIES_JSON",
        "login_redirect_domains": ["passport.volcengine.com", "sso.volcengine.com", "passport.douyin.com"],
    },
    "deepseek": {
        "url":              "https://chat.deepseek.com",
        "input_selector":   "textarea, [contenteditable='true']",
        "submit_selector":  "button[class*='send'], button[aria-label*='Send'], button[aria-label*='send']",
        "response_selector":".ds-markdown, [class*='message-content'] .markdown, [class*='message'] .markdown",
        "wait_for_done":    "textarea:not([disabled])",
        "stream_cursor_selector": "[class*='loading'], [class*='typing']",
        "response_timeout": 90_000,
        "requires_login":   True,
        "cookies_env":      "DEEPSEEK_COOKIES_JSON",
        "login_redirect_domains": ["login.deepseek.com"],
    },
    "zhipu": {
        "url":              "https://chatglm.cn",
        "input_selector":   "textarea",
        "submit_selector":  "button.send-button",
        "response_selector":".chat-message.assistant .content",
        "wait_for_done":    "button.send-button:not([disabled])",
        "response_timeout": 90_000,
        "requires_login":   True,
    },
}


# ─── 主执行器 ─────────────────────────────────────────────────────────────────

class QueryExecutor:
    def __init__(
        self,
        account_pool: AccountPool,
        proxy_pool: ProxyPool,
        captcha_solver: CaptchaSolver,
    ):
        self.account_pool  = account_pool
        self.proxy_pool    = proxy_pool
        self.captcha_solver = captcha_solver

    async def execute(self, query: Query) -> Optional[LLMResponse]:
        """
        执行单条 Query：
        1. 选账号 & 代理
        2. 启动 Camoufox 浏览器（带指纹异化）
        3. 注入 cookies（跳过登录）
        4. 发送查询，等待响应
        5. 上报结果，持久化 cookies
        """
        llm = query.target_llm
        config = LLM_CONFIG.get(llm)
        if not config:
            logger.error(f"Unknown LLM: {llm}")
            return None

        # 1. 获取账号 & 代理
        country = query.profile.country_code if query.profile else None
        account = await self.account_pool.acquire(llm, country)
        proxy   = await self.proxy_pool.acquire(llm, country)

        if not account:
            logger.error(f"No account available for {llm}")
            return None

        # 构建 Camoufox 参数
        browser_profile = account.profile.browser_profile if account.profile else None
        camoufox_kwargs = _build_camoufox_kwargs(browser_profile, proxy)
        browser = None
        context = None
        page = None
        camoufox_ctx = None

        try:
            camoufox_ctx = AsyncCamoufox(**camoufox_kwargs)
            browser = await camoufox_ctx.__aenter__()
            if True:
                context: BrowserContext = await _prepare_context(browser, account, config)
                await install_resource_blocker(context)
                page: Page = await context.new_page()

                response_text = await self._run_query(page, config, query.query_text)

                if response_text:
                    # 持久化 cookies
                    cookies = await context.cookies()
                    await self.account_pool.save_cookies(account.id, json.dumps(cookies))

                    # 截图存档
                    screenshot_path = await _save_screenshot(page, query.id)

                    await self.account_pool.report_success(account.id)
                    if proxy:
                        await self.proxy_pool.report_success(proxy.id)

                    return LLMResponse(
                        query_id=query.id,
                        raw_text=response_text,
                        screenshot_path=str(screenshot_path),
                        collected_at=datetime.utcnow(),
                    )
                else:
                    await self.account_pool.report_failure(account.id, reason="no_response")
                    return None

        except Exception as e:
            err = str(e).lower()
            is_ban = any(k in err for k in ["banned", "blocked", "suspended", "403"])
            reason = "ban" if is_ban else "exception"
            logger.exception(f"Query {query.id} failed: {e}")

            await self.account_pool.report_failure(account.id, reason=reason, is_ban=is_ban)
            if proxy:
                await self.proxy_pool.report_failure(proxy.id, ban=is_ban)
            return None
        finally:
            await cleanup_browser_resources(
                page=page,
                context=context,
                browser=browser,
                camoufox_ctx=camoufox_ctx,
            )

    async def _run_query(
        self, page: Page, config: dict, query_text: str
    ) -> Optional[str]:
        """页面操作：导航 → 处理验证码 → 输入 → 等待响应"""

        await page.goto(config["url"], wait_until="domcontentloaded")
        await pre_query_pause()

        # 检测是否跳转到登录页（cookie 过期或无效）
        login_domains = config.get("login_redirect_domains", [])
        if login_domains:
            current_url = page.url
            if any(d in current_url for d in login_domains):
                logger.warning(f"Redirected to login page: {current_url}, cookies may be expired")
                return None

        # 检测 & 处理验证码
        captcha_ok = await detect_and_solve(page, self.captcha_solver)
        if not captcha_ok:
            logger.warning("Captcha not solved, aborting")
            return None

        # 等待输入框出现
        try:
            await page.wait_for_selector(config["input_selector"], timeout=15_000)
        except Exception:
            logger.warning(f"Input selector not found: {config['input_selector']}")
            return None

        # 模拟人类打字输入
        await human_type(page, config["input_selector"], query_text)
        await asyncio.sleep(random.uniform(0.5, 1.5))

        # 点击发送
        submit_btn = await page.query_selector(config["submit_selector"])
        if submit_btn:
            await submit_btn.click()
        else:
            await page.keyboard.press("Enter")

        await post_submit_wait()

        timeout = config.get("response_timeout", 90_000)

        # 等待流式光标消失（如果有）
        stream_cursor = config.get("stream_cursor_selector")
        if stream_cursor:
            try:
                await page.wait_for_selector(
                    stream_cursor, state="detached", timeout=timeout
                )
            except Exception:
                pass   # 有些情况不出现 cursor，不阻塞

        # 等待发送按钮重新可用（响应完毕的最终信号）
        try:
            await page.wait_for_selector(
                config["wait_for_done"], timeout=timeout
            )
        except Exception:
            logger.warning("Timeout waiting for response to complete")

        # 模拟阅读响应
        await human_scroll_read(page, min_sec=4.0, max_sec=10.0)

        # 提取响应文本
        response_el = await page.query_selector(config["response_selector"])
        if response_el:
            return await response_el.inner_text()

        # fallback：提取所有可见文本中最长的块
        logger.warning("Response selector not matched, using fallback extraction")
        return await page.evaluate("""
            () => {
                const els = document.querySelectorAll('p, li, div');
                let best = '';
                els.forEach(el => {
                    if (el.innerText && el.innerText.length > best.length) {
                        best = el.innerText;
                    }
                });
                return best;
            }
        """)


# ─── 辅助函数 ─────────────────────────────────────────────────────────────────

def _build_camoufox_kwargs(browser_profile, proxy) -> dict:
    kwargs: dict = {
        "headless":  True,
        "humanize":  True,           # Camoufox 内置人类行为注入
        "block_images": should_block_heavy_resources(),
    }

    if browser_profile:
        kwargs["os"] = _platform_to_os(browser_profile.platform)
        kwargs["screen"] = {
            "width":  browser_profile.viewport_width,
            "height": browser_profile.viewport_height,
        }
        if browser_profile.language:
            kwargs["locale"] = browser_profile.language
        if browser_profile.timezone:
            kwargs["timezone"] = browser_profile.timezone

    if proxy:
        kwargs["proxy"] = {"server": proxy.proxy_url}

    return kwargs


def _platform_to_os(platform: str) -> str:
    mapping = {"Win32": "windows", "MacIntel": "macos", "Linux": "linux"}
    return mapping.get(platform, "windows")


async def _prepare_context(browser, account: LLMAccount, config: dict = None) -> BrowserContext:
    """创建浏览器上下文，注入已保存的 cookies（免登录）"""
    context = await browser.new_context()

    cookies_loaded = False
    if account.cookies_json:
        try:
            cookies = json.loads(account.cookies_json)
            await context.add_cookies(cookies)
            logger.info(f"Loaded {len(cookies)} cookies for account {account.id}")
            cookies_loaded = True
        except Exception as e:
            logger.warning(f"Failed to load cookies: {e}")

    # 如果数据库无 cookies，尝试从环境变量加载（适用于豆包等国内 LLM 手动导出 cookie 的场景）
    if not cookies_loaded and config:
        cookies_env = config.get("cookies_env")
        if cookies_env:
            raw = os.getenv(cookies_env, "").strip()
            if raw:
                try:
                    cookies = json.loads(raw)
                    await context.add_cookies(cookies)
                    logger.info(f"Loaded {len(cookies)} cookies from env {cookies_env}")
                except Exception as e:
                    logger.warning(f"Failed to load cookies from {cookies_env}: {e}")

    return context


async def _save_screenshot(page: Page, query_id: int) -> Path:
    path = SCREENSHOT_DIR / f"query_{query_id}_{int(datetime.utcnow().timestamp())}.png"
    await page.screenshot(path=str(path), full_page=False)
    return path


# asyncio 需要在模块顶层 import
import asyncio  # noqa: E402 — must be after type annotations
