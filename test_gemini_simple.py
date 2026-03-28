"""
Simple Gemini test script - standalone
诊断 + 修复版：处理 consent 弹窗、stealth、等待策略
"""
import asyncio
import os
import random
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright, Page

# Random User-Agent pool
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

GEMINI_CONFIG = {
    "url": "https://gemini.google.com/app",
    "input_selector": "rich-textarea .ql-editor, rich-textarea, [contenteditable='true'], textarea",
    "submit_key": "Enter",
    "response_selector": "message-content .markdown, model-response .markdown, .response-content, [class*='response']",
    "wait_after_submit": 60000,
    "load_wait": 30000,
}


def random_delay(min_ms: int = 50, max_ms: int = 150) -> float:
    return random.uniform(min_ms, max_ms) / 1000


async def handle_consent(page: Page):
    """处理 Google Cookie Consent 弹窗"""
    consent_selectors = [
        # Google consent iframe 内的按钮
        'button:has-text("Accept all")',
        'button:has-text("I agree")',
        'button:has-text("Accept")',
        'button:has-text("Agree")',
        'button:has-text("全部接受")',
        'button:has-text("同意")',
        'button:has-text("Got it")',
        # GDPR consent
        '[aria-label="Accept all"]',
        '[data-consent="accept"]',
        'form[action*="consent"] button',
    ]

    # 先检查主页面上的 consent 按钮
    for sel in consent_selectors:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                print(f"  -> Found consent button: {sel}")
                await btn.click()
                await page.wait_for_timeout(2000)
                return True
        except Exception:
            continue

    # 检查 iframe 中的 consent（Google 常用）
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        for sel in consent_selectors:
            try:
                btn = await frame.query_selector(sel)
                if btn:
                    print(f"  -> Found consent button in iframe: {sel}")
                    await btn.click()
                    await page.wait_for_timeout(2000)
                    return True
            except Exception:
                continue

    return False


async def dump_page_debug(page: Page, label: str):
    """保存调试信息"""
    timestamp = int(datetime.utcnow().timestamp())

    # 截图
    screenshot_path = Path(f"gemini_debug_{label}_{timestamp}.png")
    await page.screenshot(path=str(screenshot_path), full_page=False)
    print(f"  Screenshot: {screenshot_path}")

    # 保存 HTML
    try:
        content = await page.content()
        html_path = Path(f"gemini_debug_{label}_{timestamp}.html")
        html_path.write_text(content[:100000], encoding="utf-8")
        print(f"  HTML saved: {html_path} ({len(content)} bytes)")
    except Exception as e:
        print(f"  Failed to save HTML: {e}")

    # 打印页面信息
    try:
        title = await page.title()
        url = page.url
        print(f"  Title: {title}")
        print(f"  URL: {url}")
    except Exception:
        pass

    # 检查 iframe 数量
    frames = page.frames
    print(f"  Frames: {len(frames)}")
    for i, frame in enumerate(frames):
        print(f"    Frame {i}: {frame.url[:100]}")


