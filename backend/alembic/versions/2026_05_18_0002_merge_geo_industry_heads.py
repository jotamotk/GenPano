"""Merge the two 2026-05-18 alembic heads.

`20260518_pano_geo_nullable` (#1207, response_analyses.geo_score default)
and `20260518_set_bestcoffer_industry` (#1218/#975, brands.industry data
fix) were both authored against `20260517_exec_mode` without a merge
migration, so alembic upgrade head fails with "Multiple head revisions
are present for given argument 'head'". This empty merge migration
re-unifies the chain so `alembic upgrade head` resumes deterministically.
The two parent migrations touch disjoint tables, so the merge has no
schema or data work of its own.
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "20260518_merge_geo_industry"
down_revision: str | Sequence[str] | None = (
    "20260518_pano_geo_nullable",
    "20260518_set_bestcoffer_industry",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
