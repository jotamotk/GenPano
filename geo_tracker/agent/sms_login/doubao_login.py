"""
豆包 (doubao.com) SMS 登录处理器

登录流程（基于实际页面 HTML）：
1. 打开 doubao.com/chat
2. 点击右上角 "登录" 按钮 → 弹出登录 modal（不跳转页面）
3. 勾选协议 checkbox
4. 输入手机号
5. 点击 "下一步" → 发送验证码
6. 输入验证码 → 完成登录
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


@register("doubao")
class DoubaoLoginHandler(BaseSMSLoginHandler):
    platform = "doubao"
    service_id_env = "LUBANSMS_PROJECT_DOUBAO"
    login_url = "https://www.doubao.com/chat"

    # ── 抽象方法实现 ────────────────────────────────────────────────────

    async def navigate_to_login(self, page: Page) -> bool:
        """
        触发登录 modal 弹出。

        豆包现在允许游客直接访问聊天页，页面上没有明显的"登录"文字按钮。
        登录入口可能是：
        1. 右上角无文字的头像/图标按钮
        2. 某个隐藏的登录链接
        3. 通过发送消息触发登录弹窗
        """
        # 先保存页面加载后的状态，便于调试
        await self._save_debug(page, "page_loaded")
        logger.info(f"[doubao] 当前 URL: {page.url}")

        # 检查登录 modal 是否已经弹出
        modal = await page.query_selector("[data-testid='login_content']")
        if modal:
            logger.info("[doubao] 登录 modal 已存在")
            return await self._handle_agreement(page)

        # 策略 1: data-testid 选择器
        login_btn = await page.query_selector("[data-testid='to_login_button']")
        if login_btn:
            logger.info("[doubao] 点击 to_login_button")
            await login_btn.click()
            await page.wait_for_timeout(2000)
            if await self._check_modal(page):
                return await self._handle_agreement(page)

        # 策略 2: 点击右上角头像/用户区域（空文字按钮或头像图标）
        # 豆包游客模式下，登录入口是右上角的头像区域
        clicked = await page.evaluate("""
            () => {
                // 查找所有可点击元素中包含"登录"的
                const allEls = document.querySelectorAll(
                    'button, [role="button"], a, div[class*="login"], ' +
                    'div[class*="avatar"], div[class*="user"], span[class*="login"]'
                );
                for (const el of allEls) {
                    const text = (el.textContent || '').trim();
                    if (text === '登录' || text === '登录/注册' || text === '注册/登录') {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            el.click();
                            return `clicked_login_text: ${el.tagName}.${el.className.slice(0,50)} "${text}"`;
                        }
                    }
                }

                // 查找头像区域 —— 通常在页面右上角的空文字按钮
                const buttons = [...document.querySelectorAll('button')];
                for (const btn of buttons) {
                    const text = (btn.textContent || '').trim();
                    const rect = btn.getBoundingClientRect();
                    // 空文字按钮，在右上角区域（x > 页面宽度一半，y < 100）
                    if (text === '' && rect.width > 0 && rect.x > window.innerWidth / 2 && rect.y < 100) {
                        btn.click();
                        return `clicked_avatar: button at (${Math.round(rect.x)},${Math.round(rect.y)}) ${Math.round(rect.width)}x${Math.round(rect.height)} class="${btn.className.slice(0,80)}"`;
                    }
                }

                // 列出所有按钮和链接供调试
                const debug = buttons.map(b => {
                    const r = b.getBoundingClientRect();
                    return `"${(b.textContent||'').trim().slice(0,20)}" pos=(${Math.round(r.x)},${Math.round(r.y)}) ${Math.round(r.width)}x${Math.round(r.height)} class="${(b.className||'').slice(0,40)}"`;
                });
                return `no_match. all_buttons=[${debug.join(' | ')}]`;
            }
        """)
        logger.info(f"[doubao] JS 查找结果: {clicked}")

        if clicked and clicked.startswith("clicked"):
            await page.wait_for_timeout(3000)
            if await self._check_modal(page):
                return await self._handle_agreement(page)
            # 可能点开了用户菜单，查找菜单里的"登录"选项
            menu_clicked = await page.evaluate("""
                () => {
                    const items = document.querySelectorAll(
                        '[role="menuitem"], [role="option"], ' +
                        'div[class*="menu"] a, div[class*="menu"] div, ' +
                        'div[class*="dropdown"] a, div[class*="popover"] a'
                    );
                    for (const el of items) {
                        const text = (el.textContent || '').trim();
                        if (text.includes('登录') || text.includes('注册')) {
                            el.click();
                            return `clicked_menu_item: "${text}"`;
                        }
                    }
                    return 'no_menu_login';
                }
            """)
            logger.info(f"[doubao] 菜单查找结果: {menu_clicked}")
            if menu_clicked.startswith("clicked"):
                await page.wait_for_timeout(2000)
                if await self._check_modal(page):
                    return await self._handle_agreement(page)

        # 策略 3: 尝试在聊天框输入内容触发登录弹窗
        # 有些平台在游客尝试发消息时会弹出登录
        logger.info("[doubao] 尝试通过发送消息触发登录弹窗")
        try:
            textarea = await page.query_selector(
                "textarea, [contenteditable='true'], "
                "[data-testid='chat_input_input']"
            )
            if textarea:
                await textarea.click()
                await page.keyboard.type("hello", delay=100)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(3000)
                if await self._check_modal(page):
                    logger.info("[doubao] 发送消息后登录 modal 弹出")
                    return await self._handle_agreement(page)
        except Exception as e:
            logger.warning(f"[doubao] 发消息触发登录失败: {e}")

        # 策略 4: 直接导航到 passport 登录页
        logger.info("[doubao] 尝试直接跳转到 passport 登录页")
        try:
            await page.goto(
                "https://www.doubao.com/chat/login",
                wait_until="domcontentloaded", timeout=15000,
            )
            await page.wait_for_timeout(3000)
            if await self._check_modal(page):
                return await self._handle_agreement(page)
        except Exception:
            pass

        # 所有策略失败
        await self._save_debug(page, "all_strategies_failed")
        logger.error("[doubao] 所有登录触发策略均失败")
        return False

    async def _check_modal(self, page: Page) -> bool:
        """检查登录 modal 是否出现"""
        try:
            modal = await page.wait_for_selector(
                "[data-testid='login_content']", timeout=5000
            )
            if modal:
                logger.info("[doubao] 登录 modal 已弹出")
                return True
        except Exception:
            pass
        return False

    async def _handle_agreement(self, page: Page) -> bool:
        """勾选协议 checkbox"""
        try:
            checkbox = await page.query_selector(
                "[data-testid='login_agreement_check']"
            )
            if checkbox:
                state = await checkbox.get_attribute("data-state")
                if state != "checked":
                    logger.info("[doubao] 勾选用户协议")
                    await checkbox.click()
                    await page.wait_for_timeout(500)
        except Exception as e:
            logger.warning(f"[doubao] 勾选协议失败: {e}")
        return True

    async def _save_debug(self, page: Page, suffix: str) -> None:
        """保存截图和 HTML 用于调试"""
        try:
            import time
            ts = int(time.time())
            # 保存截图
            screenshot_path = DEBUG_DIR / f"doubao_{suffix}_{ts}.png"
            await page.screenshot(path=str(screenshot_path), full_page=False)
            logger.info(f"[doubao] 截图已保存: {screenshot_path}")
            # 保存 HTML
            html_path = DEBUG_DIR / f"doubao_{suffix}_{ts}.html"
            html = await page.content()
            html_path.write_text(html[:200000], encoding="utf-8")
            logger.info(f"[doubao] HTML 已保存: {html_path} ({len(html)} bytes)")
        except Exception as e:
            logger.warning(f"[doubao] 保存调试信息失败: {e}")

    async def input_phone(self, page: Page, phone: str) -> bool:
        """在登录 modal 中输入手机号"""
        # LubanSMS 返回 +86xxx 格式，豆包页面只需要纯手机号
        clean_phone = phone.lstrip("+")
        if clean_phone.startswith("86") and len(clean_phone) > 11:
            clean_phone = clean_phone[2:]

        phone_input = await page.query_selector(
            "[data-testid='login_phone_number_input']"
        )
        if not phone_input:
            # fallback
            phone_input = await self._find_element(page, [
                "input[placeholder*='手机']",
                "input[inputmode='decimal']",
                "input[type='text']",
            ])

        if not phone_input:
            logger.error("[doubao] 未找到手机号输入框")
            return False

        logger.info(f"[doubao] 输入手机号: {clean_phone} (原始: {phone})")
        await self._type_slowly(page, phone_input, clean_phone)
        return True

    async def click_send_sms(self, page: Page) -> bool:
        """
        点击"下一步"按钮发送验证码。
        豆包的流程是：输入手机号 → 点下一步 → 发送验证码到手机。
        """
        # 点击 "下一步" 按钮
        next_btn = await page.query_selector(
            "[data-testid='login_next_button']"
        )
        if next_btn:
            # 检查按钮是否可用（需要先勾选协议）
            disabled = await next_btn.get_attribute("disabled")
            if disabled is not None:
                logger.warning("[doubao] 下一步按钮不可用，尝试重新勾选协议")
                checkbox = await page.query_selector(
                    "[data-testid='login_agreement_check']"
                )
                if checkbox:
                    await checkbox.click()
                    await page.wait_for_timeout(500)

            logger.info("[doubao] 点击下一步按钮")
            await next_btn.click()
            await page.wait_for_timeout(random.randint(2000, 3000))

            # 处理可能出现的 CAPTCHA
            await self._handle_captcha(page)
            return True

        logger.warning("[doubao] 未找到下一步按钮")
        return False

    async def input_code(self, page: Page, code: str) -> bool:
        """输入 SMS 验证码"""
        # 点击下一步后可能出现验证码输入框
        code_input = await self._find_element(page, [
            "input[placeholder*='验证码']",
            "input[placeholder*='code']",
            "[data-testid*='code'] input",
            "[data-testid*='verify'] input",
            "input[name*='code']",
            "input[type='number']",
        ])

        # Fallback: modal 内非手机号的 input
        if not code_input:
            inputs = await page.query_selector_all(
                "[data-testid='login_content'] input, "
                ".login-modal input, "
                ".semi-modal input"
            )
            for inp in inputs:
                placeholder = await inp.get_attribute("placeholder") or ""
                testid = await inp.get_attribute("data-testid") or ""
                if "手机" not in placeholder and "phone" not in testid:
                    code_input = inp
                    break

        if not code_input:
            logger.error("[doubao] 未找到验证码输入框")
            return False

        await self._type_slowly(page, code_input, code)
        return True

    async def submit_login(self, page: Page) -> bool:
        """
        提交验证码登录。
        输入验证码后可能有"登录"按钮或自动提交。
        """
        submit_btn = await self._find_element(page, [
            "[data-testid='login_next_button']",
            "button:has-text('登录')",
            "button:has-text('确认')",
            "button:has-text('提交')",
            "button[type='submit']",
        ])
        if submit_btn:
            await submit_btn.click()
            return True

        logger.warning("[doubao] 未找到提交按钮")
        return False

    async def verify_success(self, page: Page) -> bool:
        """
        验证是否成功登录。
        成功后 modal 关闭，页面仍在 doubao.com/chat，
        检查聊天输入框或登录按钮消失。
        """
        await page.wait_for_timeout(5000)

        # 检查登录 modal 是否消失
        modal = await page.query_selector("[data-testid='login_content']")
        if modal:
            visible = await modal.is_visible()
            if visible:
                logger.warning("[doubao] 登录 modal 仍然可见")

        # 检查聊天输入框（登录后应该可用）
        chat_input = await page.query_selector(
            "[data-testid='chat_input_input']"
        )
        if chat_input:
            logger.info("[doubao] 登录成功，聊天输入框已出现")
            return True

        # fallback: 检查 textarea
        textarea = await page.query_selector("textarea")
        if textarea:
            logger.info("[doubao] 登录成功（textarea 可用）")
            return True

        # 检查登录按钮是否还在（如果消失说明已登录）
        login_btn = await page.query_selector(
            "[data-testid='to_login_button']"
        )
        if not login_btn:
            logger.info("[doubao] 登录成功（登录按钮已消失）")
            return True

        # 可能有额外验证
        await self._handle_captcha(page)
        await page.wait_for_timeout(3000)

        chat_input = await page.query_selector(
            "[data-testid='chat_input_input']"
        )
        if chat_input:
            logger.info("[doubao] 登录成功（CAPTCHA 后）")
            return True

        logger.error(f"[doubao] 登录验证失败, URL: {page.url}")
        return False
