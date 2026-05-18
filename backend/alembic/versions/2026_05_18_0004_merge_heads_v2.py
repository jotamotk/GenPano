"""Merge concurrent alembic heads (second occurrence on 2026-05-18).

Two siblings landed on ``main`` after PR #1227's first merge migration:

- ``20260518_backfill_brand_websites``
  (#1234 — Refs Issue #1225 — backfill ``brands.website`` for bestCoffer,
  欧莱雅, 雅诗兰黛 so the citation-mapper domain lookup has anything to
  match against).
- ``20260518_backfill_ds_brands``
  (#1236 — Refs Issue #1185 / #1230 — backfill 9 数据安全 industry brands).

Both used ``20260518_merge_heads`` as their ``down_revision`` and landed
concurrently, so ``alembic upgrade head`` raises
``Multiple head revisions are present`` on every deployment — same class
of issue PR #1227 (``20260518_merge_heads``) resolved earlier today.
That earlier merge migration only collapsed the heads that existed at
its time; subsequent concurrent merges produce new sibling heads that
need another structural merge revision.

No-op merge — purely a graph join so future migrations chain off one
head again.
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
    """No-op: downgrade walks back to whichever parent the user picks."""
