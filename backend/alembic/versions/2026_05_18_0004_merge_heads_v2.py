"""Merge second concurrent head pair on 2026-05-18.

Two more sibling migrations landed on ``main`` with the same
``down_revision`` of ``20260518_merge_heads``:

- ``20260518_backfill_brand_websites``
  (PR #1234 — symmetric citation->brand domain attribution + backfill
  website columns).
- ``20260518_backfill_ds_brands``
  (PR #1236 — backfill ``brands`` table with 9 数据安全 industry
  entries so #1218's unified industry filter resolves the name-only
  mention buckets and the bestCoffer competitor panel populates).

Each was correct in isolation, but the live ``alembic upgrade head``
step in ``deploy.yml`` failed with "Multiple head revisions are
present", blocking the prod rollout that #1236 needs to deliver the
business goal on #1185. This migration is a no-op graph merge — no
schema change, no data change — purely a structural join so future
migrations chain off a single head again.
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "20260518_merge_heads_v2"
down_revision: str | Sequence[str] | None = (
    "20260518_backfill_brand_websites",
    "20260518_backfill_ds_brands",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No-op: this revision only joins two concurrent heads."""


def downgrade() -> None:
    """No-op: matching no-op downgrade."""
