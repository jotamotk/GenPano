"""
LubanSMS (鲁班短信) 接码平台 API 客户端
API 文档: https://lubansms.com/api_docs/

提供临时手机号获取和 SMS 验证码接收功能，
用于 LLM 平台的自动注册/登录。
"""
from __future__ import annotations

import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)

LUBANSMS_BASE = "https://lubansms.com/v2/api"


class LubanSMSClient:
    """LubanSMS 接码平台 API 封装（异步）"""

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

    async def get_number(self, service_id: str) -> tuple[str, int]:
        """
        获取临时手机号

        Args:
            service_id: 平台对应的 service_id（如豆包/抖音）

        Returns:
            (phone_number, request_id)
        """
        resp = await self.client.get(
            f"{LUBANSMS_BASE}/getNumber",
            params={"apikey": self.token, "service_id": service_id},
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"getNumber failed: {data}")
        phone = data["number"]
        request_id = data["request_id"]
        logger.info(f"获取手机号: {phone} (request_id={request_id})")
        return phone, request_id

    async def get_sms(self, request_id: int, timeout: int = 120) -> str:
        """
        轮询获取 SMS 验证码

        Args:
            request_id: getNumber 返回的 request_id
            timeout: 最大等待秒数

        Returns:
            验证码字符串

        Raises:
            TimeoutError: 超时未收到验证码
            RuntimeError: 号码已过期或 API 错误
        """
        waited = 0
        interval = 3
        while waited < timeout:
            resp = await self.client.get(
                f"{LUBANSMS_BASE}/getSms",
                params={"apikey": self.token, "request_id": request_id},
            )
            data = resp.json()

            if data.get("msg") == "success" and data.get("sms_code"):
                code = data["sms_code"]
                logger.info(f"收到验证码: {code}")
                return code

            if data.get("code") == 400:
                raise RuntimeError(f"getSms 失败 (号码可能已过期): {data}")

            await asyncio.sleep(interval)
            waited += interval
            if waited % 15 == 0:
                logger.info(f"等待验证码中... ({waited}s/{timeout}s)")

        raise TimeoutError(f"等待验证码超时 ({timeout}s)")

    async def release_number(self, request_id: int) -> None:
        """释放未使用的号码"""
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
            logger.info(f"释放号码: {data}")
        except Exception as e:
            logger.warning(f"释放号码失败: {e}")

    async def close(self) -> None:
        await self.client.aclose()
