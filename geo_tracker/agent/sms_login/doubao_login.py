"""
豆包 (doubao.com) SMS 登录处理器

从 scripts/auto_register.py 的 DoubaoRegistrar 提取并适配到
BaseSMSLoginHandler 框架。
"""
from __future__ import annotations

import logging
import random

from playwright.async_api import Page

from geo_tracker.agent.sms_login import register
from geo_tracker.agent.sms_login.base import BaseSMSLoginHandler

logger = logging.getLogger(__name__)

# 登录跳转域名
LOGIN_DOMAINS = [
    "passport.volcengine.com",
    "sso.volcengine.com",
    "passport.douyin.com",
]


@register("doubao")
class DoubaoLoginHandler(BaseSMSLoginHandler):
    platform = "doubao"
    service_id_env = "LUBANSMS_PROJECT_DOUBAO"
    login_url = "https://www.doubao.com/chat"

    # ── 选择器 ──────────────────────────────────────────────────────────

    phone_selectors = [
        "input[type='tel']",
        "input[placeholder*='手机']",
        "input[placeholder*='phone']",
        "input[name*='phone']",
        "input[name*='mobile']",
        "input[class*='phone']",
        "input[type='text']",  # 火山引擎 passport 通用 fallback
    ]

    sms_button_selectors = [
        "button:has-text('获取验证码')",
        "button:has-text('发送验证码')",
        "button:has-text('获取')",
        "span:has-text('获取验证码')",
        "[class*='send-code']",
        "[class*='verify-btn']",
        "[class*='sms-btn']",
    ]

    code_selectors = [
        "input[placeholder*='验证码']",
        "input[placeholder*='code']",
        "input[name*='code']",
        "input[class*='code']",
        "input[type='number']",
    ]

    submit_selectors = [
        "button:has-text('登录')",
        "button:has-text('注册')",
        "button:has-text('登录/注册')",
        "button[type='submit']",
        "[class*='submit']",
        "[class*='login-btn']",
    ]

    chat_input_selectors = [
        "textarea",
        "[contenteditable='true']",
        "[class*='chat-input']",
    ]

    # ── 抽象方法实现 ────────────────────────────────────────────────────

    async def navigate_to_login(self, page: Page) -> bool:
        """
        从 doubao.com/chat 导航到 passport 手机号登录页。
        如果已自动跳转到 passport 域名则无需操作。
        """
        current_url = page.url

        # 已经在登录页
        if any(d in current_url for d in LOGIN_DOMAINS):
            logger.info("[doubao] 已在 passport 登录页")
            await page.wait_for_timeout(2000)
            return True

        # 尝试用 locator（支持 :has-text）点击登录相关按钮
        login_texts = ["登录", "登录/注册", "立即体验", "开始对话", "免费使用", "开始使用"]
        for text in login_texts:
            try:
                loc = page.get_by_text(text, exact=False).first
                if await loc.is_visible(timeout=2000):
                    logger.info(f"[doubao] 点击按钮: '{text}'")
                    await loc.click()
                    await page.wait_for_timeout(3000)
                    break
            except Exception:
                continue

        # 也尝试 CSS 选择器 fallback
        if not any(d in page.url for d in LOGIN_DOMAINS):
            login_btn = await self._find_element(page, [
                "[class*='login']",
                "[class*='sign-in']",
                "[class*='sign-up']",
                "[data-testid*='login']",
            ])
            if login_btn:
                logger.info("[doubao] 通过 CSS 选择器点击登录按钮")
                await login_btn.click()
                await page.wait_for_timeout(3000)

        # 等待跳转到 passport 页面
        try:
            await page.wait_for_url(
                lambda url: any(d in url for d in LOGIN_DOMAINS),
                timeout=15000,
            )
        except Exception:
            logger.info(f"[doubao] 等待跳转超时, 当前页面: {page.url}")

        # 如果仍未跳转，直接访问 passport 登录页
        if not any(d in page.url for d in LOGIN_DOMAINS):
            logger.info("[doubao] 直接访问 passport 登录页")
            await page.goto(
                "https://www.doubao.com/chat/login",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            await page.wait_for_timeout(3000)

            # 最后再检查一次
            if not any(d in page.url for d in LOGIN_DOMAINS):
                # 再试 passport 直链
                await page.goto(
                    "https://passport.volcengine.com/auth/login",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                await page.wait_for_timeout(3000)

        await page.wait_for_timeout(2000)

        # 验证是否到达登录页
        on_login = any(d in page.url for d in LOGIN_DOMAINS)
        if not on_login:
            logger.error(f"[doubao] 导航登录页失败, 最终 URL: {page.url}")
        return on_login

    async def input_phone(self, page: Page, phone: str) -> bool:
        """在 passport 页面输入手机号"""
        # LubanSMS 返回 +86xxx 格式，passport 页面只需要纯数字
        clean_phone = phone.lstrip("+")
        if clean_phone.startswith("86") and len(clean_phone) > 11:
            clean_phone = clean_phone[2:]

        phone_input = await self._find_element(page, self.phone_selectors)
        if not phone_input:
            logger.error("[doubao] 未找到手机号输入框")
            return False

        logger.info(f"[doubao] 输入手机号: {clean_phone} (原始: {phone})")
        await self._type_slowly(page, phone_input, clean_phone)
        return True

    async def click_send_sms(self, page: Page) -> bool:
        """点击获取验证码按钮"""
        sms_btn = await self._find_element(page, self.sms_button_selectors)
        if sms_btn:
            await sms_btn.click()
            await page.wait_for_timeout(random.randint(1500, 2500))
            return True

        logger.warning("[doubao] 未找到获取验证码按钮")
        return False

    async def input_code(self, page: Page, code: str) -> bool:
        """输入 SMS 验证码"""
        code_input = await self._find_element(page, self.code_selectors)

        # Fallback: 页面上第二个 input（第一个是手机号）
        if not code_input:
            inputs = await page.query_selector_all(
                "input[type='text'], input[type='tel'], input[type='number']"
            )
            if len(inputs) >= 2:
                code_input = inputs[1]

        if not code_input:
            logger.error("[doubao] 未找到验证码输入框")
            return False

        await self._type_slowly(page, code_input, code)
        return True

    async def submit_login(self, page: Page) -> bool:
        """点击登录/注册按钮"""
        submit_btn = await self._find_element(page, self.submit_selectors)
        if submit_btn:
            await submit_btn.click()
            return True

        logger.warning("[doubao] 未找到提交按钮")
        return False

    async def verify_success(self, page: Page) -> bool:
        """
        验证是否成功进入聊天界面。
        检查 URL 是否回到 doubao.com/chat + 聊天输入框是否存在。
        """
        # 等待跳转回聊天页
        try:
            await page.wait_for_url(
                lambda url: "doubao.com/chat" in url,
                timeout=30000,
            )
        except Exception:
            logger.warning(f"[doubao] 登录后页面: {page.url}")

        await page.wait_for_timeout(3000)

        # 检查聊天输入框
        chat_input = await self._find_element(page, self.chat_input_selectors)
        if chat_input:
            logger.info("[doubao] 登录成功，聊天输入框已出现")
            return True

        # 可能有额外验证/弹窗，等待再试
        await self._handle_captcha(page)
        await page.wait_for_timeout(3000)

        chat_input = await self._find_element(page, self.chat_input_selectors)
        if chat_input:
            logger.info("[doubao] 登录成功（CAPTCHA 后）")
            return True

        logger.error(f"[doubao] 登录验证失败, URL: {page.url}")
        return False
