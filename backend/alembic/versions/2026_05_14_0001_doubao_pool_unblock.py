"""One-shot Doubao account pool unblock for incident #908 / Epic #852.

Production snapshot (#853, brand 24): 12 banned + 2 cooldown + 3 expired
Doubao accounts, all with cookies still present, ``0`` active. ``acquire()``
filters strictly by ``status='active'`` so the pool reads exhausted even
though usable login material exists on the non-active rows.

This migration flips Doubao accounts in (cooldown, expired, banned) back to
ACTIVE for rows where cookies_json is still present. The companion code
change (``promote_expired_cooldowns`` + read-side pool snapshot) prevents
the regression for cooldown windows going forward; this migration is the
single data repair so the user-visible Doubao pipeline unblocks on deploy
without an extra operator script invocation.

Authorization: user goal directive on issue #908 — "账号你可以自己重置，或者启用".

Safety:
- Scoped to ``llm_name='doubao'`` only.
- Skips rows whose cookies_json is NULL or empty (those need cookie re-import
  via ``scripts/import_cookies.py``).
- Idempotent within a single Alembic run: ``status IN (...)`` filter is
  empty after a successful repair.
- Alembic runs each revision once per database, so the same deploy will
  not re-flip a row that has been manually banned again later.
- ``consecutive_fails=0`` and ``query_count_today=0`` are reset so the
  acquire() path can pick the rows up without re-banning them on the
  first daily-quota check.

Revision ID: 20260514_doubao_unblock
Revises: 20260513_analyzer_batches
Create Date: 2026-05-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20260514_doubao_unblock"
down_revision: str | Sequence[str] | None = "20260513_analyzer_batches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(name: str) -> bool:
    return inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if not _table_exists("llm_accounts"):
        return

    result = bind.execute(
        sa.text(
            """
            UPDATE llm_accounts
            SET status='active',
                cooldown_until=NULL,
                consecutive_fails=0,
                query_count_today=0
            WHERE llm_name='doubao'
              AND lower(status) IN ('cooldown', 'expired', 'banned')
              AND cookies_json IS NOT NULL
              AND cookies_json != ''
            RETURNING id, status
            """
        )
    )
    repaired = [(int(row[0]), str(row[1])) for row in result.fetchall()]
    if repaired:
        print(
            f"[20260514_doubao_unblock] Repaired {len(repaired)} Doubao accounts "
            f"(non-active -> active, cookies retained): "
            f"{[r[0] for r in repaired]}"
        )
    else:
        print("[20260514_doubao_unblock] No Doubao accounts required repair.")


def downgrade() -> None:
    # No-op: this is a one-shot data repair. We do not unfilp accounts back
    # to their previous broken state. If a rollback is needed, operators can
    # manually adjust statuses via the Admin API.
    pass
