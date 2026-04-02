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
import logging
import os
import re

import httpx

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
        action = f"复用 {phone}" if phone else "随机获取"
        logger.info(f"获取手机号 ({action}): {result_phone}")
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
                logger.info(f"收到短信: {msg}")
                match = re.search(r"(\d{4,8})", msg)
                if match:
                    code = match.group(1)
                    logger.info(f"提取验证码: {code}")
                    return code
                raise RuntimeError(f"无法从短信中提取验证码: {msg}")

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
            logger.info(f"释放号码: {phone} → {data}")
        except Exception as e:
            logger.warning(f"释放号码失败 ({phone}): {e}")

    async def close(self) -> None:
        await self.client.aclose()
