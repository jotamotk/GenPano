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

from geo_tracker.agent.response_validation import doubao_auth_state_reason
from geo_tracker.agent.sms_login import register
from geo_tracker.agent.sms_login.base import BaseSMSLoginHandler
from geo_tracker.agent.sms_redaction import mask_phone

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
        等待页面 SPA 完全渲染，然后准备好登录表单。
        豆包 2026 版已不再弹 modal —— 登录表单（+86 输入框 + 下一步）直接
        内联渲染在 /chat 页面底部，所以我们要先检测表单是否已 ready，
        只有未 ready 时才去点 "登录" 按钮触发。

        策略：
        1. 先检测内联登录表单（phone input）是否已经可见 → 直接返回
        2. 否则等 data-testid / 登录文本元素出现
        3. 枚举所有 "登录" 候选，逐个点击，每次点击后再检测表单是否 ready
        """
        logger.info(f"[doubao] 当前 URL: {page.url}")

        # Step 0: 若 cookies 仍有效、账号已经处于登录状态，直接返回成功，
        # 避免把"已登录"误判为"无法打开登录表单"
        if await self._already_logged_in(page):
            logger.info("[doubao] 检测到账号已登录，跳过登录流程")
            return True

        # Step 0.5: 登录表单可能已经内联渲染 —— 先检查 phone input 是否可用
        if await self._login_form_ready(page):
            logger.info("[doubao] 登录表单已就绪（内联渲染，无需点击按钮）")
            return await self._handle_agreement(page)

        # 兼容旧版：检查 modal 容器
        modal = await page.query_selector("[data-testid='login_content']")
        if modal:
            logger.info("[doubao] 登录 modal 已存在")
            return await self._handle_agreement(page)

        # 先等页面稳定（等任何"登录"字样的可点击元素或 phone input 出现）
        try:
            await page.wait_for_selector(
                "[data-testid='login_phone_number_input'], "
                "[data-testid='to_login_button'], "
                "[data-testid='login_button'], "
                "[data-testid='header_login_button'], "
                "button:has-text('登录'), a:has-text('登录'), "
                "[role='button']:has-text('登录')",
                timeout=20000,
            )
        except Exception:
            logger.info("[doubao] 20s 内未检测到任何 '登录' 元素，继续尝试枚举")

        # 等 SPA 可能把 phone input 延迟渲染出来
        if await self._login_form_ready(page):
            logger.info("[doubao] 等待后登录表单已就绪（内联）")
            return await self._handle_agreement(page)

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

            # 1) 登录表单就绪（modal 或内联 phone input）→ 完成
            if await self._check_modal(page):
                logger.info(f"[doubao] {label} 触发登录表单成功")
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

        # 所有候选均失败 —— 最后再尝试一次检测内联表单
        if await self._login_form_ready(page):
            logger.info("[doubao] 候选点击完毕后发现内联登录表单已就绪")
            return await self._handle_agreement(page)

        await self._save_debug(page, "modal_timeout")
        logger.error("[doubao] 所有候选登录按钮均未能就绪登录表单")
        return False

    async def _post_login_auth_failure_reason(self, page: Page) -> str | None:
        body_text = ""
        html = ""
        try:
            body_text = await page.evaluate("document.body?.innerText || ''")
        except Exception:
            pass
        try:
            html = await page.content()
        except Exception:
            pass
        return doubao_auth_state_reason(body_text, html)

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

    async def _already_logged_in(self, page: Page) -> bool:
        """
        判断当前页面是否已经处于登录态。
        特征：
        - 全页严格鉴权状态没有登录/过期/登出运行时信号
        - 聊天输入区的 textarea（placeholder='发消息...'）可见
        - 且页面上没有可见的 '登录' 按钮 / 链接
        这样可以避免在 cookies 仍有效时把账号误当做需要重新登录。
        """
        auth_reason = await self._post_login_auth_failure_reason(page)
        if auth_reason:
            logger.warning(
                "[doubao] existing-cookie auth proof failed: %s",
                auth_reason,
            )
            return False

        try:
            res = await page.evaluate(
                """
                () => {
                    // 1) chat textarea 是否可见
                    const inputs = [...document.querySelectorAll('textarea')];
                    const chatInput = inputs.find(t => {
                        const ph = t.getAttribute('placeholder') || '';
                        const r = t.getBoundingClientRect();
                        return /发消息|Message/i.test(ph) && r.width > 50 && r.height > 10;
                    });
                    if (!chatInput) return { chat: false, loginBtn: false };

                    // 2) 是否还有 '登录' 按钮 / 链接可见
                    const clickable = [...document.querySelectorAll(
                        'button, a, [role="button"]'
                    )];
                    const hasLoginBtn = clickable.some(el => {
                        const txt = (el.textContent || '').trim();
                        if (txt !== '登录' && !/^登录$|立即登录|去登录/.test(txt)) return false;
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    });
                    return { chat: true, loginBtn: hasLoginBtn };
                }
                """
            )
            if res and res.get("chat") and not res.get("loginBtn"):
                return True
        except Exception:
            pass
        return False

    async def _login_form_ready(self, page: Page) -> bool:
        """
        检查登录表单（phone input + 下一步按钮）是否已经可交互。
        豆包新版把登录 UI 直接内联渲染在 /chat 页面，没有 modal 容器。
        """
        try:
            # 首选 data-testid，fallback 到常见占位符 / 输入模式
            phone_input = await page.query_selector(
                "[data-testid='login_phone_number_input'], "
                "input[placeholder*='手机'], "
                "input[inputmode='decimal'][maxlength='11'], "
                "input[maxlength='11'][type='text']"
            )
            if not phone_input:
                return False
            if not await phone_input.is_visible():
                return False
            box = await phone_input.bounding_box()
            if not box or box["width"] < 20 or box["height"] < 10:
                return False
            return True
        except Exception:
            return False

    async def _login_form_is_available(self, page: Page) -> bool:
        if await self._login_form_ready(page):
            return True
        return await super()._login_form_is_available(page)

    async def _check_modal(self, page: Page) -> bool:
        """
        检查登录 UI 是否就绪 —— 兼容两种形态：
        1. 旧版：data-testid='login_content' modal 弹出
        2. 新版：内联 phone input 已可见
        """
        # 新版内联形态先快速检查一次（无需等待）
        if await self._login_form_ready(page):
            logger.info("[doubao] 登录表单已就绪（内联）")
            return True

        # 旧版 modal，等待最多 5s
        try:
            modal = await page.wait_for_selector(
                "[data-testid='login_content']", timeout=5000
            )
            if modal:
                logger.info("[doubao] 登录 modal 已弹出")
                return True
        except Exception:
            pass

        # 5s 内 modal 未现，再查一次内联表单
        return await self._login_form_ready(page)

    async def _handle_agreement(self, page: Page) -> bool:
        """
        勾选 "已阅读并同意" checkbox。

        豆包新版内联表单的 checkbox 不再是 testid=login_agreement_check，
        需要通过多种方式定位：testid / role / 旁边文本 "已阅读并同意" 等。
        """
        checkbox = await self._find_agreement_checkbox(page)
        if not checkbox:
            logger.warning("[doubao] 未找到协议 checkbox（可能已默认勾选）")
            return True

        try:
            # 判断是否已勾选：优先看 data-state / aria-checked / checked 属性
            state = await checkbox.get_attribute("data-state")
            aria_checked = await checkbox.get_attribute("aria-checked")
            is_checked_attr = await checkbox.get_attribute("checked")
            # class 里常出现 "checked" / "active"
            cls = (await checkbox.get_attribute("class")) or ""

            already = (
                state == "checked"
                or aria_checked == "true"
                or is_checked_attr is not None
                or "checked" in cls.lower()
                or "active" in cls.lower()
            )

            if already:
                logger.info("[doubao] 协议已勾选，跳过")
                return True

            logger.info("[doubao] 勾选用户协议")
            try:
                await checkbox.click()
            except Exception as e:
                logger.warning(f"[doubao] 常规点击 checkbox 失败: {e}，尝试 JS click")
                await checkbox.evaluate("el => el.click()")
            await page.wait_for_timeout(500)
        except Exception as e:
            logger.warning(f"[doubao] 勾选协议失败: {e}")
        return True

    async def _find_agreement_checkbox(self, page: Page):
        """多策略定位 '已阅读并同意' checkbox。"""
        # 1) 明确 testid
        for sel in [
            "[data-testid='login_agreement_check']",
            "[data-testid*='agreement']",
            "[data-testid*='protocol']",
        ]:
            el = await page.query_selector(sel)
            if el:
                try:
                    if await el.is_visible():
                        return el
                except Exception:
                    return el

        # 2) 文本 "已阅读并同意" 附近的 checkbox / role=checkbox
        # 注意：豆包 2026 用的是 <button role="checkbox" data-slot="checkbox">
        # 并非真正的 <input type="checkbox">，所以要先找 role / data-slot
        text_selectors = [
            "label:has-text('已阅读并同意') [data-slot='checkbox']",
            "label:has-text('已阅读并同意') [role='checkbox']",
            "label:has-text('已阅读并同意') button[role='checkbox']",
            "label:has-text('已阅读并同意') input[type='checkbox']",
            "[data-slot='checkbox']",
            "button[role='checkbox']",
            "[role='checkbox']",
            "*:has-text('已阅读并同意') >> [data-slot='checkbox']",
            "*:has-text('已阅读并同意') >> [role='checkbox']",
            "*:has-text('已阅读并同意') >> input[type='checkbox']",
        ]
        for sel in text_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    return await loc.element_handle()
            except Exception:
                continue

        # 3) JS 兜底：找 "已阅读并同意" 文本附近的可点击 checkbox 元素
        try:
            handle = await page.evaluate_handle(
                """
                () => {
                    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                    let node;
                    while ((node = walker.nextNode())) {
                        const t = (node.textContent || '').trim();
                        if (t.includes('已阅读') && t.includes('同意')) {
                            // 向上找最近的包含 checkbox 的容器
                            let el = node.parentElement;
                            for (let i = 0; i < 6 && el; i++, el = el.parentElement) {
                                const cb = el.querySelector(
                                    'input[type="checkbox"], [role="checkbox"], '
                                    + '.semi-checkbox, [class*="checkbox" i]'
                                );
                                if (cb && cb.getBoundingClientRect().width > 0) return cb;
                            }
                        }
                    }
                    return null;
                }
                """
            )
            as_element = handle.as_element() if handle else None
            if as_element:
                return as_element
        except Exception:
            pass

        return None

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

            # 保存截图（full_page=True 抓整个 DOM 高度，避免只截半张）
            screenshot_path = DEBUG_DIR / f"doubao_{suffix}_{ts}.png"
            await page.screenshot(path=str(screenshot_path), full_page=True)
            logger.info(f"[doubao] 截图已保存: {screenshot_path}")

            # 保存 body HTML（跳过 head 大脚本 chunk，只留渲染后的 DOM）
            try:
                body_html = await page.evaluate(
                    "() => document.body ? document.body.outerHTML : ''"
                )
            except Exception:
                body_html = ""
            html_path = DEBUG_DIR / f"doubao_{suffix}_{ts}.html"
            html_path.write_text(body_html[:400000], encoding="utf-8")
            logger.info(
                f"[doubao] body HTML 已保存: {html_path} ({len(body_html)} bytes)"
            )

            # 额外抓取：所有 input / 候选登录容器 / 含 '登录' 或 '手机' 字样的块
            try:
                snippet = await page.evaluate("""
                    () => {
                        const pick = el => {
                            const r = el.getBoundingClientRect();
                            return {
                                tag: el.tagName,
                                id: el.id || '',
                                cls: (el.className || '').toString().slice(0, 80),
                                testid: el.getAttribute('data-testid') || '',
                                placeholder: el.getAttribute('placeholder') || '',
                                type: el.getAttribute('type') || '',
                                name: el.getAttribute('name') || '',
                                inputmode: el.getAttribute('inputmode') || '',
                                maxlength: el.getAttribute('maxlength') || '',
                                text: (el.textContent || '').trim().slice(0, 60),
                                rect: [Math.round(r.x), Math.round(r.y),
                                       Math.round(r.width), Math.round(r.height)],
                                visible: r.width > 0 && r.height > 0,
                            };
                        };
                        const inputs = [...document.querySelectorAll('input, textarea')]
                            .map(pick);
                        const testids = [...document.querySelectorAll('[data-testid]')]
                            .filter(e => /login|phone|mobile|sms|verify|agreement|next/i
                                .test(e.getAttribute('data-testid') || ''))
                            .map(pick);
                        const buttons = [...document.querySelectorAll('button, [role="button"]')]
                            .filter(e => /登录|下一步|发送|获取验证码|确认/.test(e.textContent || ''))
                            .map(pick);
                        return {inputs, testids, buttons};
                    }
                """)
                import json
                snippet_path = DEBUG_DIR / f"doubao_{suffix}_{ts}.snapshot.json"
                snippet_path.write_text(
                    json.dumps(snippet, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                logger.info(
                    f"[doubao] DOM 快照已保存: {snippet_path} "
                    f"(inputs={len(snippet.get('inputs',[]))} "
                    f"testids={len(snippet.get('testids',[]))} "
                    f"buttons={len(snippet.get('buttons',[]))})"
                )
                # 把关键信息直接打到日志里，方便不取文件也能看
                logger.info(f"[doubao] inputs: {snippet.get('inputs')!r}")
                logger.info(f"[doubao] login-related testids: {snippet.get('testids')!r}")
            except Exception as e:
                logger.warning(f"[doubao] 抓取 DOM 快照失败: {e}")
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

        logger.info(
            f"[doubao] 输入手机号: {mask_phone(clean_phone)} "
            f"(原始: {mask_phone(phone)})"
        )
        await self._type_slowly(page, phone_input, clean_phone)
        return True

    async def click_send_sms(self, page: Page) -> bool:
        """
        点击"下一步"按钮发送验证码。
        豆包的流程是：输入手机号 → 点下一步 → 发送验证码到手机。

        2026 版按钮有多种可能形态：
          - [data-testid='login_next_button']
          - <button> 文本为 "下一步" / "发送验证码" / "获取验证码"
          - 某些实验组为 role=button 的 div
        这里用多轮轮询 + 多 selector，并在失败前 dump 页面调试信息。
        """
        # 点击下一步前，先确保 "已阅读并同意" 协议 checkbox 已勾选，
        # 否则按钮会一直是 disabled 状态
        await self._handle_agreement(page)

        next_btn = None
        # 按钮可能在手机号校验通过后才变 enabled，做几轮轮询
        for attempt in range(6):
            next_btn = await self._find_next_button(page)
            if next_btn:
                break
            await page.wait_for_timeout(500)

        if not next_btn:
            logger.warning("[doubao] 未找到下一步按钮")
            await self._dump_buttons(page, "no_next_button")
            await self._save_debug(page, "no_next_button")
            return False

        # 检查按钮是否可用（需要先勾选协议）
        async def _is_disabled(btn) -> bool:
            try:
                disabled_attr = await btn.get_attribute("disabled")
                data_disabled = await btn.get_attribute("data-disabled")
                aria_disabled = await btn.get_attribute("aria-disabled")
                cls = (await btn.get_attribute("class")) or ""
                return (
                    disabled_attr is not None
                    or data_disabled == "true"
                    or aria_disabled == "true"
                    or "disabled" in cls.lower()
                    or "cursor-not-allowed" in cls.lower()
                )
            except Exception:
                return False

        is_disabled = await _is_disabled(next_btn)

        if is_disabled:
            logger.warning("[doubao] 下一步按钮不可用，尝试重新勾选协议")
            await self._handle_agreement(page)
            # 等待按钮 enable（最多 ~3s）
            for _ in range(6):
                await page.wait_for_timeout(500)
                refreshed = await self._find_next_button(page)
                if refreshed:
                    next_btn = refreshed
                if not await _is_disabled(next_btn):
                    is_disabled = False
                    break
            if is_disabled:
                logger.warning(
                    "[doubao] 下一步按钮仍 disabled，强制尝试点击"
                )

        logger.info("[doubao] 点击下一步按钮")
        try:
            await next_btn.click()
        except Exception as e:
            logger.warning(f"[doubao] 常规点击失败: {e}，尝试 JS click")
            try:
                await next_btn.evaluate("el => el.click()")
            except Exception as e2:
                logger.error(f"[doubao] JS click 亦失败: {e2}")
                await self._save_debug(page, "next_click_failed")
                return False
        await page.wait_for_timeout(random.randint(2000, 3000))

        # 处理可能出现的 CAPTCHA
        await self._handle_captcha(page)
        return True

    async def _find_next_button(self, page: Page):
        """寻找"下一步 / 发送验证码"按钮。优先 testid，其次文本匹配。"""
        # 1) 明确的 testid
        el = await page.query_selector("[data-testid='login_next_button']")
        if el:
            try:
                if await el.is_visible():
                    return el
            except Exception:
                return el

        # 2) Playwright :has-text + role=button
        text_selectors = [
            "button:has-text('下一步')",
            "button:has-text('发送验证码')",
            "button:has-text('获取验证码')",
            "button:has-text('发送短信')",
            "[role='button']:has-text('下一步')",
            "[role='button']:has-text('发送验证码')",
            "[role='button']:has-text('获取验证码')",
        ]
        for sel in text_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    return await loc.element_handle()
            except Exception:
                continue

        # 3) 兜底：遍历所有 button / role=button，按文本匹配
        try:
            handle = await page.evaluate_handle(
                """
                () => {
                    const re = /(下一步|发送验证码|获取验证码|发送短信)/;
                    const nodes = [...document.querySelectorAll('button, [role="button"]')];
                    for (const n of nodes) {
                        const txt = (n.textContent || '').trim();
                        const r = n.getBoundingClientRect();
                        if (re.test(txt) && r.width > 0 && r.height > 0) return n;
                    }
                    return null;
                }
                """
            )
            as_element = handle.as_element() if handle else None
            if as_element:
                return as_element
        except Exception:
            pass

        return None

    async def _dump_buttons(self, page: Page, label: str) -> None:
        """把当前页面上所有可见按钮的文本/testid 打到日志，方便远程排查。"""
        try:
            btns = await page.evaluate(
                """
                () => [...document.querySelectorAll('button, [role="button"]')]
                    .map(e => {
                        const r = e.getBoundingClientRect();
                        return {
                            text: (e.textContent || '').trim().slice(0, 30),
                            testid: e.getAttribute('data-testid') || '',
                            disabled: e.hasAttribute('disabled') || e.getAttribute('aria-disabled') === 'true' || e.getAttribute('data-disabled') === 'true',
                            visible: r.width > 0 && r.height > 0,
                            x: Math.round(r.x), y: Math.round(r.y),
                        };
                    })
                    .filter(b => b.visible)
                    .slice(0, 30)
                """
            )
            logger.warning(f"[doubao] [{label}] 可见按钮 {len(btns)} 个:")
            for b in btns:
                logger.warning(
                    f"[doubao]   '{b['text']}' testid='{b['testid']}' "
                    f"disabled={b['disabled']} @ ({b['x']},{b['y']})"
                )
        except Exception as e:
            logger.warning(f"[doubao] dump buttons 失败: {e}")

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
            try:
                await submit_btn.click()
                return True
            except Exception as e:
                message = str(e)
                if "not attached to the DOM" in message:
                    logger.warning(
                        "[doubao] submit button detached after click; "
                        "checking whether login already continued"
                    )
                    await page.wait_for_timeout(1500)
                    auth_reason = await self._post_login_auth_failure_reason(page)
                    if not auth_reason:
                        logger.info(
                            "[doubao] submit click detached during page update; "
                            "continuing to login verification"
                        )
                        return True
                    logger.warning(
                        "[doubao] submit click detached but auth proof still failed: %s",
                        auth_reason,
                    )
                else:
                    logger.warning(f"[doubao] submit button click failed: {e}")
                return False

        logger.warning("[doubao] 未找到提交按钮")
        return False

    async def verify_success(self, page: Page) -> bool:
        """
        验证是否成功登录。
        成功后 modal 关闭，页面仍在 doubao.com/chat，
        检查聊天输入框或登录按钮消失。

        Refs #963: the previous proof-of-login here was too permissive — a
        chat input element is also visible on Doubao 2026's logged-out
        landing page (so guests can preview the input before the login
        modal opens), so finding it did not actually prove a session had
        been established. The SMS reauth flow could "succeed" by writing
        cookies that the very next ``execute_query`` page load then
        rejected as ``doubao_not_logged_in``, producing the
        ``doubao_post_reauth_doubao_not_logged_in`` failure observed on
        query 184968 retry 14 after PR #1000 deploy. Mirror the stricter
        check from ``_already_logged_in``: a chat input visible AND no
        visible "登录" button.
        """
        await page.wait_for_timeout(5000)

        # 检查登录 modal 是否消失
        modal = await page.query_selector("[data-testid='login_content']")
        if modal:
            visible = await modal.is_visible()
            if visible:
                logger.warning("[doubao] 登录 modal 仍然可见")

        # 检查聊天输入框（登录后应该可用）。2026 新版 UI 已无 testid，改用稳定 id/class
        auth_reason = await self._post_login_auth_failure_reason(page)
        if auth_reason:
            logger.warning("[doubao] post-login auth proof failed: %s", auth_reason)
            return auth_reason

        # Strict proof-of-login (Refs #963): reuse the same chat-input +
        # no-visible-login-button check we run in _already_logged_in. The
        # plain-text "登录" button stays visible on the logged-out landing
        # even when the chat input is rendered, so we MUST require its
        # absence before we accept this state as logged-in.
        if await self._already_logged_in(page):
            logger.info("[doubao] 登录成功（strict logged-in proof：chat input + no 登录 button）")
            return True

        # 可能有额外验证（图形验证码 / 滑块）。Handle and re-check.
        await self._handle_captcha(page)
        await page.wait_for_timeout(3000)

        if await self._already_logged_in(page):
            logger.info("[doubao] 登录成功（CAPTCHA 后 strict 校验通过）")
            return True

        logger.error(f"[doubao] 登录验证失败 (strict proof of login not met), URL: {page.url}")
        return False
