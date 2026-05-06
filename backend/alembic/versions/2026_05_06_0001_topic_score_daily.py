"""topic_score_daily — per-(brand, topic, date) mention aggregation.

Revision ID: 20260506_topic_score_daily
Revises: 20260505_phase_a
Create Date: 2026-05-06

Backs the projects /topics endpoint with real mention_count / avg_sentiment /
avg_position_rank values aggregated nightly by Aggregator._aggregate_topic_daily.
Until this table is populated the endpoint returned all zeros (stub).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260506_topic_score_daily"
down_revision: str | Sequence[str] | None = "20260505_phase_a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "topic_score_daily",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("brand_id", sa.Integer, nullable=False),
        sa.Column("topic_id", sa.Integer, nullable=False),
        sa.Column("date", sa.DateTime, nullable=False),
        sa.Column("mention_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_responses", sa.Integer, nullable=False, server_default="0"),
        sa.Column("mention_rate", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("avg_position_rank", sa.Float, nullable=True),
        sa.Column("avg_sentiment_score", sa.Float, nullable=True),
        sa.Column("avg_geo_score", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("brand_id", "topic_id", "date", name="uq_topic_daily"),
    )
    op.create_index(
        "topic_score_daily_topic_date_idx",
        "topic_score_daily",
        ["topic_id", "date"],
    )
    op.create_index(
        "topic_score_daily_brand_date_idx",
        "topic_score_daily",
        ["brand_id", "date"],
    )


def downgrade() -> None:
    op.drop_index("topic_score_daily_brand_date_idx", table_name="topic_score_daily")
    op.drop_index("topic_score_daily_topic_date_idx", table_name="topic_score_daily")
    op.drop_table("topic_score_daily")
