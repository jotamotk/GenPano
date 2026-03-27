"""
无账号浏览器执行器（Guest Mode）
- 使用 Playwright 直接访问 LLM 网站，无需账号
- 支持 ChatGPT、Gemini、Perplexity、Kimi、Doubao、DeepSeek 等
- 反爬虫优化：随机 UA、随机打字、鼠标轨迹、指纹随机化
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, BrowserContext, Page

from geo_tracker.db.models import LLMResponse, Query, QueryStatus

logger = logging.getLogger(__name__)

SCREENSHOT_DIR = Path(os.getenv("SCREENSHOT_DIR", "/data/screenshots"))
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# 随机 User-Agent 池
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]


def random_delay(min_ms: int = 50, max_ms: int = 150) -> float:
    """随机延迟（毫秒转秒）"""
    return random.uniform(min_ms, max_ms) / 1000


def random_type_delay() -> float:
    """随机打字延迟：20-80ms，模拟人类打字节奏"""
    base = random.uniform(20, 60)
    if random.random() < 0.1:
        base += random.uniform(100, 300)
    return base / 1000


async def human_like_click(page: Page, element):
    """模拟人类点击：先移动鼠标，再点击"""
    try:
        box = await element.bounding_box()
        if box:
            start_x = random.randint(0, int(box["x"] + box["width"]))
            start_y = random.randint(0, int(box["y"] + box["height"]))
            target_x = box["x"] + box["width"] / 2 + random.uniform(-5, 5)
            target_y = box["y"] + box["height"] / 2 + random.uniform(-5, 5)

            await page.mouse.move(start_x, start_y)
            await asyncio.sleep(random_delay(100, 300))

            steps = random.randint(3, 6)
            for i in range(steps):
                progress = (i + 1) / steps
                x = start_x + (target_x - start_x) * progress + random.uniform(-2, 2)
                y = start_y + (target_y - start_y) * progress + random.uniform(-2, 2)
                await page.mouse.move(x, y)
                await asyncio.sleep(random_delay(20, 50))

            await asyncio.sleep(random_delay(100, 200))
            await page.mouse.click(target_x, target_y)
        else:
            await element.click()
    except Exception:
        try:
            await element.click()
        except Exception:
            pass


# 各 LLM 的浏览器操作配置
GUEST_LLM_CONFIG = {
    "chatgpt": {
        "url":              "https://chatgpt.com",
        "input_selector":   "#prompt-textarea, [data-testid='prompt-textarea'], textarea, [role='textbox']",
        "submit_key":       "Enter",
        "response_selector": "[data-message-author-role='assistant'] .markdown, article, [class*='message']",
        "wait_after_submit": 25000,
        "load_wait":        10000,
        "requires_login":   False,
    },
    "gemini": {
        "url":              "https://gemini.google.com",
        "input_selector":   "textarea, [contenteditable='true'], [role='textbox'], input[type='text'], rich-textarea",
        "submit_key":       "Enter",
        "response_selector": ".response-content, [class*='response'], [class*='message'], [class*='content'], body",
        "wait_after_submit": 60000,
        "load_wait":        45000,
        "requires_login":   False,
    },
    "perplexity": {
        "url":              "https://www.perplexity.ai",
        "input_selector":   "textarea, [placeholder*='Ask'], input[type='text']",
        "submit_key":       "Enter",
        "response_selector": ".prose, [class*='answer'], [class*='response']",
        "wait_after_submit": 20000,
        "load_wait":        8000,
        "requires_login":   False,
    },
    "kimi": {
        "url":              "https://kimi.moonshot.cn",
        "input_selector":   ".chat-input-editor, textarea, [contenteditable='true']",
        "submit_key":       "Enter",
        "response_selector": "[class*='segment-content'], [class*='message-content'], .chat-message",
        "wait_after_submit": 25000,
        "load_wait":        12000,
        "requires_login":   False,
        "contenteditable":  True,
    },
    "doubao": {
        "url":              "https://www.doubao.com/chat",
        "input_selector":   "textarea, [contenteditable='true']",
        "submit_key":       "Enter",
        "response_selector": "[class*='message'], [class*='content']",
        "wait_after_submit": 25000,
        "load_wait":        15000,
        "requires_login":   False,
    },
    "deepseek": {
        "url":              "https://chat.deepseek.com",
        "input_selector":   "textarea, [contenteditable=true], input[type=text]",
        "submit_key":       "Enter",
        "response_selector": "[class*='message'], [class*='content'], .markdown",
        "wait_after_submit": 25000,
        "load_wait":        12000,
        "requires_login":   False,
    },
    "claude": {
        "url":              "https://claude.ai",
        "input_selector":   '[contenteditable="true"], textarea',
        "submit_key":       "Enter",
        "response_selector": ".claude-message .prose, [class*='message'], [class*='content']",
        "wait_after_submit": 25000,
        "load_wait":        12000,
        "requires_login":   True,
    },
    "grok": {
        "url":              "https://x.com/i/grok",
        "input_selector":   "textarea",
        "submit_key":       "Enter",
        "response_selector": "[data-testid='grok-response'] .prose, [class*='message']",
        "wait_after_submit": 25000,
        "load_wait":        12000,
        "requires_login":   True,
    },
    "zhipu": {
        "url":              "https://chatglm.cn",
        "input_selector":   "textarea",
        "submit_key":       "Enter",
        "response_selector": ".chat-message.assistant .content, [class*='message']",
        "wait_after_submit": 25000,
        "load_wait":        12000,
        "requires_login":   True,
    },
}

# 国内 LLM 列表（直连，不走代理）
DOMESTIC_LLMS = {"kimi", "doubao", "deepseek", "zhipu"}


class GuestQueryExecutor:
    """无账号查询执行器 - 优化反爬虫版"""

    def __init__(self, proxy_url: Optional[str] = None):
        self.proxy_url = proxy_url or os.getenv("CLASH_PROXY_URL") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")

    async def execute(self, query: Query) -> Optional[LLMResponse]:
        llm = query.target_llm
        config = GUEST_LLM_CONFIG.get(llm)
        if not config:
            logger.error(f"Unknown LLM: {llm}")
            return None

        use_proxy = self.proxy_url and llm not in DOMESTIC_LLMS
        proxy_cfg = {"server": self.proxy_url} if use_proxy else None

        if use_proxy:
            logger.info(f"[{llm}] 使用代理: {self.proxy_url}")

        page_obj = None
        browser = None

        try:
            async with async_playwright() as p:
                logger.info(f"[{llm}] 启动浏览器...")

                user_agent = random.choice(USER_AGENTS)

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
                        "--disable-infobars",
                        "--disable-notifications",
                        "--disable-popup-blocking",
                        "--disable-save-password-bubble",
                        "--disable-translate",
                        "--no-first-run",
                        "--no-default-browser-check",
                    ],
                )
                logger.info(f"[{llm}] 浏览器启动成功")

                viewport_width = random.choice([1920, 1920, 1920, 1440, 1536])
                viewport_height = random.choice([1080, 1080, 1080, 900, 960])

                context = await browser.new_context(
                    user_agent=user_agent,
                    viewport={"width": viewport_width, "height": viewport_height},
                    locale="en-US" if llm not in DOMESTIC_LLMS else "zh-CN",
                    timezone_id="Asia/Shanghai",
                    ignore_https_errors=True,
                    bypass_csp=True,
                    reduced_motion="reduce",
                    permissions=["geolocation"],
                    color_scheme=random.choice(["light", "dark", "no-preference"]),
                )

                stealth_js = """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [
                        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                        { name: 'Native Client', filename: 'internal-nacl-plugin' }
                    ]
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en', 'zh-CN']
                });
                window.chrome = {
                    runtime: {},
                    loadTimes: () => {},
                    csi: () => {}
                };
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) =>
                    parameters.name === 'notifications'
                        ? Promise.resolve({ state: Notification.permission })
                        : originalQuery(parameters);
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    if (parameter === 37445) return 'Intel Inc.';
                    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                    return getParameter.call(this, parameter);
                };
                const toDataURL = HTMLCanvasElement.prototype.toDataURL;
                HTMLCanvasElement.prototype.toDataURL = function(...args) {
                    const result = toDataURL.apply(this, args);
                    if (result && result.length > 100) {
                        return result.replace(/.(?=.{0,3}$)/, () => String.fromCharCode(Math.random() * 256));
                    }
                    return result;
                };
                delete window.__playwright;
                delete window.__PW_inspect;
                delete window.__PW_recorder;
                """
                await context.add_init_script(stealth_js)

                page_obj = await context.new_page()

                logger.info(f"[{llm}] 打开: {config['url']}")
                try:
                    await page_obj.goto("about:blank", wait_until="commit", timeout=30000)
                    await asyncio.sleep(random_delay(500, 1500))

                    # 先尝试用 commit，不等待 networkidle（避免超时）
                    try:
                        await page_obj.goto(config["url"], wait_until="commit", timeout=60000)
                    except Exception:
                        # 如果 commit 也超时，直接继续尝试找元素
                        logger.warning(f"[{llm}] 页面加载超时，继续尝试找输入框")

                    # 等待一段时间让页面渲染
                    await asyncio.sleep(config.get("load_wait", 10000) / 1000)

                    try:
                        title = await page_obj.title()
                        logger.info(f"[{llm}] 页面标题: {title}")
                    except Exception:
                        logger.warning(f"[{llm}] 无法获取页面标题")
                except Exception as e:
                    logger.error(f"[{llm}] 页面加载异常: {e}")
                    # 即使页面加载失败，也继续尝试找输入框（可能部分加载成功）

                input_el = None
                selectors = [s.strip() for s in config["input_selector"].split(",")]
                logger.info(f"[{llm}] 尝试选择器: {selectors}")

                for sel in selectors:
                    if not sel:
                        continue
                    try:
                        logger.debug(f"[{llm}] 尝试选择器: {sel}")
                        input_el = await page_obj.wait_for_selector(sel, timeout=15000, state="attached")
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

                resp_text = await self._browser_query(page_obj, config, query.query_text, llm, input_el)

                if resp_text and len(resp_text.strip()) > 5:
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
                    logger.error(f"[{llm}] 未能获取有效响应 (resp_len={len(resp_text) if resp_text else 0})")
                    if page_obj:
                        await _save_screenshot(page_obj, query.id, f"{llm}_no_response")
                    return None

        except Exception as e:
            logger.exception(f"[{llm}] 执行异常: {e}")
            if page_obj:
                try:
                    await _save_screenshot(page_obj, query.id, f"{llm}_exception")
                except Exception:
                    pass
            return None
        finally:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass

    async def _browser_query(
        self, page: Page, cfg: dict, query_text: str, llm_name: str, input_el=None
    ) -> str:
        if input_el is None:
            input_el = await page.wait_for_selector(cfg["input_selector"].split(",")[0], timeout=15000)

        await human_like_click(page, input_el)
        await asyncio.sleep(random_delay(500, 1500))

        if cfg.get("contenteditable"):
            try:
                await input_el.focus()
                await asyncio.sleep(random_delay(100, 300))
                await page.keyboard.press("Control+a")
                await asyncio.sleep(random_delay(100, 200))
                await page.keyboard.press("Delete")
                await asyncio.sleep(random_delay(200, 500))
            except Exception:
                pass
        else:
            try:
                await input_el.fill("")
                await asyncio.sleep(random_delay(200, 400))
            except Exception:
                pass

        for char in query_text:
            await page.keyboard.type(char, delay=random_type_delay() * 1000)
            if random.random() < 0.05:
                await asyncio.sleep(random_delay(200, 500))

        await asyncio.sleep(random_delay(500, 1500))

        await page.keyboard.press("Enter")
        logger.info(f"[{llm_name}] 已提交 Query，等待响应…")

        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass

        await asyncio.sleep(cfg["wait_after_submit"] / 1000)

        try:
            elements = await page.query_selector_all(cfg["response_selector"])
            if elements:
                texts = []
                for el in elements:
                    try:
                        txt = await el.inner_text()
                        if txt and txt.strip():
                            texts.append(txt)
                    except Exception:
                        pass
                if texts:
                    return "\n".join(texts)[-5000:]

            logger.warning(f"[{llm_name}] 响应选择器未匹配，使用 fallback 提取")
            body_text = await page.inner_text("body")
            return body_text[:5000] if body_text else ""
        except Exception as e:
            logger.warning(f"[{llm_name}] 提取响应异常: {e}")
            try:
                body_text = await page.inner_text("body")
                return body_text[:5000] if body_text else ""
            except Exception:
                return ""


async def _save_screenshot(page: Page, query_id: int, suffix: str = "") -> Optional[Path]:
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
