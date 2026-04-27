"""
Test Gemini input visibility
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
    "load_wait": 60000,
}


async def test_visibility():
    """Test visibility check"""
    print("=" * 60)
    print("Testing Gemini input visibility")
    print("=" * 60)

    proxy_url = os.getenv("CLASH_PROXY_URL") or "http://clash:7890"
    proxy_cfg = {"server": proxy_url}
    print(f"[Config] Using proxy: {proxy_url}")

    async with async_playwright() as p:
        print("\n[1/4] Launching browser...")
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

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            window.chrome = { runtime: {} };
        """)

        page = await context.new_page()

        print(f"\n[2/4] Opening page: {GEMINI_CONFIG['url']}")
        await page.goto(GEMINI_CONFIG["url"], wait_until="commit", timeout=180000)
        print("[OK] Page request sent")

        wait_time = GEMINI_CONFIG["load_wait"]
        print(f"\n[3/4] Waiting {wait_time/1000} seconds...")
        await asyncio.sleep(wait_time / 1000)

        title = await page.title()
        print(f"Page title: {title}")

        print("\n[4/4] Testing selectors...")
        selectors = [s.strip() for s in GEMINI_CONFIG["input_selector"].split(",")]

        for sel in selectors:
            print(f"\nTesting selector: {sel}")
            try:
                # Try query_selector (like debug script)
                el = await page.query_selector(sel)
                if el:
                    print(f"  [query_selector] FOUND element")

                    # Check visibility
                    try:
                        visible = await el.is_visible()
                        print(f"  [is_visible] visible={visible}")
                    except Exception as e:
                        print(f"  [is_visible] ERROR: {e}")

                    # Check if it's in DOM
                    try:
                        in_dom = await el.is_enabled()
                        print(f"  [is_enabled] enabled={in_dom}")
                    except Exception as e:
                        print(f"  [is_enabled] ERROR: {e}")

                    # Get some info
                    try:
                        tag = await el.evaluate("el => el.tagName")
                        _id = await el.evaluate("el => el.id")
                        classes = await el.evaluate("el => el.className")
                        print(f"  Tag: {tag}, id='{_id}', class='{classes[:80]}'")
                    except Exception as e:
                        print(f"  [evaluate] ERROR: {e}")

            except Exception as e:
                print(f"  [query_selector] ERROR: {e}")

        # Screenshot
        screenshot_path = SCREENSHOT_DIR / "gemini_visibility_test.png"
        await page.screenshot(path=str(screenshot_path))
        print(f"\n[OK] Screenshot saved: {screenshot_path}")

        await browser.close()
        print("\n[DONE!]")


if __name__ == "__main__":
    asyncio.run(test_visibility())
