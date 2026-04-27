"""
简单的浏览器测试脚本
"""
import asyncio
import os
from playwright.async_api import async_playwright

async def test_simple():
    """Test simple browser functionality"""
    print("=" * 60)
    print("Testing simple browser")
    print("=" * 60)

    proxy_url = os.getenv("CLASH_PROXY_URL") or "http://clash:7890"
    print(f"[Config] Using proxy: {proxy_url}")

    async with async_playwright() as p:
        print("\n[1/3] Launching browser...")
        browser = await p.chromium.launch(
            headless=True,
            proxy={"server": proxy_url},
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        print("[OK] Browser launched")

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=True,
        )

        page = await context.new_page()

        print("\n[2/3] Testing example.com...")
        try:
            await page.goto("https://example.com", wait_until="networkidle", timeout=30000)
            title = await page.title()
            print(f"[OK] Page loaded, title: {title}")
        except Exception as e:
            print(f"[ERROR] Example.com failed: {e}")

        print("\n[3/3] Testing google.com...")
        try:
            await page.goto("https://www.google.com", wait_until="commit", timeout=60000)
            title = await page.title()
            print(f"[OK] Google loaded, title: {title}")

            # Wait a bit and screenshot
            await asyncio.sleep(5)
            screenshot_path = "/data/screenshots/test_google.png"
            await page.screenshot(path=screenshot_path)
            print(f"[OK] Screenshot saved: {screenshot_path}")

        except Exception as e:
            print(f"[ERROR] Google failed: {e}")

        await browser.close()
        print("\n[DONE!]")


if __name__ == "__main__":
    asyncio.run(test_simple())
