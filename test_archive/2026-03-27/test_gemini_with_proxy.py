"""
本地测试 Gemini 页面加载 - 支持代理
"""
import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright

SCREENSHOT_DIR = Path("./screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# 配置你的代理地址
# 例如: "http://127.0.0.1:7890" 或者 "socks5://127.0.0.1:1080"
PROXY_URL = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY") or ""

GEMINI_CONFIG = {
    "url": "https://gemini.google.com",
    "input_selector": "textarea, [contenteditable='true'], [role='textbox'], input[type='text'], rich-textarea",
    "load_wait": 90000,  # 90 seconds
}


async def test_gemini_load():
    """Test Gemini page loading"""
    print("=" * 60)
    print("Testing Gemini page load")
    print("=" * 60)

    proxy_cfg = None
    if PROXY_URL:
        proxy_cfg = {"server": PROXY_URL}
        print(f"[Config] Using proxy: {PROXY_URL}")
    else:
        print("[Config] No proxy configured")
        print("         Set HTTPS_PROXY or HTTP_PROXY environment variable, or edit PROXY_URL in the script")

    async with async_playwright() as p:
        print("\n[1/5] Launching browser...")
        browser = await p.chromium.launch(
            headless=True,
            proxy=proxy_cfg,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        print("[OK] Browser launched")

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            ignore_https_errors=True,
        )

        # Hide webdriver features
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            window.chrome = { runtime: {} };
        """)

        page = await context.new_page()

        print(f"\n[2/5] Opening page: {GEMINI_CONFIG['url']}")
        try:
            await page.goto(GEMINI_CONFIG["url"], wait_until="commit", timeout=120000)
            print("[OK] Page request sent")
        except Exception as e:
            print(f"[ERROR] Page load timeout/error: {e}")
            if page:
                try:
                    screenshot_path = SCREENSHOT_DIR / "gemini_error.png"
                    await page.screenshot(path=str(screenshot_path))
                    print(f"[SAVED] Error screenshot: {screenshot_path}")
                except:
                    pass
            return

        # Wait and check
        wait_time = GEMINI_CONFIG["load_wait"]
        print(f"\n[3/5] Waiting {wait_time/1000} seconds...")

        # Check every 15 seconds
        num_checks = wait_time // 15000
        for i in range(num_checks):
            await asyncio.sleep(15)
            elapsed = (i + 1) * 15

            try:
                title = await page.title()
                print(f"  [{elapsed}s] Page title: {title}")

                # Screenshot
                screenshot_path = SCREENSHOT_DIR / f"gemini_proxy_{elapsed}s.png"
                await page.screenshot(path=str(screenshot_path))
                print(f"  [{elapsed}s] Screenshot saved: {screenshot_path}")

                # Try to find input
                selectors = [s.strip() for s in GEMINI_CONFIG["input_selector"].split(",")]
                found = False
                for sel in selectors:
                    try:
                        el = await page.query_selector(sel)
                        if el:
                            print(f"  [{elapsed}s] [FOUND] Input: {sel}")
                            found = True
                            break
                    except:
                        pass
                if not found:
                    print(f"  [{elapsed}s] [NOT FOUND] No input")

            except Exception as e:
                print(f"  [{elapsed}s] Error: {e}")

        print("\n[4/5] Saving final page content...")
        try:
            content = await page.content()
            content_path = SCREENSHOT_DIR / "gemini_proxy_final.html"
            content_path.write_text(content, encoding="utf-8")
            print(f"[OK] Page content saved: {content_path}")
        except Exception as e:
            print(f"[ERROR] Save page content failed: {e}")

        print("\n[5/5] Saving final screenshot...")
        try:
            screenshot_path = SCREENSHOT_DIR / "gemini_proxy_final.png"
            await page.screenshot(path=str(screenshot_path))
            print(f"[OK] Final screenshot saved: {screenshot_path}")
        except Exception as e:
            print(f"[ERROR] Save final screenshot failed: {e}")

        await browser.close()
        print("\n[DONE! Test completed.")


if __name__ == "__main__":
    asyncio.run(test_gemini_load())
