"""
账号池轮换调度器
- 按 LLM + 地区选取可用账号
- 超配额自动 cooldown，连续失败自动标记 banned
- 每次轮换记录日志，支持审计
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from geo_tracker.db.models import LLMAccount, AccountRotationLog, AccountStatus

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_FAILS = 3      # 连续失败N次 → banned
COOLDOWN_HOURS        = 12     # 超配额冷却时间
DAILY_RESET_HOUR      = 0      # UTC 00:00 重置每日计数


class AccountPool:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def acquire(
        self,
        llm_name: str,
        country_code: Optional[str] = None,
    ) -> Optional[LLMAccount]:
        """
        选取可用账号，策略：
        1. 同 LLM + 同地区
        2. 未封禁、未冷却、今日未超配额
        3. 优先选 last_used_at 最早的（均匀分摊）
        """
        now = datetime.utcnow()

        stmt = (
            select(LLMAccount)
            .where(
                and_(
                    LLMAccount.llm_name == llm_name,
                    LLMAccount.status == AccountStatus.ACTIVE.value,
                    # 冷却已过期 或 从未冷却
                    (LLMAccount.cooldown_until == None) | (LLMAccount.cooldown_until <= now),
                    # 今日配额未满
                    LLMAccount.query_count_today < LLMAccount.daily_limit,
                )
            )
        )

        # 可选：按账号绑定的 profile 地区过滤
        if country_code:
            stmt = stmt.join(LLMAccount.profile).where(
                LLMAccount.profile.has(country_code=country_code.upper())
            )

        result = await self.db.execute(stmt)
        accounts = result.scalars().all()

        if not accounts:
            logger.warning(
                f"No available account for llm={llm_name} country={country_code}"
            )
            return None

        # 优先用最久没使用的账号（均匀消耗）
        accounts.sort(key=lambda a: a.last_used_at or datetime.min)
        account = accounts[0]

        account.last_used_at = now
        account.query_count_today += 1
        await self.db.commit()

        logger.info(
            f"Acquired account id={account.id} llm={llm_name} "
            f"today={account.query_count_today}/{account.daily_limit}"
        )
        return account

    async def report_success(self, account_id: int) -> None:
        account = await self.db.get(LLMAccount, account_id)
        if account:
            account.consecutive_fails = 0   # 成功后重置失败计数
            await self.db.commit()

    async def report_failure(
        self,
        account_id: int,
        reason: str = "unknown",
        is_ban: bool = False,
    ) -> None:
        """
        记录失败，达到阈值自动封禁
        reason: rate_limit | ban | captcha_fail | login_fail | cookies_expired | response_too_short | exception
        cookies_expired 不计入 consecutive_fails（只是 cookies 过期，不是账号问题）
        """
        account = await self.db.get(LLMAccount, account_id)
        if not account:
            return

        # cookies 过期只设 cooldown，不增加失败计数（避免误封）
        if reason == "cookies_expired":
            account.status = AccountStatus.COOLDOWN.value
            account.cooldown_until = datetime.utcnow() + timedelta(hours=COOLDOWN_HOURS)
            logger.warning(
                f"Account id={account_id} cookies expired, cooldown until {account.cooldown_until}"
            )
        else:
            account.consecutive_fails += 1

            if is_ban or account.consecutive_fails >= MAX_CONSECUTIVE_FAILS:
                account.status = AccountStatus.BANNED.value
                logger.warning(
                    f"Account id={account_id} BANNED after {account.consecutive_fails} fails"
                )
            elif reason == "rate_limit":
                account.status = AccountStatus.COOLDOWN.value
                account.cooldown_until = datetime.utcnow() + timedelta(hours=COOLDOWN_HOURS)
                logger.info(f"Account id={account_id} cooldown until {account.cooldown_until}")

        # 记录轮换日志
        log = AccountRotationLog(account_id=account_id, reason=reason)
        self.db.add(log)
        await self.db.commit()

    async def reset_daily_counts(self) -> None:
        """每日 UTC 00:00 由 Celery Beat 调用，重置查询计数"""
        result = await self.db.execute(select(LLMAccount))
        accounts = result.scalars().all()
        for acc in accounts:
            acc.query_count_today = 0
        await self.db.commit()
        logger.info(f"Reset daily query counts for {len(accounts)} accounts")

    async def save_cookies(self, account_id: int, cookies_json: str) -> None:
        """Agent执行成功后持久化登录态"""
        account = await self.db.get(LLMAccount, account_id)
        if account:
            account.cookies_json = cookies_json
            account.cookies_updated_at = datetime.utcnow()
            await self.db.commit()
