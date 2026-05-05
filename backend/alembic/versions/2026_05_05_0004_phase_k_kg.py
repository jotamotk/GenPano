"""Phase K — Knowledge Graph 6 tables.

Revision ID: 20260505_phase_k
Revises: 20260505_phase_m
Create Date: 2026-05-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260505_phase_k"
down_revision: str | Sequence[str] | None = "20260505_phase_m"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "kg_categories",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("industry_id", sa.Integer, nullable=True),
        sa.Column(
            "parent_id",
            sa.Integer,
            sa.ForeignKey("kg_categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name_zh", sa.String(128), nullable=False),
        sa.Column("name_en", sa.String(128), nullable=True),
        sa.Column("level", sa.SmallInteger, nullable=True),
        sa.Column("slug", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="approved"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "kg_categories_industry_idx", "kg_categories", ["industry_id", "level"]
    )

    op.create_table(
        "kg_brands",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("brand_id", sa.Integer, nullable=False, unique=True),
        sa.Column("industry_id", sa.Integer, nullable=True),
        sa.Column("primary_name", sa.String(256), nullable=False),
        sa.Column("name_zh", sa.String(256), nullable=True),
        sa.Column("name_en", sa.String(256), nullable=True),
        sa.Column("aliases", sa.JSON, nullable=True),
        sa.Column("official_domains", sa.JSON, nullable=True),
        sa.Column("group_id", sa.Integer, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="approved"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "kg_products",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.Integer, nullable=False, unique=True),
        sa.Column("brand_id", sa.Integer, nullable=False),
        sa.Column("category_id", sa.Integer, nullable=True),
        sa.Column("primary_name", sa.String(256), nullable=False),
        sa.Column("name_zh", sa.String(256), nullable=True),
        sa.Column("name_en", sa.String(256), nullable=True),
        sa.Column("aliases", sa.JSON, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="approved"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "kg_brand_relations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_a_id", sa.Integer, nullable=False),
        sa.Column("brand_b_id", sa.Integer, nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("evidence", sa.JSON, nullable=True),
        sa.Column("reviewed_by", sa.String(36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "brand_a_id", "brand_b_id", "type", name=op.f("uq_kg_brand_relations_pair_type")
        ),
        sa.CheckConstraint(
            "type IN ('COMPETES_WITH', 'SAME_GROUP')",
            name=op.f("ck_kg_brand_relations_type"),
        ),
        sa.CheckConstraint(
            "source IN ('analyzer', 'admin', 'import')",
            name=op.f("ck_kg_brand_relations_source"),
        ),
        sa.CheckConstraint(
            "brand_a_id < brand_b_id", name=op.f("ck_kg_brand_relations_order")
        ),
    )

    op.create_table(
        "kg_product_relations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("product_a_id", sa.Integer, nullable=False),
        sa.Column("product_b_id", sa.Integer, nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("source", sa.String(32), nullable=True),
        sa.Column("evidence", sa.JSON, nullable=True),
        sa.Column("reviewed_by", sa.String(36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "product_a_id",
            "product_b_id",
            "type",
            name=op.f("uq_kg_product_relations_pair_type"),
        ),
    )

    op.create_table(
        "kg_relation_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("entity_kind", sa.String(8), nullable=False),
        sa.Column("a_id", sa.Integer, nullable=False),
        sa.Column("b_id", sa.Integer, nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("evidence", sa.JSON, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("llm_model", sa.String(64), nullable=True),
        sa.Column("reviewed_by", sa.String(36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column("merged_into_relation_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "entity_kind IN ('brand', 'product')",
            name=op.f("ck_kg_relation_candidates_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'merged')",
            name=op.f("ck_kg_relation_candidates_status"),
        ),
    )
    op.create_index(
        "kg_relation_candidates_status_idx",
        "kg_relation_candidates",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "kg_relation_candidates_status_idx", table_name="kg_relation_candidates"
    )
    op.drop_table("kg_relation_candidates")
    op.drop_table("kg_product_relations")
    op.drop_table("kg_brand_relations")
    op.drop_table("kg_products")
    op.drop_table("kg_brands")
    op.drop_index("kg_categories_industry_idx", table_name="kg_categories")
    op.drop_table("kg_categories")
