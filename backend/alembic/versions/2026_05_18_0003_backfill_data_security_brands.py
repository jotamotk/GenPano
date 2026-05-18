"""Backfill ``brands`` with 9 数据安全 entries (Refs #1185 / #1218 / #1230).

User-reported on 2026-05-18 (#1185 follow-up #1230): after #1218 landed
the unified industry filter the bestCoffer competitor panel collapsed
to *empty* on the live test environment. The post-deploy readback
(https://github.com/jotamotk/trash_test/actions/runs/26024712433)
shows the LLM responses for bestCoffer in the 2026-05-11→2026-05-18
window contain 219 mentions of "IBM Security", 19 of "Intralinks",
10 of "Datasite", 5 of "三未信安", 3 of "天融信", 3 of "原点安全",
4 of "iDeals", 4 of "Filez" — and every one of them carries
``brand_id: null``. The #1218 filter resolves those name-only mention
buckets by looking up ``brands.name`` / ``name_en`` / ``name_zh`` /
``aliases``; with no row to hit, every mention is treated as
"unresolvable → drop" and the panel goes empty.

The lead-hat decision (recorded on #1230 on 2026-05-18) is a data-only
backfill: nine real-world 数据安全 brands are inserted into ``brands``
with ``industry='数据安全'`` plus the aliases needed for the
case-insensitive lookup in
``app.api.v1.projects._legacy_lookups.resolve_brand_industry_by_name``
to hit the variants observed in the mention buckets.

Schema notes (verified pre-write against #1218 / #1200 / #975):
    - The legacy ``brands`` table has no ``canonical_name`` column.
      The lookup helper scans the columns listed in
      ``BRAND_NAME_COLUMNS = ("name_zh", "name_en", "name", "primary_name")``.
      This migration stores each entry's canonical English-or-Chinese
      label in ``name_en`` (Latin) or ``name_zh`` (Han), mirroring the
      existing test fixture pattern in
      ``tests/test_competitor_industry_filter.py`` (which seeds
      ``brand_id=24`` as ``name_en='bestCoffer'``).
    - The ``aliases`` column is JSONB on Postgres (added in
      ``2026_05_06_0002_admin_console_consolidation.py`` via
      ``ALTER TABLE brands ADD COLUMN IF NOT EXISTS aliases JSONB``).
      On SQLite test binds the same column lands as TEXT — the
      JSON-string literal still round-trips through the helper, which
      falls back to ``json.loads`` when the LATERAL JSONB path raises.
    - No UNIQUE constraint exists on ``brands.name`` /
      ``brands.name_en`` / ``brands.name_zh``. Idempotency is enforced
      via ``WHERE NOT EXISTS (...)`` against the case-insensitive
      lookup columns — same shape the
      ``2026_05_10_0005_promote_brand_mentions`` migration uses.

Why this fix produces the final business outcome (per #1230 Root Cause
Gate): once the 9 rows exist, the filter's
``resolve_brand_industry_by_name`` call hits ``brands.industry='数据安全'``
for every leaked mention, the unified industry guard keeps them, and
``competitors[]`` returns the top 数据安全 rivals (IBM Security at the
top by mention count). Translation tools / general-purpose cloud AI /
cosmetics brands still resolve to a different industry (or remain
unresolvable) so they continue to be dropped.

Caveat surfaced for users on #1230 + #1185: the 9 new rows have no
historical ``geo_score_daily`` / aggregated metric rows. The
competitor panel's GeoScore / 提及率 / SoV columns will read as null
or low-confidence for these brands until the next aggregation pass
catches up. The mention-count column is correct.

Revision ID: 20260518_backfill_ds_brands
Revises: 20260518_merge_heads
Create Date: 2026-05-18
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect, text

revision: str = "20260518_backfill_ds_brands"
down_revision: str | Sequence[str] | None = "20260518_merge_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TARGET_INDUSTRY = "数据安全"


# Each tuple: (name_en, name_zh, aliases). name_en holds the canonical
# Latin label that ``resolve_brand_industry_by_name`` will hit for the
# observed mention text; name_zh holds the canonical Han label when the
# brand appears in Chinese in the live mention buckets. aliases covers
# both lowercase variants and the realistic Chinese alternates.
BRAND_BACKFILL: tuple[tuple[str | None, str | None, list[str]], ...] = (
    ("IBM Security", None, ["IBM Security", "IBM安全", "ibm security", "ibm 安全"]),
    ("Intralinks", None, ["Intralinks", "intralinks"]),
    ("Datasite", None, ["Datasite", "datasite"]),
    (
        "iDeals",
        None,
        ["iDeals", "iDeals Virtual Data Room", "ideals", "ideals vdr"],
    ),
    ("Filez", None, ["Filez", "filez", "联想Filez"]),
    (None, "三未信安", ["三未信安", "Sansec", "sansec"]),
    (None, "天融信", ["天融信", "Topsec", "topsec"]),
    (None, "原点安全", ["原点安全"]),
    ("DealRoom", None, ["DealRoom", "dealroom"]),
)


def _table_exists(name: str) -> bool:
    return inspect(op.get_bind()).has_table(name)


def _columns(table: str) -> set[str]:
    insp = inspect(op.get_bind())
    if not insp.has_table(table):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _table_exists("brands"):
        # Defensive: env that has not promoted the legacy `brands` table
        # is a no-op. Production has had this table since well before
        # the ORM era.
        return

    cols = _columns("brands")
    if "industry" not in cols:
        # The unified filter relies on `brands.industry`; without the
        # column there is nothing meaningful to backfill.
        return

    has_name_en = "name_en" in cols
    has_name_zh = "name_zh" in cols
    has_name = "name" in cols
    has_aliases = "aliases" in cols
    has_source = "source" in cols
    has_status = "status" in cols
    has_created_at = "created_at" in cols

    if not (has_name_en or has_name_zh or has_name):
        # Without any name column the lookup helper cannot hit these
        # rows. Skip rather than insert orphan rows.
        return

    bind = op.get_bind()
    dialect = bind.dialect.name

    for entry in BRAND_BACKFILL:
        name_en, name_zh, aliases = entry

        # Choose the canonical label for the bare ``name`` column when it
        # exists — the legacy helper checks ``name`` too. Prefer the
        # Latin form when present, otherwise the Han form. This mirrors
        # how older rows in production were promoted.
        canonical = name_en or name_zh
        if canonical is None:
            continue

        # Idempotency: skip the insert if a row already matches any of
        # the available name columns case-insensitively against the
        # canonical label. Uses the same OR-shape as
        # ``resolve_brand_industry_by_name`` so a row that would already
        # resolve is never duplicated.
        check_parts: list[str] = []
        check_params: dict[str, str] = {"canon_lower": canonical.casefold()}
        if has_name_en:
            check_parts.append("LOWER(TRIM(name_en)) = :canon_lower")
        if has_name_zh:
            check_parts.append("LOWER(TRIM(name_zh)) = :canon_lower")
        if has_name:
            check_parts.append("LOWER(TRIM(name)) = :canon_lower")

        check_sql = (
            "SELECT 1 FROM brands WHERE " + " OR ".join(check_parts) + " LIMIT 1"
        )
        existing = bind.execute(text(check_sql).bindparams(**check_params)).first()
        if existing is not None:
            continue

        # Build the INSERT column list dynamically so test/staging
        # schemas without optional columns still succeed. Always
        # populates ``industry``.
        insert_cols: list[str] = ["industry"]
        insert_placeholders: list[str] = [":industry"]
        params: dict[str, object] = {"industry": TARGET_INDUSTRY}

        if has_name_en and name_en is not None:
            insert_cols.append("name_en")
            insert_placeholders.append(":name_en")
            params["name_en"] = name_en
        if has_name_zh and name_zh is not None:
            insert_cols.append("name_zh")
            insert_placeholders.append(":name_zh")
            params["name_zh"] = name_zh
        if has_name:
            insert_cols.append("name")
            insert_placeholders.append(":name")
            params["name"] = canonical

        if has_aliases:
            insert_cols.append("aliases")
            aliases_payload = json.dumps(aliases, ensure_ascii=False)
            if dialect == "postgresql":
                insert_placeholders.append("CAST(:aliases AS JSONB)")
            else:
                insert_placeholders.append(":aliases")
            params["aliases"] = aliases_payload

        if has_source:
            insert_cols.append("source")
            insert_placeholders.append(":source")
            params["source"] = "backfill-1230"

        if has_status:
            insert_cols.append("status")
            insert_placeholders.append(":status")
            params["status"] = "active"

        if has_created_at and dialect == "postgresql":
            insert_cols.append("created_at")
            insert_placeholders.append("NOW()")

        insert_sql = (
            f"INSERT INTO brands ({', '.join(insert_cols)}) "
            f"VALUES ({', '.join(insert_placeholders)})"
        )
        # exec_driver_sql expects a sequence of params; pass the dict
        # directly since SQLAlchemy translates :name placeholders.
        op.execute(text(insert_sql).bindparams(**params))


def downgrade() -> None:
    """Best-effort removal of the 9 backfilled rows.

    Targets rows tagged with ``source='backfill-1230'`` when available,
    otherwise falls back to a case-insensitive name match scoped to
    ``industry='数据安全'`` so a later manual edit on an unrelated
    数据安全 row (e.g. bestCoffer itself) is never stomped.
    """
    if not _table_exists("brands"):
        return

    cols = _columns("brands")
    if "industry" not in cols:
        return

    if "source" in cols:
        op.execute(
            text("DELETE FROM brands WHERE source = :src AND industry = :ind").bindparams(
                src="backfill-1230", ind=TARGET_INDUSTRY
            )
        )
        return

    has_name_en = "name_en" in cols
    has_name_zh = "name_zh" in cols
    has_name = "name" in cols
    if not (has_name_en or has_name_zh or has_name):
        return

    for entry in BRAND_BACKFILL:
        name_en, name_zh, _aliases = entry
        canonical = name_en or name_zh
        if canonical is None:
            continue
        parts: list[str] = []
        if has_name_en:
            parts.append("LOWER(TRIM(name_en)) = :canon_lower")
        if has_name_zh:
            parts.append("LOWER(TRIM(name_zh)) = :canon_lower")
        if has_name:
            parts.append("LOWER(TRIM(name)) = :canon_lower")
        sql = (
            "DELETE FROM brands WHERE industry = :ind AND ("
            + " OR ".join(parts)
            + ")"
        )
        op.execute(
            text(sql).bindparams(canon_lower=canonical.casefold(), ind=TARGET_INDUSTRY)
        )
