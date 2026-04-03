"""
DeepSeek (chat.deepseek.com) SMS 登录处理器

登录流程：
1. 打开 chat.deepseek.com
2. 点击登录按钮
3. 切换到手机号登录（默认可能是邮箱）
4. 输入手机号 → 点击获取验证码
5. 处理 CAPTCHA（如有）
6. 输入验证码 → 提交登录
7. 验证聊天界面出现
"""
from __future__ import annotations

import logging
import os
import random
import time
from pathlib import Path

from playwright.async_api import Page

from geo_tracker.agent.sms_login import register
from geo_tracker.agent.sms_login.base import BaseSMSLoginHandler

logger = logging.getLogger(__name__)

DEBUG_DIR = Path(os.getenv("SCREENSHOT_DIR", "/data/screenshots"))
DEBUG_DIR.mkdir(parents=True, exist_ok=True)


@register("deepseek")
class DeepseekLoginHandler(BaseSMSLoginHandler):
    platform = "deepseek"
    sms_keyword = "DeepSeek"  # LubanSMS 过滤关键词，如不匹配可改为 "深度求索"
    login_url = "https://chat.deepseek.com"

    # ── 抽象方法实现 ────────────────────────────────────────────────────

    async def navigate_to_login(self, page: Page) -> bool:
        """
        点击登录按钮，弹出登录表单，并切换到手机号登录 Tab。
        DeepSeek 可能默认显示邮箱登录，需要显式切换。
        """
        logger.info(f"[deepseek] 当前 URL: {page.url}")

        # 检查是否已经在登录/注册页面
        if "login" in page.url or "auth" in page.url:
            logger.info("[deepseek] 已在登录页面")
            return await self._switch_to_phone_tab(page)

        # 查找并点击登录按钮
        login_btn = await self._find_element(page, [
            "button:has-text('Log In')",
            "button:has-text('Sign Up')",
            "button:has-text('登录')",
            "button:has-text('注册')",
            "a:has-text('Log In')",
            "a:has-text('Sign Up')",
            "a:has-text('登录')",
            "a:has-text('注册')",
            "[class*='login']",
            "[class*='sign']",
        ])

        if not login_btn:
            await self._save_debug(page, "no_login_btn")
            debug_info = await page.evaluate("""
                () => {
                    const items = [...document.querySelectorAll('button, a, [role="button"]')]
                        .filter(e => e.getBoundingClientRect().width > 0)
                        .map(e => {
                            const r = e.getBoundingClientRect();
                            return `${e.tagName} "${(e.textContent||'').trim().slice(0,30)}" (${Math.round(r.x)},${Math.round(r.y)})`;
                        });
                    return items.join('\\n');
                }
            """)
            logger.error(f"[deepseek] 未找到登录按钮，页面可点击元素:\n{debug_info}")
            return False

        logger.info("[deepseek] 点击登录按钮")
        await login_btn.click()
        await page.wait_for_timeout(random.randint(2000, 3000))

        # 切换到手机号登录
        return await self._switch_to_phone_tab(page)

    async def _switch_to_phone_tab(self, page: Page) -> bool:
        """切换到手机号登录 Tab（DeepSeek 可能默认邮箱登录）"""
        phone_tab = await self._find_element(page, [
            "div:has-text('手机号')",
            "span:has-text('手机号')",
            "button:has-text('手机号')",
            "div:has-text('Phone')",
            "span:has-text('Phone')",
            "button:has-text('Phone')",
            "[class*='phone-tab']",
            "[class*='phone-login']",
        ])
        if phone_tab:
            logger.info("[deepseek] 切换到手机号登录 Tab")
            await phone_tab.click()
            await page.wait_for_timeout(random.randint(800, 1500))
        else:
            # 可能已经在手机号登录页面，或不需要切换
            logger.info("[deepseek] 未找到手机号 Tab（可能已在手机号模式）")

        # 处理用户协议 checkbox（如有）
        await self._handle_agreement(page)
        return True

    async def _handle_agreement(self, page: Page) -> None:
        """勾选用户协议 checkbox（如果存在）"""
        try:
            checkbox = await self._find_element(page, [
                "input[type='checkbox']",
                "[class*='agreement'] input",
                "[class*='checkbox']",
                "[class*='protocol'] input",
            ])
            if checkbox:
                checked = await checkbox.is_checked() if hasattr(checkbox, "is_checked") else False
                if not checked:
                    logger.info("[deepseek] 勾选用户协议")
                    await checkbox.click()
                    await page.wait_for_timeout(500)
        except Exception as e:
            logger.warning(f"[deepseek] 勾选协议失败（可能不存在）: {e}")

    async def input_phone(self, page: Page, phone: str) -> bool:
        """输入手机号"""
        # LubanSMS 返回 +86xxx 格式，去掉前缀
        clean_phone = phone.lstrip("+")
        if clean_phone.startswith("86") and len(clean_phone) > 11:
            clean_phone = clean_phone[2:]

        phone_input = await self._find_element(page, [
            "input[type='tel']",
            "input[placeholder*='手机']",
            "input[placeholder*='phone' i]",
            "input[name*='phone']",
            "input[name*='mobile']",
            "input[class*='phone']",
            "input[type='text']",
        ])

        if not phone_input:
            await self._save_debug(page, "no_phone_input")
            logger.error("[deepseek] 未找到手机号输入框")
            return False

        logger.info(f"[deepseek] 输入手机号: {clean_phone} (原始: {phone})")
        await self._type_slowly(page, phone_input, clean_phone)
        return True

    async def click_send_sms(self, page: Page) -> bool:
        """点击获取验证码按钮"""
        sms_btn = await self._find_element(page, [
            "button:has-text('获取验证码')",
            "button:has-text('发送验证码')",
            "button:has-text('Send Code')",
            "button:has-text('Get Code')",
            "span:has-text('获取验证码')",
            "span:has-text('发送验证码')",
            "[class*='send-code']",
            "[class*='verify-btn']",
            "[class*='code-btn']",
        ])

        if not sms_btn:
            await self._save_debug(page, "no_sms_btn")
            logger.error("[deepseek] 未找到获取验证码按钮")
            return False

        logger.info("[deepseek] 点击获取验证码")
        await sms_btn.click()
        await page.wait_for_timeout(random.randint(2000, 3000))

        # 处理可能出现的 CAPTCHA
        await self._handle_captcha(page)
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

        # Fallback: 找到所有 input，排除手机号输入框，取第二个
        if not code_input:
            inputs = await page.query_selector_all(
                "input[type='text'], input[type='tel'], input[type='number']"
            )
            if len(inputs) >= 2:
                code_input = inputs[1]
                logger.info("[deepseek] 使用 fallback: 第二个 input 作为验证码输入框")

        if not code_input:
            await self._save_debug(page, "no_code_input")
            logger.error("[deepseek] 未找到验证码输入框")
            return False

        logger.info(f"[deepseek] 输入验证码: {code}")
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
            "button:has-text('提交')",
            "button[type='submit']",
            "[class*='submit']",
            "[class*='login-btn']",
        ])

        if submit_btn:
            logger.info("[deepseek] 点击提交按钮")
            await submit_btn.click()
            return True

        logger.warning("[deepseek] 未找到提交按钮")
        return False

    async def verify_success(self, page: Page) -> bool:
        """
        验证登录是否成功。
        成功后应进入聊天界面，检查 textarea 或 chat input 出现。
        """
        await page.wait_for_timeout(5000)

        # 检查聊天输入框
        chat_input = await self._find_element(page, [
            "textarea",
            "[contenteditable='true']",
            "[class*='chat-input']",
            "[id*='chat-input']",
        ])
        if chat_input:
            logger.info("[deepseek] 登录成功，聊天输入框已出现")
            return True

        # 再等一会，SPA 可能需要额外加载时间
        await page.wait_for_timeout(5000)

        # 处理可能的登录后 CAPTCHA
        await self._handle_captcha(page)
        await page.wait_for_timeout(2000)

        chat_input = await self._find_element(page, [
            "textarea",
            "[contenteditable='true']",
            "[class*='chat-input']",
            "[id*='chat-input']",
        ])
        if chat_input:
            logger.info("[deepseek] 登录成功（延迟检测）")
            return True

        # 检查是否有登录按钮消失（说明已登录）
        login_btn = await self._find_element(page, [
            "button:has-text('Log In')",
            "button:has-text('登录')",
        ])
        if not login_btn:
            logger.info("[deepseek] 登录成功（登录按钮已消失）")
            return True

        await self._save_debug(page, "verify_failed")
        logger.error(f"[deepseek] 登录验证失败, URL: {page.url}")
        return False

    # ── 辅助方法 ────────────────────────────────────────────────────────

    async def _save_debug(self, page: Page, suffix: str) -> None:
        """保存截图和 HTML 用于调试"""
        try:
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
