"""
代理池管理器
- 按地理位置 & LLM类型选取合适代理
- 失败自动标记 cooldown，成功更新统计
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from geo_tracker.db.models import Proxy, ProxyType

logger = logging.getLogger(__name__)

# 各LLM对代理类型的要求
LLM_PROXY_REQUIREMENTS: dict[str, list[ProxyType]] = {
    "chatgpt":    [ProxyType.RESIDENTIAL, ProxyType.MOBILE],
    "gemini":     [ProxyType.RESIDENTIAL, ProxyType.MOBILE],
    "claude":     [ProxyType.RESIDENTIAL, ProxyType.MOBILE],
    "grok":       [ProxyType.RESIDENTIAL, ProxyType.MOBILE],
    "perplexity": [ProxyType.RESIDENTIAL, ProxyType.DATACENTER, ProxyType.MOBILE],
    "kimi":       [ProxyType.RESIDENTIAL, ProxyType.MOBILE],   # 国内IP
    "doubao":     [ProxyType.RESIDENTIAL, ProxyType.MOBILE],
}

COOLDOWN_MINUTES = 30


class ProxyPool:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def acquire(
        self,
        llm_name: str,
        country_code: Optional[str] = None,
    ) -> Optional[Proxy]:
        """
        为指定LLM + 地区选取最优代理
        优先级: success_rate DESC, last_used_at ASC
        """
        allowed_types = LLM_PROXY_REQUIREMENTS.get(llm_name, list(ProxyType))
        now = datetime.utcnow()

        stmt = (
            select(Proxy)
            .where(
                and_(
                    Proxy.is_banned == False,
                    Proxy.type.in_(allowed_types),
                    # cooldown 已过期 或 从未冷却
                    (Proxy.cooldown_until == None) | (Proxy.cooldown_until <= now),
                )
            )
        )

        if country_code:
            stmt = stmt.where(Proxy.country == country_code.upper())

        result = await self.db.execute(stmt)
        proxies = result.scalars().all()

        if not proxies:
            logger.warning(f"No available proxy for llm={llm_name} country={country_code}")
            return None

        # 按 success_rate DESC, last_used_at ASC 排序
        proxies.sort(
            key=lambda p: (-p.success_rate, p.last_used_at or datetime.min)
        )

        proxy = proxies[0]
        proxy.last_used_at = now
        await self.db.commit()

        logger.info(f"Acquired proxy id={proxy.id} type={proxy.type} country={proxy.country}")
        return proxy

    async def report_success(self, proxy_id: int) -> None:
        proxy = await self.db.get(Proxy, proxy_id)
        if proxy:
            proxy.success_count += 1
            await self.db.commit()

    async def report_failure(self, proxy_id: int, ban: bool = False) -> None:
        proxy = await self.db.get(Proxy, proxy_id)
        if not proxy:
            return

        proxy.fail_count += 1

        if ban:
            proxy.is_banned = True
            logger.warning(f"Proxy id={proxy_id} marked as BANNED")
        else:
            proxy.cooldown_until = datetime.utcnow() + timedelta(minutes=COOLDOWN_MINUTES)
            logger.info(f"Proxy id={proxy_id} in cooldown for {COOLDOWN_MINUTES}min")

        await self.db.commit()
