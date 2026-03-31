"""
自动注册豆包 & DeepSeek 账号 + Cookie 提取

使用 LubanSMS 接码平台获取手机号和验证码，
通过 Playwright 自动完成注册/登录流程，提取 cookies 保存为 JSON。

用法:
    python scripts/auto_register.py --platform doubao --count 1
    python scripts/auto_register.py --platform deepseek --count 3
    python scripts/auto_register.py --platform doubao --count 1 --headless
    python scripts/auto_register.py --platform doubao --count 2 --output ./my_cookies/

环境变量:
    LUBANSMS_TOKEN            LubanSMS API token (必需)
    LUBANSMS_PROJECT_DOUBAO   豆包对应的 service_id (--platform doubao 时必需)
    LUBANSMS_PROJECT_DEEPSEEK DeepSeek 对应的 service_id (--platform deepseek 时必需)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from playwright.async_api import async_playwright, BrowserContext, Page

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─── LubanSMS API 客户端 ──────────────────────────────────────────────────────

LUBANSMS_BASE = "https://lubansms.com/v2/api"


class LubanSMSClient:
    """LubanSMS 接码平台 API 封装"""

    def __init__(self, token: str):
        self.token = token
        self.client = httpx.AsyncClient(timeout=30)

    async def get_balance(self) -> str:
        resp = await self.client.get(
            f"{LUBANSMS_BASE}/getBalance", params={"apikey": self.token}
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"getBalance failed: {data}")
        return data["balance"]

    async def get_number(self, service_id: str) -> tuple[str, int]:
        """
        获取手机号
        返回: (phone_number, request_id)
        """
        resp = await self.client.get(
            f"{LUBANSMS_BASE}/getNumber",
            params={"apikey": self.token, "service_id": service_id},
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"getNumber failed: {data}")
        phone = data["number"]
        request_id = data["request_id"]
        logger.info(f"获取手机号: {phone} (request_id={request_id})")
        return phone, request_id

    async def get_sms(self, request_id: int, timeout: int = 120) -> str:
        """
        轮询获取短信验证码
        timeout: 最大等待秒数
        返回: 验证码字符串
        """
        waited = 0
        interval = 3
        while waited < timeout:
            resp = await self.client.get(
                f"{LUBANSMS_BASE}/getSms",
                params={"apikey": self.token, "request_id": request_id},
            )
            data = resp.json()

            if data.get("msg") == "success" and data.get("sms_code"):
                code = data["sms_code"]
                logger.info(f"收到验证码: {code}")
                return code

            if data.get("code") == 400:
                raise RuntimeError(f"getSms 失败 (号码可能已过期): {data}")

            # 继续等待
            await asyncio.sleep(interval)
            waited += interval
            if waited % 15 == 0:
                logger.info(f"等待验证码中... ({waited}s/{timeout}s)")

        raise TimeoutError(f"等待验证码超时 ({timeout}s)")

    async def release_number(self, request_id: int) -> None:
        """释放号码（未收到短信时使用）"""
        try:
            resp = await self.client.get(
                f"{LUBANSMS_BASE}/setStatus",
                params={
                    "apikey": self.token,
                    "request_id": request_id,
                    "status": "reject",
                },
            )
            data = resp.json()
            logger.info(f"释放号码: {data}")
        except Exception as e:
            logger.warning(f"释放号码失败: {e}")

    async def close(self):
        await self.client.aclose()


# ─── 注册器基类 ────────────────────────────────────────────────────────────────


class PlatformRegistrar(ABC):
    """平台注册器基类"""

    platform_name: str = ""

    def __init__(self, page: Page, sms_client: LubanSMSClient):
        self.page = page
        self.sms_client = sms_client

    @abstractmethod
    async def register(self, phone: str, request_id: int) -> bool:
        """
        执行注册/登录流程
        返回 True 表示成功（页面已进入聊天界面）
        """
        ...

    async def _wait_for_captcha(self) -> None:
        """
        检测验证码（滑块/点选），如果存在则暂停等待用户手动完成。
        """
        captcha_selectors = [
            "[class*='verify']",
            "[class*='captcha']",
            "#captcha-verify",
            "[class*='slide-verify']",
            "[class*='slider-verify']",
            "iframe[src*='captcha']",
            "[class*='secsdk']",
            "[class*='geetest']",
        ]
        selector = ", ".join(captcha_selectors)

        captcha_el = await self.page.query_selector(selector)
        if captcha_el:
            print("\n" + "=" * 60)
            print("  检测到验证码，请在浏览器窗口手动完成验证...")
            print("  完成后脚本将自动继续")
            print("=" * 60 + "\n")
            try:
                await self.page.wait_for_selector(
                    selector, state="hidden", timeout=300_000  # 5 分钟
                )
                logger.info("验证码已通过")
            except Exception:
                logger.warning("验证码等待超时，继续尝试...")

    async def _type_slowly(self, selector: str, text: str, delay: int = 80) -> None:
        """模拟人类输入速度"""
        el = await self.page.wait_for_selector(selector, timeout=10_000)
        if el:
            await el.click()
            await self.page.keyboard.type(text, delay=delay)


# ─── 豆包注册器 ────────────────────────────────────────────────────────────────


class DoubaoRegistrar(PlatformRegistrar):
    """
    豆包 (doubao.com) 注册流程:
    1. 打开 doubao.com/chat → 检测登录按钮/跳转
    2. 在 passport 页面填手机号、获取验证码
    3. 处理可能的 CAPTCHA（手动）
    4. 填入 SMS 验证码 → 提交
    5. 等待聊天界面加载完成
    """

    platform_name = "doubao"

    async def register(self, phone: str, request_id: int) -> bool:
        page = self.page

        # 1. 打开豆包
        logger.info("打开 doubao.com/chat ...")
        await page.goto("https://www.doubao.com/chat", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # 2. 检查是否需要登录
        current_url = page.url
        login_domains = ["passport.volcengine.com", "sso.volcengine.com", "passport.douyin.com"]

        if not any(d in current_url for d in login_domains):
            # 可能需要点击登录按钮
            login_btn = await page.query_selector(
                "button:has-text('登录'), a:has-text('登录'), "
                "[class*='login'], [class*='sign-in']"
            )
            if login_btn:
                logger.info("点击登录按钮...")
                await login_btn.click()
                await page.wait_for_timeout(3000)

        # 3. 等待进入 passport 页面
        try:
            await page.wait_for_url(
                lambda url: any(d in url for d in login_domains),
                timeout=15_000,
            )
        except Exception:
            # 可能已经在登录页面或弹窗中
            logger.info(f"当前页面: {page.url}")

        await page.wait_for_timeout(2000)

        # 4. 查找手机号输入框并填入
        logger.info(f"填入手机号: {phone}")

        # 火山引擎 passport 页面可能有多种布局
        phone_input = await self._find_phone_input()
        if not phone_input:
            logger.error("未找到手机号输入框")
            return False

        await phone_input.click()
        await phone_input.fill("")
        await page.keyboard.type(phone, delay=60)
        await page.wait_for_timeout(1000)

        # 5. 点击获取验证码
        logger.info("点击获取验证码...")
        sms_btn = await self._find_sms_button()
        if sms_btn:
            await sms_btn.click()
        else:
            logger.warning("未找到获取验证码按钮，尝试直接提交...")

        await page.wait_for_timeout(2000)

        # 6. 处理 CAPTCHA
        await self._wait_for_captcha()

        # 7. 等待并填入验证码
        logger.info("等待接收验证码...")
        try:
            sms_code = await self.sms_client.get_sms(request_id, timeout=120)
        except (TimeoutError, RuntimeError) as e:
            logger.error(f"获取验证码失败: {e}")
            return False

        logger.info(f"填入验证码: {sms_code}")
        code_input = await self._find_code_input()
        if code_input:
            await code_input.click()
            await code_input.fill("")
            await page.keyboard.type(sms_code, delay=60)
        else:
            logger.error("未找到验证码输入框")
            return False

        await page.wait_for_timeout(1000)

        # 8. 点击登录/提交
        submit_btn = await self._find_submit_button()
        if submit_btn:
            logger.info("点击登录按钮...")
            await submit_btn.click()
        else:
            # 尝试按 Enter
            await page.keyboard.press("Enter")

        # 9. 等待跳转到聊天页面
        logger.info("等待登录完成...")
        try:
            await page.wait_for_url(
                lambda url: "doubao.com/chat" in url,
                timeout=30_000,
            )
        except Exception:
            logger.warning(f"登录后页面: {page.url}")

        await page.wait_for_timeout(3000)

        # 10. 验证登录成功：检查聊天输入框
        chat_input = await page.query_selector(
            "textarea, [contenteditable='true'], [class*='chat-input']"
        )
        if chat_input:
            logger.info("豆包登录成功！")
            return True

        # 可能有额外的验证或弹窗
        await self._wait_for_captcha()
        await page.wait_for_timeout(3000)

        chat_input = await page.query_selector(
            "textarea, [contenteditable='true'], [class*='chat-input']"
        )
        if chat_input:
            logger.info("豆包登录成功！")
            return True

        logger.error(f"登录可能失败，当前页面: {page.url}")
        return False

    async def _find_phone_input(self) -> Optional[object]:
        """查找手机号输入框"""
        selectors = [
            "input[type='tel']",
            "input[placeholder*='手机']",
            "input[placeholder*='phone']",
            "input[name*='phone']",
            "input[name*='mobile']",
            "input[class*='phone']",
            # 火山引擎 passport 通用选择器
            "input[type='text']",
        ]
        for sel in selectors:
            el = await self.page.query_selector(sel)
            if el:
                return el
        return None

    async def _find_sms_button(self) -> Optional[object]:
        """查找获取验证码按钮"""
        selectors = [
            "button:has-text('获取验证码')",
            "button:has-text('发送验证码')",
            "button:has-text('获取')",
            "span:has-text('获取验证码')",
            "[class*='send-code']",
            "[class*='verify-btn']",
            "[class*='sms-btn']",
        ]
        for sel in selectors:
            el = await self.page.query_selector(sel)
            if el:
                return el
        return None

    async def _find_code_input(self) -> Optional[object]:
        """查找验证码输入框"""
        selectors = [
            "input[placeholder*='验证码']",
            "input[placeholder*='code']",
            "input[name*='code']",
            "input[class*='code']",
            "input[type='number']",
        ]
        for sel in selectors:
            el = await self.page.query_selector(sel)
            if el:
                return el
        # Fallback: 找第二个 input
        inputs = await self.page.query_selector_all("input[type='text'], input[type='tel'], input[type='number']")
        if len(inputs) >= 2:
            return inputs[1]
        return None

    async def _find_submit_button(self) -> Optional[object]:
        """查找提交/登录按钮"""
        selectors = [
            "button:has-text('登录')",
            "button:has-text('注册')",
            "button:has-text('登录/注册')",
            "button[type='submit']",
            "[class*='submit']",
            "[class*='login-btn']",
        ]
        for sel in selectors:
            el = await self.page.query_selector(sel)
            if el:
                return el
        return None


# ─── DeepSeek 注册器 ──────────────────────────────────────────────────────────


class DeepSeekRegistrar(PlatformRegistrar):
    """
    DeepSeek (chat.deepseek.com) 注册流程:
    1. 打开 chat.deepseek.com → 点击登录/注册
    2. 选择手机号方式 → 填入手机号
    3. 获取验证码 → 填入
    4. 完成登录，等待聊天界面
    """

    platform_name = "deepseek"

    async def register(self, phone: str, request_id: int) -> bool:
        page = self.page

        # 1. 打开 DeepSeek
        logger.info("打开 chat.deepseek.com ...")
        await page.goto("https://chat.deepseek.com", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # 2. 检查是否需要登录
        login_btn = await page.query_selector(
            "button:has-text('Log In'), button:has-text('Sign Up'), "
            "button:has-text('登录'), button:has-text('注册'), "
            "a:has-text('Log In'), a:has-text('Sign Up'), "
            "[class*='login'], [class*='sign']"
        )
        if login_btn:
            logger.info("点击登录/注册按钮...")
            await login_btn.click()
            await page.wait_for_timeout(3000)

        # 3. 寻找手机号登录入口
        # DeepSeek 可能默认显示邮箱，需要切换到手机号
        phone_tab = await page.query_selector(
            "div:has-text('手机号'), span:has-text('手机号'), "
            "button:has-text('手机号'), [class*='phone-tab'], "
            "div:has-text('Phone'), span:has-text('Phone')"
        )
        if phone_tab:
            logger.info("切换到手机号登录...")
            await phone_tab.click()
            await page.wait_for_timeout(1000)

        # 4. 填入手机号
        logger.info(f"填入手机号: {phone}")
        phone_input = await self._find_phone_input()
        if not phone_input:
            logger.error("未找到手机号输入框")
            return False

        await phone_input.click()
        await phone_input.fill("")
        await page.keyboard.type(phone, delay=60)
        await page.wait_for_timeout(1000)

        # 5. 点击获取验证码
        logger.info("点击获取验证码...")
        sms_btn = await self._find_sms_button()
        if sms_btn:
            await sms_btn.click()
        else:
            logger.warning("未找到获取验证码按钮")

        await page.wait_for_timeout(2000)

        # 6. 处理 CAPTCHA
        await self._wait_for_captcha()

        # 7. 等待并填入验证码
        logger.info("等待接收验证码...")
        try:
            sms_code = await self.sms_client.get_sms(request_id, timeout=120)
        except (TimeoutError, RuntimeError) as e:
            logger.error(f"获取验证码失败: {e}")
            return False

        logger.info(f"填入验证码: {sms_code}")
        code_input = await self._find_code_input()
        if code_input:
            await code_input.click()
            await code_input.fill("")
            await page.keyboard.type(sms_code, delay=60)
        else:
            logger.error("未找到验证码输入框")
            return False

        await page.wait_for_timeout(1000)

        # 8. 点击登录/注册提交
        submit_btn = await self._find_submit_button()
        if submit_btn:
            logger.info("点击提交...")
            await submit_btn.click()
        else:
            await page.keyboard.press("Enter")

        # 9. 等待聊天界面
        logger.info("等待登录完成...")
        await page.wait_for_timeout(5000)

        # 检查是否有额外的 CAPTCHA
        await self._wait_for_captcha()

        # 10. 验证登录成功
        chat_input = await page.query_selector(
            "textarea, [contenteditable='true'], input[type='text'], "
            "[class*='chat-input'], [id*='chat-input']"
        )
        if chat_input:
            logger.info("DeepSeek 登录成功！")
            return True

        # 再等一会
        await page.wait_for_timeout(5000)
        chat_input = await page.query_selector(
            "textarea, [contenteditable='true'], [class*='chat-input']"
        )
        if chat_input:
            logger.info("DeepSeek 登录成功！")
            return True

        logger.error(f"登录可能失败，当前页面: {page.url}")
        return False

    async def _find_phone_input(self) -> Optional[object]:
        selectors = [
            "input[type='tel']",
            "input[placeholder*='手机']",
            "input[placeholder*='phone' i]",
            "input[name*='phone']",
            "input[name*='mobile']",
            "input[class*='phone']",
            "input[type='text']",
        ]
        for sel in selectors:
            el = await self.page.query_selector(sel)
            if el:
                return el
        return None

    async def _find_sms_button(self) -> Optional[object]:
        selectors = [
            "button:has-text('获取验证码')",
            "button:has-text('发送验证码')",
            "button:has-text('Send')",
            "button:has-text('Get Code')",
            "button:has-text('Send Code')",
            "span:has-text('获取验证码')",
            "[class*='send-code']",
            "[class*='verify-btn']",
        ]
        for sel in selectors:
            el = await self.page.query_selector(sel)
            if el:
                return el
        return None

    async def _find_code_input(self) -> Optional[object]:
        selectors = [
            "input[placeholder*='验证码']",
            "input[placeholder*='code' i]",
            "input[name*='code']",
            "input[class*='code']",
            "input[type='number']",
        ]
        for sel in selectors:
            el = await self.page.query_selector(sel)
            if el:
                return el
        inputs = await self.page.query_selector_all("input[type='text'], input[type='tel'], input[type='number']")
        if len(inputs) >= 2:
            return inputs[1]
        return None

    async def _find_submit_button(self) -> Optional[object]:
        selectors = [
            "button:has-text('登录')",
            "button:has-text('注册')",
            "button:has-text('Log In')",
            "button:has-text('Sign Up')",
            "button:has-text('Submit')",
            "button[type='submit']",
            "[class*='submit']",
            "[class*='login-btn']",
        ]
        for sel in selectors:
            el = await self.page.query_selector(sel)
            if el:
                return el
        return None


# ─── 注册器工厂 ────────────────────────────────────────────────────────────────

REGISTRARS = {
    "doubao": DoubaoRegistrar,
    "deepseek": DeepSeekRegistrar,
}

SERVICE_ID_ENV = {
    "doubao": "LUBANSMS_PROJECT_DOUBAO",
    "deepseek": "LUBANSMS_PROJECT_DEEPSEEK",
}


# ─── Cookie 提取 & 保存 ───────────────────────────────────────────────────────


async def extract_and_save_cookies(
    context: BrowserContext,
    platform: str,
    phone: str,
    output_dir: Path,
) -> Path:
    """提取浏览器 cookies 并保存为 JSON 文件"""
    cookies = await context.cookies()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 只保留手机号后4位用于文件名
    phone_suffix = phone[-4:] if len(phone) >= 4 else phone
    filename = f"{platform}_{phone_suffix}_{timestamp}.json"
    filepath = output_dir / filename

    data = {
        "platform": platform,
        "phone": phone,
        "registered_at": datetime.now().isoformat(),
        "cookies": cookies,
    }

    filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    logger.info(f"Cookies 已保存: {filepath}")

    # 打印可用于环境变量的格式
    cookies_json = json.dumps(cookies)
    env_var = f"{platform.upper()}_COOKIES_JSON"
    print(f"\n可直接设置环境变量:")
    print(f'export {env_var}=\'{cookies_json[:200]}...\'')
    print(f"(完整内容见文件: {filepath})\n")

    return filepath


# ─── 主流程 ────────────────────────────────────────────────────────────────────


async def register_one(
    platform: str,
    sms_client: LubanSMSClient,
    service_id: str,
    output_dir: Path,
    headless: bool = False,
) -> Optional[Path]:
    """注册单个账号，返回 cookies 文件路径"""
    phone = None
    request_id = None

    try:
        # 1. 获取手机号
        phone, request_id = await sms_client.get_number(service_id)

        # 2. 启动浏览器
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )
            page = await context.new_page()

            # 3. 执行注册
            registrar_cls = REGISTRARS[platform]
            registrar = registrar_cls(page, sms_client)

            success = await registrar.register(phone, request_id)

            if success:
                # 4. 提取 cookies
                filepath = await extract_and_save_cookies(
                    context, platform, phone, output_dir
                )
                await browser.close()
                return filepath
            else:
                logger.error(f"注册失败: {platform} / {phone}")
                await browser.close()
                return None

    except Exception as e:
        logger.exception(f"注册异常: {e}")
        # 释放号码
        if request_id:
            await sms_client.release_number(request_id)
        return None


async def main():
    parser = argparse.ArgumentParser(description="自动注册豆包/DeepSeek 并提取 Cookies")
    parser.add_argument(
        "--platform",
        required=True,
        choices=list(REGISTRARS.keys()),
        help="注册平台: doubao, deepseek",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="注册账号数量 (默认 1)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="./cookies",
        help="Cookie 输出目录 (默认 ./cookies)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="无头模式运行 (无法手动处理 CAPTCHA)",
    )
    args = parser.parse_args()

    # 检查环境变量
    token = os.getenv("LUBANSMS_TOKEN")
    if not token:
        print("错误: 请设置 LUBANSMS_TOKEN 环境变量")
        sys.exit(1)

    service_id_env = SERVICE_ID_ENV[args.platform]
    service_id = os.getenv(service_id_env)
    if not service_id:
        print(f"错误: 请设置 {service_id_env} 环境变量 (LubanSMS 项目 ID)")
        sys.exit(1)

    # 创建输出目录
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 初始化 SMS 客户端
    sms_client = LubanSMSClient(token)

    try:
        # 检查余额
        balance = await sms_client.get_balance()
        logger.info(f"LubanSMS 余额: {balance}")

        # 批量注册
        results = []
        for i in range(args.count):
            print(f"\n{'='*60}")
            print(f"  注册第 {i+1}/{args.count} 个 {args.platform} 账号")
            print(f"{'='*60}\n")

            filepath = await register_one(
                platform=args.platform,
                sms_client=sms_client,
                service_id=service_id,
                output_dir=output_dir,
                headless=args.headless,
            )
            if filepath:
                results.append(filepath)
            else:
                logger.warning(f"第 {i+1} 个账号注册失败，继续下一个...")

            # 多个账号间间隔
            if i < args.count - 1:
                logger.info("等待 5 秒后继续下一个...")
                await asyncio.sleep(5)

        # 汇总
        print(f"\n{'='*60}")
        print(f"  注册完成: {len(results)}/{args.count} 成功")
        print(f"{'='*60}")
        for fp in results:
            print(f"  - {fp}")
        print()

    finally:
        await sms_client.close()


if __name__ == "__main__":
    asyncio.run(main())
