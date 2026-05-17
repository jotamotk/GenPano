from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from geo_tracker.pool.account_pool import (
    AccountPool,
    refund_account_quota_reservation,
)
from geo_tracker.tasks.query_failure import _should_report_account_failure


@dataclass
class AccountQuotaSettlement:
    """Per-worker-attempt guard for account quota reservation settlement."""

    reserved_account_id: int | None = None
    settled: bool = False
    platform_consumed: bool = False

    def reserve(self, account_id: int | None) -> None:
        self.reserved_account_id = account_id
        self.settled = False
        self.platform_consumed = False

    def mark_platform_consumed(self) -> None:
        self.platform_consumed = True

    async def settle_success(self, pool: AccountPool | None) -> bool:
        if not self.reserved_account_id or self.settled:
            return False
        if pool is not None:
            await pool.report_success(self.reserved_account_id)
        self.settled = True
        return False

    async def settle_failure(
        self,
        db: Any,
        pool: AccountPool | None,
        *,
        reason: str | None,
        query_id: int | None = None,
    ) -> bool:
        if not self.reserved_account_id or self.settled:
            return False

        self.settled = True

        if _should_report_account_failure(reason):
            if pool is not None:
                # Refs #963 (PR ``claude/issue-963-3strike-respect-real-response``):
                # forward ``query_id`` so :meth:`AccountPool.report_failure`
                # can skip the ``expired_transition_count`` strike when the
                # query already has a real captured ``llm_responses`` row
                # (defense-in-depth against the Mode-C validator
                # false-positive — see ``STRIKE_SKIP_MIN_RAW_TEXT_CHARS`` in
                # ``geo_tracker.pool.account_pool``).
                await pool.report_failure(
                    self.reserved_account_id,
                    reason=reason or "unknown",
                    query_id=query_id,
                )
            return False

        if self.platform_consumed:
            return False

        return await refund_account_quota_reservation(
            db,
            self.reserved_account_id,
            reason=reason,
        )
