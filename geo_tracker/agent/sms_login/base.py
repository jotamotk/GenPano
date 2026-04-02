"""
SMS 登录处理器抽象基类

每个 LLM 平台实现自己的子类，只需关注页面操作逻辑。
浏览器启动、LubanSMS 交互、错误处理由基类模板方法统一封装。
"""
from __future__ import annotations

import json
import logging
import os
import random
from abc import ABC, abstractmethod
from typing import Optional

from playwright.async_api import Page, async_playwright

from geo_tracker.agent.sms_login.luban_client import LubanSMSClient

logger = logging.getLogger(__name__)

# Camoufox 可选依赖
try:
    from camoufox.async_api import AsyncCamoufox
    HAS_CAMOUFOX = True
except ImportError:
    HAS_CAMOUFOX = False

# 国内 LLM 直连不走代理
DOMESTIC_LLMS = {"kimi", "doubao", "deepseek", "zhipu"}

# CAPTCHA 检测选择器（字节跳动/通用）
CAPTCHA_SELECTORS = [
    "[class*='verify']",
    "[class*='captcha']",
    "#captcha-verify",
    "[class*='slide-verify']",
    "[class*='slider-verify']",
    "iframe[src*='captcha']",
    "[class*='secsdk']",
    "[class*='geetest']",
]


