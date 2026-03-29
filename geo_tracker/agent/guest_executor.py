"""
无账号浏览器执行器（Guest Mode）
- 使用 Playwright 直接访问 LLM 网站，无需账号
- 支持 ChatGPT、Gemini、Perplexity、Kimi、Doubao、DeepSeek 等
- Gemini 支持通过 GEMINI_COOKIES_JSON 环境变量注入 Google session cookie
"""
from __future__ import annotations

import asyncio
import json
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
        "response_selector": "[data-message-author-role='assistant'] .markdown, article, [class*='message']",
        "wait_after_submit": 25000,
        "load_wait":        8000,
        "requires_login":   False,
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
                        # Docker/headless 稳定性:
                        # --disable-gpu: 关闭 GPU 硬件加速
                        # --use-gl=swiftshader: 用软件 OpenGL (SwiftShader) 代替 GPU,
                        #   防止 ChatGPT/WebGL 密集页面因无 GPU 导致 Page crashed
                        # 注意: 不要加 --disable-software-rasterizer，否则无任何渲染后端会崩溃
                        "--disable-gpu",
                        "--use-gl=swiftshader",
                        "--no-zygote",
                        "--window-size=1920,1080",
                        "--disable-background-timer-throttling",
                        "--disable-backgrounding-occluded-windows",
                        "--disable-renderer-backgrounding",
                    ],
                )
                logger.info(f"[{llm}] 浏览器启动成功")

                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                    timezone_id="America/New_York",
                    ignore_https_errors=True,
                    bypass_csp=True,
                    reduced_motion="reduce",
                )

                # 注入 LLM 专属 cookies（如 GEMINI_COOKIES_JSON）
                cookies_env = config.get("cookies_env")
                if cookies_env:
                    cookies = _load_cookies_from_env(cookies_env)
                    if cookies:
                        await context.add_cookies(cookies)
                        logger.info(f"[{llm}] 已注入 {len(cookies)} 个 cookies")

                page_obj = await context.new_page()

                # 隐藏自动化特征
                await page_obj.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    delete navigator.__proto__.webdriver;
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => {
                            const p = [
                                {name:'Chrome PDF Plugin', filename:'internal-pdf-viewer', description:'Portable Document Format'},
                                {name:'Chrome PDF Viewer', filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai', description:''},
                                {name:'Native Client', filename:'internal-nacl-plugin', description:''}
                            ];
                            p.length = 3;
                            return p;
                        }
                    });
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                    Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
                    Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
                    window.chrome = {
                        runtime: { onMessage: {addListener:()=>{},removeListener:()=>{}}, sendMessage:()=>{} },
                        loadTimes: () => ({}), csi: () => ({})
                    };
                    // Hide headless indicators
                    Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 1});
                    Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
                    Object.defineProperty(screen, 'colorDepth', {get: () => 24});
                    Object.defineProperty(screen, 'pixelDepth', {get: () => 24});
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.query = (params) =>
                        params.name === 'notifications'
                            ? Promise.resolve({state: Notification.permission})
                            : originalQuery(params);
                """)

                # 对于 Gemini，先访问 google.com 建立 cookie
                if config.get("visit_google_first"):
                    try:
                        logger.info(f"[{llm}] 先访问 google.com 建立 cookie...")
                        await page_obj.goto("https://www.google.com", wait_until="domcontentloaded", timeout=30000)
                        await page_obj.wait_for_timeout(2000)
                        # 处理 Google consent 弹窗
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

                    # 优先等待输入框出现，最多等 load_wait 时间，避免固定等待
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
                        # 输入框未就绪时仍等待剩余时间
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
                                # 对于某些 LLM（如 Gemini），元素可能存在但报告为不可见，仍然尝试使用
                                logger.info(f"[{llm}] 输入框找到但报告为不可见，仍尝试使用: {sel}")
                                break
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

        # 点击输入框（force=True 绕开可见性检查）
        try:
            await input_el.click(force=True, timeout=5000)
        except:
            pass
        await page.wait_for_timeout(500)

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
            await page.wait_for_timeout(300)
            await page.keyboard.type(query_text, delay=30)

        await page.wait_for_timeout(800)

        # 提交：优先点击提交按钮，fallback 用 Enter
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
        if not submitted:
            await page.keyboard.press("Enter")
            logger.info(f"[{llm_name}] 通过 Enter 键提交")

        # 等待响应生成（分段等待，每隔一段检查是否已有内容）
        wait_total = cfg["wait_after_submit"]
        wait_interval = 5000  # 每 5 秒检查一次
        elapsed = 0
        response_selectors = [s.strip() for s in cfg["response_selector"].split(",") if s.strip()]

        while elapsed < wait_total:
            await page.wait_for_timeout(min(wait_interval, wait_total - elapsed))
            elapsed += wait_interval

            # 检测是否跳转到登录页
            current_url = page.url
            login_domains = cfg.get("login_redirect_domains", [])
            if any(d in current_url for d in login_domains):
                logger.warning(f"[{llm_name}] 检测到跳转到登录页: {current_url}，中止等待")
                await _save_screenshot(page, -1, f"{llm_name}_login_redirect")
                return ""

            # 提前检查是否已有响应内容（避免浪费剩余等待时间）
            for sel in response_selectors:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        txt = await el.inner_text()
                        if txt and len(txt.strip()) > 20:
                            logger.info(f"[{llm_name}] 响应内容提前就绪（{elapsed}ms），selector: {sel}")
                            break
                except Exception:
                    continue

        # 抓取响应文本
        try:
            # 优先尝试配置的 selectors
            for sel in response_selectors:
                try:
                    elements = await page.query_selector_all(sel)
                    if elements:
                        texts = []
                        for el in elements:
                            try:
                                txt = await el.inner_text()
                                if txt and txt.strip():
                                    texts.append(txt.strip())
                            except:
                                pass
                        combined = "\n".join(texts)
                        if len(combined) > 20:
                            logger.info(f"[{llm_name}] 通过 selector 提取响应: {sel} ({len(combined)} chars)")
                            return combined[-5000:]
                except Exception:
                    continue

            # fallback 1：拼接所有 <p> 标签文本（Gemini 响应通常是多段落）
            logger.warning(f"[{llm_name}] 响应选择器未匹配，使用 JS fallback 提取")
            await _save_html(page, -1, f"{llm_name}_extract_fail")
            js_text = await page.evaluate("""
                () => {
                    // 拼接所有段落文本（用 textContent 不受可见性影响）
                    const paras = [...document.querySelectorAll('p, li')];
                    const paraText = paras
                        .map(p => (p.textContent || '').trim())
                        .filter(t => t.length > 5)
                        .join('\\n');
                    if (paraText.length > 50) return paraText;

                    // fallback 2：取 body 全部文本的后半段
                    const bodyText = (document.body.textContent || document.body.innerText || '').trim();
                    if (bodyText.length > 100) return bodyText.slice(-4000);

                    return '';
                }
            """)
            if js_text and len(js_text) > 20:
                logger.info(f"[{llm_name}] JS fallback 提取成功 ({len(js_text)} chars)")
                return js_text[:5000]

            logger.warning(f"[{llm_name}] 所有提取方式均失败，当前 URL: {page.url}")
            return ""
        except Exception as e:
            logger.warning(f"[{llm_name}] 提取响应异常: {e}")
            return ""


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
        await page.screenshot(path=str(path), full_page=False)
        logger.info(f"截图已保存: {path}")
        return path
    except Exception as e:
        logger.warning(f"保存截图失败: {e}")
        return None
