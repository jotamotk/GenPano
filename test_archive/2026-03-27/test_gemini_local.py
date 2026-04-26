"""
本地测试 Gemini 页面加载
"""
import asyncio
import os
from pathlib import Path
from playwright.async_api import async_playwright

SCREENSHOT_DIR = Path("./screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

GEMINI_CONFIG = {
    "url": "https://gemini.google.com",
    "input_selector": "textarea, [contenteditable='true'], [role='textbox'], input[type='text'], rich-textarea",
    "load_wait": 90000,  # 90秒
}


async def test_gemini_load():
    """测试 Gemini 页面加载"""
    print("=" * 60)
    print("测试 Gemini 页面加载")
    print("=" * 60)

    async with async_playwright() as p:
        print("\n[1/5] 启动浏览器...")
        browser = await p.chromium.launch(
            headless=False,  # 非无头模式，能看到浏览器
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        print("✓ 浏览器启动成功")

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            ignore_https_errors=True,
        )

        # 隐藏 webdriver 特征
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            window.chrome = { runtime: {} };
        """)

        page = await context.new_page()

        print(f"\n[2/5] 打开页面: {GEMINI_CONFIG['url']}")
        try:
            await page.goto(GEMINI_CONFIG["url"], wait_until="commit", timeout=120000)
            print("✓ 页面请求已发送")
        except Exception as e:
            print(f"✗ 页面加载超时/错误: {e}")
            return

        # 每隔一段时间截图看看
        total_wait = GEMINI_CONFIG["load_wait"]
        interval = 10000  # 每10秒截图一次
        num_intervals = total_wait // interval

        print(f"\n[3/5] 等待 {total_wait/1000} 秒，每 {interval/1000} 秒截图一次...")

        for i in range(num_intervals):
            await asyncio.sleep(interval / 1000)
            elapsed = (i + 1) * interval

            try:
                title = await page.title()
                print(f"  [{elapsed/1000}s] 页面标题: {title}")

                # 截图
                screenshot_path = SCREENSHOT_DIR / f"gemini_test_{elapsed}ms.png"
                await page.screenshot(path=str(screenshot_path))
                print(f"  [{elapsed/1000}s] 截图已保存: {screenshot_path}")

                # 尝试找输入框
                selectors = [s.strip() for s in GEMINI_CONFIG["input_selector"].split(",")]
                found = False
                for sel in selectors:
                    try:
                        el = await page.query_selector(sel)
                        if el:
                            print(f"  [{elapsed/1000}s] ✓ 找到输入框: {sel}")
                            found = True
                            break
                    except:
                        pass
                if not found:
                    print(f"  [{elapsed/1000}s] ✗ 未找到输入框")

            except Exception as e:
                print(f"  [{elapsed/1000}s] 错误: {e}")

        print("\n[4/5] 最后检查...")
        try:
            content = await page.content()
            content_path = SCREENSHOT_DIR / "gemini_final.html"
            content_path.write_text(content, encoding="utf-8")
            print(f"✓ 页面内容已保存: {content_path}")
        except Exception as e:
            print(f"✗ 保存页面内容失败: {e}")

        print("\n[5/5] 完成！按 Ctrl+C 关闭浏览器，或者等 30 秒自动关闭...")
        await asyncio.sleep(30)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(test_gemini_load())
