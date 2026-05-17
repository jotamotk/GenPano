"""
将 EditThisCookie 导出的 JSON 转换为 Playwright 兼容格式并测试豆包连通性。

用法:
    python scripts/test_doubao_cookies.py cookies_file.json
    # 或直接从 stdin:
    cat cookies.json | python scripts/test_doubao_cookies.py -
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def convert_editthiscookie(cookies: list[dict]) -> list[dict]:
    """将 EditThisCookie 格式转换为 Playwright add_cookies 格式"""
    SAME_SITE_MAP = {
        "unspecified": "Lax",
        "no_restriction": "None",
        "lax": "Lax",
        "strict": "Strict",
    }

    result = []
    for c in cookies:
        entry = {
            "name": c["name"],
            "value": c["value"],
            "domain": c["domain"],
            "path": c.get("path", "/"),
        }
        if c.get("expirationDate"):
            entry["expires"] = c["expirationDate"]
        if c.get("httpOnly"):
            entry["httpOnly"] = True
        if c.get("secure"):
            entry["secure"] = True
        same_site = c.get("sameSite", "unspecified")
        entry["sameSite"] = SAME_SITE_MAP.get(same_site, "Lax")
        result.append(entry)
    return result


async def test_cookies(cookies: list[dict]):
    from playwright.async_api import async_playwright

    print(f"共 {len(cookies)} 个 cookies，开始测试豆包连通性...\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )

        await context.add_cookies(cookies)
        print("✓ Cookies 注入成功")

        page = await context.new_page()
        await page.goto("https://www.doubao.com/chat", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)

        # 检查是否被重定向到登录页
        url = page.url
        login_domains = ["passport.volcengine.com", "sso.volcengine.com", "passport.douyin.com"]
        if any(d in url for d in login_domains):
            print(f"✗ 被重定向到登录页: {url}")
            print("  Cookies 可能已过期，请重新导出")
            await browser.close()
            return False

        print(f"✓ 页面加载成功: {url}")

        # 检查聊天输入框
        chat_input = await page.query_selector(
            "textarea, [contenteditable='true'], [class*='chat-input']"
        )
        if chat_input:
            print("✓ 检测到聊天输入框，登录状态有效！")
        else:
            print("? 未检测到聊天输入框，可能需要更长加载时间")

        # 尝试发送一条测试消息
        print("\n正在发送测试消息: '你好'...")
        try:
            if chat_input:
                await chat_input.click()
                await page.keyboard.type("你好", delay=80)
                await page.wait_for_timeout(500)
                await page.keyboard.press("Enter")
                print("✓ 消息已发送，等待回复...")

                await page.wait_for_timeout(15000)

                # 提取回复
                response_els = await page.query_selector_all(
                    "[class*='receive-message'] [class*='content'], "
                    "[class*='bot-message'] [class*='content'], "
                    "[class*='message-content']"
                )
                if response_els:
                    last = response_els[-1]
                    text = (await last.inner_text()).strip()
                    if text and len(text) > 5:
                        print(f"✓ 收到回复 ({len(text)} 字):")
                        print(f"  {text[:200]}...")
                        await browser.close()
                        return True
                    else:
                        print(f"? 回复内容太短: '{text}'")
                else:
                    print("? 未检测到回复元素")
        except Exception as e:
            print(f"? 发送测试消息异常: {e}")

        await browser.close()
        return chat_input is not None


async def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/test_doubao_cookies.py <cookies.json>")
        print("      cat cookies.json | python scripts/test_doubao_cookies.py -")
        sys.exit(1)

    source = sys.argv[1]
    if source == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(source).read_text(encoding="utf-8")

    raw_cookies = json.loads(raw)

    # 检测格式：EditThisCookie 有 storeId/hostOnly 字段
    if raw_cookies and isinstance(raw_cookies, list):
        if "storeId" in raw_cookies[0] or "hostOnly" in raw_cookies[0]:
            print("检测到 EditThisCookie 格式，自动转换...\n")
            cookies = convert_editthiscookie(raw_cookies)
        elif "platform" in raw_cookies[0]:
            # auto_register.py 输出格式
            cookies = raw_cookies[0]["cookies"]
        else:
            cookies = raw_cookies
    else:
        print("无法识别的 cookies 格式")
        sys.exit(1)

    # 保存转换后的 cookies（可用于环境变量或导入）
    converted_path = Path("cookies/doubao_converted.json")
    converted_path.parent.mkdir(parents=True, exist_ok=True)
    converted_data = {
        "platform": "doubao",
        "phone": "manual_export",
        "registered_at": "manual",
        "cookies": cookies,
    }
    converted_path.write_text(json.dumps(converted_data, ensure_ascii=False, indent=2))
    print(f"转换后的 cookies 已保存: {converted_path}")
    print(f"可用: python scripts/import_cookies.py {converted_path}\n")

    success = await test_cookies(cookies)

    if success:
        print("\n🎉 豆包 cookies 测试通过！")
        print(f"\n后续步骤:")
        print(f"  1. 导入数据库: python scripts/import_cookies.py {converted_path}")
        # Phase 3 cleanup (Refs #1118 / Epic #1110): the legacy doubao
        # env-cookie injection path was removed — doubao runs via vm_session
        # (ADR-016). Import into AccountPool is now the only supported path.
    else:
        print("\n⚠ 测试未完全通过，请检查输出")


if __name__ == "__main__":
    asyncio.run(main())
