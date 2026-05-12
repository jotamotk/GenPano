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

from sqlalchemy import select, and_, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from geo_tracker.db.models import LLMAccount, AccountRotationLog, AccountStatus
from geo_tracker.agent.sms_redaction import mask_phone
from geo_tracker.tasks.query_failure import _should_report_account_failure

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_FAILS = 3      # 连续失败N次 → banned
COOLDOWN_HOURS        = 12     # 超配额冷却时间
DAILY_RESET_HOUR      = 0      # UTC 00:00 重置每日计数
DOUBAO_SESSION_COOLDOWN_REASONS = frozenset(
    {
        "doubao_not_logged_in",
        "doubao_auth_state_missing",
        "doubao_page_unavailable",
    }
)


async def reserve_account_quota(
    db: AsyncSession,
    account: LLMAccount,
    *,
    now: datetime | None = None,
) -> bool:
    """Atomically reserve one daily execution slot for an account."""
    now = now or datetime.utcnow()

    if not hasattr(db, "execute"):
        daily_limit = int(account.daily_limit or 0)
        if daily_limit <= 0 or int(account.query_count_today or 0) >= daily_limit:
            return False
        account.last_used_at = now
        account.query_count_today = int(account.query_count_today or 0) + 1
        await db.commit()
        return True

    count_today = func.coalesce(LLMAccount.query_count_today, 0)
    stmt = (
        update(LLMAccount)
        .where(
            LLMAccount.id == account.id,
            func.coalesce(LLMAccount.daily_limit, 0) > 0,
            count_today < LLMAccount.daily_limit,
        )
        .values(last_used_at=now, query_count_today=count_today + 1)
    )
    result = await db.execute(stmt)
    if result.rowcount != 1:
        await db.rollback()
        return False

    await db.commit()
    await db.refresh(account)
    return True


async def refund_account_quota_reservation(
    db: AsyncSession,
    account_id: int,
    *,
    reason: str | None,
) -> bool:
    """Refund a reserved slot for failures that did not consume platform quota."""
    if _should_report_account_failure(reason):
        return False

    count_today = func.coalesce(LLMAccount.query_count_today, 0)
    stmt = (
        update(LLMAccount)
        .where(LLMAccount.id == account_id, count_today > 0)
        .values(query_count_today=count_today - 1)
    )
    result = await db.execute(stmt)
    if result.rowcount != 1:
        await db.rollback()
        return False

    await db.commit()
    logger.info(
        "Refunded account quota reservation account_id=%s reason=%s",
        account_id,
        reason,
    )
    return True


class AccountPool:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def acquire(
        self,
        llm_name: str,
        country_code: Optional[str] = None,
        profile_id: Optional[str] = None,
    ) -> Optional[LLMAccount]:
        """
        选取可用账号，策略：
        1. 同 LLM + 同地区 (+ 可选: 同 profile_id 已绑定)
        2. 未封禁、未冷却、今日未超配额
        3. 优先选 last_used_at 最早的（均匀分摊）

        ``profile_id`` filters via the ``account_profile_map`` table (M:N),
        falling back to legacy ``llm_accounts.profile_id`` when no binding rows
        exist for the account. This lets the Scheduler honor per-(account,
        profile) daily quotas while staying compatible with old configs.
        """
        from sqlalchemy import text  # local: avoid forcing the import on import
        now = datetime.utcnow()

        stmt = (
            select(LLMAccount)
            .where(
                and_(
                    LLMAccount.llm_name == llm_name,
                    LLMAccount.status == AccountStatus.ACTIVE.value,
                    # 必须有 cookies
                    LLMAccount.cookies_json != None,
                    LLMAccount.cookies_json != "",
                    # 冷却已过期 或 从未冷却
                    (LLMAccount.cooldown_until == None) | (LLMAccount.cooldown_until <= now),
                    # 今日配额未满
                    func.coalesce(LLMAccount.daily_limit, 0) > 0,
                    func.coalesce(LLMAccount.query_count_today, 0) < LLMAccount.daily_limit,
                )
            )
        )

        # 可选：按账号绑定的 profile 地区过滤
        if country_code:
            stmt = stmt.join(LLMAccount.profile).where(
                LLMAccount.profile.has(country_code=country_code.upper())
            )

        # 可选：限定到与该 profile 显式绑定 (M:N) 的账号，
        # 兼容旧 llm_accounts.profile_id (1:1) 字段
        if profile_id:
            stmt = stmt.where(
                text(
                    "(EXISTS (SELECT 1 FROM account_profile_map apm "
                    "         WHERE apm.account_id = llm_accounts.id "
                    "           AND apm.profile_id = :pf) "
                    " OR llm_accounts.profile_id::text = :pf)"
                ).bindparams(pf=str(profile_id))
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
        account = None
        for candidate in accounts:
            if await reserve_account_quota(self.db, candidate, now=now):
                account = candidate
                break

        if account is None:
            logger.warning(
                f"No account reservation available for llm={llm_name} country={country_code}"
            )
            return None

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

        # cookies 过期 / 响应太短 只设 cooldown，不增加失败计数（避免误封）
        # 这些通常是平台侧或网络问题，不是账号本身的问题
        if reason in ("cookies_expired", "response_too_short", "token_invalidated") or (
            account.llm_name == "doubao" and reason in DOUBAO_SESSION_COOLDOWN_REASONS
        ):
            account.status = AccountStatus.COOLDOWN.value
            account.cooldown_until = datetime.utcnow() + timedelta(hours=COOLDOWN_HOURS)
            logger.warning(
                f"Account id={account_id} {reason}, cooldown until {account.cooldown_until}"
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

    async def create_account(
        self, llm_name: str, phone: str, cookies_json: str
    ) -> LLMAccount:
        """注册新账号后创建 DB 记录"""
        account = LLMAccount(
            llm_name=llm_name,
            phone_number=phone,
            email=f"{phone}@{llm_name}.local",
            cookies_json=cookies_json,
            cookies_updated_at=datetime.utcnow(),
            status=AccountStatus.ACTIVE.value,
        )
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        logger.info(
            f"Created new account id={account.id} llm={llm_name} phone={mask_phone(phone)}"
        )
        return account
