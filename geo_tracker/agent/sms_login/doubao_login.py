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
    sms_keyword = "豆包"
    login_url = "https://www.doubao.com/chat"

    # ── 抽象方法实现 ────────────────────────────────────────────────────

    async def navigate_to_login(self, page: Page) -> bool:
        """
        等待页面 SPA 完全渲染，然后点击登录按钮触发 modal。
        豆包是重型 React SPA，JS 渲染登录按钮需要额外时间。

        策略：
        1. 优先等 data-testid 匹配的按钮
        2. 若 data-testid 未出现 / 点击后 modal 未弹，枚举所有 "登录" 文本候选
        3. 逐个点击，直到 modal 出现
        """
        logger.info(f"[doubao] 当前 URL: {page.url}")

        # 检查登录 modal 是否已经弹出
        modal = await page.query_selector("[data-testid='login_content']")
        if modal:
            logger.info("[doubao] 登录 modal 已存在")
            return await self._handle_agreement(page)

        # 先等页面稳定（等任何"登录"字样的可点击元素出现即可）
        try:
            await page.wait_for_selector(
                "[data-testid='to_login_button'], "
                "[data-testid='login_button'], "
                "[data-testid='header_login_button'], "
                "button:has-text('登录'), a:has-text('登录'), "
                "[role='button']:has-text('登录')",
                timeout=20000,
            )
        except Exception:
            logger.info("[doubao] 20s 内未检测到任何 '登录' 元素，继续尝试枚举")

        # 收集所有候选登录按钮（按优先级排序）
        candidates = await self._collect_login_candidates(page)

        if not candidates:
            await self._save_debug(page, "no_login_btn")
            debug_info = await page.evaluate("""
                () => {
                    const items = [...document.querySelectorAll('button, a, [role="button"]')]
                        .filter(e => e.getBoundingClientRect().width > 0)
                        .map(e => {
                            const r = e.getBoundingClientRect();
                            return `${e.tagName} "${(e.textContent||'').trim().slice(0,30)}" (${Math.round(r.x)},${Math.round(r.y)}) data-testid="${e.getAttribute('data-testid')||''}"`;
                        });
                    return items.join('\\n');
                }
            """)
            logger.error(f"[doubao] 未找到登录按钮候选，页面可点击元素:\n{debug_info}")
            return False

        logger.info(f"[doubao] 收集到 {len(candidates)} 个候选登录按钮")
        for i, (label, _el, pos) in enumerate(candidates, 1):
            logger.info(
                f"[doubao]   #{i}: {label} @ ({pos[0]}, {pos[1]})"
            )

        # 已试过的候选签名 —— 点击后若 DOM 重置需要重新收集，避免重复点同一个
        tried_keys: set[str] = set()

        for attempt in range(1, len(candidates) + 1):
            # 找出一个还没试过的候选
            current = None
            for label, el, pos in candidates:
                try:
                    key = await el.evaluate("e => (e.outerHTML || '').slice(0, 200)")
                except Exception:
                    key = f"{label}@{pos}"
                if key in tried_keys:
                    continue
                current = (label, el, key)
                break

            if current is None:
                break  # 所有候选都试过了

            label, btn, key = current
            tried_keys.add(key)
            logger.info(f"[doubao] 尝试 #{attempt}: {label}")

            pre_url = page.url
            try:
                await btn.click(timeout=5000)
            except Exception as e:
                logger.warning(f"[doubao] 点击 {label} 失败: {e}")
                continue

            # 1) modal 成功弹出 → 完成
            if await self._check_modal(page):
                logger.info(f"[doubao] {label} 触发 modal 成功")
                return await self._handle_agreement(page)

            # 2) 没弹 modal：检查是否导致页面导航 / SPA 路由变化 / DOM 重置
            navigated = page.url != pre_url
            dom_reset = await self._dom_reset(page)

            if navigated or dom_reset:
                logger.warning(
                    f"[doubao] {label} 点击后 "
                    f"{'导航至 ' + page.url if navigated else 'DOM 被重置'}，"
                    f"返回 {self.login_url} 重新收集候选"
                )
                try:
                    await page.goto(
                        self.login_url, wait_until="load", timeout=60000
                    )
                    await page.wait_for_timeout(random.randint(3000, 5000))
                except Exception as e:
                    logger.warning(f"[doubao] 重新加载失败: {e}")
                    continue

                # 重新收集候选（DOM 已变，旧 handle 失效）
                candidates = await self._collect_login_candidates(page)
                logger.info(
                    f"[doubao] 重新收集到 {len(candidates)} 个候选（已排除 {len(tried_keys)} 个试过的）"
                )
            else:
                logger.info(f"[doubao] {label} 点击无效（页面未变），尝试下一个")

        # 所有候选均失败
        await self._save_debug(page, "modal_timeout")
        logger.error("[doubao] 所有候选登录按钮均未能触发 modal")
        return False

    async def _dom_reset(self, page: Page) -> bool:
        """
        判断点击后 DOM 是否被重置（React 应用卸载 / SPA 路由切换等）。
        简单启发：body 内可点击元素数量锐减到个位数 = 重置了。
        """
        try:
            count = await page.evaluate(
                "() => document.querySelectorAll('button, a, [role=\"button\"]').length"
            )
            return count < 3
        except Exception:
            return False

    async def _collect_login_candidates(
        self, page: Page
    ) -> list[tuple[str, object, tuple[int, int]]]:
        """
        收集所有"可能是登录入口"的可见元素。

        返回 [(label, handle, (x, y)), ...]，按以下策略排序：
          1. 优先级：data-testid > 精确 "登录" 文本 > 含 "登录" 的短文本
          2. 同优先级内：先上后下、先右后左（登录按钮通常在右上角）

        `<a>` 标签放在 button 之后，避免优先点击会触发 SPA 路由跳转的链接。
        """
        seen_keys: set[str] = set()
        # (priority, is_anchor, -x, y, label, el, pos)
        # 右边越大 -x 越小；故 -x 升序 = x 降序 = 右边优先
        results: list[tuple] = []

        try:
            viewport = await page.evaluate(
                "() => ({w: window.innerWidth, h: window.innerHeight})"
            )
        except Exception:
            viewport = {"w": 1920, "h": 1080}

        async def _add(label: str, el, priority: int) -> None:
            if el is None:
                return
            try:
                if not await el.is_visible():
                    return
                box = await el.bounding_box()
                if not box or box["width"] == 0 or box["height"] == 0:
                    return
                x = int(box["x"])
                y = int(box["y"])
                # 超过屏幕太远 (y > 屏高 * 0.6) 的不是 header login
                if y > viewport["h"] * 0.7:
                    return
                key = await el.evaluate("e => (e.outerHTML || '').slice(0, 200)")
                if key in seen_keys:
                    return
                seen_keys.add(key)
                is_anchor = await el.evaluate(
                    "e => e.tagName === 'A' && e.hasAttribute('href') ? 1 : 0"
                )
                results.append(
                    (priority, is_anchor, -x, y, label, el, (x, y))
                )
            except Exception:
                pass

        # Priority 0: 明确的 data-testid
        for tid in ("to_login_button", "login_button", "header_login_button"):
            el = await page.query_selector(f"[data-testid='{tid}']")
            await _add(f"data-testid={tid}", el, 0)

        # Priority 1: 精确文本匹配（避免 "登录后查看..." 之类长文本）
        exact_texts = ["登录", "登录/注册", "登录 / 注册", "立即登录", "去登录"]
        for text in exact_texts:
            try:
                loc = page.locator(
                    f"button:text-is('{text}'), "
                    f"a:text-is('{text}'), "
                    f"[role='button']:text-is('{text}')"
                )
                count = await loc.count()
                for i in range(count):
                    el = await loc.nth(i).element_handle()
                    await _add(f"text-is={text!r}[{i}]", el, 1)
            except Exception:
                continue

        # Priority 2: 包含 "登录" 的短文本（< 10 字符）
        try:
            loc = page.locator(
                "button:has-text('登录'), a:has-text('登录'), "
                "[role='button']:has-text('登录')"
            )
            count = await loc.count()
            for i in range(count):
                el = await loc.nth(i).element_handle()
                if not el:
                    continue
                try:
                    text = (await el.text_content() or "").strip()
                    if len(text) > 10:
                        continue
                except Exception:
                    continue
                await _add(f"has-text=登录[{i}] ({text!r})", el, 2)
        except Exception:
            pass

        # 排序：priority → 非 anchor 优先 → x 降序 (右边) → y 升序 (上边)
        results.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
        return [(r[4], r[5], r[6]) for r in results]

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
        """保存截图、HTML 和关键页面状态用于调试"""
        try:
            import time
            ts = int(time.time())
            # 页面状态信息（URL / 标题 / 可点击元素数 / body 前 500 字）
            try:
                state = await page.evaluate("""
                    () => ({
                        url: location.href,
                        title: document.title,
                        clickableCount: document.querySelectorAll(
                            'button, a, [role="button"]'
                        ).length,
                        bodyTextHead: (document.body?.innerText || '').slice(0, 500),
                    })
                """)
                logger.info(
                    f"[doubao] 调试状态({suffix}): "
                    f"url={state['url']} title={state['title']!r} "
                    f"clickable={state['clickableCount']}"
                )
                logger.info(
                    f"[doubao] body 文本 (前 500 字): {state['bodyTextHead']!r}"
                )
            except Exception:
                pass

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
