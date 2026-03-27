"""
无账号浏览器执行器（Guest Mode）
- 使用 Playwright 直接访问 LLM 网站，无需账号
- 支持 ChatGPT、Gemini、Perplexity、Kimi、Doubao、DeepSeek 等
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, BrowserContext, Page

from geo_tracker.db.models import LLMResponse, Query, QueryStatus

logger = logging.getLogger(__name__)

SCREENSHOT_DIR = Path(os.getenv("SCREENSHOT_DIR", "/data/screenshots"))
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# 各 LLM 的浏览器操作配置（无账号 guest 模式）
GUEST_LLM_CONFIG = {
    "chatgpt": {
        "url":              "https://chatgpt.com",
        "input_selector":   "#prompt-textarea, [data-testid='prompt-textarea'], textarea",
        "submit_key":       "Enter",
        "response_selector": "[data-message-author-role='assistant'] .markdown, article",
        "wait_after_submit": 20000,
        "load_wait":        5000,
        "requires_login":   False,
    },
    "gemini": {
        "url":              "https://gemini.google.com",
        "input_selector":   "rich-textarea .ql-editor, textarea, [contenteditable='true']",
        "submit_key":       "Enter",
        "response_selector": "message-content, .response-container, model-response",
        "wait_after_submit": 20000,
        "load_wait":        5000,
        "requires_login":   False,
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
        "input_selector":   ".chat-input-editor",
        "submit_key":       "Enter",
        "response_selector": "[class*='segment-content'], [class*='message-content'], .chat-message",
        "wait_after_submit": 20000,
        "load_wait":        8000,
        "requires_login":   False,
        "contenteditable":  True,
    },
    "doubao": {
        "url":              "https://www.doubao.com/chat",
        "input_selector":   "textarea",
        "submit_key":       "Enter",
        "response_selector": "[class*='message'], [class*='content']",
        "wait_after_submit": 20000,
        "load_wait":        10000,
        "requires_login":   False,
    },
    "deepseek": {
        "url":              "https://chat.deepseek.com",
        "input_selector":   "textarea, [contenteditable=true], input[type=text]",
        "submit_key":       "Enter",
        "response_selector": "[class*='message'], [class*='content'], .markdown",
        "wait_after_submit": 20000,
        "load_wait":        8000,
        "requires_login":   False,
    },
    "claude": {
        "url":              "https://claude.ai",
        "input_selector":   '[contenteditable="true"], textarea',
        "submit_key":       "Enter",
        "response_selector": ".claude-message .prose, [class*='message'], [class*='content']",
        "wait_after_submit": 20000,
        "load_wait":        8000,
        "requires_login":   True,  # Claude 通常需要登录
    },
    "grok": {
        "url":              "https://x.com/i/grok",
        "input_selector":   "textarea",
        "submit_key":       "Enter",
        "response_selector": "[data-testid='grok-response'] .prose, [class*='message']",
        "wait_after_submit": 20000,
        "load_wait":        8000,
        "requires_login":   True,  # Grok 需要 X/Twitter 账号
    },
    "zhipu": {
        "url":              "https://chatglm.cn",
        "input_selector":   "textarea",
        "submit_key":       "Enter",
        "response_selector": ".chat-message.assistant .content, [class*='message']",
        "wait_after_submit": 20000,
        "load_wait":        8000,
        "requires_login":   True,  # 智谱通常需要登录
    },
}

# 国内 LLM 列表（直连，不走代理）
DOMESTIC_LLMS = {"kimi", "doubao", "deepseek", "zhipu"}


class GuestQueryExecutor:
    """无账号查询执行器"""

    def __init__(self, proxy_url: Optional[str] = None):
        """
        Args:
            proxy_url: 代理 URL，用于访问国际 LLM
        """
        self.proxy_url = proxy_url or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")

    async def execute(self, query: Query) -> Optional[LLMResponse]:
        """
        执行单条查询（无账号模式）

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

        # 确定是否使用代理
        use_proxy = self.proxy_url and llm not in DOMESTIC_LLMS
        proxy_cfg = {"server": self.proxy_url} if use_proxy else None

        if use_proxy:
            logger.info(f"[{llm}] 使用代理: {self.proxy_url}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                proxy=proxy_cfg,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-web-security",
                ],
            )

            try:
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1440, "height": 900},
                    locale="en-US",
                    ignore_https_errors=True,
                )
                page = await context.new_page()

                # 隐藏 webdriver 特征
                await page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )

                # 打开页面
                logger.info(f"[{llm}] 打开: {config['url']}")
                try:
                    await page.goto(config["url"], wait_until="domcontentloaded", timeout=45000)
                    await page.wait_for_timeout(config.get("load_wait", 4000))
                    logger.debug(f"[{llm}] 页面标题: {await page.title()}")
                except Exception as e:
                    logger.error(f"[{llm}] 页面加载失败: {e}")
                    return None

                # 尝试找输入框
                input_el = None
                for sel in config["input_selector"].split(", "):
                    try:
                        input_el = await page.wait_for_selector(sel.strip(), timeout=8000, state="visible")
                        logger.debug(f"[{llm}] 输入框找到: {sel.strip()}")
                        break
                    except Exception:
                        continue

                if not input_el:
                    logger.error(f"[{llm}] 找不到输入框")
                    await _save_screenshot(page, query.id, f"{llm}_no_input")
                    return None

                # 执行查询
                resp_text = await self._browser_query(page, config, query.query_text, llm, input_el)

                if resp_text:
                    # 截图存档
                    screenshot_path = await _save_screenshot(page, query.id, llm)

                    return LLMResponse(
                        query_id=query.id,
                        raw_text=resp_text,
                        screenshot_path=str(screenshot_path) if screenshot_path else None,
                        response_time_ms=0,
                        llm_version=f"guest_{llm}",
                        collected_at=datetime.utcnow(),
                    )
                else:
                    logger.error(f"[{llm}] 未能获取响应")
                    return None

            finally:
                await browser.close()

    async def _browser_query(
        self, page: Page, cfg: dict, query_text: str, llm_name: str, input_el=None
    ) -> str:
        """在已打开的页面里输入 query，等待响应，抓取文本"""
        if input_el is None:
            input_el = await page.wait_for_selector(cfg["input_selector"].split(", ")[0], timeout=10000)
        await input_el.click()
        await page.wait_for_timeout(500)

        # contenteditable div 不支持 fill()，用 Ctrl+A 清空后直接 type()
        if cfg.get("contenteditable"):
            await page.keyboard.press("Control+a")
            await page.keyboard.press("Delete")
        else:
            await input_el.fill("")
        await page.keyboard.type(query_text, delay=25)
        await page.wait_for_timeout(500)

        # 提交
        await page.keyboard.press("Enter")
        logger.debug(f"[{llm_name}] 已提交 Query，等待响应…")

        # 等待响应生成
        await page.wait_for_timeout(cfg["wait_after_submit"])

        # 抓取响应文本
        try:
            elements = await page.query_selector_all(cfg["response_selector"])
            if elements:
                texts = [await el.inner_text() for el in elements]
                return "\n".join(t for t in texts if t.strip())[-5000:]  # 最多保留 5000 字符
            else:
                # fallback：取页面主体文本
                return (await page.inner_text("body"))[:5000]
        except Exception:
            return (await page.inner_text("body"))[:5000]


async def _save_screenshot(page: Page, query_id: int, suffix: str = "") -> Optional[Path]:
    """保存截图"""
    try:
        timestamp = int(datetime.utcnow().timestamp())
        filename = f"query_{query_id}_{suffix}_{timestamp}.png" if suffix else f"query_{query_id}_{timestamp}.png"
        path = SCREENSHOT_DIR / filename
        await page.screenshot(path=str(path), full_page=False)
        return path
    except Exception as e:
        logger.warning(f"保存截图失败: {e}")
        return None
