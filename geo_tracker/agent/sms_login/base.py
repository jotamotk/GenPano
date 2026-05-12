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
import re
from abc import ABC, abstractmethod
from typing import Optional

from playwright.async_api import Page, async_playwright

from geo_tracker.agent.browser_lifecycle import (
    cleanup_browser_resources,
    install_resource_blocker,
)
from geo_tracker.agent.sms_login.phone_blacklist import (
    add_to_blacklist,
    is_blacklisted,
)
from geo_tracker.agent.sms_login.providers import (
    LubanSMSProvider,
    SMSNumberLease,
    SMSProvider,
)
from geo_tracker.agent.sms_redaction import (
    mask_phone,
    redact_sensitive_text,
)

logger = logging.getLogger(__name__)

# Camoufox 可选依赖
try:
    from camoufox.async_api import AsyncCamoufox
    HAS_CAMOUFOX = True
except ImportError:
    HAS_CAMOUFOX = False

# 国内 LLM 直连不走代理
DOMESTIC_LLMS = {"kimi", "doubao", "deepseek", "zhipu"}

# CAPTCHA 检测选择器（数美/字节跳动/通用）
CAPTCHA_SELECTORS = [
    ".shumei_captcha_wrapper",
    "#sm-captcha",
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
    - sms_keyword: 短信关键词，用于 getKeywordSms 过滤（如 "豆包"、"抖音"）
    - login_url: 登录入口 URL
    """

    platform: str = ""
    sms_keyword: str = ""
    login_url: str = ""
    sms_provider_factory = LubanSMSProvider

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

    # 最大换号重试次数（收不到短信时换新号码重试）
    MAX_PHONE_RETRIES = 5
    # 单次取号时最多跳过多少个黑名单号码
    _MAX_BLACKLIST_SKIP = 20

    async def _get_clean_number(
        self,
        sms_provider: SMSProvider,
        used_leases: list[SMSNumberLease],
    ) -> SMSNumberLease:
        """
        随机获取一个不在黑名单中的手机号。
        若取到黑名单号码，加入 used_phones（留待最终统一释放）并重新取，
        最多跳过 _MAX_BLACKLIST_SKIP 个。
        """
        for _ in range(self._MAX_BLACKLIST_SKIP):
            lease = await sms_provider.reserve_number()
            if not await is_blacklisted(self.platform, lease.phone):
                return lease
            used_leases.append(lease)
            logger.info(
                f"[{self.platform}] skipped blacklisted phone "
                f"{mask_phone(lease.phone)}"
            )
        raise RuntimeError(
            f"all {self._MAX_BLACKLIST_SKIP} reserved numbers were blacklisted"
        )

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
            phone: 已有手机号（重新登录场景）；None 时从 LubanSMS 随机获取新号

        Returns:
            {"phone": "138xxx", "cookies": [...]} 成功
            {"status": "failed", "reason": "..."} 失败（附带原因）
        """
        if not self.sms_keyword:
            raise ValueError(
                f"[{self.platform}] sms_keyword 未设置，无法使用 Keyword API"
            )

        sms_provider: SMSProvider | None = None
        browser = None
        context = None
        page = None
        _camoufox_ctx = None
        _playwright = None
        # 所有本次申请过的手机号，流程结束后统一释放
        used_leases: list[SMSNumberLease] = []
        current_lease: SMSNumberLease | None = None
        # 手机号是否为有效 11 位数字（web_upload 等占位符跳过 SMS 登录）
        is_valid_phone = bool(phone) and bool(re.fullmatch(r"\d{11}", phone or ""))
        is_relogin = is_valid_phone  # 只有合法手机号才走重登录流程

        if phone and not is_valid_phone:
            logger.warning(
                f"[{self.platform}] 传入的 phone='{mask_phone(phone)}' 非 11 位数字，"
                f"降级为新注册流程"
            )

        def _fail(reason: str) -> dict:
            logger.error(f"[{self.platform}] {reason}")
            return {"status": "failed", "reason": reason}

        if phone and not is_valid_phone and existing_cookies:
            return _fail(
                "invalid phone for re-login; refusing to request a new SMS number"
            )

        try:
            sms_provider = self.sms_provider_factory()

            # ── 获取初始手机号 ──────────────────────────────────────────
            if is_relogin:
                # 重新登录：通过 getKeywordNumber(phone=xxx) 复用已有号码
                try:
                    current_lease = await sms_provider.reserve_number(phone=phone)
                    phone = current_lease.phone
                    used_leases.append(current_lease)
                    logger.info(
                        f"[{self.platform}] 复用手机号: {mask_phone(phone)}"
                    )
                except RuntimeError as e:
                    # 号码不在线 / 通道无此号码等：降级为随机取新号
                    logger.warning(
                        f"[{self.platform}] 复用手机号失败 "
                        f"({redact_sensitive_text(e)})，降级为随机取号"
                    )
                    is_relogin = False
                    current_lease = await self._get_clean_number(
                        sms_provider, used_leases
                    )
                    used_leases.append(current_lease)
                    phone = current_lease.phone
                    logger.info(
                        f"[{self.platform}] 获取新手机号: {mask_phone(phone)}"
                    )
            else:
                # 新注册：随机取号，跳过黑名单
                current_lease = await self._get_clean_number(
                    sms_provider, used_leases
                )
                used_leases.append(current_lease)
                phone = current_lease.phone
                logger.info(f"[{self.platform}] 获取手机号: {mask_phone(phone)}")

            # 启动浏览器
            browser, _camoufox_ctx, _playwright, context = await self._launch_browser()
            # Keep CAPTCHA images available for SMS login, but drop heavier assets.
            await install_resource_blocker(context, block_images=False)

            # 注入已有 cookies（可能帮助跳过部分登录步骤）
            if existing_cookies:
                try:
                    parsed = json.loads(existing_cookies)
                    # 支持新格式 {"cookies": [...], "localStorage": {...}}
                    if isinstance(parsed, dict) and "cookies" in parsed:
                        cookies = parsed["cookies"]
                    elif isinstance(parsed, list):
                        cookies = parsed
                    else:
                        cookies = []
                    if cookies:
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

            # ── 手机号 + 短信验证码循环 ─────────────────────────────────
            # 重新登录时不换号（号码绑定账号），新注册时收不到短信则换号重试
            max_attempts = 1 if is_relogin else self.MAX_PHONE_RETRIES
            last_fail_reason = ""

            for attempt in range(max_attempts):
                if attempt > 0:
                    # 新注册换号：旧号已加黑名单，直接取新号
                    logger.warning(
                        f"[{self.platform}] 手机号 {mask_phone(phone)} 收不到短信，"
                        f"换新号码 (第{attempt + 1}次尝试)"
                    )
                    current_lease = await self._get_clean_number(
                        sms_provider, used_leases
                    )
                    used_leases.append(current_lease)
                    phone = current_lease.phone
                    logger.info(f"[{self.platform}] 新手机号: {mask_phone(phone)}")

                    # 重新加载登录页
                    await page.goto(
                        self.login_url, wait_until="domcontentloaded", timeout=60000
                    )
                    await page.wait_for_timeout(random.randint(2000, 4000))
                    if not await self.navigate_to_login(page):
                        last_fail_reason = "重试时无法导航到登录表单"
                        logger.error(f"[{self.platform}] {last_fail_reason}")
                        continue

                logger.info(f"[{self.platform}] 输入手机号: {mask_phone(phone)}")
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
                logger.info(
                    f"[{self.platform}] 等待 SMS 验证码 "
                    f"(尝试 {attempt + 1}/{max_attempts}, keyword={self.sms_keyword})..."
                )
                try:
                    sms_code = await sms_provider.poll_sms_code(
                        current_lease, keyword=self.sms_keyword, timeout=120
                    )
                except (TimeoutError, RuntimeError) as e:
                    last_fail_reason = (
                        f"手机号 {mask_phone(phone)} 获取验证码失败: "
                        f"{redact_sensitive_text(e)}"
                    )
                    logger.warning(f"[{self.platform}] {last_fail_reason}")
                    if not is_relogin:
                        # 新注册：将收不到短信的号码加黑名单
                        await add_to_blacklist(self.platform, phone, reason="sms_timeout")
                    continue  # 重新登录只有 1 次，直接失败退出

                # 收到验证码，继续登录流程
                logger.info(f"[{self.platform}] 输入验证码: [sms-code-redacted]")
                if not await self.input_code(page, sms_code):
                    return _fail("无法输入验证码（找不到验证码输入框）")

                await page.wait_for_timeout(random.randint(500, 1000))

                # 开启网络响应监听（比 toast 更可靠，不会消失）
                api_errors = []

                async def _capture_api_error(response):
                    try:
                        if response.status >= 400 or (
                            response.url and any(
                                kw in response.url for kw in
                                ["login", "send_code", "sms", "verify", "auth", "register"]
                            )
                        ):
                            try:
                                body = await response.text()
                            except Exception:
                                body = ""
                            if body:
                                safe_body = redact_sensitive_text(body)
                                api_errors.append({
                                    "url": response.url,
                                    "status": response.status,
                                    "body": safe_body[:500],
                                })
                                logger.info(
                                    f"[{self.platform}] API响应: "
                                    f"{response.status} {response.url.split('?')[0]} → {safe_body[:200]}"
                                )
                    except Exception:
                        pass

                page.on("response", _capture_api_error)

                logger.info(f"[{self.platform}] 提交登录...")
                if not await self.submit_login(page):
                    logger.warning(f"[{self.platform}] 提交按钮未找到，尝试 Enter")
                    await page.keyboard.press("Enter")

                # 等待登录完成
                await page.wait_for_timeout(random.randint(3000, 5000))

                # 停止监听
                page.remove_listener("response", _capture_api_error)

                # 检查捕获到的 API 错误
                # DeepSeek login_by_mobile_sms 返回:
                # {"code":0,"data":{"biz_code":11,"biz_msg":"RISK_DEVICE_DETECTED",...}}
                device_env_error = False
                for err in api_errors:
                    body_lower = err["body"].lower()
                    if "risk_device_detected" in body_lower:
                        logger.warning(
                            f"[{self.platform}] API返回 RISK_DEVICE_DETECTED: "
                            f"{err['url'].split('?')[0]} → {err['body'][:300]}"
                        )
                        device_env_error = True
                        break
                    if "device" in body_lower and "environment" in body_lower:
                        logger.warning(
                            f"[{self.platform}] API返回设备环境错误: "
                            f"{err['url'].split('?')[0]} → {err['body'][:300]}"
                        )
                        device_env_error = True
                        break

                # 兜底：检查 toast DOM
                if not device_env_error:
                    toast_error = await self._detect_error_toast(page)
                    if toast_error:
                        logger.warning(f"[{self.platform}] toast 错误: {toast_error}")
                        if any(kw in toast_error for kw in [
                            "device environment", "risk_device",
                            "设备环境", "环境异常", "运行环境",
                            "Device Environment", "RISK_DEVICE",
                        ]):
                            device_env_error = True

                if device_env_error:
                    logger.warning(
                        f"[{self.platform}] 手机号 {mask_phone(phone)} 设备环境错误，加入黑名单并换号"
                    )
                    await add_to_blacklist(self.platform, phone, reason="device_env_error", permanent=True)
                    last_fail_reason = f"手机号 {mask_phone(phone)} 设备环境错误"
                    continue

                # 可能有登录后的 CAPTCHA
                await self._handle_captcha(page)
                await page.wait_for_timeout(2000)

                # 验证登录成功
                verify_result = await self.verify_success(page)
                if verify_result == "device_env_error":
                    logger.warning(
                        f"[{self.platform}] 设备环境错误 (verify阶段)，"
                        f"手机号 {mask_phone(phone)} 不干净，加入黑名单并换号"
                    )
                    await add_to_blacklist(self.platform, phone, reason="device_env_error", permanent=True)
                    last_fail_reason = f"手机号 {mask_phone(phone)} 设备环境错误"
                    continue
                if not verify_result:
                    return _fail(f"登录验证失败（验证码已提交但未登录成功），URL: {page.url}")

                # 提取 cookies
                new_cookies = await context.cookies()
                cookies_list = self._format_cookies(new_cookies)

                # 提取 localStorage（DeepSeek 需要 userToken）
                local_storage = {}
                try:
                    local_storage = await page.evaluate("""
                        () => {
                            const keys = ['userToken'];
                            const result = {};
                            for (const k of keys) {
                                const v = localStorage.getItem(k);
                                if (v) result[k] = v;
                            }
                            return result;
                        }
                    """)
                except Exception as e:
                    logger.debug(f"[{self.platform}] 提取 localStorage 失败: {e}")

                logger.info(
                    f"[{self.platform}] 登录成功! "
                    f"phone={mask_phone(phone)}, cookies={len(cookies_list)}"
                    + (f", localStorage={len(local_storage)} 项" if local_storage else "")
                )
                result = {"phone": phone, "cookies": cookies_list}
                if local_storage:
                    result["localStorage"] = local_storage
                return result

            # 所有重试都失败
            return _fail(
                f"{'重新登录' if is_relogin else f'连续 {max_attempts} 次新注册'}均失败，"
                f"最后失败原因: {last_fail_reason}"
            )

        except Exception as e:
            safe_error = redact_sensitive_text(e)
            logger.error(
                f"[{self.platform}] 登录异常: {safe_error} "
                f"(exception_type={type(e).__name__})"
            )
            return {"status": "failed", "reason": f"异常: {safe_error}"}

        finally:
            # 生产事故 2026-04-27 根因修复 (browser.close() hang 导致进程泄漏 + SMS 浪费):
            # SMS 登录路径同样会 hang, 而且这条路径每次失败都会再要新手机号 → 鲁班扣费.
            # 必须先安全清理浏览器, 再释放手机号, 顺序不可换.
            await cleanup_browser_resources(
                page=page,
                context=context,
                browser=browser,
                camoufox_ctx=_camoufox_ctx,
                playwright=_playwright,
            )
            if sms_provider:
                # 统一释放所有本次申请过的手机号
                for lease in used_leases:
                    try:
                        await sms_provider.release_number(lease)
                    except Exception:
                        pass
                await sms_provider.close()

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

    async def _detect_error_toast(self, page: Page) -> Optional[str]:
        """检测页面上的错误 toast/提示，返回错误文本或 None。"""
        try:
            error_text = await page.evaluate("""
                () => {
                    const sels = [
                        '.ds-toast', '[class*="toast"]', '[class*="Toast"]',
                        '[class*="message-error"]', '[class*="error-message"]',
                        '[role="alert"]', '.ant-message-error',
                        '[class*="notice"]', '[class*="notification"]',
                    ];
                    for (const sel of sels) {
                        const els = document.querySelectorAll(sel);
                        for (const el of els) {
                            const text = (el.textContent || '').trim();
                            if (text && el.offsetParent !== null) {
                                return text.slice(0, 300);
                            }
                        }
                    }
                    return null;
                }
            """)
            return error_text
        except Exception:
            return None

    async def _handle_captcha(self, page: Page) -> None:
        """检测并处理 CAPTCHA。优先使用视觉模型求解，降级为等待消失。"""
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
                    f"[{self.platform}] 检测到 CAPTCHA，尝试视觉模型求解..."
                )
                # 优先尝试视觉模型求解
                try:
                    from geo_tracker.agent.vision_captcha import solve_vision_captcha
                    solved = await solve_vision_captcha(page, max_retries=3)
                    if solved:
                        logger.info(f"[{self.platform}] 视觉验证码求解成功")
                        return
                except Exception as e:
                    logger.warning(f"[{self.platform}] 视觉求解异常: {e}")

                # 降级：等待验证码自动消失
                logger.info(f"[{self.platform}] 视觉求解未成功，等待消失...")
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
        """模拟人类输入（用 focus 代替 click，避免容器 div 拦截 pointer events）"""
        try:
            await element.focus()
        except Exception:
            # focus 不支持时回退到 JS focus
            await element.evaluate("el => el.focus()")
        await element.fill("")
        await page.keyboard.type(text, delay=delay)
        await page.wait_for_timeout(random.randint(500, 1000))
