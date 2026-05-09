"""LLM extraction candidates and KG attribute/claim layers.

Revision ID: 20260510_llm_extraction
Revises: 20260510_query_metadata
Create Date: 2026-05-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260510_llm_extraction"
down_revision: str | Sequence[str] | None = "20260510_query_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_entity_candidates (
            id VARCHAR(36) PRIMARY KEY,
            brand_id INTEGER,
            brand_context_version VARCHAR(64),
            entity_type VARCHAR(32) NOT NULL
                CHECK (entity_type IN ('brand','product','competitor','segment','profile','scenario')),
            name VARCHAR(256) NOT NULL,
            normalized_name VARCHAR(256) NOT NULL,
            parent_brand_id INTEGER,
            parent_brand_name VARCHAR(256),
            domain VARCHAR(256),
            candidate_key VARCHAR(768) NOT NULL UNIQUE,
            source VARCHAR(64) NOT NULL DEFAULT 'llm_search',
            confidence DOUBLE PRECISION,
            attributes_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            source_notes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            status VARCHAR(16) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','approved','rejected')),
            reviewed_by VARCHAR(36),
            reviewed_at TIMESTAMP,
            review_reason TEXT,
            mapped_entity_kind VARCHAR(32),
            mapped_entity_id VARCHAR(64),
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_llm_entity_candidates_status "
        "ON llm_entity_candidates (status, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_llm_entity_candidates_brand_context "
        "ON llm_entity_candidates (brand_id, brand_context_version);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_llm_entity_candidates_type "
        "ON llm_entity_candidates (entity_type, status);"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_attribute_candidates (
            id VARCHAR(36) PRIMARY KEY,
            brand_id INTEGER,
            brand_context_version VARCHAR(64),
            entity_kind VARCHAR(32) NOT NULL
                CHECK (entity_kind IN ('brand','product','competitor','segment','profile','scenario')),
            entity_id VARCHAR(64),
            entity_name VARCHAR(256) NOT NULL,
            attribute_key VARCHAR(128) NOT NULL,
            attribute_value TEXT NOT NULL,
            normalized_value VARCHAR(512) NOT NULL,
            candidate_key VARCHAR(1024) NOT NULL UNIQUE,
            source VARCHAR(64) NOT NULL DEFAULT 'llm_search',
            confidence DOUBLE PRECISION,
            evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            source_notes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            status VARCHAR(16) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','approved','rejected')),
            reviewed_by VARCHAR(36),
            reviewed_at TIMESTAMP,
            review_reason TEXT,
            mapped_attribute_id VARCHAR(36),
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_llm_attribute_candidates_status "
        "ON llm_attribute_candidates (status, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_llm_attribute_candidates_entity "
        "ON llm_attribute_candidates (entity_kind, entity_id, status);"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_claim_candidates (
            id VARCHAR(36) PRIMARY KEY,
            brand_id INTEGER,
            brand_context_version VARCHAR(64),
            entity_kind VARCHAR(32) NOT NULL
                CHECK (entity_kind IN ('brand','product','competitor','segment','profile','scenario')),
            entity_id VARCHAR(64),
            entity_name VARCHAR(256) NOT NULL,
            claim_type VARCHAR(64) NOT NULL,
            text TEXT NOT NULL,
            normalized_text VARCHAR(700) NOT NULL,
            scenario VARCHAR(256),
            candidate_key VARCHAR(1024) NOT NULL UNIQUE,
            source VARCHAR(64) NOT NULL DEFAULT 'llm_search',
            confidence DOUBLE PRECISION,
            evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            source_notes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            status VARCHAR(16) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','approved','rejected')),
            reviewed_by VARCHAR(36),
            reviewed_at TIMESTAMP,
            review_reason TEXT,
            mapped_claim_id VARCHAR(36),
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_llm_claim_candidates_status "
        "ON llm_claim_candidates (status, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_llm_claim_candidates_entity "
        "ON llm_claim_candidates (entity_kind, entity_id, status);"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS kg_entity_attributes (
            id VARCHAR(36) PRIMARY KEY,
            entity_kind VARCHAR(32) NOT NULL
                CHECK (entity_kind IN ('brand','product','competitor','segment','profile','scenario')),
            entity_id VARCHAR(64),
            entity_name VARCHAR(256),
            entity_ref_key VARCHAR(384) NOT NULL,
            attribute_key VARCHAR(128) NOT NULL,
            attribute_value TEXT NOT NULL,
            normalized_value VARCHAR(512) NOT NULL,
            value_json JSONB,
            source VARCHAR(64) NOT NULL DEFAULT 'llm_extraction',
            evidence JSONB,
            status VARCHAR(16) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','archived')),
            approved_from_candidate_id VARCHAR(36),
            reviewed_by VARCHAR(36),
            reviewed_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_kg_entity_attributes_key_value UNIQUE
                (entity_ref_key, attribute_key, normalized_value)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_kg_entity_attributes_entity "
        "ON kg_entity_attributes (entity_kind, entity_id, status);"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS kg_entity_claims (
            id VARCHAR(36) PRIMARY KEY,
            entity_kind VARCHAR(32) NOT NULL
                CHECK (entity_kind IN ('brand','product','competitor','segment','profile','scenario')),
            entity_id VARCHAR(64),
            entity_name VARCHAR(256),
            entity_ref_key VARCHAR(384) NOT NULL,
            claim_type VARCHAR(64) NOT NULL,
            text TEXT NOT NULL,
            normalized_text VARCHAR(700) NOT NULL,
            scenario VARCHAR(256) NOT NULL DEFAULT '',
            source VARCHAR(64) NOT NULL DEFAULT 'llm_extraction',
            evidence JSONB,
            status VARCHAR(16) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','archived')),
            approved_from_candidate_id VARCHAR(36),
            reviewed_by VARCHAR(36),
            reviewed_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_kg_entity_claims_key_text UNIQUE
                (entity_ref_key, claim_type, normalized_text, scenario)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_kg_entity_claims_entity "
        "ON kg_entity_claims (entity_kind, entity_id, status);"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS idx_kg_entity_claims_entity;")
    op.execute("DROP TABLE IF EXISTS kg_entity_claims;")
    op.execute("DROP INDEX IF EXISTS idx_kg_entity_attributes_entity;")
    op.execute("DROP TABLE IF EXISTS kg_entity_attributes;")
    op.execute("DROP INDEX IF EXISTS idx_llm_claim_candidates_entity;")
    op.execute("DROP INDEX IF EXISTS idx_llm_claim_candidates_status;")
    op.execute("DROP TABLE IF EXISTS llm_claim_candidates;")
    op.execute("DROP INDEX IF EXISTS idx_llm_attribute_candidates_entity;")
    op.execute("DROP INDEX IF EXISTS idx_llm_attribute_candidates_status;")
    op.execute("DROP TABLE IF EXISTS llm_attribute_candidates;")
    op.execute("DROP INDEX IF EXISTS idx_llm_entity_candidates_type;")
    op.execute("DROP INDEX IF EXISTS idx_llm_entity_candidates_brand_context;")
    op.execute("DROP INDEX IF EXISTS idx_llm_entity_candidates_status;")
    op.execute("DROP TABLE IF EXISTS llm_entity_candidates;")
