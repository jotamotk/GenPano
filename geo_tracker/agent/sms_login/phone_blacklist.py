"""
手机号黑名单（基于 Redis）

收不到验证码的手机号记录到 Redis，TTL 24h。
下次取号时自动跳过这些号码。
"""
from __future__ import annotations

import logging
import os

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_TTL_SECONDS = 86400  # 24 小时（默认）
_TTL_PERMANENT = 86400 * 365  # 1 年（永久拉黑）
_KEY_PREFIX = "sms_blacklist"
# 单次取号时最多跳过多少个黑名单号码
_MAX_SKIP = 20


def _key(platform: str, phone: str) -> str:
    return f"{_KEY_PREFIX}:{platform}:{phone}"


async def add_to_blacklist(
    platform: str, phone: str, reason: str = "", permanent: bool = False,
) -> None:
    """将手机号加入黑名单。permanent=True 则永久拉黑（1年），否则 24h。"""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    client = aioredis.from_url(redis_url, decode_responses=True)
    try:
        ttl = _TTL_PERMANENT if permanent else _TTL_SECONDS
        value = reason or "1"
        await client.set(_key(platform, phone), value, ex=ttl)
        ttl_desc = "永久" if permanent else "24h"
        logger.info(
            f"[{platform}] 手机号 {phone} 已加入黑名单 (TTL={ttl_desc})"
            + (f", 原因: {reason}" if reason else "")
        )
    except Exception as e:
        logger.warning(f"[{platform}] 写入黑名单失败: {e}")
    finally:
        await client.aclose()


async def is_blacklisted(platform: str, phone: str) -> bool:
    """检查手机号是否在黑名单中"""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    client = aioredis.from_url(redis_url, decode_responses=True)
    try:
        return bool(await client.exists(_key(platform, phone)))
    except Exception as e:
        logger.warning(f"[{platform}] 查询黑名单失败: {e}")
        return False
    finally:
        await client.aclose()
