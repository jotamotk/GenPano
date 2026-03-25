"""
验证码自动处理
支持: Cloudflare Turnstile | Arkose Labs | reCAPTCHA v2/v3 | hCaptcha
使用 CapSolver API
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


class CaptchaSolver:
    def __init__(self, api_key: str = CAPSOLVER_API_KEY):
        self.api_key = api_key
        self.client  = httpx.AsyncClient(timeout=30)

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

    async def _get_result(self, task_id: str) -> Optional[str]:
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
                return data["solution"].get("token") or data["solution"].get("gRecaptchaResponse")

            if data.get("errorId") != 0:
                logger.error(f"CapSolver error: {data.get('errorDescription')}")
                return None

        logger.error(f"CapSolver timeout after {MAX_WAIT}s")
        return None

    # ── Cloudflare Turnstile（ChatGPT使用）──────────────────────────────────

    async def solve_turnstile(self, page_url: str, site_key: str) -> Optional[str]:
        task_id = await self._create_task({
            "type":    "AntiTurnstileTaskProxyLess",
            "websiteURL": page_url,
            "websiteKey": site_key,
        })
        if not task_id:
            return None
        token = await self._get_result(task_id)
        logger.info(f"Turnstile solved: {token[:30]}..." if token else "Turnstile FAILED")
        return token

    # ── Arkose Labs FunCaptcha（Claude.ai使用）──────────────────────────────

    async def solve_arkose(
        self, page_url: str, public_key: str, blob: str = ""
    ) -> Optional[str]:
        task_id = await self._create_task({
            "type":          "FunCaptchaTaskProxyLess",
            "websiteURL":    page_url,
            "websitePublicKey": public_key,
            "funcaptchaApiJSSubdomain": "client-api.arkoselabs.com",
            "data":          f'{{"blob":"{blob}"}}' if blob else "",
        })
        if not task_id:
            return None
        return await self._get_result(task_id)

    # ── reCAPTCHA v3（Gemini使用）───────────────────────────────────────────

    async def solve_recaptcha_v3(
        self, page_url: str, site_key: str, action: str = "verify"
    ) -> Optional[str]:
        task_id = await self._create_task({
            "type":       "ReCaptchaV3TaskProxyLess",
            "websiteURL": page_url,
            "websiteKey": site_key,
            "pageAction": action,
            "minScore":   0.7,
        })
        if not task_id:
            return None
        return await self._get_result(task_id)

    async def close(self) -> None:
        await self.client.aclose()


# ─── Playwright 注入工具函数 ─────────────────────────────────────────────────

async def inject_turnstile_token(page: Page, token: str) -> None:
    """将 Turnstile token 注入页面表单"""
    await page.evaluate(f"""
        (token) => {{
            const input = document.querySelector('[name="cf-turnstile-response"]');
            if (input) input.value = token;
            // 触发隐藏回调
            if (window.turnstileCallback) window.turnstileCallback(token);
        }}
    """, token)


async def detect_and_solve(page: Page, solver: CaptchaSolver) -> bool:
    """
    自动检测页面上的验证码类型并求解
    返回 True 表示处理成功或无验证码
    """
    url = page.url

    # 检测 Cloudflare Turnstile
    turnstile = await page.query_selector("[data-sitekey][class*='cf-turnstile']")
    if turnstile:
        site_key = await turnstile.get_attribute("data-sitekey")
        logger.info(f"Detected Turnstile sitekey={site_key}")
        token = await solver.solve_turnstile(url, site_key)
        if token:
            await inject_turnstile_token(page, token)
            return True
        return False

    # 检测 reCAPTCHA
    recaptcha = await page.query_selector(".g-recaptcha")
    if recaptcha:
        site_key = await recaptcha.get_attribute("data-sitekey")
        logger.info(f"Detected reCAPTCHA sitekey={site_key}")
        token = await solver.solve_recaptcha_v3(url, site_key)
        if token:
            await page.evaluate(
                f'document.getElementById("g-recaptcha-response").value = "{token}"'
            )
            return True
        return False

    return True   # 无验证码，正常通过
