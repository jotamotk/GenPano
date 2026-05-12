"""ChatGPT SMS login handler using the shared SMS provider boundary."""

from __future__ import annotations

import logging
import re

from playwright.async_api import Page

from geo_tracker.agent.response_validation import chatgpt_auth_state_reason
from geo_tracker.agent.sms_login import register
from geo_tracker.agent.sms_login.base import BaseSMSLoginHandler
from geo_tracker.agent.sms_login.providers import HeroSMSProvider
from geo_tracker.agent.sms_redaction import mask_phone, redact_sensitive_text

logger = logging.getLogger(__name__)


@register("chatgpt")
class ChatGPTLoginHandler(BaseSMSLoginHandler):
    platform = "chatgpt"
    sms_keyword = "OpenAI"
    login_url = "https://chatgpt.com/"
    sms_provider_factory = HeroSMSProvider
    local_storage_keys = None
    phone_relogin_pattern = r"\+?1\d{10}"
    fallback_to_new_number_on_relogin_unavailable = True

    async def navigate_to_login(self, page: Page) -> bool | str:
        if await self._authenticated(page):
            return True

        block_reason = await self._blocked_reason(page, include_auth_state=False)
        if block_reason:
            return block_reason

        login_button = await self._find_element(
            page,
            [
                "button:has-text('Log in')",
                "a:has-text('Log in')",
                "button:has-text('Sign up')",
                "a:has-text('Sign up')",
                "[data-testid='login-button']",
                "[data-testid='signup-button']",
            ],
        )
        if login_button:
            await login_button.click()
            await page.wait_for_timeout(1500)

        phone_entry = await self._find_element(
            page,
            [
                "button:has-text('Continue with phone')",
                "button:has-text('Phone')",
                "button:has-text('Use phone')",
                "button:has-text('SMS')",
                "a:has-text('Continue with phone')",
            ],
        )
        if phone_entry:
            await phone_entry.click()
            await page.wait_for_timeout(1000)

        block_reason = await self._blocked_reason(page, include_auth_state=False)
        if block_reason:
            return block_reason
        return await self._phone_input_ready(page)

    async def input_phone(self, page: Page, phone: str) -> bool | str:
        block_reason = await self._blocked_reason(page, include_auth_state=False)
        if block_reason:
            return block_reason

        phone_input = await self._find_element(
            page,
            [
                "input[type='tel']",
                "input[name*='phone' i]",
                "input[autocomplete='tel']",
                "input[placeholder*='phone' i]",
                "input[id*='phone' i]",
            ],
        )
        if not phone_input:
            return False

        clean_phone = re.sub(r"[^0-9+]", "", phone)
        logger.info("[chatgpt] entering phone %s", mask_phone(clean_phone))
        try:
            await phone_input.fill(clean_phone)
        except Exception:
            await phone_input.click()
            await page.keyboard.type(clean_phone, delay=60)
        await page.wait_for_timeout(500)
        return True

    async def click_send_sms(self, page: Page) -> bool | str:
        block_reason = await self._blocked_reason(page, include_auth_state=False)
        if block_reason:
            return block_reason

        send_button = await self._find_element(
            page,
            [
                "button:has-text('Continue')",
                "button:has-text('Send code')",
                "button:has-text('Send Code')",
                "button:has-text('Text me')",
                "button[type='submit']",
            ],
        )
        if not send_button:
            return False
        await send_button.click()
        await page.wait_for_timeout(1500)
        block_reason = await self._blocked_reason(page, include_auth_state=False)
        return block_reason or True

    async def input_code(self, page: Page, code: str) -> bool | str:
        block_reason = await self._blocked_reason(page, include_auth_state=False)
        if block_reason:
            return block_reason

        code_input = await self._find_element(
            page,
            [
                "input[autocomplete='one-time-code']",
                "input[name*='code' i]",
                "input[placeholder*='code' i]",
                "input[inputmode='numeric']",
                "input[type='text']",
            ],
        )
        if not code_input:
            return False
        try:
            await code_input.fill(code)
        except Exception:
            await code_input.click()
            await page.keyboard.type(code, delay=60)
        await page.wait_for_timeout(500)
        return True

    async def submit_login(self, page: Page) -> bool | str:
        block_reason = await self._blocked_reason(page, include_auth_state=False)
        if block_reason:
            return block_reason

        submit_button = await self._find_element(
            page,
            [
                "button:has-text('Continue')",
                "button:has-text('Verify')",
                "button:has-text('Submit')",
                "button[type='submit']",
            ],
        )
        if submit_button:
            await submit_button.click()
            await page.wait_for_timeout(2500)
            return await self._blocked_reason(page) or True
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(2500)
        return await self._blocked_reason(page) or True

    async def verify_success(self, page: Page) -> bool | str:
        block_reason = await self._blocked_reason(page)
        if block_reason:
            return block_reason

        try:
            await page.wait_for_selector(
                "#prompt-textarea, [data-testid='prompt-textarea'], "
                "div[contenteditable='true'][role='textbox']",
                timeout=15000,
            )
        except Exception:
            block_reason = await self._blocked_reason(page)
            return block_reason or False

        if await self._login_buttons_visible(page):
            return False
        return await self._authenticated(page)

    async def classify_non_success(self, page: Page) -> str | None:
        return await self._blocked_reason(page) or "requires_manual_challenge"

    async def _phone_input_ready(self, page: Page) -> bool:
        return bool(
            await self._find_element(
                page,
                [
                    "input[type='tel']",
                    "input[name*='phone' i]",
                    "input[autocomplete='tel']",
                    "input[placeholder*='phone' i]",
                    "input[id*='phone' i]",
                ],
            )
        )

    async def _authenticated(self, page: Page) -> bool:
        session_state = await self._session_state(page)
        if session_state is not None:
            return bool(
                session_state.get("hasAccessToken") and session_state.get("hasUser")
            )

        try:
            state = await page.evaluate("""
                () => {
                    const visible = (el) => {
                        if (!el) return false;
                        const r = el.getBoundingClientRect();
                        const s = window.getComputedStyle(el);
                        return r.width > 0 && r.height > 0 &&
                            s.visibility !== 'hidden' && s.display !== 'none';
                    };
                    const prompt = [...document.querySelectorAll(
                        "#prompt-textarea, [data-testid='prompt-textarea'], " +
                        "div[contenteditable='true'][role='textbox']"
                    )].some(visible);
                    const body = (document.body?.innerText || '').toLowerCase();
                    const loginVisible = [...document.querySelectorAll('button, a')]
                        .some((el) => visible(el) && /^(log in|sign up)/i.test(
                            (el.textContent || '').trim()
                        ));
                    const accountChrome =
                        body.includes('upgrade') ||
                        body.includes('get plus') ||
                        body.includes('free') ||
                        Boolean(document.querySelector(
                            "[data-testid*='profile'], [aria-label*='account' i]"
                        ));
                    return {prompt, loginVisible, accountChrome};
                }
            """)
            return bool(
                state
                and state.get("prompt")
                and not state.get("loginVisible")
                and state.get("accountChrome")
            )
        except Exception:
            return False

    async def _session_state(self, page: Page) -> dict | None:
        try:
            result = await page.evaluate("""
                async () => {
                    const state = {
                        status: 0,
                        hasAccessToken: false,
                        hasUser: false,
                    };
                    try {
                        const response = await fetch('/api/auth/session', {
                            credentials: 'include',
                            cache: 'no-store'
                        });
                        state.status = response.status;
                        const data = await response.json().catch(() => ({}));
                        state.hasAccessToken = Boolean(data && data.accessToken);
                        state.hasUser = Boolean(data && data.user);
                        return state;
                    } catch (err) {
                        state.error = err && err.message ? String(err.message) : 'session_probe_failed';
                        return state;
                    }
                }
            """)
            return result if isinstance(result, dict) else None
        except Exception as exc:
            logger.info(
                "[chatgpt] session probe failed without sensitive details: %s",
                redact_sensitive_text(exc),
            )
            return None

    async def _login_buttons_visible(self, page: Page) -> bool:
        try:
            return bool(
                await page.evaluate("""
                    () => [...document.querySelectorAll('button, a')].some((el) => {
                        const text = (el.textContent || '').trim();
                        const r = el.getBoundingClientRect();
                        const s = window.getComputedStyle(el);
                        return /^(Log in|Sign up)/.test(text) &&
                            r.width > 0 && r.height > 0 &&
                            s.visibility !== 'hidden' && s.display !== 'none';
                    })
                """)
            )
        except Exception:
            return False

    async def _blocked_reason(
        self,
        page: Page,
        *,
        include_auth_state: bool = True,
    ) -> str | None:
        try:
            text = await page.evaluate("document.body?.innerText || ''")
        except Exception:
            text = ""
        try:
            title = await page.title()
        except Exception:
            title = ""
        if include_auth_state:
            auth_reason = chatgpt_auth_state_reason(
                text,
                url=getattr(page, "url", ""),
                title=title,
            )
            if auth_reason:
                return auth_reason
        lower = f"{getattr(page, 'url', '')}\n{title}\n{text}".lower()
        if any(
            marker in lower
            for marker in (
                "captcha",
                "cloudflare",
                "turnstile",
                "verify you are human",
                "are you human",
                "manual verification",
                "security check",
            )
        ):
            return "requires_manual_challenge"
        if any(
            marker in lower
            for marker in (
                "verify your email",
                "check your email",
                "email verification",
                "enter the code sent to your email",
            )
        ):
            return "requires_manual_challenge"
        if any(
            marker in lower
            for marker in (
                "suspicious",
                "too many attempts",
                "temporarily blocked",
                "unable to verify your phone",
                "risk",
            )
        ):
            return "risk_blocked"
        return None
