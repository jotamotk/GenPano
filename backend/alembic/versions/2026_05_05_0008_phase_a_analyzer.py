"""Phase A — Analyzer extension 9 tables.

Revision ID: 20260505_phase_a
Revises: 20260505_phase_o
Create Date: 2026-05-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260505_phase_a"
down_revision: str | Sequence[str] | None = "20260505_phase_o"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "brand_official_domains",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("brand_id", sa.Integer, nullable=False),
        sa.Column("domain", sa.String(256), nullable=False),
        sa.Column("is_primary", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("brand_id", "domain", name=op.f("uq_brand_official_domains_pair")),
    )
    op.create_index(
        "brand_official_domains_domain_idx", "brand_official_domains", ["domain"]
    )

    op.create_table(
        "domain_authorities",
        sa.Column("domain", sa.String(256), primary_key=True),
        sa.Column("tier", sa.SmallInteger, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("site_type", sa.String(32), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("reviewed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("domain_authorities_tier_idx", "domain_authorities", ["tier"])

    op.create_table(
        "brand_groups",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("parent_company", sa.String(256), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "brand_group_members",
        sa.Column(
            "group_id",
            sa.Integer,
            sa.ForeignKey("brand_groups.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("brand_id", sa.Integer, primary_key=True),
        sa.Column("role", sa.String(32), nullable=True),
        sa.Column("joined_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "role IS NULL OR role IN ('flagship', 'sister', 'sub')",
            name=op.f("ck_brand_group_members_role"),
        ),
    )

    op.create_table(
        "brand_group_shared_domains",
        sa.Column(
            "group_id",
            sa.Integer,
            sa.ForeignKey("brand_groups.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("domain", sa.String(256), primary_key=True),
        sa.Column("brand_count", sa.Integer, nullable=False),
        sa.Column("total_mentions", sa.Integer, nullable=False),
        sa.Column("last_seen_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "competitor_mention_daily",
        sa.Column("brand_id", sa.Integer, primary_key=True),
        sa.Column("competitor_id", sa.Integer, primary_key=True),
        sa.Column("date", sa.DateTime, primary_key=True),
        sa.Column("target_llm", sa.String(64), primary_key=True),
        sa.Column("co_mention_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("my_mention_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("comp_mention_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("avg_sentiment_diff", sa.Float, nullable=True),
        sa.Column("sov_diff", sa.Float, nullable=True),
    )
    op.create_index(
        "competitor_mention_daily_pair_date_idx",
        "competitor_mention_daily",
        ["brand_id", "competitor_id", "date"],
    )

    op.create_table(
        "geo_score_weekly",
        sa.Column("brand_id", sa.Integer, primary_key=True),
        sa.Column("week_start", sa.DateTime, primary_key=True),
        sa.Column("target_llm", sa.String(64), primary_key=True),
        sa.Column("avg_geo_score", sa.Float, nullable=True),
        sa.Column("avg_authority_tier", sa.Float, nullable=True),
        sa.Column("top_authority_domains_json", sa.JSON, nullable=True),
        sa.Column("tier1_citation_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tier2_citation_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tier3_citation_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tier4_citation_count", sa.Integer, nullable=False, server_default="0"),
    )

    op.create_table(
        "citation_weekly_by_domain",
        sa.Column("brand_id", sa.Integer, primary_key=True),
        sa.Column("domain", sa.String(256), primary_key=True),
        sa.Column("week_start", sa.DateTime, primary_key=True),
        sa.Column("citation_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("avg_position_rank", sa.Float, nullable=True),
    )
    op.create_index(
        "citation_weekly_by_domain_brand_idx",
        "citation_weekly_by_domain",
        ["brand_id", "week_start"],
    )

    op.create_table(
        "industry_topic_daily",
        sa.Column("industry_id", sa.Integer, primary_key=True),
        sa.Column("category", sa.String(128), primary_key=True, server_default=""),
        sa.Column("topic_id", sa.Integer, primary_key=True, server_default="0"),
        sa.Column("date", sa.DateTime, primary_key=True),
        sa.Column("mention_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("unique_brand_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("hot_score", sa.Float, nullable=True),
    )
    op.create_index(
        "industry_topic_daily_industry_date_idx",
        "industry_topic_daily",
        ["industry_id", "date"],
    )


def downgrade() -> None:
    op.drop_index("industry_topic_daily_industry_date_idx", table_name="industry_topic_daily")
    op.drop_table("industry_topic_daily")
    op.drop_index("citation_weekly_by_domain_brand_idx", table_name="citation_weekly_by_domain")
    op.drop_table("citation_weekly_by_domain")
    op.drop_table("geo_score_weekly")
    op.drop_index("competitor_mention_daily_pair_date_idx", table_name="competitor_mention_daily")
    op.drop_table("competitor_mention_daily")
    op.drop_table("brand_group_shared_domains")
    op.drop_table("brand_group_members")
    op.drop_table("brand_groups")
    op.drop_index("domain_authorities_tier_idx", table_name="domain_authorities")
    op.drop_table("domain_authorities")
    op.drop_index("brand_official_domains_domain_idx", table_name="brand_official_domains")
    op.drop_table("brand_official_domains")
