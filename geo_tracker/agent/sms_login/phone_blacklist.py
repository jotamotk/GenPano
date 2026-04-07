"""
手机号黑名单（基于 PostgreSQL）

不干净的手机号（如 device_env_error）或收不到短信的号码记录到数据库。
下次取号时自动跳过这些号码。

表结构会在首次使用时自动创建。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import text

from geo_tracker.config import DATABASE_URL

logger = logging.getLogger(__name__)

# 默认过期时间
_TTL_DEFAULT = timedelta(hours=24)
_TTL_PERMANENT = timedelta(days=365)


async def _ensure_table(conn) -> None:
    """确保 phone_blacklist 表存在"""
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS phone_blacklist (
            id SERIAL PRIMARY KEY,
            platform VARCHAR(32) NOT NULL,
            phone VARCHAR(32) NOT NULL,
            reason VARCHAR(128) DEFAULT '',
            permanent BOOLEAN DEFAULT FALSE,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(platform, phone)
        )
    """))
    await conn.commit()


async def _get_connection():
    """获取一个独立的 async 数据库连接"""
    from sqlalchemy.ext.asyncio import create_async_engine
    engine = create_async_engine(DATABASE_URL, pool_size=1, max_overflow=0)
    conn = await engine.connect()
    return engine, conn


async def add_to_blacklist(
    platform: str, phone: str, reason: str = "", permanent: bool = False,
) -> None:
    """将手机号加入黑名单。permanent=True 则永久拉黑（1年），否则 24h。"""
    engine, conn = await _get_connection()
    try:
        await _ensure_table(conn)
        ttl = _TTL_PERMANENT if permanent else _TTL_DEFAULT
        expires_at = datetime.utcnow() + ttl
        await conn.execute(text("""
            INSERT INTO phone_blacklist (platform, phone, reason, permanent, expires_at)
            VALUES (:platform, :phone, :reason, :permanent, :expires_at)
            ON CONFLICT (platform, phone)
            DO UPDATE SET reason = :reason, permanent = :permanent,
                          expires_at = :expires_at, created_at = NOW()
        """), {
            "platform": platform,
            "phone": phone,
            "reason": reason,
            "permanent": permanent,
            "expires_at": expires_at,
        })
        await conn.commit()
        ttl_desc = "永久" if permanent else "24h"
        logger.info(
            f"[{platform}] 手机号 {phone} 已加入黑名单 (TTL={ttl_desc})"
            + (f", 原因: {reason}" if reason else "")
        )
    except Exception as e:
        logger.warning(f"[{platform}] 写入黑名单失败: {e}")
    finally:
        await conn.close()
        await engine.dispose()


async def is_blacklisted(platform: str, phone: str) -> bool:
    """检查手机号是否在黑名单中（未过期）"""
    engine, conn = await _get_connection()
    try:
        await _ensure_table(conn)
        result = await conn.execute(text("""
            SELECT 1 FROM phone_blacklist
            WHERE platform = :platform AND phone = :phone
              AND expires_at > NOW()
            LIMIT 1
        """), {"platform": platform, "phone": phone})
        return result.fetchone() is not None
    except Exception as e:
        logger.warning(f"[{platform}] 查询黑名单失败: {e}")
        return False
    finally:
        await conn.close()
        await engine.dispose()
