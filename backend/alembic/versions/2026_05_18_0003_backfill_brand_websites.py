"""Backfill ``brands.website`` for bestCoffer + competitors (Refs Issue #1225).

User-reported on 2026-05-18 (#1225): the bestCoffer brand-overview
dashboard surfaced ``引用份额 = 100%``. The captured DB probe
(workflow run 26026560992) confirmed:

  - ``brands.website`` is empty for bestCoffer (brand_id=24), 欧莱雅
    (brand_id=11), and 雅诗兰黛 (brand_id=12).
  - ``citation_sources`` shows 1243 ``unresolved_brand`` rows
    (``mention_id IS NULL``), of which 200 rows on **44 responses**
    point at ``bestcoffer.com`` — the target's own domain falls into
    the unresolved bucket because ``citation_mapper.map_citations`` only
    seeds ``brand_domains`` from ``target_brand.website`` (line 80-84),
    and the column is empty.
  - As a downstream effect, ``contracts/builder.py`` joins
    ``citation_sources.mention_id`` → ``brand_mentions`` on
    ``brand_id != target`` to compute ``competitive_citation_count``.
    NULL never joins, so the count is 0 and the frontend divides
    ``target_sum / total_sum = 127/127 = 100%``.

The companion code change in ``geo_tracker/analyzer/citation_mapper.py``
extends ``map_citations`` to include competitor websites in
``brand_domains``. For that fix to take effect, the columns must hold
the actual domains. This migration backfills the three rows that the
probe identified as empty.

Brands ``2`` (理肤泉) and ``10`` (华为) already have non-empty
``website`` values from the legacy data load — those rows are NOT
touched. The companion table ``brand_official_domains`` is out of
scope for this migration; the citation_mapper does not currently read
from it.

The migration is **idempotent**: each UPDATE only takes effect if
``website`` is currently NULL or empty, so re-running on an already-
populated row is a no-op. Downgrade clears the value back to NULL only
when it still matches what this migration wrote, so a later manual
edit is preserved.

Revision ID: 20260518_backfill_brand_websites
Revises: 20260518_merge_heads
Create Date: 2026-05-18
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

revision: str = "20260518_backfill_brand_websites"
down_revision: str | Sequence[str] | None = "20260518_merge_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (brand_id, website) tuples for rows whose ``website`` is currently
# empty per the readonly evidence probe (run 26026560992).
BRAND_WEBSITES: tuple[tuple[int, str], ...] = (
    (24, "bestcoffer.com"),
    (11, "loreal.com.cn"),
    (12, "esteelauder.com.cn"),
)


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
    if not _column_exists("brands", "website"):
        # Same defensive stance - the column is part of the baseline
        # ORM schema; tests / fresh schemas without it are explicit
        # no-op territory.
        return

    for brand_id, website in BRAND_WEBSITES:
        op.execute(
            f"""
            UPDATE brands
            SET website = '{website}'
            WHERE id = {brand_id}
              AND (website IS NULL OR website = '')
            """
        )


def downgrade() -> None:
    if not _table_exists("brands") or not _column_exists("brands", "website"):
        return

    for brand_id, website in BRAND_WEBSITES:
        op.execute(
            f"""
            UPDATE brands
            SET website = NULL
            WHERE id = {brand_id}
              AND website = '{website}'
            """
        )
