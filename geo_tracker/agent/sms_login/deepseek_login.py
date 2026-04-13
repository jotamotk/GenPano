"""
DeepSeek (chat.deepseek.com) SMS 登录处理器

登录流程：
1. 打开 chat.deepseek.com
2. 点击登录/注册入口
3. 切换到"手机号登录"
4. 输入手机号 → 点击"发送验证码"
5. 输入验证码 → 点击登录
6. 登录成功后进入聊天界面
"""
from __future__ import annotations

import logging
import os
import random
from pathlib import Path

from playwright.async_api import Page

from geo_tracker.agent.sms_login import register
from geo_tracker.agent.sms_login.base import BaseSMSLoginHandler

logger = logging.getLogger(__name__)

DEBUG_DIR = Path(os.getenv("SCREENSHOT_DIR", "/data/screenshots"))
DEBUG_DIR.mkdir(parents=True, exist_ok=True)


@register("deepseek")
class DeepSeekLoginHandler(BaseSMSLoginHandler):
    platform = "deepseek"
    sms_keyword = "DeepSeek"
    login_url = "https://chat.deepseek.com"

    # ── 抽象方法实现 ────────────────────────────────────────────────────

    async def navigate_to_login(self, page: Page) -> bool:
        """点击登录/注册入口，切到手机号 tab。"""
        logger.info(f"[deepseek] 当前 URL: {page.url}")

        # 若已经能看到手机号输入框，直接返回
        phone_input = await self._find_element(page, [
            "input[type='tel']",
            "input[placeholder*='手机']",
        ])
        if phone_input:
            logger.info("[deepseek] 登录表单已就绪")
            return await self._switch_to_phone_tab(page)

        # 尝试点击登录/注册入口
        login_btn = await self._find_element(page, [
            "button:has-text('登录')",
            "button:has-text('注册')",
            "button:has-text('Log In')",
            "button:has-text('Sign Up')",
            "a:has-text('登录')",
            "a:has-text('Log In')",
            "[class*='login']",
            "[class*='sign-in']",
        ])
        if login_btn:
            logger.info("[deepseek] 点击登录入口")
            try:
                await login_btn.click(timeout=5000)
            except Exception as e:
                logger.warning(f"[deepseek] 点击登录入口失败: {e}")
            await page.wait_for_timeout(random.randint(2000, 3000))

        return await self._switch_to_phone_tab(page)

    async def _switch_to_phone_tab(self, page: Page) -> bool:
        """DeepSeek 默认可能显示邮箱登录，需切换到手机号。"""
        phone_tab = await self._find_element(page, [
            "div:has-text('手机号登录')",
            "span:has-text('手机号登录')",
            "button:has-text('手机号')",
            "div:has-text('Phone')",
            "[class*='phone-tab']",
        ])
        if phone_tab:
            try:
                await phone_tab.click(timeout=3000)
                logger.info("[deepseek] 切换到手机号登录")
                await page.wait_for_timeout(1000)
            except Exception as e:
                logger.info(f"[deepseek] 手机号 tab 点击失败（可能默认就是）: {e}")

        # 确认手机号输入框已出现
        phone_input = await self._find_element(page, [
            "input[type='tel']",
            "input[placeholder*='手机']",
        ])
        if not phone_input:
            await self._save_debug(page, "no_phone_form")
            logger.error("[deepseek] 未找到手机号输入框")
            return False
        return True

    async def input_phone(self, page: Page, phone: str) -> bool:
        """在登录表单中输入手机号"""
        # LubanSMS 可能返回 +86xxx 格式，DeepSeek 只需要纯手机号
        clean_phone = phone.lstrip("+")
        if clean_phone.startswith("86") and len(clean_phone) > 11:
            clean_phone = clean_phone[2:]

        phone_input = await self._find_element(page, [
            "input[type='tel']",
            "input[placeholder*='手机']",
            "input[placeholder*='phone' i]",
            "input[name*='phone']",
            "input[name*='mobile']",
        ])
        if not phone_input:
            logger.error("[deepseek] 未找到手机号输入框")
            return False

        logger.info(f"[deepseek] 输入手机号: {clean_phone} (原始: {phone})")
        await self._type_slowly(page, phone_input, clean_phone)
        return True

    async def click_send_sms(self, page: Page) -> bool:
        """点击发送验证码"""
        sms_btn = await self._find_element(page, [
            "button:has-text('获取验证码')",
            "button:has-text('发送验证码')",
            "button:has-text('Send Code')",
            "button:has-text('Get Code')",
            "span:has-text('获取验证码')",
            "[class*='send-code']",
            "[class*='verify-btn']",
        ])
        if not sms_btn:
            logger.warning("[deepseek] 未找到发送验证码按钮")
            return False

        logger.info("[deepseek] 点击发送验证码")
        try:
            await sms_btn.click(timeout=5000)
        except Exception as e:
            logger.error(f"[deepseek] 点击发送验证码失败: {e}")
            return False
        await page.wait_for_timeout(random.randint(2000, 3000))
        return True

    async def input_code(self, page: Page, code: str) -> bool:
        """输入 SMS 验证码"""
        code_input = await self._find_element(page, [
            "input[placeholder*='验证码']",
            "input[placeholder*='code' i]",
            "input[name*='code']",
            "input[class*='code']",
            "input[type='number']",
        ])

        # Fallback: 取第二个 input（第一个通常是手机号）
        if not code_input:
            inputs = await page.query_selector_all(
                "input[type='text'], input[type='tel'], input[type='number']"
            )
            if len(inputs) >= 2:
                code_input = inputs[1]

        if not code_input:
            logger.error("[deepseek] 未找到验证码输入框")
            return False

        await self._type_slowly(page, code_input, code)
        return True

    async def submit_login(self, page: Page) -> bool:
        """点击登录/注册提交按钮"""
        submit_btn = await self._find_element(page, [
            "button:has-text('登录')",
            "button:has-text('注册')",
            "button:has-text('Log In')",
            "button:has-text('Sign Up')",
            "button:has-text('Submit')",
            "button[type='submit']",
            "[class*='login-btn']",
            "[class*='submit-btn']",
        ])
        if submit_btn:
            try:
                await submit_btn.click(timeout=5000)
                return True
            except Exception as e:
                logger.warning(f"[deepseek] 点击提交失败: {e}")
        logger.warning("[deepseek] 未找到提交按钮")
        return False

    async def verify_success(self, page: Page) -> bool:
        """登录成功后应出现聊天输入框"""
        await page.wait_for_timeout(5000)

        chat_input = await self._find_element(page, [
            "textarea",
            "[contenteditable='true']",
            "[class*='chat-input']",
            "[id*='chat-input']",
        ])
        if chat_input:
            logger.info("[deepseek] 登录成功，聊天输入框已出现")
            return True

        # 可能有 CAPTCHA
        await self._handle_captcha(page)
        await page.wait_for_timeout(3000)

        chat_input = await self._find_element(page, [
            "textarea",
            "[contenteditable='true']",
            "[class*='chat-input']",
        ])
        if chat_input:
            logger.info("[deepseek] 登录成功（CAPTCHA 后）")
            return True

        logger.error(f"[deepseek] 登录验证失败, URL: {page.url}")
        return False

    async def _save_debug(self, page: Page, suffix: str) -> None:
        """保存截图和 HTML 用于调试"""
        try:
            import time
            ts = int(time.time())
            screenshot_path = DEBUG_DIR / f"deepseek_{suffix}_{ts}.png"
            await page.screenshot(path=str(screenshot_path), full_page=False)
            logger.info(f"[deepseek] 截图已保存: {screenshot_path}")
            html_path = DEBUG_DIR / f"deepseek_{suffix}_{ts}.html"
            html = await page.content()
            html_path.write_text(html[:200000], encoding="utf-8")
            logger.info(f"[deepseek] HTML 已保存: {html_path} ({len(html)} bytes)")
        except Exception as e:
            logger.warning(f"[deepseek] 保存调试信息失败: {e}")
