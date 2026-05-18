"""Stop response_analyses.geo_score from coercing N/A to 0.0 (Refs PR #1207).

The column had ``server_default="0.0"``. The analyzer at
``geo_tracker/analyzer/cli.py:1251`` produces ``geo_score = None`` whenever
the target brand is not mentioned, or when any GEOScorer component
(visibility/sentiment/sov/citations) is missing. Per the aggregator's own
warning at ``geo_tracker/analyzer/aggregator.py:387-389`` — "SQLAlchemy
client defaults on legacy score columns can coerce absent values to 0.0
on INSERT" — those NULLs ended up as 0.0 in the DB, and downstream
unweighted means (e.g. the brand-overview admin-facts path at
``backend/app/api/v1/projects/_overview_service.py:552``) treated those
zero-default rows as real scores.

User-visible effect (PR #1207 root-cause evidence): bestCoffer brand
overview rendered ``GeoScore = 9`` because ~121 non-mention rows for the
window stored ``geo_score = 0.0`` and dragged the mean of mention-bearing
rows down. ``GEOScorer.calc_overall`` has ``BASE_MIN = 20`` so a sub-20
average is mathematically impossible without 0.0 dilution.

Upgrade:
  1. Drop the server default (idempotent — guarded by inspecting the
     current column metadata).
  2. Backfill 0.0 → NULL on rows where ``target_brand_mentioned = false``.
     That subset cannot have a real GEOScorer.calc_overall output (the
     analyzer short-circuits to ``geo_score = None`` for those rows), so
     a 0.0 there is necessarily a default-coercion artifact.
  3. Leave 0.0 values on ``target_brand_mentioned = true`` rows alone:
     they could be either default-coercion (analyzer hit a missing
     component) or a real near-floor calc, and we have no per-row signal
     to tell them apart. Downstream consumers should treat NULL as
     "no data".

Downgrade:
  Re-add ``server_default="0.0"``. We do NOT re-coerce the rows we
  NULLed: NULL is the semantically correct value for "no data", and a
  downgrade is a rollback of the schema metadata only.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20260518_pano_geo_nullable"
down_revision: str | Sequence[str] | None = "20260517_exec_mode"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "response_analyses"
COLUMN = "geo_score"


def _column_default(table: str, column: str) -> str | None:
    insp = inspect(op.get_bind())
    if not insp.has_table(table):
        return None
    for col in insp.get_columns(table):
        if col["name"] == column:
            return col.get("default")
    return None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table(TABLE):
        return

    # Step 1: drop the column default. Postgres takes a plain ALTER COLUMN.
    # SQLite cannot ALTER COLUMN DROP DEFAULT in place; the usual escape
    # is batch_alter_table, but that reflects every FK target (including
    # llm_responses which is owned by the legacy migrations directory and
    # not present at this point in the alembic chain on a fresh DB), so it
    # raises NoSuchTableError on SQLite. Tests build the schema via
    # ``Base.metadata.create_all`` directly from the model in
    # ``backend/genpano_models/analyzer.py`` (which already has no default),
    # so skipping the SQLite branch leaves test behaviour correct.
    current_default = _column_default(TABLE, COLUMN)
    if current_default is not None and bind.dialect.name == "postgresql":
        # Bound the lock_timeout to the same 5s the recent
        # expired-trans-count migration uses (PR #1102/#1104 incident —
        # long AccessExclusiveLock on a table with active analyzer
        # writers).
        op.execute("SET lock_timeout = '5s'")
        op.alter_column(
            TABLE,
            COLUMN,
            existing_type=sa.Float(),
            existing_nullable=True,
            server_default=None,
        )

    # Step 2: backfill 0.0 → NULL for the rows that cannot represent a real
    # calc_overall output (target not mentioned ⇒ analyzer returned None ⇒
    # current 0.0 is a server_default coercion). The predicate covers both
    # FALSE and NULL ``target_brand_mentioned`` rows (canonical_brand_repair
    # can leave the flag NULL on legacy paths). Runs on both PG and SQLite.
    op.execute(
        sa.text(
            f"UPDATE {TABLE} "
            f"SET {COLUMN} = NULL "
            f"WHERE {COLUMN} = 0.0 "
            f"AND (target_brand_mentioned IS NULL OR target_brand_mentioned = FALSE)"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table(TABLE):
        return
    if bind.dialect.name != "postgresql":
        # Same SQLite caveat as upgrade(): batch_alter_table cannot reflect
        # llm_responses FK target in this alembic chain. Tests don't rely
        # on the column default, so leave the SQLite schema untouched.
        return
    op.execute("SET lock_timeout = '5s'")
    op.alter_column(
        TABLE,
        COLUMN,
        existing_type=sa.Float(),
        existing_nullable=True,
        server_default="0.0",
    )
