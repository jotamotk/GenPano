"""
验证码自动处理（通用模块）
支持: Cloudflare Turnstile | Cloudflare Challenge | Arkose Labs |
      reCAPTCHA v2/v3 | hCaptcha | GeeTest v3/v4
使用 CapSolver API — 任何页面遇到人机验证时均可调用

用法:
    from geo_tracker.agent.captcha import CaptchaSolver, detect_and_solve

    solver = CaptchaSolver()          # 读取 CAPSOLVER_API_KEY 环境变量
    solved = await detect_and_solve(page, solver)
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import httpx
from playwright.async_api import Page

logger = logging.getLogger(__name__)

CAPSOLVER_API_KEY = os.getenv("CAPSOLVER_API_KEY", "")
CAPSOLVER_BASE    = "https://api.capsolver.com"
POLL_INTERVAL     = 3    # 秒
MAX_WAIT          = 120  # 秒
CLASH_PROXY_URL   = os.getenv("CLASH_PROXY_URL", "")  # e.g. http://clash:7890


class CaptchaSolver:
    """CapSolver API 统一封装，支持多种验证码类型。"""

    def __init__(self, api_key: str = CAPSOLVER_API_KEY):
        self.api_key = api_key
        self.client  = httpx.AsyncClient(
            timeout=30,
            proxy=CLASH_PROXY_URL if CLASH_PROXY_URL else None,
        )

    @property
    def enabled(self) -> bool:
        """是否已配置 API Key"""
        return bool(self.api_key)

    async def _create_task(self, task: dict) -> Optional[str]:
        resp = await self.client.post(
            f"{CAPSOLVER_BASE}/createTask",
            json={"clientKey": self.api_key, "task": task},
        )
        data = resp.json()
        if data.get("errorId") != 0:
            logger.error(f"CapSolver createTask error: {data.get('errorDescription')}")
            return None
        return data["taskId"]

    async def _get_result(self, task_id: str) -> Optional[dict]:
        """轮询获取结果，返回完整的 solution dict"""
        waited = 0
        while waited < MAX_WAIT:
            await asyncio.sleep(POLL_INTERVAL)
            waited += POLL_INTERVAL

            resp = await self.client.post(
                f"{CAPSOLVER_BASE}/getTaskResult",
                json={"clientKey": self.api_key, "taskId": task_id},
            )
            data = resp.json()

            if data.get("status") == "ready":
                return data.get("solution", {})

            if data.get("errorId") != 0:
                logger.error(f"CapSolver error: {data.get('errorDescription')}")
                return None

        logger.error(f"CapSolver timeout after {MAX_WAIT}s")
        return None

    async def _solve(self, task: dict, label: str) -> Optional[dict]:
        """通用求解：创建任务 → 轮询结果"""
        task_id = await self._create_task(task)
        if not task_id:
            return None
        solution = await self._get_result(task_id)
        if solution:
            token_preview = (solution.get("token") or "")[:30]
            logger.info(f"[capsolver] {label} solved: {token_preview}...")
        else:
            logger.error(f"[capsolver] {label} FAILED")
        return solution

    # ── Cloudflare Turnstile ─────────────────────────────────────────────

    async def solve_turnstile(
        self, page_url: str, site_key: str, action: str = "", cdata: str = ""
    ) -> Optional[str]:
        metadata = {}
        if action:
            metadata["action"] = action
        if cdata:
            metadata["cdata"] = cdata

        task: dict = {
            "type":       "AntiTurnstileTaskProxyLess",
            "websiteURL": page_url,
            "websiteKey": site_key,
        }
        if metadata:
            task["metadata"] = metadata

        solution = await self._solve(task, "Turnstile")
        return solution.get("token") if solution else None

    # ── Cloudflare Challenge (5s 盾) ─────────────────────────────────────

    async def solve_cloudflare_challenge(
        self, page_url: str, proxy: str = "", user_agent: str = ""
    ) -> Optional[dict]:
        """
        返回 {"token": "...", "cookies": {"cf_clearance": "..."}, ...}
        注意: Challenge 类型需要代理
        """
        task: dict = {
            "type":       "AntiCloudflareTask",
            "websiteURL": page_url,
        }
        if proxy:
            task["proxy"] = proxy
        if user_agent:
            task["userAgent"] = user_agent
        return await self._solve(task, "Cloudflare Challenge")

    # ── Arkose Labs FunCaptcha ───────────────────────────────────────────

    async def solve_arkose(
        self, page_url: str, public_key: str, blob: str = ""
    ) -> Optional[str]:
        task: dict = {
            "type":             "FunCaptchaTaskProxyLess",
            "websiteURL":       page_url,
            "websitePublicKey": public_key,
            "funcaptchaApiJSSubdomain": "client-api.arkoselabs.com",
        }
        if blob:
            task["data"] = f'{{"blob":"{blob}"}}'
        solution = await self._solve(task, "Arkose/FunCaptcha")
        return solution.get("token") if solution else None

    # ── reCAPTCHA v2 ─────────────────────────────────────────────────────

    async def solve_recaptcha_v2(
        self, page_url: str, site_key: str
    ) -> Optional[str]:
        solution = await self._solve({
            "type":       "ReCaptchaV2TaskProxyLess",
            "websiteURL": page_url,
            "websiteKey": site_key,
        }, "reCAPTCHA v2")
        return solution.get("gRecaptchaResponse") if solution else None

    # ── reCAPTCHA v3 ─────────────────────────────────────────────────────

    async def solve_recaptcha_v3(
        self, page_url: str, site_key: str, action: str = "verify"
    ) -> Optional[str]:
        solution = await self._solve({
            "type":       "ReCaptchaV3TaskProxyLess",
            "websiteURL": page_url,
            "websiteKey": site_key,
            "pageAction": action,
            "minScore":   0.7,
        }, "reCAPTCHA v3")
        return solution.get("gRecaptchaResponse") if solution else None

    # ── hCaptcha ─────────────────────────────────────────────────────────

    async def solve_hcaptcha(
        self, page_url: str, site_key: str
    ) -> Optional[str]:
        solution = await self._solve({
            "type":       "HCaptchaTaskProxyLess",
            "websiteURL": page_url,
            "websiteKey": site_key,
        }, "hCaptcha")
        return solution.get("gRecaptchaResponse") if solution else None

    # ── GeeTest v3 ───────────────────────────────────────────────────────

    async def solve_geetest_v3(
        self, page_url: str, gt: str, challenge: str
    ) -> Optional[dict]:
        """返回 {"challenge": ..., "validate": ..., "seccode": ...}"""
        return await self._solve({
            "type":       "GeeTestTaskProxyLess",
            "websiteURL": page_url,
            "gt":         gt,
            "challenge":  challenge,
        }, "GeeTest v3")

    # ── GeeTest v4 ───────────────────────────────────────────────────────

    async def solve_geetest_v4(
        self, page_url: str, captcha_id: str
    ) -> Optional[dict]:
        """返回 {"captcha_id": ..., "captcha_output": ..., ...}"""
        return await self._solve({
            "type":       "GeeTestTaskProxyLess",
            "websiteURL": page_url,
            "captchaId":  captcha_id,
            "geetestApiServerSubdomain": "gcaptcha4.geetest.com",
        }, "GeeTest v4")

    async def close(self) -> None:
        await self.client.aclose()


# ─── Playwright 页面注入工具函数 ──────────────────────────────────────────────

async def inject_turnstile_token(page: Page, token: str) -> None:
    """将 Turnstile token 注入页面并触发回调"""
    await page.evaluate("""
        (token) => {
            // 方式1: 隐藏 input
            const input = document.querySelector(
                '[name="cf-turnstile-response"], [name="cf-chl-widget-response"]'
            );
            if (input) input.value = token;

            // 方式2: 调用 Turnstile 全局回调
            if (window.turnstile && window.turnstile.getResponse) {
                // Turnstile widget 已加载
                const widgets = document.querySelectorAll('[data-sitekey]');
                widgets.forEach(w => {
                    const widgetId = w.getAttribute('data-turnstile-id');
                    if (widgetId) {
                        try { window.turnstile.remove(widgetId); } catch(e) {}
                    }
                });
            }

            // 方式3: 触发自定义回调
            if (window.turnstileCallback) window.turnstileCallback(token);
            if (window.onTurnstileSuccess) window.onTurnstileSuccess(token);

            // 方式4: dispatch event 让框架感知变化
            const evt = new Event('input', { bubbles: true });
            if (input) input.dispatchEvent(evt);
        }
    """, token)


async def inject_recaptcha_token(page: Page, token: str) -> None:
    """将 reCAPTCHA token 注入页面"""
    await page.evaluate("""
        (token) => {
            const el = document.getElementById('g-recaptcha-response');
            if (el) { el.value = token; el.style.display = 'none'; }
            // v3 回调
            if (window.grecaptcha && window.grecaptcha.execute) return;
            // 自定义回调
            if (window.onRecaptchaSuccess) window.onRecaptchaSuccess(token);
        }
    """, token)


async def inject_hcaptcha_token(page: Page, token: str) -> None:
    """将 hCaptcha token 注入页面"""
    await page.evaluate("""
        (token) => {
            const el = document.querySelector('[name="h-captcha-response"]');
            if (el) el.value = token;
            const el2 = document.querySelector('[name="g-recaptcha-response"]');
            if (el2) el2.value = token;
            if (window.hcaptcha) {
                try { window.hcaptcha.execute(); } catch(e) {}
            }
        }
    """, token)


# ─── 通用自动检测 & 求解 ─────────────────────────────────────────────────────

async def detect_and_solve(page: Page, solver: CaptchaSolver) -> bool:
    """
    自动检测页面上的验证码类型并求解。
    返回 True 表示处理成功或无验证码。

    支持检测顺序:
    1. Cloudflare Turnstile (widget / iframe)
    2. Cloudflare Challenge (5s 盾页面)
    3. hCaptcha
    4. reCAPTCHA v2/v3
    5. GeeTest
    6. 字节跳动/火山引擎验证
    """
    if not solver.enabled:
        logger.warning("[capsolver] CAPSOLVER_API_KEY 未配置，跳过自动求解")
        return False

    url = page.url

    # ── 1. Cloudflare Turnstile ──────────────────────────────────────────
    site_key = await _extract_turnstile_sitekey(page)
    if site_key:
        logger.info(f"[capsolver] 检测到 Turnstile sitekey={site_key}")
        token = await solver.solve_turnstile(url, site_key)
        if token:
            await inject_turnstile_token(page, token)
            await page.wait_for_timeout(2000)
            return True
        return False

    # ── 2. Cloudflare Challenge (5s 盾) ──────────────────────────────────
    is_challenge = await page.evaluate("""
        () => document.title.includes('Just a moment')
           || document.title.includes('Attention Required')
           || !!document.getElementById('challenge-running')
    """)
    if is_challenge:
        logger.info("[capsolver] 检测到 Cloudflare Challenge (5s 盾)")
        solution = await solver.solve_cloudflare_challenge(url)
        if solution and solution.get("cookies"):
            cf_clearance = solution["cookies"].get("cf_clearance", "")
            if cf_clearance:
                domain = url.split("//")[-1].split("/")[0]
                await page.context.add_cookies([{
                    "name": "cf_clearance",
                    "value": cf_clearance,
                    "domain": f".{domain}",
                    "path": "/",
                }])
                await page.reload()
                await page.wait_for_timeout(3000)
                return True
        return False

    # ── 3. hCaptcha ──────────────────────────────────────────────────────
    hcaptcha = await page.query_selector(
        "[data-sitekey].h-captcha, iframe[src*='hcaptcha.com']"
    )
    if hcaptcha:
        hc_key = await _extract_attr(hcaptcha, "data-sitekey")
        if not hc_key:
            hc_key = await page.evaluate("""
                () => {
                    const f = document.querySelector('iframe[src*="hcaptcha.com"]');
                    if (f) { const u = new URL(f.src); return u.searchParams.get('sitekey'); }
                    return null;
                }
            """)
        if hc_key:
            logger.info(f"[capsolver] 检测到 hCaptcha sitekey={hc_key}")
            token = await solver.solve_hcaptcha(url, hc_key)
            if token:
                await inject_hcaptcha_token(page, token)
                await page.wait_for_timeout(2000)
                return True
        return False

    # ── 4. reCAPTCHA ─────────────────────────────────────────────────────
    recaptcha = await page.query_selector(
        ".g-recaptcha, iframe[src*='recaptcha']"
    )
    if recaptcha:
        rc_key = await _extract_attr(recaptcha, "data-sitekey")
        if not rc_key:
            rc_key = await page.evaluate("""
                () => {
                    const f = document.querySelector('iframe[src*="recaptcha"]');
                    if (f) { const m = f.src.match(/[?&]k=([^&]+)/); return m ? m[1] : null; }
                    return null;
                }
            """)
        if rc_key:
            logger.info(f"[capsolver] 检测到 reCAPTCHA sitekey={rc_key}")
            # 尝试判断 v2 vs v3
            is_v3 = await page.evaluate("""
                () => !!document.querySelector('.grecaptcha-badge')
                   || !!document.querySelector('[data-size="invisible"]')
            """)
            if is_v3:
                token = await solver.solve_recaptcha_v3(url, rc_key)
            else:
                token = await solver.solve_recaptcha_v2(url, rc_key)
            if token:
                await inject_recaptcha_token(page, token)
                await page.wait_for_timeout(2000)
                return True
        return False

    # ── 5. GeeTest ───────────────────────────────────────────────────────
    geetest = await page.query_selector("[class*='geetest']")
    if geetest:
        gt_info = await page.evaluate("""
            () => {
                const el = document.querySelector('[class*="geetest"]');
                // v4
                const captchaId = el?.getAttribute('data-captcha_id')
                    || document.querySelector('[data-captcha_id]')?.getAttribute('data-captcha_id');
                if (captchaId) return { version: 4, captchaId };
                // v3
                const gt = el?.getAttribute('data-gt')
                    || document.querySelector('[data-gt]')?.getAttribute('data-gt');
                const challenge = el?.getAttribute('data-challenge')
                    || document.querySelector('[data-challenge]')?.getAttribute('data-challenge');
                if (gt && challenge) return { version: 3, gt, challenge };
                return null;
            }
        """)
        if gt_info:
            if gt_info["version"] == 4:
                logger.info(f"[capsolver] 检测到 GeeTest v4 id={gt_info['captchaId']}")
                await solver.solve_geetest_v4(url, gt_info["captchaId"])
                return True
            else:
                logger.info(f"[capsolver] 检测到 GeeTest v3 gt={gt_info['gt']}")
                await solver.solve_geetest_v3(url, gt_info["gt"], gt_info["challenge"])
                return True
        logger.warning("[capsolver] 检测到 GeeTest 元素但无法提取参数")
        return False

    # ── 6. 字节跳动/火山引擎验证（豆包使用）──────────────────────────────
    #    使用更精确的选择器，避免误匹配 Cloudflare 等其他验证码
    bytedance_captcha = await page.query_selector(
        "#captcha-verify, [class*='secsdk'], [class*='slide-verify'], "
        "[class*='slider-verify'], [class*='bytedance-captcha'], "
        "[class*='volcengine-captcha']"
    )
    if bytedance_captcha:
        logger.warning(
            "[capsolver] 检测到字节跳动验证码（slider/click），"
            "CapSolver 暂不支持此类型，请手动刷新 cookies"
        )
        return False

    # ── 7. 未知类型：检测通用 CAPTCHA 元素 ───────────────────────────────
    #    宽泛选择器放在最后，避免误判
    unknown_captcha = await page.query_selector(
        "[class*='captcha']:not([class*='cf-']), "
        "iframe[src*='captcha']"
    )
    if unknown_captcha:
        visible = await page.evaluate(
            "(el) => !!el.offsetParent", unknown_captcha
        )
        if visible:
            logger.warning(
                "[capsolver] 检测到未识别的验证码类型，尝试 Cloudflare Turnstile..."
            )
            # 最后尝试一次 Turnstile（可能 sitekey 在 iframe 内部）
            site_key = await _extract_turnstile_sitekey(page)
            if site_key:
                token = await solver.solve_turnstile(url, site_key)
                if token:
                    await inject_turnstile_token(page, token)
                    await page.wait_for_timeout(2000)
                    return True
            logger.warning("[capsolver] 未识别的验证码类型，无法自动求解")
            return False

    return True   # 无验证码，正常通过


# ─── 内部辅助 ─────────────────────────────────────────────────────────────────

async def _extract_attr(element, attr: str) -> Optional[str]:
    """安全提取元素属性"""
    try:
        return await element.get_attribute(attr)
    except Exception:
        return None


async def _extract_turnstile_sitekey(page: Page) -> Optional[str]:
    """从多种位置提取 Turnstile sitekey"""
    return await page.evaluate("""
        () => {
            // 方式1: cf-turnstile widget div
            const widget = document.querySelector(
                '[data-sitekey].cf-turnstile, .cf-turnstile[data-sitekey]'
            );
            if (widget) return widget.getAttribute('data-sitekey');

            // 方式2: 任何带 data-sitekey 的 Cloudflare 元素
            const el = document.querySelector(
                '[data-sitekey][class*="turnstile"], [data-sitekey][class*="cf-"]'
            );
            if (el) return el.getAttribute('data-sitekey');

            // 方式3: iframe src 提取
            const frames = document.querySelectorAll(
                'iframe[src*="challenges.cloudflare.com"], iframe[src*="turnstile"]'
            );
            for (const f of frames) {
                const m = f.src.match(/[?&](?:sitekey|k)=([^&]+)/);
                if (m) return m[1];
            }

            // 方式4: 页面脚本中的 sitekey
            const scripts = document.querySelectorAll('script');
            for (const s of scripts) {
                const text = s.textContent || '';
                const m = text.match(/sitekey['"\\s:]+['"]([0-9x-]{20,})['"]/);
                if (m) return m[1];
            }

            return null;
        }
    """)