class BaseSMSLoginHandler(ABC):
    """
    SMS 登录处理器基类。

    子类需要实现的方法（页面操作）：
    - navigate_to_login: 从首页导航到手机号登录表单
    - input_phone: 输入手机号
    - click_send_sms: 点击发送验证码按钮
    - input_code: 输入验证码
    - submit_login: 点击登录/注册按钮
    - verify_success: 验证登录是否成功

    子类需要设置的属性：
    - platform: 平台标识 ("doubao", "deepseek", ...)
    - service_id_env: LubanSMS service_id 的环境变量名
    - login_url: 登录入口 URL
    """

    platform: str = ""
    service_id_env: str = ""
    login_url: str = ""

    @abstractmethod
    async def navigate_to_login(self, page: Page) -> bool:
        """从首页导航到手机号登录表单。返回 True 表示成功。"""

    @abstractmethod
    async def input_phone(self, page: Page, phone: str) -> bool:
        """输入手机号到登录表单。返回 True 表示成功。"""

    @abstractmethod
    async def click_send_sms(self, page: Page) -> bool:
        """点击发送验证码按钮。返回 True 表示成功。"""

    @abstractmethod
    async def input_code(self, page: Page, code: str) -> bool:
        """输入验证码。返回 True 表示成功。"""

    @abstractmethod
    async def submit_login(self, page: Page) -> bool:
        """点击登录/注册按钮。返回 True 表示成功。"""

    @abstractmethod
    async def verify_success(self, page: Page) -> bool:
        """验证登录是否成功（如检查聊天输入框）。"""

    def get_service_id(self) -> str:
        """获取 LubanSMS 对应的 service_id"""
        sid = os.getenv(self.service_id_env, "")
        if not sid:
            raise ValueError(f"环境变量 {self.service_id_env} 未设置")
        return sid

    # 最大换号重试次数（收不到短信时换新号码重试）
    MAX_PHONE_RETRIES = 3

    async def login_or_register(
        self,
        existing_cookies: str | None = None,
        phone: str | None = None,
    ) -> dict | None:
        """
        模板方法 — 完整的 SMS 登录/注册流程。

        当手机号收不到短信时，自动释放号码并获取新号码重试，
        最多重试 MAX_PHONE_RETRIES 次。

        Args:
            existing_cookies: 已有的 cookies JSON（用于重新登录）
            phone: 已有手机号（重新登录场景）；None 时从 LubanSMS 获取新号

        Returns:
            {"phone": "138xxx", "cookies": [...]} 成功
            {"status": "failed", "reason": "..."} 失败（附带原因）
            None 异常
        """
        sms_client = None
        browser = None
        _camoufox_ctx = None
        _playwright = None
        request_id = None
        phone_from_luban = False

        def _fail(reason: str) -> dict:
            logger.error(f"[{self.platform}] {reason}")
            return {"status": "failed", "reason": reason}

        try:
            sms_client = LubanSMSClient()
            service_id = self.get_service_id()

            # 获取初始手机号
            phone, request_id = await sms_client.get_number(service_id)
            phone_from_luban = True
            logger.info(
                f"[{self.platform}] 获取手机号: {phone} "
                f"(request_id={request_id})"
            )

            # 启动浏览器
            browser, _camoufox_ctx, _playwright, context = await self._launch_browser()

            # 注入已有 cookies（可能帮助跳过部分登录步骤）
            if existing_cookies:
                try:
                    cookies = json.loads(existing_cookies)
                    await context.add_cookies(cookies)
                    logger.info(
                        f"[{self.platform}] 注入 {len(cookies)} 个已有 cookies"
                    )
                except Exception as e:
                    logger.warning(f"[{self.platform}] 注入 cookies 失败: {e}")

            page = await context.new_page()

            # 添加反检测脚本（Playwright 模式）
            if not _camoufox_ctx:
                await self._add_stealth_script(page)

            # 访问登录页
            logger.info(f"[{self.platform}] 打开: {self.login_url}")
            await page.goto(
                self.login_url, wait_until="load", timeout=60000
            )
            await page.wait_for_timeout(random.randint(5000, 8000))

            # 执行登录流程
            logger.info(f"[{self.platform}] 导航到登录表单...")
            if not await self.navigate_to_login(page):
                return _fail("无法导航到登录表单（modal 未弹出）")

            # ── 手机号 + 短信验证码循环（收不到短信时换号重试）──
            last_fail_reason = ""
            for attempt in range(self.MAX_PHONE_RETRIES):
                if attempt > 0:
                    # 释放上一个收不到短信的号码，获取新号码
                    logger.warning(
                        f"[{self.platform}] 手机号 {phone} 收不到短信，"
                        f"释放并获取新号码 (第{attempt + 1}次尝试)"
                    )
                    await sms_client.release_number(request_id)
                    phone, request_id = await sms_client.get_number(service_id)
                    logger.info(
                        f"[{self.platform}] 新手机号: {phone} "
                        f"(request_id={request_id})"
                    )

                    # 重新加载登录页（清除上次输入状态）
                    await page.goto(
                        self.login_url, wait_until="domcontentloaded", timeout=60000
                    )
                    await page.wait_for_timeout(random.randint(2000, 4000))
                    if not await self.navigate_to_login(page):
                        last_fail_reason = "重试时无法导航到登录表单"
                        logger.error(f"[{self.platform}] {last_fail_reason}")
                        continue

                logger.info(f"[{self.platform}] 输入手机号: {phone}")
                if not await self.input_phone(page, phone):
                    last_fail_reason = "无法输入手机号（找不到输入框）"
                    logger.error(f"[{self.platform}] {last_fail_reason}")
                    continue

                logger.info(f"[{self.platform}] 点击发送验证码...")
                if not await self.click_send_sms(page):
                    last_fail_reason = "无法点击发送验证码按钮"
                    logger.error(f"[{self.platform}] {last_fail_reason}")
                    continue

                # 处理 CAPTCHA
                await self._handle_captcha(page)

                # 等待并获取验证码
                logger.info(f"[{self.platform}] 等待 SMS 验证码 (尝试 {attempt + 1}/{self.MAX_PHONE_RETRIES})...")
                try:
                    sms_code = await sms_client.get_sms(request_id, timeout=120)
                except (TimeoutError, RuntimeError) as e:
                    last_fail_reason = f"手机号 {phone} 获取验证码失败: {e}"
                    logger.warning(f"[{self.platform}] {last_fail_reason}")
                    continue  # 换下一个号码

                # 收到验证码，继续登录流程
                logger.info(f"[{self.platform}] 输入验证码: {sms_code}")
                if not await self.input_code(page, sms_code):
                    return _fail("无法输入验证码（找不到验证码输入框）")

                await page.wait_for_timeout(random.randint(500, 1000))

                logger.info(f"[{self.platform}] 提交登录...")
                if not await self.submit_login(page):
                    logger.warning(f"[{self.platform}] 提交按钮未找到，尝试 Enter")
                    await page.keyboard.press("Enter")

                # 等待登录完成
                await page.wait_for_timeout(random.randint(3000, 5000))

                # 可能有登录后的 CAPTCHA
                await self._handle_captcha(page)
                await page.wait_for_timeout(2000)

                # 验证登录成功
                if not await self.verify_success(page):
                    return _fail(f"登录验证失败（验证码已提交但未登录成功），URL: {page.url}")

                # 提取 cookies
                new_cookies = await context.cookies()
                cookies_list = self._format_cookies(new_cookies)

                logger.info(
                    f"[{self.platform}] 登录成功! "
                    f"phone={phone}, cookies={len(cookies_list)}"
                )
                return {"phone": phone, "cookies": cookies_list}

            # 所有重试都失败
            return _fail(
                f"连续 {self.MAX_PHONE_RETRIES} 次尝试均失败，"
                f"最后失败原因: {last_fail_reason}"
            )

        except Exception as e:
            logger.exception(f"[{self.platform}] 登录异常: {e}")
            # 释放未使用的号码
            if phone_from_luban and request_id and sms_client:
                await sms_client.release_number(request_id)
            return {"status": "failed", "reason": f"异常: {e}"}

        finally:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass
            if _camoufox_ctx:
                try:
                    await _camoufox_ctx.__aexit__(None, None, None)
                except Exception:
                    pass
            if _playwright:
                try:
                    await _playwright.stop()
                except Exception:
                    pass
            if sms_client:
                await sms_client.close()

    # ── 内部方法 ────────────────────────────────────────────────────────

    async def _launch_browser(self) -> tuple:
        """
        启动浏览器，返回 (browser, camoufox_ctx, playwright, context)。
        优先用 Camoufox 反指纹，降级到 Playwright Chromium。
        """
        is_domestic = self.platform in DOMESTIC_LLMS

        if HAS_CAMOUFOX:
            logger.info(f"[{self.platform}] 启动 Camoufox...")
            camoufox_kwargs = {
                "headless": True,
                "humanize": True,
                "block_images": False,
                "os": "windows",
                "locale": "zh-CN" if is_domestic else "en-US",
            }
            ctx = AsyncCamoufox(**camoufox_kwargs)
            browser = await ctx.__aenter__()
            context = await browser.new_context()
            return browser, ctx, None, context
        else:
            logger.info(f"[{self.platform}] 启动 Playwright Chromium...")
            pw = await async_playwright().start()
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-gpu",
                    "--use-gl=swiftshader",
                    "--no-zygote",
                    "--window-size=1920,1080",
                ],
            )
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN" if is_domestic else "en-US",
                timezone_id="Asia/Shanghai" if is_domestic else "America/New_York",
                ignore_https_errors=True,
            )
            return browser, None, pw, context

    async def _add_stealth_script(self, page: Page) -> None:
        """Playwright 模式下隐藏自动化特征"""
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            delete navigator.__proto__.webdriver;
            Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh']});
            Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
            Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
        """)

    async def _handle_captcha(self, page: Page) -> None:
        """检测并处理 CAPTCHA。当前 ByteDance 验证码无法自动解决。"""
        selector = ", ".join(CAPTCHA_SELECTORS)
        captcha_el = await page.query_selector(selector)
        if captcha_el:
            is_visible = False
            try:
                is_visible = await captcha_el.is_visible()
            except Exception:
                pass

            if is_visible:
                logger.warning(
                    f"[{self.platform}] 检测到 CAPTCHA，等待自动消失..."
                )
                try:
                    await page.wait_for_selector(
                        selector, state="hidden", timeout=30000
                    )
                    logger.info(f"[{self.platform}] CAPTCHA 已消失")
                except Exception:
                    logger.warning(
                        f"[{self.platform}] CAPTCHA 等待超时, 继续尝试..."
                    )

    @staticmethod
    def _format_cookies(raw_cookies: list[dict]) -> list[dict]:
        """将浏览器 cookies 转为 Playwright 注入格式"""
        formatted = []
        for c in raw_cookies:
            entry = {
                "name": c["name"],
                "value": c["value"],
                "domain": c["domain"],
                "path": c.get("path", "/"),
            }
            if c.get("expires", -1) > 0:
                entry["expires"] = c["expires"]
            if c.get("httpOnly"):
                entry["httpOnly"] = True
            if c.get("secure"):
                entry["secure"] = True
            if c.get("sameSite") and c["sameSite"] != "None":
                entry["sameSite"] = c["sameSite"]
            formatted.append(entry)
        return formatted

    # ── 辅助方法供子类使用 ──────────────────────────────────────────────

    @staticmethod
    async def _find_element(page: Page, selectors: list[str]):
        """依次尝试多个选择器，返回第一个匹配的元素。

        支持 Playwright 扩展伪类（如 :has-text()）——
        对这类选择器使用 locator API 而非 query_selector。
        """
        for sel in selectors:
            try:
                if ":has-text(" in sel:
                    # Playwright locator API 支持 :has-text
                    loc = page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        return await loc.element_handle()
                else:
                    el = await page.query_selector(sel)
                    if el:
                        return el
            except Exception:
                continue
        return None

    @staticmethod
    async def _type_slowly(
        page: Page, element, text: str, delay: int = 60
    ) -> None:
        """模拟人类输入"""
        await element.click()
        await element.fill("")
        await page.keyboard.type(text, delay=delay)
        await page.wait_for_timeout(random.randint(500, 1000))
