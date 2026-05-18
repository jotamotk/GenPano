"""Merge concurrent alembic heads on 2026-05-18.

Two siblings landed on ``main`` with the same ``down_revision`` of
``20260517_exec_mode``:

- ``20260518_pano_geo_nullable``
  (PR #1207 — ``response_analyses.geo_score`` nullable + drop the
  ``server_default="0.0"`` so absent target-brand scores no longer
  coerce to 0.0 and dilute brand-overview means).
- ``20260518_set_bestcoffer_industry``
  (Issue #1185/#1200/#975 — backfill ``brands.industry='数据安全'`` for
  bestCoffer so the unified industry guard at #1192 does not collapse
  the panel to ``state=empty``).

Each was correct in isolation, but the result is two heads. CI's
``alembic upgrade head`` regression guard rejects multi-head states
("Multiple head revisions are present"), which blocks every other PR.
This migration is a no-op graph merge — no schema change, no data
change — purely a structural join so future migrations chain off a
single head again.
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "20260518_merge_heads"
down_revision: str | Sequence[str] | None = (
    "20260518_pano_geo_nullable",
    "20260518_set_bestcoffer_industry",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No-op: this revision only joins two concurrent heads."""


def downgrade() -> None:
    """No-op: downgrade walks back to whichever parent the user picks."""
