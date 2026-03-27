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
        "input_selector":   "#prompt-textarea, [data-testid='prompt-textarea'], textarea, [role='textbox']",
        "submit_key":       "Enter",
        "response_selector": "[data-message-author-role='assistant'] .markdown, article, [class*='message']",
        "wait_after_submit": 25000,
        "load_wait":        8000,
        "requires_login":   False,
    },
    "gemini": {
        "url":              "https://gemini.google.com",
        "input_selector":   "textarea, [contenteditable='true'], [role='textbox'], input[type='text'], rich-textarea",
        "submit_key":       "Enter",
        "response_selector": "message-content, .response-container, model-response, [class*='message'], [class*='content']",
        "wait_after_submit": 25000,
        "load_wait":        60000,
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
        "input_selector":   "textarea, [contenteditable='true']",
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

    def __init__(self, proxy_url: Optional[str] = None):
        """
        Args:
            proxy_url: 代理 URL，用于访问国际 LLM
        """
        self.proxy_url = proxy_url or os.getenv("CLASH_PROXY_URL") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")

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

        page_obj = None
        browser = None

        try:
            async with async_playwright() as p:
                logger.info(f"[{llm}] 启动浏览器...")
                browser = await p.chromium.launch(
                    headless=True,
                    proxy=proxy_cfg,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-web-security",
                        "--disable-features=IsolateOrigins,site-per-process",
                        "--disable-gpu",
                        "--disable-software-rasterizer",
                    ],
                )
                logger.info(f"[{llm}] 浏览器启动成功")

                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                    ignore_https_errors=True,
                    bypass_csp=True,
                    reduced_motion="reduce",
                )
                page_obj = await context.new_page()

                # 隐藏 webdriver 特征
                await page_obj.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                    window.chrome = { runtime: {} };
                """)

                # 打开页面
                logger.info(f"[{llm}] 打开: {config['url']} (proxy: {self.proxy_url if use_proxy else 'none'})")
                try:
                    await page_obj.goto(config["url"], wait_until="commit", timeout=90000)
                    await page_obj.wait_for_timeout(config.get("load_wait", 8000))
                    title = await page_obj.title()
                    logger.info(f"[{llm}] 页面标题: {title}")
                except Exception as e:
                    logger.error(f"[{llm}] 页面加载失败: {e}")
                    if page_obj:
                        try:
                            await _save_screenshot(page_obj, query.id, f"{llm}_load_error")
                        except:
                            pass
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
                            # 检查是否可见
                            is_visible = await input_el.is_visible()
                            if is_visible:
                                logger.info(f"[{llm}] 输入框找到且可见: {sel}")
                                break
                            else:
                                logger.debug(f"[{llm}] 选择器找到但不可见: {sel}")
                                input_el = None
                    except Exception as e:
                        logger.debug(f"[{llm}] 选择器失败: {sel} - {e}")
                        continue

                if not input_el:
                    logger.error(f"[{llm}] 找不到输入框")
                    if page_obj:
                        await _save_screenshot(page_obj, query.id, f"{llm}_no_input")
                        # 也保存页面内容用于调试
                        try:
                            content = await page_obj.content()
                            content_path = SCREENSHOT_DIR / f"query_{query.id}_{llm}_content.html"
                            content_path.write_text(content[:50000], encoding='utf-8')
                            logger.info(f"[{llm}] 页面内容已保存: {content_path}")
                        except Exception as e:
                            logger.warning(f"保存页面内容失败: {e}")
                    return None

                # 执行查询
                resp_text = await self._browser_query(page_obj, config, query.query_text, llm, input_el)

                if resp_text:
                    # 截图存档
                    screenshot_path = await _save_screenshot(page_obj, query.id, llm)

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

    async def _browser_query(
        self, page: Page, cfg: dict, query_text: str, llm_name: str, input_el=None
    ) -> str:
        """在已打开的页面里输入 query，等待响应，抓取文本"""
        if input_el is None:
            input_el = await page.wait_for_selector(cfg["input_selector"].split(",")[0], timeout=10000)

        # 点击输入框
        try:
            await input_el.click(timeout=5000)
        except:
            pass
        await page.wait_for_timeout(500)

        # contenteditable div 不支持 fill()，用 Ctrl+A 清空后直接 type()
        if cfg.get("contenteditable"):
            try:
                await input_el.focus()
                await page.keyboard.press("Control+a")
                await page.wait_for_timeout(100)
                await page.keyboard.press("Delete")
            except:
                pass
        else:
            try:
                await input_el.fill("")
            except:
                pass

        await page.wait_for_timeout(300)
        await page.keyboard.type(query_text, delay=30)
        await page.wait_for_timeout(800)

        # 提交
        await page.keyboard.press("Enter")
        logger.info(f"[{llm_name}] 已提交 Query，等待响应…")

        # 等待响应生成
        await page.wait_for_timeout(cfg["wait_after_submit"])

        # 抓取响应文本
        try:
            elements = await page.query_selector_all(cfg["response_selector"])
            if elements:
                texts = []
                for el in elements:
                    try:
                        txt = await el.inner_text()
                        if txt and txt.strip():
                            texts.append(txt)
                    except:
                        pass
                if texts:
                    return "\n".join(texts)[-5000:]

            # fallback：取页面主体文本
            logger.warning(f"[{llm_name}] 响应选择器未匹配，使用 fallback 提取")
            body_text = await page.inner_text("body")
            return body_text[:5000] if body_text else ""
        except Exception as e:
            logger.warning(f"[{llm_name}] 提取响应异常: {e}")
            try:
                body_text = await page.inner_text("body")
                return body_text[:5000] if body_text else ""
            except:
                return ""


async def _save_screenshot(page: Page, query_id: int, suffix: str = "") -> Optional[Path]:
    """保存截图"""
    try:
        timestamp = int(datetime.utcnow().timestamp())
        filename = f"query_{query_id}_{suffix}_{timestamp}.png" if suffix else f"query_{query_id}_{timestamp}.png"
        path = SCREENSHOT_DIR / filename
        await page.screenshot(path=str(path), full_page=False)
        logger.info(f"截图已保存: {path}")
        return path
    except Exception as e:
        logger.warning(f"保存截图失败: {e}")
        return None
