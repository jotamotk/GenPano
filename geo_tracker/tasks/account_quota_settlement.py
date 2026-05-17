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
        response_text: str | None = None,
    ) -> bool:
        if not self.reserved_account_id or self.settled:
            return False

        self.settled = True

        if _should_report_account_failure(reason):
            if pool is not None:
                # Refs #963 Codex P1 on PR #1109: the strike-skip guard
                # in :meth:`AccountPool.report_failure` is consulted at
                # the failure decision moment — BEFORE ``db.add(response)``
                # has inserted the ``LLMResponse`` row. Forward
                # ``response_text`` (the in-memory captured answer) so
                # the helper can detect a first-time Mode-C false-
                # positive even when no orphan row exists yet. The DB
                # lookup remains as a fallback for orphan-row cases
                # (e.g. Q-184971's row 668 from a prior successful attempt).
                await pool.report_failure(
                    self.reserved_account_id,
                    reason=reason or "unknown",
                    query_id=query_id,
                    response_text=response_text,
                )
            return False

        if self.platform_consumed:
            return False

        return await refund_account_quota_reservation(
            db,
            self.reserved_account_id,
            reason=reason,
        )
