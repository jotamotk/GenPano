"""
DeepSeek (chat.deepseek.com) SMS 登录处理器

登录流程：
1. 打开 chat.deepseek.com 首页，模拟浏览行为
2. 点击登录按钮
3. 切换到手机号登录（默认可能是邮箱）
4. 输入手机号 → 点击获取验证码
5. 处理 CAPTCHA（如有）
6. 输入验证码 → 提交登录
7. 验证聊天界面出现

反风控策略：
- 先访问首页模拟浏览（随机滚动+停留），再进入登录页
- 所有点击前先用贝塞尔曲线移动鼠标到元素附近
- 打字速度随机化，模拟真人节奏
- 操作间添加充足的随机延迟
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from pathlib import Path

from playwright.async_api import Page, ElementHandle

from geo_tracker.agent.captcha import CaptchaSolver, detect_and_solve
from geo_tracker.agent.sms_login import register
from geo_tracker.agent.sms_login.base import BaseSMSLoginHandler

logger = logging.getLogger(__name__)

_solver = CaptchaSolver()

DEBUG_DIR = Path(os.getenv("SCREENSHOT_DIR", "/data/screenshots"))
DEBUG_DIR.mkdir(parents=True, exist_ok=True)


@register("deepseek")
class DeepseekLoginHandler(BaseSMSLoginHandler):
    platform = "deepseek"
    sms_keyword = "深度求索"
    login_url = "https://chat.deepseek.com"

    # ── 抽象方法实现 ────────────────────────────────────────────────────

    async def navigate_to_login(self, page: Page) -> bool:
        """
        模拟真人浏览行为后，点击登录按钮并切换到手机号 Tab。
        """
        logger.info(f"[deepseek] 当前 URL: {page.url}")

        # ── 模拟真人浏览行为（降低风控触发）──
        await self._simulate_browsing(page)

        # 检查是否已经在登录页面（DeepSeek 可能直接跳转到 sign_in）
        if "sign_in" in page.url or "login" in page.url:
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
        await self._human_click(page, login_btn)
        await page.wait_for_timeout(random.randint(2500, 4000))

        return await self._switch_to_phone_tab(page)

    async def _switch_to_phone_tab(self, page: Page) -> bool:
        """切换到手机号登录 Tab"""
        # 先停顿一下，像真人在看页面
        await page.wait_for_timeout(random.randint(1000, 2000))

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
            await self._human_click(page, phone_tab)
            await page.wait_for_timeout(random.randint(1000, 2000))
        else:
            logger.info("[deepseek] 未找到手机号 Tab（可能已在手机号模式）")

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
                    await page.wait_for_timeout(random.randint(300, 600))
        except Exception as e:
            logger.warning(f"[deepseek] 勾选协议失败（可能不存在）: {e}")

    async def input_phone(self, page: Page, phone: str) -> bool:
        """输入手机号（模拟真人打字节奏）"""
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
        # 先点击输入框
        await self._human_click(page, phone_input)
        await page.wait_for_timeout(random.randint(300, 600))
        # 用慢速打字
        await self._type_slowly(page, phone_input, clean_phone, delay=random.randint(80, 150))
        # 输入完后停顿，像真人在检查号码
        await page.wait_for_timeout(random.randint(1500, 3000))
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
        await self._human_click(page, sms_btn)
        await page.wait_for_timeout(random.randint(3000, 5000))

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
        await self._human_click(page, code_input)
        await page.wait_for_timeout(random.randint(200, 500))
        await self._type_slowly(page, code_input, code, delay=random.randint(100, 180))
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
            await self._human_click(page, submit_btn)
            return True

        logger.warning("[deepseek] 未找到提交按钮")
        return False

    async def verify_success(self, page: Page) -> bool:
        """验证登录是否成功"""
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

        await page.wait_for_timeout(5000)
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

    # ── CAPTCHA 处理 ──────────────────────────────────────────────────────

    async def _handle_captcha(self, page: Page) -> None:
        """
        检测并处理 DeepSeek 的人机验证（Cloudflare Turnstile/Challenge）。
        DeepSeek 使用 Cloudflare 验证，按优先级尝试：
        1. 提取 sitekey → CapSolver Turnstile 求解
        2. 无 sitekey → CapSolver Cloudflare Challenge 求解
        3. 都失败 → 等待消失
        """
        await self._save_debug(page, "captcha_before")

        if not _solver.enabled:
            logger.warning("[deepseek] CAPSOLVER_API_KEY 未配置，无法自动求解")
            await self._wait_captcha_dismiss(page)
            return

        # ── 检测验证码是否存在 ──
        has_captcha = await page.evaluate("""
            () => {
                // 数美 (Shumei) 验证码 — DeepSeek 实际使用的验证码
                const shumei = document.querySelector(
                    '.shumei_captcha_wrapper, #sm-captcha'
                );
                if (shumei && shumei.offsetParent !== null) {
                    const tips = document.querySelector('.shumei_captcha_slide_tips');
                    const prompt = tips ? tips.textContent.trim() : '';
                    return 'shumei_captcha|' + prompt;
                }

                // Cloudflare iframe
                const cfIframe = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
                if (cfIframe) return 'cloudflare_iframe|' + cfIframe.src;

                // Turnstile widget
                const tw = document.querySelector('[data-sitekey]');
                if (tw) return 'turnstile_widget|' + tw.getAttribute('data-sitekey');

                // 5s 盾
                if (document.title.includes('Just a moment'))
                    return 'challenge_page|' + document.title;

                // 任何 iframe（验证码通常在 iframe 中）
                const iframes = [...document.querySelectorAll('iframe')];
                const captchaIframe = iframes.find(f =>
                    f.src && (f.src.includes('captcha') || f.src.includes('challenge')
                    || f.src.includes('turnstile') || f.src.includes('cloudflare')
                    || f.src.includes('verify'))
                );
                if (captchaIframe) return 'captcha_iframe|' + captchaIframe.src;

                // 通用 CAPTCHA 弹窗 — 收集详细信息用于诊断
                const captchaEl = document.querySelector(
                    '[class*="captcha"]:not([class*="secsdk"]), '
                    + '[class*="geetest"], [class*="verify-wrap"], '
                    + '[class*="shield"], [class*="firewall"]'
                );
                if (captchaEl && captchaEl.offsetParent) {
                    const info = captchaEl.tagName + '.' + captchaEl.className.slice(0, 100);
                    // 查找内部 iframe
                    const innerIframe = captchaEl.querySelector('iframe');
                    if (innerIframe) return 'generic_with_iframe|' + info + '|' + innerIframe.src;
                    return 'generic_captcha|' + info;
                }

                return null;
            }
        """)

        if not has_captcha:
            logger.info("[deepseek] 未检测到验证码")
            return

        # 解析检测结果: "type|detail"
        captcha_type = has_captcha.split("|")[0]
        captcha_detail = "|".join(has_captcha.split("|")[1:]) if "|" in has_captcha else ""
        logger.info(f"[deepseek] 检测到验证码: type={captcha_type}, detail={captcha_detail}")
        await self._save_debug(page, f"captcha_{captcha_type}")

        # ── 策略 0: 数美验证码 — 使用视觉模型求解（最高优先级）──
        if captcha_type == "shumei_captcha":
            try:
                from geo_tracker.agent.vision_captcha import solve_vision_captcha
                logger.info(f"[deepseek] 数美验证码，调用视觉模型求解 (题目: {captcha_detail})")
                solved = await solve_vision_captcha(page, max_retries=3)
                if solved:
                    logger.info("[deepseek] 数美验证码求解成功")
                    await page.wait_for_timeout(random.randint(1000, 2000))
                    return
                logger.warning("[deepseek] 数美验证码求解失败")
            except Exception as e:
                logger.warning(f"[deepseek] 视觉求解异常: {e}")
            await self._wait_captcha_dismiss(page)
            return

        from geo_tracker.agent.captcha import (
            _extract_turnstile_sitekey,
            inject_turnstile_token,
        )

        # ── 策略1: 如果检测到 iframe，尝试从 iframe src 提取 sitekey ──
        site_key = None
        if captcha_detail and ("turnstile" in captcha_detail or "cloudflare" in captcha_detail):
            # 从 iframe URL 参数提取 sitekey
            import re as _re
            m = _re.search(r'[?&](?:sitekey|k)=([^&]+)', captcha_detail)
            if m:
                site_key = m.group(1)
                logger.info(f"[deepseek] 从 iframe URL 提取 sitekey={site_key}")

        # 也用通用提取器
        if not site_key:
            site_key = await _extract_turnstile_sitekey(page)

        if site_key:
            logger.info(f"[deepseek] Turnstile sitekey={site_key}，调用 CapSolver...")
            token = await _solver.solve_turnstile(page.url, site_key)
            if token:
                await inject_turnstile_token(page, token)
                logger.info("[deepseek] Turnstile 求解成功，已注入 token")
                await page.wait_for_timeout(random.randint(2000, 3000))
                return
            logger.warning("[deepseek] Turnstile 求解失败")

        # ── 策略2: Cloudflare Challenge (需要 proxy) ──
        if captcha_type in ("cloudflare_iframe", "challenge_page", "captcha_iframe"):
            proxy = os.getenv("CLASH_PROXY_URL", "")
            if proxy:
                logger.info(f"[deepseek] 尝试 Cloudflare Challenge 求解 (proxy={proxy})...")
                solution = await _solver.solve_cloudflare_challenge(
                    page.url, proxy=proxy
                )
                if solution:
                    cf_clearance = (solution.get("cookies") or {}).get("cf_clearance")
                    token = solution.get("token")
                    if cf_clearance:
                        domain = page.url.split("//")[-1].split("/")[0]
                        await page.context.add_cookies([{
                            "name": "cf_clearance",
                            "value": cf_clearance,
                            "domain": f".{domain}",
                            "path": "/",
                        }])
                        logger.info("[deepseek] Challenge 求解成功，已注入 cf_clearance")
                        await page.reload()
                        await page.wait_for_timeout(random.randint(3000, 5000))
                        return
                    if token:
                        await inject_turnstile_token(page, token)
                        logger.info("[deepseek] Challenge 求解成功，已注入 token")
                        await page.wait_for_timeout(random.randint(2000, 3000))
                        return
                logger.warning("[deepseek] Challenge 求解失败")
            else:
                logger.warning("[deepseek] 跳过 Challenge 求解（未配置代理）")

        # ── 策略3: 视觉模型求解（3D 图形点选验证码）──
        try:
            from geo_tracker.agent.vision_captcha import solve_vision_captcha
            logger.info("[deepseek] 尝试视觉模型求解验证码...")
            solved = await solve_vision_captcha(page, max_retries=3)
            if solved:
                logger.info("[deepseek] 视觉验证码求解成功")
                await page.wait_for_timeout(random.randint(1000, 2000))
                return
        except Exception as e:
            logger.warning(f"[deepseek] 视觉验证码求解异常: {e}")

        # ── 策略4: generic_captcha — 尝试直接用 Turnstile ProxyLess ──
        if captcha_type in ("generic_captcha", "generic_with_iframe"):
            logger.info("[deepseek] generic 类型，尝试 Turnstile ProxyLess (用页面 URL 作为 key)...")
            # 枚举页面中所有 iframe 的 src 以辅助诊断
            all_iframes = await page.evaluate("""
                () => [...document.querySelectorAll('iframe')]
                    .map(f => f.src || '(empty)')
                    .join(' | ')
            """)
            logger.info(f"[deepseek] 页面 iframes: {all_iframes}")

        # ── 最终 fallback: 等待消失 ──
        logger.warning("[deepseek] 所有求解策略失败，等待消失...")
        await self._wait_captcha_dismiss(page)

    async def _wait_captcha_dismiss(self, page: Page) -> None:
        """等待验证码弹窗自动消失或尝试关闭"""
        # 尝试关闭验证码弹窗
        close_btn = await self._find_element(page, [
            "[class*='captcha'] [class*='close']",
            "[class*='verify'] [class*='close']",
            "[class*='captcha'] button:has-text('×')",
        ])
        if close_btn:
            logger.info("[deepseek] 尝试关闭验证码弹窗")
            await close_btn.click()
            await page.wait_for_timeout(random.randint(2000, 3000))
            return

        logger.warning("[deepseek] 等待验证码弹窗消失...")
        try:
            await page.wait_for_function(
                """() => {
                    const els = document.querySelectorAll(
                        '[class*="captcha"], iframe[src*="challenges.cloudflare.com"]'
                    );
                    return [...els].every(el => !el.offsetParent);
                }""",
                timeout=20000,
            )
            logger.info("[deepseek] 验证码弹窗已消失")
        except Exception:
            logger.warning("[deepseek] 验证码弹窗未消失，继续...")

    # ── 拟人行为方法 ──────────────────────────────────────────────────────

    async def _simulate_browsing(self, page: Page) -> None:
        """
        模拟真人浏览行为：随机鼠标移动、滚动、停留。
        在执行登录操作前调用，降低被识别为自动化的概率。
        """
        vp = page.viewport_size or {"width": 1920, "height": 1080}

        # 随机移动鼠标 2-3 次
        for _ in range(random.randint(2, 3)):
            target_x = random.randint(100, vp["width"] - 100)
            target_y = random.randint(100, vp["height"] - 100)
            await self._bezier_move(page, target_x, target_y)
            await asyncio.sleep(random.uniform(0.3, 0.8))

        # 小幅滚动
        scroll_amount = random.randint(100, 300)
        await page.mouse.wheel(0, scroll_amount)
        await asyncio.sleep(random.uniform(1.0, 2.5))

        # 偶尔回滚
        if random.random() < 0.4:
            await page.mouse.wheel(0, -random.randint(50, 150))
            await asyncio.sleep(random.uniform(0.5, 1.0))

        # 停留阅读
        await asyncio.sleep(random.uniform(2.0, 4.0))

    async def _human_click(self, page: Page, element: ElementHandle) -> None:
        """
        模拟真人点击：先移动鼠标到元素位置（贝塞尔曲线），
        短暂停顿后点击。
        """
        try:
            box = await element.bounding_box()
            if box:
                # 目标点在元素范围内随机偏移（不总是正中心）
                target_x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
                target_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
                await self._bezier_move(page, target_x, target_y)
                await asyncio.sleep(random.uniform(0.1, 0.3))
                await page.mouse.click(target_x, target_y)
            else:
                await element.click()
        except Exception:
            await element.click()

    async def _bezier_move(
        self, page: Page, target_x: float, target_y: float
    ) -> None:
        """贝塞尔曲线鼠标移动（自然弧线轨迹）"""
        vp = page.viewport_size or {"width": 1920, "height": 1080}

        # 起点：屏幕中间附近随机位置
        start_x = random.uniform(vp["width"] * 0.2, vp["width"] * 0.8)
        start_y = random.uniform(vp["height"] * 0.2, vp["height"] * 0.8)

        # 两个控制点（产生自然弯曲）
        cp1_x = start_x + random.uniform(-150, 150)
        cp1_y = start_y + random.uniform(-150, 150)
        cp2_x = target_x + random.uniform(-80, 80)
        cp2_y = target_y + random.uniform(-80, 80)

        steps = random.randint(18, 30)
        for i in range(steps + 1):
            t = i / steps
            # 三次贝塞尔插值
            x = ((1 - t) ** 3 * start_x
                 + 3 * (1 - t) ** 2 * t * cp1_x
                 + 3 * (1 - t) * t ** 2 * cp2_x
                 + t ** 3 * target_x)
            y = ((1 - t) ** 3 * start_y
                 + 3 * (1 - t) ** 2 * t * cp1_y
                 + 3 * (1 - t) * t ** 2 * cp2_y
                 + t ** 3 * target_y)
            await page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.008, 0.025))

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