async def test_gemini():
    proxy_url = os.getenv("CLASH_PROXY_URL", "http://clash:7890")
    print(f"Using proxy: {proxy_url}")

    async with async_playwright() as p:
        user_agent = random.choice(USER_AGENTS)
        print(f"Using UA: {user_agent}")

        browser = await p.chromium.launch(
            headless=False,
            proxy={"server": proxy_url},
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                # 额外的反检测
                "--disable-infobars",
                "--window-size=1920,1080",
            ],
        )

        context = await browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
            ignore_https_errors=True,
            bypass_csp=True,
            # 添加更真实的权限
            permissions=["geolocation"],
            geolocation={"latitude": 40.7128, "longitude": -74.006},
        )

        # 更全面的 stealth 注入
        stealth_js = """
        // 隐藏 webdriver
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        delete navigator.__proto__.webdriver;

        // 真实的 plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                const plugins = [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                    { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
                ];
                plugins.length = 3;
                return plugins;
            }
        });

        // languages
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

        // chrome 对象
        window.chrome = {
            runtime: {
                onMessage: { addListener: () => {}, removeListener: () => {} },
                sendMessage: () => {},
                connect: () => ({ onMessage: { addListener: () => {} }, postMessage: () => {}, disconnect: () => {} }),
            },
            loadTimes: () => ({}),
            csi: () => ({}),
        };

        // 隐藏 Playwright 特征
        Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
        Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

        // 伪装 permissions API
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) =>
            parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : originalQuery(parameters);

        // WebGL vendor
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Intel Inc.';
            if (parameter === 37446) return 'Intel Iris OpenGL Engine';
            return getParameter.apply(this, arguments);
        };
        """
        await context.add_init_script(stealth_js)

        page = await context.new_page()

        print(f"\n=== Step 1: Navigate to Gemini ===")
        try:
            # 先访问 google.com 建立 cookie
            print("Visiting google.com first to establish cookies...")
            await page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            # 处理 Google 首页的 consent
            consent_handled = await handle_consent(page)
            if consent_handled:
                print("  Consent handled on google.com")
                await page.wait_for_timeout(2000)

            # 然后访问 Gemini
            print(f"Navigating to {GEMINI_CONFIG['url']}...")
            await page.goto(GEMINI_CONFIG["url"], wait_until="domcontentloaded", timeout=90000)
            print("  Page domcontentloaded")

        except Exception as e:
            print(f"  Navigation error (may be OK): {e}")

        # 等待页面初始化
        print(f"\n=== Step 2: Waiting for page to initialize ===")
        await page.wait_for_timeout(5000)
        await dump_page_debug(page, "after_nav")

        # 处理 Gemini 页面上的 consent
        print(f"\n=== Step 3: Check for consent dialogs ===")
        consent_handled = await handle_consent(page)
        if consent_handled:
            print("  Consent handled on Gemini page")
            await page.wait_for_timeout(3000)
            await dump_page_debug(page, "after_consent")

        # 检查是否有 "Try Gemini" / "Get started" 按钮
        print(f"\n=== Step 4: Check for onboarding buttons ===")
        onboarding_selectors = [
            'button:has-text("Try Gemini")',
            'button:has-text("Get started")',
            'button:has-text("Start")',
            'button:has-text("Continue")',
            'button:has-text("开始")',
            'a:has-text("Try Gemini")',
        ]
        for sel in onboarding_selectors:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    print(f"  -> Found onboarding button: {sel}")
                    await btn.click()
                    await page.wait_for_timeout(3000)
                    break
            except Exception:
                continue

        # 等待输入框出现
        print(f"\n=== Step 5: Wait for input element ===")
        input_el = None
        selectors = [s.strip() for s in GEMINI_CONFIG["input_selector"].split(",")]

        # 最多等 60 秒
        for attempt in range(12):
            for sel in selectors:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        is_visible = await el.is_visible()
                        print(f"  Attempt {attempt+1}: {sel} -> found (visible={is_visible})")
                        if is_visible:
                            input_el = el
                            break
                except Exception:
                    pass
            if input_el:
                break
            print(f"  Attempt {attempt+1}: no input found, waiting 5s...")
            await page.wait_for_timeout(5000)

        if not input_el:
            print("\n  *** INPUT NOT FOUND - dumping final state ***")
            await dump_page_debug(page, "no_input_final")

            # 列出页面上所有可交互元素
            print("\n=== Visible interactive elements ===")
            try:
                elements = await page.query_selector_all("button, input, textarea, [contenteditable], [role='textbox']")
                for i, el in enumerate(elements[:20]):
                    try:
                        tag = await el.evaluate("el => el.tagName")
                        text = await el.inner_text()
                        visible = await el.is_visible()
                        print(f"  [{i}] <{tag}> visible={visible} text='{text[:50]}'")
                    except Exception:
                        pass
            except Exception as e:
                print(f"  Error listing elements: {e}")
        else:
            print(f"\n  Input element found! Trying a test query...")

            # 测试输入
            try:
                await input_el.click()
                await page.wait_for_timeout(500)
                test_query = "What is the capital of France?"
                await page.keyboard.type(test_query, delay=50)
                await page.wait_for_timeout(1000)
                await dump_page_debug(page, "after_type")

                # 提交：优先点击发送按钮
                submitted = False
                for btn_sel in ["button.send-button", "button[aria-label='Send message']", "button[aria-label='Send']"]:
                    try:
                        btn = await page.query_selector(btn_sel)
                        if btn and await btn.is_visible():
                            await btn.click()
                            submitted = True
                            print(f"  Submitted via button: {btn_sel}")
                            break
                    except Exception:
                        continue
                if not submitted:
                    await page.keyboard.press("Enter")
                    print("  Submitted via Enter key")

                print("  Waiting for response...")
                await page.wait_for_timeout(GEMINI_CONFIG["wait_after_submit"])
                await dump_page_debug(page, "after_response")

                # 提取响应
                resp_selectors = [s.strip() for s in GEMINI_CONFIG["response_selector"].split(",")]
                for sel in resp_selectors:
                    try:
                        elements = await page.query_selector_all(sel)
                        for el in elements:
                            text = await el.inner_text()
                            if text and len(text.strip()) > 20:
                                print(f"\n=== Response (via {sel}) ===")
                                print(text[:500])
                                break
                    except Exception:
                        continue

            except Exception as e:
                print(f"  Error during query: {e}")
                await dump_page_debug(page, "query_error")

        print("\n\nClosing browser...")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(test_gemini())
