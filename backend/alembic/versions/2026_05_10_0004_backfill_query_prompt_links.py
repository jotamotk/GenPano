"""Backfill orphan queries → topics/prompts links.

Revision ID: 20260510_backfill_links
Revises: 20260510_llm_extraction
Create Date: 2026-05-10

The admin "Query Attempts" filter dropdowns cascade brand → topic → prompt
via the picker endpoint. Queries created through the ad-hoc POST /api/queries
path (app/admin/queries/db.py:create_query, pre-fix) inserted rows with
prompt_id=NULL, so the topic/prompt dropdowns showed nothing for brands whose
data only came from that path — operators couldn't drill into 雅诗兰黛
(Estée Lauder) data even though the rows were there.

This migration is idempotent — it inserts a default `legacy-import` topic
per brand-with-orphans, fans out a prompt per (brand, query_text), then
links queries.prompt_id where NULL. NOT EXISTS guards make re-running a
no-op. The forward-path fix lives in app/admin/queries/db.py:create_query
which now calls ensure_default_prompt() before INSERT.

SQLite (CI) is a no-op — these tables aren't on the CI bind.
"""
from collections.abc import Sequence
import logging

from alembic import op
from sqlalchemy import inspect

revision: str = "20260510_backfill_links"
down_revision: str | Sequence[str] | None = "20260510_llm_extraction"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger("alembic.runtime.migration")


def _table_exists(name: str) -> bool:
    return inspect(op.get_bind()).has_table(name)


def _columns(table: str) -> set[str]:
    if not _table_exists(table):
        return set()
    return {col["name"] for col in inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    if not (_table_exists("queries") and _table_exists("topics") and _table_exists("prompts")):
        return

    bind = op.get_bind()
    queries_cols = _columns("queries")
    topics_cols = _columns("topics")
    prompts_cols = _columns("prompts")
    if not (
        {"brand_id", "query_text", "prompt_id"}.issubset(queries_cols)
        and {"brand_id", "text"}.issubset(topics_cols)
        and {"topic_id", "text"}.issubset(prompts_cols)
    ):
        return

    has_topic_category = "category" in topics_cols
    has_topic_status = "status" in topics_cols
    has_topic_generated_by = "generated_by" in topics_cols
    has_topic_created_at = "created_at" in topics_cols
    has_prompt_intent = "intent" in prompts_cols
    has_prompt_language = "language" in prompts_cols
    has_prompt_status = "status" in prompts_cols
    has_prompt_generated_by = "generated_by" in prompts_cols
    has_prompt_created_at = "created_at" in prompts_cols

    if not has_topic_category:
        log.warning(
            "backfill_query_prompt_links: topics.category missing — skipping (cannot mark legacy-import)"
        )
        return

    # ── Step 1: default topic per brand ─────────────────────────────────
    topic_columns = ["brand_id", "text", "category"]
    topic_values = [":brand_id", "'未分类查询'", "'legacy-import'"]
    if has_topic_generated_by:
        topic_columns.append("generated_by")
        topic_values.append("'backfill'")
    if has_topic_status:
        topic_columns.append("status")
        topic_values.append("'active'")
    if has_topic_created_at:
        topic_columns.append("created_at")
        topic_values.append("NOW()")

    insert_topics_sql = f"""
        INSERT INTO topics ({', '.join(topic_columns)})
        SELECT DISTINCT
            q.brand_id,
            '未分类查询',
            'legacy-import'
            {", 'backfill'" if has_topic_generated_by else ''}
            {", 'active'" if has_topic_status else ''}
            {", NOW()" if has_topic_created_at else ''}
        FROM queries q
        WHERE q.brand_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM topics t
              WHERE t.brand_id = q.brand_id AND t.category = 'legacy-import'
          )
        RETURNING id
    """
    result = bind.exec_driver_sql(insert_topics_sql)
    topics_inserted = result.rowcount or 0

    # ── Step 2: default prompt per (brand, query_text) ──────────────────
    prompt_columns = ["topic_id", "text"]
    prompt_select = ["t.id", "q.query_text"]
    if has_prompt_intent:
        prompt_columns.append("intent")
        prompt_select.append("'informational'")
    if has_prompt_language:
        prompt_columns.append("language")
        prompt_select.append("'zh'")
    if has_prompt_status:
        prompt_columns.append("status")
        prompt_select.append("'active'")
    if has_prompt_generated_by:
        prompt_columns.append("generated_by")
        prompt_select.append("'backfill'")
    if has_prompt_created_at:
        prompt_columns.append("created_at")
        prompt_select.append("NOW()")

    insert_prompts_sql = f"""
        INSERT INTO prompts ({', '.join(prompt_columns)})
        SELECT DISTINCT {', '.join(prompt_select)}
        FROM queries q
        JOIN topics t ON t.brand_id = q.brand_id AND t.category = 'legacy-import'
        WHERE q.prompt_id IS NULL
          AND q.query_text IS NOT NULL
          AND q.query_text <> ''
          AND NOT EXISTS (
              SELECT 1 FROM prompts pr
              WHERE pr.topic_id = t.id AND pr.text = q.query_text
          )
        RETURNING id
    """
    result = bind.exec_driver_sql(insert_prompts_sql)
    prompts_inserted = result.rowcount or 0

    # ── Step 3: link orphan queries to their prompts ────────────────────
    update_sql = """
        UPDATE queries q
        SET prompt_id = pr.id
        FROM prompts pr
        JOIN topics t ON pr.topic_id = t.id
        WHERE q.prompt_id IS NULL
          AND q.brand_id = t.brand_id
          AND pr.text = q.query_text
          AND t.category = 'legacy-import'
    """
    result = bind.exec_driver_sql(update_sql)
    queries_linked = result.rowcount or 0

    brands_processed = bind.exec_driver_sql(
        "SELECT COUNT(DISTINCT brand_id) FROM topics WHERE category='legacy-import'"
    ).scalar() or 0

    log.info(
        "backfill_query_prompt_links: brands=%d topics+=%d prompts+=%d queries_linked=%d",
        int(brands_processed),
        int(topics_inserted),
        int(prompts_inserted),
        int(queries_linked),
    )


def downgrade() -> None:
    """No-op. This is a data backfill; rolling back would either leave
    queries with dangling prompt_ids or destroy the legacy-import
    bookkeeping. Operators can manually purge category='legacy-import'
    rows if absolutely needed (see DEPLOY_GUIDE rollback section)."""
    return
