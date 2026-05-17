"""
账号池轮换调度器
- 按 LLM + 地区选取可用账号
- 超配额自动 cooldown，连续失败自动标记 banned
- 每次轮换记录日志，支持审计
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from geo_tracker.agent.sms_redaction import mask_phone
from geo_tracker.db.models import (
    AccountRotationLog,
    AccountStatus,
    LLMAccount,
    LLMResponse,
)
from geo_tracker.tasks.query_failure import _should_report_account_failure

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_FAILS = 3      # 连续失败N次 → banned
COOLDOWN_HOURS        = 12     # 超配额冷却时间
DAILY_RESET_HOUR      = 0      # UTC 00:00 重置每日计数

# Refs #963 audit pain point #2 (3-strike ban on expired ricochet).
# Doubao accounts whose primary failure mode IS ``doubao_not_logged_in`` (one
# of EXPIRED_ACCOUNT_REASONS below) cycle ``expired → re-login → active →
# expired`` indefinitely because ``report_failure`` resets ``consecutive_fails``
# to 0 on every expired transition (the ban gate
# ``consecutive_fails >= MAX_CONSECUTIVE_FAILS=3`` therefore never fires for
# them). This separate counter is incremented per expired transition for the
# SAME account and triggers a permanent ban once the account has been bounced
# back to expired 3 times. ``save_cookies`` resets it to 0 when a re-login
# actually produces fresh cookies. Scoped to Doubao because other engines'
# dominant failure modes are not in EXPIRED_ACCOUNT_REASONS and the existing
# ``consecutive_fails`` gate already handles them. Configurable via env so
# operators can lower / disable in production without code change.
MAX_EXPIRED_TRANSITIONS_DEFAULT = 3
# Phase 3 cleanup follow-up (Refs #1118 / Epic #1110): after the vm_session
# execution mode (ADR-016) takes over doubao + deepseek, the routing layer
# (see Phase 2 ramp #1117 / PR #1121) short-circuits ``report_failure`` for
# those engines before this ricochet branch runs, so this set is effectively
# inert for them. The membership is intentionally kept (Admin Surface Rule
# 维护原则: 禁止删除未替换的规则) for two reasons:
#   1) defence-in-depth — if a regression re-introduces a local_cookie
#      ricochet for doubao, the 3-strike ban still fires;
#   2) the set is per-engine, so future engines that exhibit the same
#      expired-ricochet pattern can be added without resurrecting deleted
#      code.
EXPIRED_RICOCHET_BAN_ENGINES = frozenset({"doubao"})

# Refs #963 verify-readonly evidence (issue #963 comment 4469641196 at
# 2026-05-17T06:47:58Z, Q-184971 / Q-184988): defense-in-depth against the
# Mode-C validator false-positive that wrongly tags real Doubao answers as
# ``doubao_homepage_content`` / ``no_response``. When ``report_failure`` is
# called with ``reason in EXPIRED_ACCOUNT_REASONS`` AND the triggering query
# has at least one ``llm_responses`` row whose ``raw_text`` is >= this many
# characters of real captured content, we treat the failure as a validator
# false-positive: status still flips to ``expired`` (the page chrome was
# genuinely odd; cookies may still need refresh), but the
# ``expired_transition_count`` strike is SKIPPED so an account that captured
# a real answer is not punished toward the 3-strike permanent ban.
#
# Threshold justification: Q-184971 had a 1255-char real Doubao answer
# ("是的，bestCoffer 企业级 AI 数据脱敏工具非常适合金融行业的多业务场景使
# 用…") with retry_reason that was nonetheless classified as a failure;
# Q-184988 had 1191 chars. Any threshold strictly less than ~1100 catches
# both real cases. We pick 100 chars to match the analogous whitelist gate
# in ``response_validation.doubao_persistence_auth_reason`` (the
# ``.flow-markdown-body >= 100`` answer override), so the two layers agree
# on what "real captured answer" means and a future tweak to one will not
# desynchronize from the other. Login-redirect pages typically render
# 10–30 chars of UI chrome; 100 chars is comfortably above that ceiling.
STRIKE_SKIP_MIN_RAW_TEXT_CHARS = 100


async def _query_has_real_captured_response(
    db: AsyncSession,
    query_id: int | None,
    *,
    min_chars: int = STRIKE_SKIP_MIN_RAW_TEXT_CHARS,
    response_text: str | None = None,
) -> bool:
    """Return True iff the failing query has an in-memory or persisted real
    response (``raw_text`` length >= ``min_chars``).

    Refs #963 Codex P1 on PR #1109: at the post-extract Doubao failure paths
    (celery_tasks.py:1136 / 1176), the ``LLMResponse`` row is NOT yet inserted
    into ``llm_responses`` — that only happens on the success path
    (``db.add(response)`` at line 1223). For a first-time Mode-C false-
    positive the DB lookup therefore misses and the legacy strike fires,
    defeating the whole point of the defense-in-depth guard. Accept the
    caller-provided in-memory ``response_text`` so the check succeeds at the
    moment the failure branch runs (before the row would have been inserted).
    DB lookup remains as a fallback for callers that pass only ``query_id``
    (orphan-row case from a prior successful attempt — Q-184971's row 668 from
    2026-05-16 16:57 is exactly this shape) and for legacy callers that have
    no in-memory response (e.g. cookie keep-alive probe).
    """
    if response_text is not None and len(response_text) >= int(min_chars):
        return True
    if not query_id:
        return False
    try:
        row = (
            await db.execute(
                select(func.length(LLMResponse.raw_text))
                .where(LLMResponse.query_id == int(query_id))
                .where(LLMResponse.raw_text.isnot(None))
                .order_by(func.length(LLMResponse.raw_text).desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    except Exception as exc:
        logger.warning(
            "report_failure: could not check llm_responses for query_id=%s: %s "
            "(falling back to legacy strike behavior)",
            query_id,
            exc,
        )
        return False
    return bool(row and int(row) >= int(min_chars))


def _max_expired_transitions() -> int:
    raw = os.getenv("DOUBAO_MAX_EXPIRED_TRANSITIONS")
    if raw is None:
        return MAX_EXPIRED_TRANSITIONS_DEFAULT
    try:
        value = int(raw.strip())
    except (TypeError, ValueError):
        return MAX_EXPIRED_TRANSITIONS_DEFAULT
    if value <= 0:
        # Treat <=0 as "disable the gate" — preserves pre-#963 behavior so
        # operators can quickly roll back if the ban gate misfires.
        return 0
    return value

# Refs #958: doubao_page_unavailable 是平台瞬时错误，不是账号问题。
# 用 12 小时 cooldown 把账号雪藏太重；改用一个短得多的窗口（默认 30 分钟），
# 让账号在平台恢复后能尽快重新承接流量。可通过 env 调，0/负值回退到全局 COOLDOWN_HOURS。
DOUBAO_PAGE_UNAVAILABLE_COOLDOWN_MINUTES_DEFAULT = 30


def _doubao_page_unavailable_cooldown() -> timedelta:
    raw = os.getenv("DOUBAO_PAGE_UNAVAILABLE_COOLDOWN_MINUTES")
    minutes = DOUBAO_PAGE_UNAVAILABLE_COOLDOWN_MINUTES_DEFAULT
    if raw is not None:
        try:
            minutes = int(raw.strip())
        except (TypeError, ValueError):
            minutes = DOUBAO_PAGE_UNAVAILABLE_COOLDOWN_MINUTES_DEFAULT
    if minutes <= 0:
        return timedelta(hours=COOLDOWN_HOURS)
    return timedelta(minutes=minutes)
EXPIRED_ACCOUNT_REASONS = frozenset(
    {
        "chatgpt_auth_redirect",
        "chatgpt_login_page",
        "chatgpt_not_logged_in",
        "cookies_expired",
        "doubao_not_logged_in",
        "doubao_auth_state_missing",
        # Refs #963 production evidence (server-diagnostics run 25955749209
        # at 2026-05-16 07:07:50–07:11:01): after all the fingerprint /
        # routing / persistence-gate fixes deployed, the worker submitted
        # the prompt successfully ("已确认消息发送成功") on account 44 but
        # Doubao stopped responding — page reverted to the home shell and
        # the scraper bailed with retry_reason=doubao_homepage_content.
        # This is the same symptom as a server-side shadow-ban: cookies are
        # accepted enough to submit, but the session is not actually live.
        # Without expiring the account, the worker keeps re-picking the
        # same broken cookies forever (account stays "active") and never
        # triggers auto_login → the LubanSMS service_id fallback we just
        # shipped never gets a chance to register a fresh account with a
        # persisted fingerprint. Treat ``doubao_homepage_content`` as an
        # expired-login signal so the next acquisition cycle queues a
        # re-login.
        "doubao_homepage_content",
        "login_redirect",
        "session_expired",
        "token_invalidated",
    }
)
DOUBAO_SESSION_COOLDOWN_REASONS = frozenset({"doubao_page_unavailable"})


@dataclass(frozen=True)
class PoolHealthSnapshot:
    """Read-only counts of an LLM's accounts by status.

    ``cooldown_expired`` counts accounts whose ``cooldown_until`` has elapsed
    but whose ``status`` is still ``cooldown`` — these are the rows that
    :func:`promote_expired_cooldowns` will promote back to ``active``.
    """

    llm_name: str
    active: int
    cooldown: int
    cooldown_expired: int
    expired: int
    banned: int
    with_cookies: int
    captured_at: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "llm_name": self.llm_name,
            "active": self.active,
            "cooldown": self.cooldown,
            "cooldown_expired": self.cooldown_expired,
            "expired": self.expired,
            "banned": self.banned,
            "with_cookies": self.with_cookies,
            "captured_at": self.captured_at.isoformat(),
        }


async def snapshot_pool_health(
    db: AsyncSession,
    llm_name: str,
    *,
    now: datetime | None = None,
) -> PoolHealthSnapshot:
    """Return per-status counts for ``llm_name``. Read-only; idempotent."""
    captured_at = now or datetime.utcnow()
    rows = (
        await db.execute(select(LLMAccount).where(LLMAccount.llm_name == llm_name))
    ).scalars().all()

    active = 0
    cooldown = 0
    cooldown_expired = 0
    expired = 0
    banned = 0
    with_cookies = 0
    for acc in rows:
        if acc.cookies_json:
            with_cookies += 1
        status = (acc.status or "").lower()
        if status == AccountStatus.ACTIVE.value:
            active += 1
        elif status == AccountStatus.COOLDOWN.value:
            cooldown += 1
            if acc.cooldown_until is None or acc.cooldown_until <= captured_at:
                cooldown_expired += 1
        elif status == AccountStatus.EXPIRED.value:
            expired += 1
        elif status == AccountStatus.BANNED.value:
            banned += 1

    return PoolHealthSnapshot(
        llm_name=llm_name,
        active=active,
        cooldown=cooldown,
        cooldown_expired=cooldown_expired,
        expired=expired,
        banned=banned,
        with_cookies=with_cookies,
        captured_at=captured_at,
    )


async def count_acquirable_accounts(
    db: AsyncSession,
    llm_name: str,
    *,
    now: datetime | None = None,
) -> int:
    """Return the count of ``llm_name`` accounts that :meth:`AccountPool.acquire`
    would currently consider candidates — i.e. rows that satisfy ALL the same
    predicates ``acquire()`` filters on, NOT just ``status='active'``.

    Why this exists (Refs #963 Codex P2 review
    https://github.com/jotamotk/trash_test/pull/1102#discussion_r3253924434):
    ``snapshot_pool_health.active`` counts every row with ``status='active'``
    regardless of whether the row has cookies, is in a per-row cooldown window,
    or has already exhausted ``query_count_today >= daily_limit``. That over-
    counts when the proactive pre-warm task uses ``active`` as the basis for
    the deficit calculation: e.g. 3 Doubao rows with ``status='active'`` but
    all of them with ``cookies_json=NULL`` (or quota-exhausted) produces
    ``deficit=0`` from snapshot, but ``acquire()`` returns None — the pool
    is effectively empty. This function mirrors the exact predicate set
    in :meth:`AccountPool.acquire` (around line 356–370) so callers can
    compute deficits against the *usable* count, not the *labeled* count.

    Read-only; idempotent. Does NOT promote expired cooldowns (the caller
    is expected to invoke :func:`promote_expired_cooldowns` first if they
    want elapsed-cooldown rows to count as usable; otherwise those rows are
    excluded because ``acquire()`` itself promotes them before filtering).
    """
    current = now or datetime.utcnow()
    count_today = func.coalesce(LLMAccount.query_count_today, 0)
    stmt = (
        select(func.count(LLMAccount.id))
        .where(
            and_(
                LLMAccount.llm_name == llm_name,
                LLMAccount.status == AccountStatus.ACTIVE.value,
                # 必须有 cookies (matches acquire() line ~363-364)
                LLMAccount.cookies_json != None,
                LLMAccount.cookies_json != "",
                # 冷却已过期 或 从未冷却 (matches acquire() line ~366)
                (LLMAccount.cooldown_until == None)
                | (LLMAccount.cooldown_until <= current),
                # 今日配额未满 (matches acquire() line ~368-369)
                func.coalesce(LLMAccount.daily_limit, 0) > 0,
                count_today < LLMAccount.daily_limit,
            )
        )
    )
    result = await db.execute(stmt)
    scalar = result.scalar()
    return int(scalar or 0)


async def promote_expired_cooldowns(
    db: AsyncSession,
    llm_name: str | None = None,
    *,
    now: datetime | None = None,
    dry_run: bool = False,
) -> list[int]:
    """Promote ``cooldown`` accounts whose ``cooldown_until`` has elapsed.

    Idempotent. Returns the promoted account ids. When ``llm_name`` is None,
    the scan covers all LLMs. The previous code path left an account stuck in
    ``cooldown`` forever because :meth:`AccountPool.acquire` filters by
    ``status='active'`` only — even after ``cooldown_until`` had passed.
    """
    current = now or datetime.utcnow()
    stmt = select(LLMAccount).where(
        and_(
            LLMAccount.status == AccountStatus.COOLDOWN.value,
            LLMAccount.cooldown_until != None,
            LLMAccount.cooldown_until <= current,
        )
    )
    if llm_name:
        stmt = stmt.where(LLMAccount.llm_name == llm_name)

    rows = (await db.execute(stmt)).scalars().all()
    promoted: list[int] = []
    for acc in rows:
        promoted.append(int(acc.id))
        if dry_run:
            continue
        previous_status = str(acc.status or "")
        acc.status = AccountStatus.ACTIVE.value
        acc.cooldown_until = None
        _log_account_state_transition(
            acc,
            previous_status=previous_status,
            new_status=AccountStatus.ACTIVE.value,
            reason="cooldown_window_elapsed",
            evidence="auto_promote_expired_cooldowns",
        )
    if rows and not dry_run:
        await db.commit()
    return promoted


def _log_account_state_transition(
    account: LLMAccount,
    *,
    previous_status: str | None,
    new_status: str,
    reason: str,
    evidence: str,
    provider: str = "none",
    price_bucket: str = "none",
    run_id: str = "none",
) -> None:
    logger.info(
        "Account lifecycle transition account_id=%s engine=%s "
        "previous_status=%s new_status=%s reason=%s evidence=%s "
        "provider=%s price_bucket=%s run_id=%s account_ref=%s",
        account.id,
        account.llm_name,
        previous_status or "unknown",
        new_status,
        reason,
        evidence,
        provider,
        price_bucket,
        run_id,
        f"id:{account.id}",
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

        # Promote cooldown accounts whose window has elapsed. Without this the
        # ``status='active'`` filter below permanently hides accounts whose
        # cooldown timer expired hours ago, leading to "0 active" pool
        # exhaustion symptoms (e.g. issue #908 / #917).
        await promote_expired_cooldowns(self.db, llm_name, now=now)

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
            snapshot = await snapshot_pool_health(self.db, llm_name, now=now)
            logger.warning(
                "No available account llm=%s country=%s pool_health=%s",
                llm_name,
                country_code,
                snapshot.to_dict(),
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
            snapshot = await snapshot_pool_health(self.db, llm_name, now=now)
            logger.warning(
                "No account reservation available llm=%s country=%s pool_health=%s",
                llm_name,
                country_code,
                snapshot.to_dict(),
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
        evidence: str | None = None,
        provider: str = "none",
        price_bucket: str = "none",
        run_id: str = "none",
        query_id: int | None = None,
        response_text: str | None = None,
    ) -> None:
        """
        记录失败，达到阈值自动封禁
        reason: rate_limit | ban | captcha_fail | login_fail | cookies_expired | response_too_short | exception
        cookies_expired 不计入 consecutive_fails（只是 cookies 过期，不是账号问题）

        ``query_id`` (Refs #963 / PR ``claude/issue-963-3strike-respect-real-response``):
        when provided AND ``reason`` is in :data:`EXPIRED_ACCOUNT_REASONS`,
        :func:`_query_has_real_captured_response` is consulted. If the query
        already has a captured ``llm_responses`` row whose ``raw_text`` is
        >= :data:`STRIKE_SKIP_MIN_RAW_TEXT_CHARS`, the
        ``expired_transition_count`` strike is SKIPPED — the account captured
        a real answer, so this is a validator false-positive, not real
        account exhaustion. Status still flips to ``expired`` (the next
        request should still wait for a fresh cookie cycle), but the strike
        counter does not climb. Without ``query_id`` (e.g. cookie keep-alive
        probe), the legacy strike behavior is preserved.
        """
        account = await self.db.get(LLMAccount, account_id)
        if not account:
            return

        # Expired login material waits for re-login/import; transient response
        # failures stay on cooldown so they can retry later without a ban.
        previous_status = str(account.status or "")

        if reason in EXPIRED_ACCOUNT_REASONS:
            # Refs #963 audit pain point #2: increment the per-account
            # expired-transition counter BEFORE deciding final status. Doubao
            # accounts that ricochet ``expired → re-login → active → expired``
            # forever get permanently banned at the 3-strike threshold;
            # other engines keep the legacy expired-then-wait-for-re-login
            # semantics because their dominant failure modes are not
            # ``doubao_not_logged_in`` style cookie-acceptance lies.
            #
            # Refs #963 verify-readonly comment 4469641196 (2026-05-17):
            # before bumping the strike, check if the triggering query has
            # a real captured response (raw_text >= 100 chars). If so, the
            # current failure is a validator false-positive — the account
            # actually served a real answer, so we must NOT punish it
            # toward the 3-strike permanent ban. Defense-in-depth against
            # Mode-C-style flagging even after the orthogonal validator
            # fix on ``claude/issue-963-validator-false-positive`` ships:
            # if a future regression slips through the validator, the
            # strike layer is still safe. Status still flips to expired
            # (cookies may genuinely need refresh), but the strike is
            # skipped so genuine re-login can recover the account.
            real_response_captured = (
                await _query_has_real_captured_response(
                    self.db,
                    query_id,
                    response_text=response_text,
                )
            )
            if real_response_captured:
                logger.warning(
                    "report_failure: skipping strike for account_id=%s "
                    "engine=%s reason=%s query_id=%s — real captured "
                    "response found (raw_text >= %s chars). Status still "
                    "transitions to expired; strike count stays at %s.",
                    account.id,
                    account.llm_name,
                    reason,
                    query_id,
                    STRIKE_SKIP_MIN_RAW_TEXT_CHARS,
                    int(account.expired_transition_count or 0),
                )
                account.status = AccountStatus.EXPIRED.value
                account.cooldown_until = None
                account.consecutive_fails = 0
                _log_account_state_transition(
                    account,
                    previous_status=previous_status,
                    new_status=AccountStatus.EXPIRED.value,
                    reason=reason,
                    evidence=(
                        evidence
                        or "strike_skipped:real_captured_response "
                        f"query_id={query_id}"
                    ),
                    provider=provider,
                    price_bucket=price_bucket,
                    run_id=run_id,
                )
                # Persist & log; bail out before the strike-increment branch.
                log = AccountRotationLog(account_id=account_id, reason=reason)
                self.db.add(log)
                await self.db.commit()
                return

            next_expired_transitions = int(account.expired_transition_count or 0) + 1
            account.expired_transition_count = next_expired_transitions
            max_transitions = _max_expired_transitions()
            should_ban_for_ricochet = (
                account.llm_name in EXPIRED_RICOCHET_BAN_ENGINES
                and max_transitions > 0
                and next_expired_transitions >= max_transitions
            )
            if should_ban_for_ricochet:
                account.status = AccountStatus.BANNED.value
                account.cooldown_until = None
                account.consecutive_fails = 0
                _log_account_state_transition(
                    account,
                    previous_status=previous_status,
                    new_status=AccountStatus.BANNED.value,
                    reason=reason,
                    evidence=(
                        evidence
                        or f"expired_ricochet_ban count={next_expired_transitions}"
                    ),
                    provider=provider,
                    price_bucket=price_bucket,
                    run_id=run_id,
                )
                logger.warning(
                    "account_id=%s engine=%s "
                    "banned_for_repeated_expired_ricochet count=%s reason=%s",
                    account.id,
                    account.llm_name,
                    next_expired_transitions,
                    reason,
                )
            else:
                account.status = AccountStatus.EXPIRED.value
                account.cooldown_until = None
                account.consecutive_fails = 0
                _log_account_state_transition(
                    account,
                    previous_status=previous_status,
                    new_status=AccountStatus.EXPIRED.value,
                    reason=reason,
                    evidence=(
                        evidence
                        or f"expired_login_material count={next_expired_transitions}"
                    ),
                    provider=provider,
                    price_bucket=price_bucket,
                    run_id=run_id,
                )
        elif reason == "response_too_short" or (
            account.llm_name == "doubao" and reason in DOUBAO_SESSION_COOLDOWN_REASONS
        ):
            doubao_short_cd = (
                account.llm_name == "doubao"
                and reason in DOUBAO_SESSION_COOLDOWN_REASONS
            )
            cooldown_delta = (
                _doubao_page_unavailable_cooldown()
                if doubao_short_cd
                else timedelta(hours=COOLDOWN_HOURS)
            )
            account.status = AccountStatus.COOLDOWN.value
            account.cooldown_until = datetime.utcnow() + cooldown_delta
            _log_account_state_transition(
                account,
                previous_status=previous_status,
                new_status=AccountStatus.COOLDOWN.value,
                reason=reason,
                evidence="temporary_platform_failure",
            )
            logger.warning(
                f"Account id={account_id} {reason}, cooldown until {account.cooldown_until}"
            )
        else:
            account.consecutive_fails += 1

            if is_ban or account.consecutive_fails >= MAX_CONSECUTIVE_FAILS:
                account.status = AccountStatus.BANNED.value
                _log_account_state_transition(
                    account,
                    previous_status=previous_status,
                    new_status=AccountStatus.BANNED.value,
                    reason=reason,
                    evidence="ban_threshold",
                )
                logger.warning(
                    f"Account id={account_id} BANNED after {account.consecutive_fails} fails"
                )
            elif reason == "rate_limit":
                account.status = AccountStatus.COOLDOWN.value
                account.cooldown_until = datetime.utcnow() + timedelta(hours=COOLDOWN_HOURS)
                _log_account_state_transition(
                    account,
                    previous_status=previous_status,
                    new_status=AccountStatus.COOLDOWN.value,
                    reason=reason,
                    evidence="rate_limit",
                )
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
        """Agent执行成功后持久化登录态.

        Refs #963 audit pain point #2: reset ``expired_transition_count`` to 0
        here so a genuinely successful re-login (fresh cookies persisted, status
        flipped back to active) clears the ricochet counter and the account can
        cycle through expired again before triggering the 3-strike permanent ban.
        Without this reset the counter would only count down on ban.
        """
        account = await self.db.get(LLMAccount, account_id)
        if account:
            previous_status = str(account.status or "")
            account.cookies_json = cookies_json
            account.cookies_updated_at = datetime.utcnow()
            account.status = AccountStatus.ACTIVE.value
            account.cooldown_until = None
            account.consecutive_fails = 0
            account.expired_transition_count = 0
            if previous_status != AccountStatus.ACTIVE.value:
                _log_account_state_transition(
                    account,
                    previous_status=previous_status,
                    new_status=AccountStatus.ACTIVE.value,
                    reason="cookies_imported",
                    evidence="cookie_write_back",
                )
            await self.db.commit()

    async def create_account(
        self, llm_name: str, phone: str, cookies_json: str
    ) -> LLMAccount:
        """注册新账号后创建 DB 记录.

        Refs #963: ``phone`` MUST be the raw number from the SMS provider
        (e.g. ``"14712340231"`` or ``"+8614712340231"``) — never the
        masked form emitted by :func:`mask_phone` (e.g. ``"147****0231"``).
        ``auto_login``'s re-login path validates ``phone_number`` against
        ``\\d{11}`` before re-reserving an SMS lease; storing a masked
        value here breaks that regex and forces every subsequent re-login
        attempt to refuse the SMS reuse and fall through to "降级为新注册流程",
        which then aborts because ``existing_cookies`` is also set. The
        result is a Doubao account permanently stuck on a bot-flagged
        cookie set with no recovery path. Reject the masked form
        explicitly so any future regression that re-introduces the bug
        surfaces at write time instead of later, in production, when an
        account is already corrupted.
        """
        if phone and "*" in phone:
            # ``mask_phone`` is the only producer of ``*`` in our codebase
            # for phone-like strings; surfacing as ValueError makes the
            # caller's stack trace point at the offending site.
            raise ValueError(
                f"create_account refused masked phone for {llm_name!r}: "
                f"phone must be the raw SMS-provider value, not the "
                f"mask_phone() output (got {mask_phone(phone)!r})"
            )
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
