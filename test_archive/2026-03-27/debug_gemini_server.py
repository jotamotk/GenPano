"""
服务器上调试 Gemini 的脚本
"""
import asyncio
import os
from pathlib import Path
from playwright.async_api import async_playwright

SCREENSHOT_DIR = Path("/data/screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

GEMINI_CONFIG = {
    "url": "https://gemini.google.com",
    "input_selector": "textarea, [contenteditable='true'], [role='textbox'], input[type='text'], rich-textarea",
    "load_wait": 120000,  # 120 seconds
}


async def debug_gemini():
    """Debug Gemini page loading"""
    print("=" * 60)
    print("Debugging Gemini on server")
    print("=" * 60)

    proxy_url = os.getenv("CLASH_PROXY_URL") or "http://clash:7890"
    proxy_cfg = {"server": proxy_url}
    print(f"[Config] Using proxy: {proxy_url}")

    async with async_playwright() as p:
        print("\n[1/6] Launching browser...")
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
        print("[OK] Browser launched")

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

        # Hide webdriver features
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            window.chrome = { runtime: {} };
        """)

        page = await context.new_page()

        print(f"\n[2/6] Opening page: {GEMINI_CONFIG['url']}")
        try:
            await page.goto(GEMINI_CONFIG["url"], wait_until="commit", timeout=180000)
            print("[OK] Page request sent")
        except Exception as e:
            print(f"[ERROR] Page load timeout/error: {e}")
            if page:
                try:
                    screenshot_path = SCREENSHOT_DIR / "gemini_debug_error.png"
                    await page.screenshot(path=str(screenshot_path))
                    print(f"[SAVED] Error screenshot: {screenshot_path}")
                except Exception as se:
                    print(f"[ERROR] Save error screenshot failed: {se}")
            return

        # Wait and check
        wait_time = GEMINI_CONFIG["load_wait"]
        print(f"\n[3/6] Waiting {wait_time/1000} seconds...")

        # Check every 15 seconds
        num_checks = wait_time // 15000
        for i in range(num_checks):
            await asyncio.sleep(15)
            elapsed = (i + 1) * 15

            try:
                title = await page.title()
                print(f"  [{elapsed}s] Page title: {title}")

                # Screenshot
                screenshot_path = SCREENSHOT_DIR / f"gemini_debug_{elapsed}s.png"
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

                # Also log page content length
                content = await page.content()
                print(f"  [{elapsed}s] Page content length: {len(content)} chars")

            except Exception as e:
                print(f"  [{elapsed}s] Error: {e}")

        print("\n[4/6] Saving final page content...")
        try:
            content = await page.content()
            content_path = SCREENSHOT_DIR / "gemini_debug_final.html"
            content_path.write_text(content, encoding="utf-8")
            print(f"[OK] Page content saved: {content_path}")
        except Exception as e:
            print(f"[ERROR] Save page content failed: {e}")

        print("\n[5/6] Saving final screenshot...")
        try:
            screenshot_path = SCREENSHOT_DIR / "gemini_debug_final.png"
            await page.screenshot(path=str(screenshot_path))
            print(f"[OK] Final screenshot saved: {screenshot_path}")
        except Exception as e:
            print(f"[ERROR] Save final screenshot failed: {e}")

        print("\n[6/6] Checking for any interactive elements...")
        try:
            all_elements = await page.query_selector_all("*")
            print(f"[INFO] Total elements on page: {len(all_elements)}")

            # Look for any buttons or inputs
            buttons = await page.query_selector_all("button, input, textarea, [contenteditable]")
            print(f"[INFO] Found {len(buttons)} interactive elements")

            for i, btn in enumerate(buttons[:10]):
                tag = await btn.evaluate("el => el.tagName")
                _id = await btn.evaluate("el => el.id")
                classes = await btn.evaluate("el => el.className")
                print(f"  [{i}] {tag} id='{_id}' class='{classes[:50]}'")

        except Exception as e:
            print(f"[ERROR] Check elements failed: {e}")

        await browser.close()
        print("\n[DONE! Debug completed.")


if __name__ == "__main__":
    asyncio.run(debug_gemini())
