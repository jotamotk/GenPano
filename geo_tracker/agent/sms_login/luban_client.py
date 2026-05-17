"""
LubanSMS (鲁班短信) 接码平台 API 客户端
API 文档: https://lubansms.com/api_docs/

提供临时手机号获取和 SMS 验证码接收功能，
用于 LLM 平台的自动注册/登录。

使用 Keyword API（getKeywordNumber / getKeywordSms / delKeywordNumber）：
- 取号时可指定手机号复用（用于已有账号重新登录）
- 用手机号直接查短信、释放，无 request_id 概念
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re

import httpx

from geo_tracker.agent.sms_redaction import mask_phone, redact_sensitive_text

logger = logging.getLogger(__name__)

LUBANSMS_BASE = "https://lubansms.com/v2/api"


class LubanSMSClient:
    """LubanSMS 接码平台 Keyword API 封装（异步）"""

    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("LUBANSMS_TOKEN", "")
        if not self.token:
            raise ValueError("LUBANSMS_TOKEN 环境变量未设置")
        self.client = httpx.AsyncClient(timeout=30)

    async def get_balance(self) -> str:
        """查询账户余额"""
        resp = await self.client.get(
            f"{LUBANSMS_BASE}/getBalance",
            params={"apikey": self.token},
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"getBalance failed: {data}")
        return data["balance"]

    async def get_keyword_number(self, phone: str | None = None) -> str:
        """
        获取手机号（Keyword API）。

        Args:
            phone: 指定复用的手机号；None 时随机分配新号码

        Returns:
            手机号字符串
        """
        params: dict = {"apikey": self.token}
        if phone:
            params["phone"] = phone
        resp = await self.client.get(
            f"{LUBANSMS_BASE}/getKeywordNumber",
            params=params,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"getKeywordNumber failed: {data}")
        result_phone = data["phone"]
        action = f"复用 {mask_phone(phone)}" if phone else "随机获取"
        logger.info(f"获取手机号 ({action}): {mask_phone(result_phone)}")
        return result_phone

    async def get_keyword_sms(
        self, phone: str, keyword: str, timeout: int = 120
    ) -> str:
        """
        轮询获取 SMS 验证码（Keyword API）。

        Args:
            phone: 手机号（由 get_keyword_number 返回）
            keyword: 短信中包含的关键词（如 "豆包"、"抖音"）
            timeout: 最大等待秒数

        Returns:
            验证码字符串（从短信正文中提取的 4-8 位数字）

        Raises:
            TimeoutError: 超时未收到短信
            RuntimeError: API 错误或无法提取验证码
        """
        waited = 0
        interval = 3
        while waited < timeout:
            resp = await self.client.get(
                f"{LUBANSMS_BASE}/getKeywordSms",
                params={"apikey": self.token, "phone": phone, "keyword": keyword},
            )
            data = resp.json()

            if data.get("code") == 0 and data.get("msg"):
                msg = data["msg"]
                logger.info("收到短信: [sms-text-redacted]")
                match = re.search(r"(\d{4,8})", msg)
                if match:
                    code = match.group(1)
                    logger.info("提取验证码: [sms-code-redacted]")
                    return code
                # Refs #963: keep the SMS body redacted (PII), but emit
                # length + 8-char sha256 prefix so worker logs can
                # distinguish failure modes across iterations — empty
                # body vs non-empty-no-digit vs a specific recurring
                # template — without leaking the body itself. The next
                # iteration uses this to decide whether to widen the
                # regex or whitelist a service_id manually; we do NOT
                # auto-fallback to service_id from here.
                #
                # Refs #963 follow-up to PR #1101 Codex P2 review
                # (https://github.com/jotamotk/trash_test/pull/1101#discussion_r3253891280):
                # downstream ``base.py`` wraps this RuntimeError through
                # ``redact_sensitive_text`` (sms_redaction.py), whose
                # ``SMS_CODE_RE = re.compile(r"(?<!\*)\b\d{4,8}\b")``
                # would replace an all-digit 8-char sha8 with
                # ``[sms-code-redacted]`` and silently drop ~10% of
                # diagnostic samples (probability ``(10/16)^8 ≈ 10%``).
                # Prefixing the hex with a non-digit letter ``h`` defeats
                # ``\b\d{4,8}\b``: ``\b`` cannot match between the word
                # chars ``h`` and the first digit, so the digit run is
                # never standalone. PHONE_RE / E164_PHONE_RE do not
                # match either — PHONE_RE expects 11 digits structured
                # as ``(1\d{2})\d{4}(\d{4})`` and E164_PHONE_RE requires
                # 10–15, so an 8-digit run is below the floor. 12-char
                # hex was considered but rejected: a 12-digit run is
                # matched by PHONE_RE ``(?<!\d)(?:\+?86)?(1\d{2})\d{4}(\d{4})``
                # whenever the first digit is ``1`` and would be mangled
                # to ``1xx****yyyy``.
                sha8 = hashlib.sha256(msg.encode()).hexdigest()[:8]
                raise RuntimeError(
                    f"无法从短信中提取验证码: [sms-text-redacted, len={len(msg)}, sha8=h{sha8}]"
                )

            # code=400 + "不正确的apikey" 是真正的错误
            if data.get("code") == 400 and "apikey" in data.get("msg", "").lower():
                raise RuntimeError(f"getKeywordSms 认证失败: {data}")

            # "尚未收到短信" 继续等待
            await asyncio.sleep(interval)
            waited += interval
            if waited % 15 == 0:
                logger.info(f"等待验证码中... ({waited}s/{timeout}s)")

        raise TimeoutError(f"等待验证码超时 ({timeout}s)")

    async def release_keyword_number(self, phone: str) -> None:
        """释放手机号（Keyword API）"""
        try:
            resp = await self.client.get(
                f"{LUBANSMS_BASE}/delKeywordNumber",
                params={"apikey": self.token, "phone": phone},
            )
            data = resp.json()
            logger.info(
                f"释放号码: {mask_phone(phone)} → "
                f"{redact_sensitive_text(data)}"
            )
        except Exception as e:
            logger.warning(
                f"释放号码失败 ({mask_phone(phone)}): {redact_sensitive_text(e)}"
            )

    # ── 验证码接收 API (service_id-based fallback) ─────────────────────
    # Refs #963 / #973: the Keyword API ("通用短信接收") is currently
    # returning {"code":400,"msg":"未知错误"} for Doubao number requests
    # — LubanSMS's keyword-number pool is intermittently empty / offline
    # for this account. The verification-code API ("验证码接收") draws
    # from a different inventory keyed by service_id and is the
    # documented fallback path for this exact situation. We keep the
    # Keyword API as the primary path (one fewer API call when it works,
    # and supports phone reuse for re-login) and fall back to the
    # service-id API only when keyword allocation fails.

    async def get_service_number(self, service_id: str) -> tuple[str, str]:
        """Reserve a verification-code phone for ``service_id``.

        Returns (phone, request_id). Both are needed: phone is used for
        the actual registration/login on the LLM site; request_id is the
        handle passed to ``get_service_sms`` and
        ``set_service_status_reject``.
        """
        resp = await self.client.get(
            f"{LUBANSMS_BASE}/getNumber",
            params={"apikey": self.token, "service_id": service_id},
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"getNumber failed: {data}")
        phone = str(data.get("number") or "")
        request_id = str(data.get("request_id") or "")
        if not phone or not request_id:
            raise RuntimeError(
                f"getNumber returned incomplete payload (phone/request_id missing): {data}"
            )
        logger.info(
            "获取手机号 (service_id=%s): %s, request_id=%s",
            service_id,
            mask_phone(phone),
            request_id,
        )
        return phone, request_id

    async def get_service_sms(
        self, request_id: str, *, timeout: int = 120
    ) -> str:
        """Poll for SMS code by request_id (验证码接收 API).

        The verification-code API returns the parsed sms_code directly
        when the SMS arrives, so we do not need a keyword filter here —
        the service_id at reservation time already constrained which
        SMS is delivered.
        """
        waited = 0
        interval = 3
        while waited < timeout:
            resp = await self.client.get(
                f"{LUBANSMS_BASE}/getSms",
                params={"apikey": self.token, "request_id": request_id},
            )
            data = resp.json()
            if data.get("code") == 0 and data.get("msg") == "success":
                sms_code = str(data.get("sms_code") or "")
                if sms_code:
                    logger.info(
                        "收到验证码 (request_id=%s): [sms-code-redacted]",
                        request_id,
                    )
                    return sms_code
                raise RuntimeError(
                    f"getSms success but missing sms_code: {data}"
                )
            if (
                data.get("code") == 400
                and "apikey" in str(data.get("msg", "")).lower()
            ):
                raise RuntimeError(f"getSms 认证失败: {data}")
            # ``{"code":0,"msg":"wait", ...}`` → still waiting, keep polling
            # ``{"code":400,"msg":"wrong_status"}`` → request expired
            # before SMS arrived; treat as timeout so the caller can retry.
            await asyncio.sleep(interval)
            waited += interval
            if waited % 15 == 0:
                logger.info(
                    f"等待验证码中 (service)... ({waited}s/{timeout}s, "
                    f"request_id={request_id})"
                )
        raise TimeoutError(
            f"等待验证码超时 (service, {timeout}s, request_id={request_id})"
        )

    async def set_service_status_reject(self, request_id: str) -> None:
        """Release a service-API request via setStatus(status=reject).

        Best-effort — a failure here just means the number stays reserved
        on LubanSMS's side until it auto-expires; it does not block the
        login flow itself, so we log and swallow exceptions.
        """
        try:
            resp = await self.client.get(
                f"{LUBANSMS_BASE}/setStatus",
                params={
                    "apikey": self.token,
                    "request_id": request_id,
                    "status": "reject",
                },
            )
            data = resp.json()
            logger.info(
                "释放请求 (service, request_id=%s): %s",
                request_id,
                redact_sensitive_text(data),
            )
        except Exception as e:
            logger.warning(
                "释放请求失败 (service, request_id=%s): %s",
                request_id,
                redact_sensitive_text(e),
            )

    async def close(self) -> None:
        await self.client.aclose()
