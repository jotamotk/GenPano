"""Backfill ``brands.industry`` for bestCoffer (Refs Issue #1200 / #1185 / #975).

User-reported on 2026-05-18 (#1185): the competitor analysis panel
for bestCoffer surfaced brands from unrelated industries. The code
path fix (#1192) added a unified industry filter that fails closed
when ``brands.industry`` is NULL/empty for the primary brand. That
behavior is correct as a guard rail, but for bestCoffer the user-
visible state would degrade to ``state="empty",
state_reason="primary_brand_industry_missing"`` until the row's
``industry`` is populated. This migration fills it in.

Issue #1200 (data fix) records:
    bestCoffer = brands.id = 24
    canonical name (name_en) = 'bestCoffer'
    correct industry text     = '数据安全'

The migration is **idempotent**: the UPDATE only takes effect if
``industry`` is currently NULL or empty, so re-running on an already-
populated row is a no-op. Downgrade clears the value back to NULL
only when it matches '数据安全' so we do not stomp a later manual
edit.

Revision ID: 20260518_set_bestcoffer_industry
Revises: 20260517_exec_mode
Create Date: 2026-05-18
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

revision: str = "20260518_set_bestcoffer_industry"
down_revision: str | Sequence[str] | None = "20260517_exec_mode"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


BRAND_ID = 24
TARGET_INDUSTRY = "数据安全"


def _table_exists(name: str) -> bool:
    return inspect(op.get_bind()).has_table(name)


def _column_exists(table: str, column: str) -> bool:
    insp = inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    if not _table_exists("brands"):
        # Defensive: env that has not yet promoted the legacy brands
        # table simply skips the data fix. Operationally this should
        # never trigger - the legacy `brands` table predates the ORM.
        return
    if not _column_exists("brands", "industry"):
        # Same defensive stance - the column has existed in production
        # since #975's first attempt; tests / fresh schemas without
        # it are explicit no-op territory.
        return

    op.execute(
        f"""
        UPDATE brands
        SET industry = '{TARGET_INDUSTRY}'
        WHERE id = {BRAND_ID}
          AND (industry IS NULL OR industry = '')
        """  # noqa: S608 - constants only, no user input
    )


def downgrade() -> None:
    if not _table_exists("brands") or not _column_exists("brands", "industry"):
        return

    op.execute(
        f"""
        UPDATE brands
        SET industry = NULL
        WHERE id = {BRAND_ID}
          AND industry = '{TARGET_INDUSTRY}'
        """  # noqa: S608 - constants only, no user input
    )
