"""
代理池管理器
- 按地理位置 & LLM类型选取合适代理
- 国内 LLM 直连，国际 LLM 走代理
- 失败自动标记 cooldown，成功更新统计
- 支持动态代理 API（BrightData/Oxylabs/SmartProxy）
"""
from __future__ import annotations

import logging
import os
import random
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from geo_tracker.db.models import Proxy, ProxyType

logger = logging.getLogger(__name__)

# 国内 LLM（直连，不走代理）
DOMESTIC_LLMS = {"kimi", "doubao", "deepseek", "zhipu", "wenxin"}

# 各 LLM 对代理类型的要求（仅国际 LLM）
LLM_PROXY_REQUIREMENTS: dict[str, list[str]] = {
    "chatgpt":    [ProxyType.RESIDENTIAL.value, ProxyType.MOBILE.value],
    "gemini":     [ProxyType.RESIDENTIAL.value, ProxyType.MOBILE.value],
    "claude":     [ProxyType.RESIDENTIAL.value, ProxyType.MOBILE.value],
    "grok":       [ProxyType.RESIDENTIAL.value, ProxyType.MOBILE.value],
    "perplexity": [ProxyType.RESIDENTIAL.value, ProxyType.DATACENTER.value, ProxyType.MOBILE.value],
}

# 代理服务商配置（环境变量）
PROXY_PROVIDER      = os.getenv("PROXY_PROVIDER", "static")  # static | clash | brightdata | oxylabs | smartproxy
CLASH_PROXY_URL     = os.getenv("CLASH_PROXY_URL", "http://clash:7890")
BRIGHTDATA_USERNAME = os.getenv("BRIGHTDATA_USERNAME", "")
BRIGHTDATA_PASSWORD = os.getenv("BRIGHTDATA_PASSWORD", "")
OXAYLABS_USERNAME   = os.getenv("OXYLABS_USERNAME", "")
OXAYLABS_PASSWORD   = os.getenv("OXYLABS_PASSWORD", "")

# 冷却时间（分钟）
COOLDOWN_MINUTES = 30

# 动态代理模板
DYNAMIC_PROXY_TEMPLATES = {
    "brightdata": "http://{username}:{password}@brd.superproxy.io:22225",
    "oxylabs":    "http://{username}:{password}@pr.oxylabs.io:7777",
    "smartproxy": "http://{username}:{password}@gate.smartproxy.com:7000",
}


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

        **国内 LLM：返回 None（直连）**
        **国际 LLM：从池中选取代理，失败则降级到动态代理**
        """
        # 国内 LLM 直接返回 None（直连）
        if llm_name.lower() in DOMESTIC_LLMS:
            logger.debug(f"[{llm_name}] 国内 LLM，直连模式")
            return None

        # 国际 LLM：先从数据库池中找
        allowed_types = LLM_PROXY_REQUIREMENTS.get(llm_name.lower(), [t.value for t in ProxyType])
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

        # 池中有可用代理
        if proxies:
            # 按 success_rate DESC, last_used_at ASC 排序
            proxies.sort(
                key=lambda p: (-p.success_rate, p.last_used_at or datetime.min)
            )
            proxy = proxies[0]
            proxy.last_used_at = now
            await self.db.commit()
            logger.info(f"[{llm_name}] Acquired proxy id={proxy.id} type={proxy.type} country={proxy.country}")
            return proxy

        # 池中无可用代理，降级到动态代理 API
        logger.warning(f"[{llm_name}] 静态代理池无可用代理，尝试动态代理 API")
        return await self._get_dynamic_proxy(country_code)

    async def _get_dynamic_proxy(self, country_code: Optional[str] = None) -> Optional[Proxy]:
        """
        从代理服务商动态获取 IP（按需创建临时 Proxy 记录）
        """
        if PROXY_PROVIDER == "static":
            logger.error("未配置动态代理服务商，且静态代理池已空")
            return None

        # Clash 本地代理（服务器上部署的 Clash 容器）
        if PROXY_PROVIDER == "clash":
            proxy = Proxy(
                provider     = "clash",
                proxy_url    = CLASH_PROXY_URL,
                type         = ProxyType.RESIDENTIAL.value,
                country      = country_code or "US",
                last_used_at = datetime.utcnow(),
            )
            logger.info(f"[动态代理] Clash fallback → {CLASH_PROXY_URL}")
            return proxy

        template = DYNAMIC_PROXY_TEMPLATES.get(PROXY_PROVIDER)
        if not template:
            logger.error(f"不支持的代理服务商: {PROXY_PROVIDER}")
            return None

        # 根据服务商填充凭据
        if PROXY_PROVIDER == "brightdata":
            if not BRIGHTDATA_USERNAME or not BRIGHTDATA_PASSWORD:
                logger.error("BrightData 凭据未配置")
                return None
            proxy_url = template.format(username=BRIGHTDATA_USERNAME, password=BRIGHTDATA_PASSWORD)
        elif PROXY_PROVIDER == "oxylabs":
            if not OXAYLABS_USERNAME or not OXAYLABS_PASSWORD:
                logger.error("Oxylabs 凭据未配置")
                return None
            proxy_url = template.format(username=OXAYLABS_USERNAME, password=OXAYLABS_PASSWORD)
        else:
            # smartproxy 或其他
            proxy_url = template

        # 创建临时 Proxy 记录（不持久化到 DB，仅用于本次请求）
        proxy = Proxy(
            provider      = PROXY_PROVIDER,
            proxy_url     = proxy_url,
            type          = ProxyType.RESIDENTIAL.value,
            country       = country_code or "US",
            last_used_at  = datetime.utcnow(),
        )
        # 不 add 到 session，直接返回临时对象
        logger.info(f"[动态代理] {PROXY_PROVIDER} country={country_code}")
        return proxy

    async def report_success(self, proxy: Proxy) -> None:
        """报告代理使用成功"""
        if proxy.id:  # 持久化的代理才更新统计
            db_proxy = await self.db.get(Proxy, proxy.id)
            if db_proxy:
                db_proxy.success_count += 1
                await self.db.commit()

    async def report_failure(self, proxy: Proxy, ban: bool = False) -> None:
        """报告代理使用失败"""
        if proxy.id:  # 持久化的代理才更新统计
            db_proxy = await self.db.get(Proxy, proxy.id)
            if not db_proxy:
                return

            db_proxy.fail_count += 1

            if ban:
                db_proxy.is_banned = True
                logger.warning(f"Proxy id={proxy.id} marked as BANNED")
            else:
                db_proxy.cooldown_until = datetime.utcnow() + timedelta(minutes=COOLDOWN_MINUTES)
                logger.info(f"Proxy id={proxy.id} in cooldown for {COOLDOWN_MINUTES}min")

            await self.db.commit()

    async def health_check(self) -> dict:
        """健康检查：统计代理池状态"""
        total = (await self.db.execute(
            select(Proxy)
        )).scalars().all()

        available = [p for p in total if not p.is_banned and (p.cooldown_until is None or p.cooldown_until <= datetime.utcnow())]
        banned = [p for p in total if p.is_banned]
        cooling = [p for p in total if p.cooldown_until and p.cooldown_until > datetime.utcnow()]

        return {
            "total": len(total),
            "available": len(available),
            "banned": len(banned),
            "cooling": len(cooling),
            "dynamic_provider": PROXY_PROVIDER,
        }
