from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from geo_tracker.db.models import AccountStatus, LLMAccount
from geo_tracker.pool.account_pool import AccountPool, reserve_account_quota

logger = logging.getLogger(__name__)


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _has_cookies(account: LLMAccount) -> bool:
    return bool((account.cookies_json or "").strip())


def _cooldown_allows(account: LLMAccount, now: datetime) -> bool:
    cooldown_until = account.cooldown_until
    if cooldown_until is None:
        return True
    if cooldown_until.tzinfo is not None:
        return cooldown_until <= datetime.now(UTC)
    return cooldown_until <= now


def _within_daily_limit(account: LLMAccount) -> bool:
    daily_limit = int(account.daily_limit or 0)
    if daily_limit <= 0:
        return False
    return int(account.query_count_today or 0) < daily_limit


def is_account_executable_for_query(
    account: LLMAccount | None,
    *,
    target_llm: str,
    now: datetime | None = None,
) -> bool:
    if account is None:
        return False
    now = now or _utcnow_naive()
    return (
        str(account.llm_name or "").lower() == str(target_llm or "").lower()
        and account.status == AccountStatus.ACTIVE.value
        and _has_cookies(account)
        and _cooldown_allows(account, now)
        and _within_daily_limit(account)
    )


def account_unavailable_reason_from_accounts(
    accounts: list[LLMAccount],
    *,
    now: datetime | None = None,
) -> str:
    """Classify why an engine has no executable account."""
    now = now or _utcnow_naive()
    if not accounts:
        return "account_pool_empty"

    expired = [
        account for account in accounts if account.status == AccountStatus.EXPIRED.value
    ]
    if len(expired) == len(accounts):
        return "account_all_expired"

    active = [account for account in accounts if account.status == AccountStatus.ACTIVE.value]
    if not active:
        return "account_no_active"

    with_cookies = [account for account in active if _has_cookies(account)]
    if not with_cookies:
        return "account_no_cookies"

    not_cooling = [account for account in with_cookies if _cooldown_allows(account, now)]
    if not not_cooling:
        return "account_cooling_down"

    if not any(_within_daily_limit(account) for account in not_cooling):
        return "account_daily_limit_exhausted"

    return "no_account_available"


async def diagnose_account_unavailable(
    db: Any,
    target_llm: str,
) -> str:
    result = await db.execute(select(LLMAccount).where(LLMAccount.llm_name == target_llm))
    return account_unavailable_reason_from_accounts(list(result.scalars().all()))


async def _claim_account(db: Any, account: LLMAccount, *, now: datetime) -> bool:
    return await reserve_account_quota(db, account, now=now)


async def acquire_query_account(
    db: Any,
    query: Any,
    *,
    pool: AccountPool | None = None,
) -> LLMAccount | None:
    """Acquire the account a query should execute with.

    Scheduler/manual dispatch may already reserve a concrete account on
    ``queries.account_id``. Honor that first; otherwise use AccountPool with the
    query profile so fallback selection stays in the same profile binding lane.
    """
    now = _utcnow_naive()
    assigned_id = getattr(query, "account_id", None)
    target_llm = str(getattr(query, "target_llm", "") or "")

    if assigned_id:
        assigned = await db.get(LLMAccount, int(assigned_id))
        if is_account_executable_for_query(assigned, target_llm=target_llm, now=now):
            if await _claim_account(db, assigned, now=now):
                logger.info(
                    "Query %s: using scheduler-assigned account id=%s for %s",
                    getattr(query, "id", None),
                    assigned.id,
                    target_llm,
                )
                return assigned
            else:
                logger.info(
                    "Query %s: scheduler-assigned account id=%s reservation failed; "
                    "falling back to account pool",
                    getattr(query, "id", None),
                    assigned_id,
                )
        else:
            logger.info(
                "Query %s: scheduler-assigned account id=%s is unavailable; "
                "falling back to account pool",
                getattr(query, "id", None),
                assigned_id,
            )

    pool = pool or AccountPool(db)
    profile_id = getattr(query, "profile_id", None)
    return await pool.acquire(
        target_llm,
        profile_id=str(profile_id) if profile_id is not None else None,
    )
