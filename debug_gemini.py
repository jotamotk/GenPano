"""
Gemini 调试脚本 — 在服务器上直接运行，逐步截图定位问题

用法（在 worker 容器内）：
  docker exec -it <worker容器名> python /app/geo_tracker/debug_gemini.py

或传入 cookie 文件：
  docker exec -it <worker容器名> python /app/geo_tracker/debug_gemini.py /path/to/gemini_cookies.json
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright

SCREENSHOT_DIR = Path(os.getenv("SCREENSHOT_DIR", "/data/screenshots"))
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
PROXY_URL = os.getenv("CLASH_PROXY_URL") or os.getenv("HTTPS_PROXY") or "http://clash:7890"

def load_cookies() -> list:
    # 1. 优先从命令行参数读取 cookie 文件
    if len(sys.argv) > 1:
        path = sys.argv[1]
        print(f"[cookie] 从文件读取: {path}")
        return json.loads(Path(path).read_text())
    # 2. 从环境变量读取
    raw = os.getenv("GEMINI_COOKIES_JSON", "").strip()
    if raw:
        cookies = json.loads(raw)
        print(f"[cookie] 从环境变量读取: {len(cookies)} 个")
        return cookies
    print("[cookie] 未找到 cookies，将以 guest 模式访问")
    return []

def save_screenshot(page, name: str):
    ts = int(datetime.utcnow().timestamp())
    path = SCREENSHOT_DIR / f"debug_gemini_{name}_{ts}.png"
    asyncio.get_event_loop().run_until_complete(page.screenshot(path=str(path)))
    print(f"[截图] {path}")
    return path

async def main():
    cookies = load_cookies()
    print(f"[proxy] 使用代理: {PROXY_URL}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy={"server": PROXY_URL},
            args=[
                "--no-sandbox", "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu", "--disable-software-rasterizer",
                "--window-size=1920,1080", "--force-device-scale-factor=1",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
        )

        if cookies:
            await context.add_cookies(cookies)
            print(f"[cookie] 已注入 {len(cookies)} 个 cookies")

        page = await context.new_page()

        # Step 1: 打开 Gemini
        print("\n[step 1] 打开 gemini.google.com/app ...")
        await page.goto("https://gemini.google.com/app", wait_until="domcontentloaded", timeout=90000)
        print(f"[step 1] 页面标题: {await page.title()}")
        print(f"[step 1] 当前 URL: {page.url}")
        await page.screenshot(path=str(SCREENSHOT_DIR / "debug_gemini_1_loaded.png"))
        print(f"[截图] debug_gemini_1_loaded.png")

        # 检查是否跳到登录页
        if "accounts.google.com" in page.url or "signin" in page.url:
            print("[❌] 跳转到登录页！cookies 无效或已过期")
            await browser.close()
            return

        # Step 2: 等待输入框
        print("\n[step 2] 等待输入框...")
        input_el = None
        for sel in ["rich-textarea .ql-editor", "rich-textarea", "[contenteditable='true']", "textarea"]:
            try:
                input_el = await page.wait_for_selector(sel, timeout=15000, state="attached")
                visible = await input_el.is_visible()
                print(f"[step 2] 找到输入框: {sel} (visible={visible})")
                break
            except Exception:
                print(f"[step 2] selector 未找到: {sel}")

        if not input_el:
            print("[❌] 找不到输入框，Gemini 页面结构可能已变化")
            await page.screenshot(path=str(SCREENSHOT_DIR / "debug_gemini_2_no_input.png"))
            await browser.close()
            return

        # Step 3: 输入文字
        print("\n[step 3] 输入测试 query...")
        try:
            await input_el.focus()
            await page.keyboard.press("Control+a")
            await page.wait_for_timeout(100)
        except Exception as e:
            print(f"[step 3] focus/clear 异常（非致命）: {e}")

        test_query = "Say hello in one sentence."
        await page.keyboard.type(test_query, delay=50)
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(SCREENSHOT_DIR / "debug_gemini_3_typed.png"))
        print(f"[截图] debug_gemini_3_typed.png")

        # Step 4: 提交
        print("\n[step 4] 提交 query...")
        submitted = False
        for btn_sel in ["button.send-button", "button[aria-label='Send message']", "button[aria-label='Send']"]:
            try:
                btn = await page.query_selector(btn_sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    submitted = True
                    print(f"[step 4] 通过按钮提交: {btn_sel}")
                    break
            except Exception:
                continue
        if not submitted:
            await page.keyboard.press("Enter")
            print("[step 4] 通过 Enter 提交")

        # Step 5: 分段等待，每 10s 截图一次
        print("\n[step 5] 等待响应（每 10s 截图一次）...")
        for i in range(6):  # 最多等 60s
            await page.wait_for_timeout(10000)
            current_url = page.url
            title = await page.title()
            screenshot_path = SCREENSHOT_DIR / f"debug_gemini_5_wait_{(i+1)*10}s.png"
            await page.screenshot(path=str(screenshot_path))
            print(f"[{(i+1)*10}s] URL={current_url} | title={title} | 截图={screenshot_path.name}")

            if "accounts.google.com" in current_url:
                print("[❌] 等待期间跳转到登录页！")
                break

            # 检查是否有响应内容
            for sel in ["model-response", "message-content", ".model-response-text", "[class*='response']"]:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        txt = await el.inner_text()
                        if txt and len(txt.strip()) > 20:
                            print(f"\n[✅] 响应内容已出现（{(i+1)*10}s），selector={sel}")
                            print(f"[response] {txt[:300]}")
                            await page.screenshot(path=str(SCREENSHOT_DIR / "debug_gemini_6_response.png"))
                            await browser.close()
                            return
                except Exception:
                    continue

        # Step 6: 最终提取
        print("\n[step 6] 最终提取页面文本...")
        body = await page.inner_text("body")
        print(f"[body text 长度] {len(body)}")
        print(f"[body text 前 500 字符]\n{body[:500]}")

        await page.screenshot(path=str(SCREENSHOT_DIR / "debug_gemini_final.png"))
        print(f"[截图] debug_gemini_final.png")

        await browser.close()
        print("\n[完成] 所有截图已保存到:", SCREENSHOT_DIR)

asyncio.run(main())
