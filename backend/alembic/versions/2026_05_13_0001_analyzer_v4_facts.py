"""Add analyzer v4 run and current fact tables.

Revision ID: 20260513_analyzer_v4
Revises: 20260511_quota_repairs
Create Date: 2026-05-13

Rollback note:
Downgrade drops the v4 fact/run tables. It also drops the product-aware
brand_mentions uniqueness constraint and attempts to restore the prior
brand-only constraint. If production already contains multiple products for the
same response/brand, operators must dedupe or archive those rows before
downgrading to the old constraint.
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

revision: str = "20260513_analyzer_v4"
down_revision: str | Sequence[str] | None = "20260511_quota_repairs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(name: str) -> bool:
    return inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    if not _table_exists("llm_responses"):
        return

    if _table_exists("brand_mentions"):
        op.execute(
            """
            ALTER TABLE brand_mentions
            DROP CONSTRAINT IF EXISTS uq_mention_response_brand;
            """
        )
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'uq_mention_response_brand_product'
                ) THEN
                    ALTER TABLE brand_mentions
                    ADD CONSTRAINT uq_mention_response_brand_product
                    UNIQUE (response_id, brand_name, product_name);
                END IF;
            END $$;
            """
        )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analyzer_runs (
            id SERIAL PRIMARY KEY,
            response_id INTEGER NOT NULL REFERENCES llm_responses(id) ON DELETE CASCADE,
            schema_version VARCHAR(64) NOT NULL DEFAULT 'analyzer_v4',
            prompt_version VARCHAR(128),
            provider VARCHAR(64),
            model VARCHAR(128),
            status VARCHAR(16) NOT NULL DEFAULT 'running',
            trigger_source VARCHAR(64),
            idempotency_key VARCHAR(128),
            raw_output_sha256 VARCHAR(64),
            validator_summary_json JSONB,
            started_at TIMESTAMP NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMP,
            failure_code VARCHAR(64),
            failure_message TEXT
        );
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS response_entities (
            id SERIAL PRIMARY KEY,
            run_id INTEGER NOT NULL REFERENCES analyzer_runs(id) ON DELETE CASCADE,
            response_id INTEGER NOT NULL REFERENCES llm_responses(id) ON DELETE CASCADE,
            entity_key VARCHAR(128) NOT NULL,
            entity_type VARCHAR(32) NOT NULL,
            raw_name VARCHAR(512) NOT NULL,
            canonical_id VARCHAR(128),
            canonical_name VARCHAR(512),
            canonicalization_status VARCHAR(32) NOT NULL,
            evidence_quote TEXT,
            confidence DOUBLE PRECISION,
            quality_flags_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_response_entities_run_key UNIQUE (run_id, entity_key)
        );
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS response_relation_facts (
            id SERIAL PRIMARY KEY,
            run_id INTEGER NOT NULL REFERENCES analyzer_runs(id) ON DELETE CASCADE,
            response_id INTEGER NOT NULL REFERENCES llm_responses(id) ON DELETE CASCADE,
            relation_key VARCHAR(128) NOT NULL,
            subject_entity_key VARCHAR(128) NOT NULL,
            relation_type VARCHAR(64) NOT NULL,
            object_entity_key VARCHAR(128) NOT NULL,
            direction VARCHAR(16),
            evidence_quote TEXT,
            confidence DOUBLE PRECISION,
            quality_flags_json JSONB,
            status VARCHAR(32) NOT NULL DEFAULT 'current',
            kg_candidate_id INTEGER,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_relation_facts_run_key UNIQUE (run_id, relation_key)
        );
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_fact_links (
            id SERIAL PRIMARY KEY,
            run_id INTEGER NOT NULL REFERENCES analyzer_runs(id) ON DELETE CASCADE,
            response_id INTEGER NOT NULL REFERENCES llm_responses(id) ON DELETE CASCADE,
            fact_type VARCHAR(32) NOT NULL,
            fact_key VARCHAR(128) NOT NULL,
            linked_fact_type VARCHAR(32) NOT NULL,
            linked_fact_key VARCHAR(128) NOT NULL,
            link_type VARCHAR(32) NOT NULL DEFAULT 'supports',
            evidence_quote TEXT,
            source_path VARCHAR(256),
            status VARCHAR(32) NOT NULL DEFAULT 'current',
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_analysis_fact_links_run_fact_link UNIQUE (
                run_id, fact_type, fact_key, linked_fact_type,
                linked_fact_key, link_type
            )
        );
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analyzer_quality_flags (
            id SERIAL PRIMARY KEY,
            run_id INTEGER NOT NULL REFERENCES analyzer_runs(id) ON DELETE CASCADE,
            response_id INTEGER NOT NULL REFERENCES llm_responses(id) ON DELETE CASCADE,
            flag_key VARCHAR(128) NOT NULL,
            severity VARCHAR(16) NOT NULL,
            code VARCHAR(64) NOT NULL,
            message TEXT NOT NULL,
            target_type VARCHAR(32) NOT NULL,
            target_key VARCHAR(128),
            blocks_metric_readiness BOOLEAN DEFAULT FALSE,
            evidence_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_analyzer_quality_flags_run_key UNIQUE (run_id, flag_key)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_analyzer_runs_response "
        "ON analyzer_runs (response_id, started_at DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_response_entities_response "
        "ON response_entities (response_id, entity_type);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_response_relation_facts_response "
        "ON response_relation_facts (response_id, relation_type);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_analysis_fact_links_response "
        "ON analysis_fact_links (response_id, fact_type);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_analyzer_quality_flags_response "
        "ON analyzer_quality_flags (response_id, code);"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("DROP TABLE IF EXISTS analyzer_quality_flags;")
    op.execute("DROP TABLE IF EXISTS analysis_fact_links;")
    op.execute("DROP TABLE IF EXISTS response_relation_facts;")
    op.execute("DROP TABLE IF EXISTS response_entities;")
    op.execute("DROP TABLE IF EXISTS analyzer_runs;")
    if _table_exists("brand_mentions"):
        op.execute(
            """
            ALTER TABLE brand_mentions
            DROP CONSTRAINT IF EXISTS uq_mention_response_brand_product;
            """
        )
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'uq_mention_response_brand'
                ) THEN
                    ALTER TABLE brand_mentions
                    ADD CONSTRAINT uq_mention_response_brand
                    UNIQUE (response_id, brand_name);
                END IF;
            END $$;
            """
        )
