"""Phase 0 — App product API base tables (6 tables).

Revision ID: 20260504_phase0_app
Revises: 20260504_legacy_sql
Create Date: 2026-05-04

Creates the 6 multi-tenant base tables that the App product API
(`/api/v1/projects/...`) will use:

  - projects                    User → Project ownership root
  - project_competitors         M:N project ↔ brand (capacity 10 enforced in service)
  - project_topic_pins          User-side topic state (tracked / ignored)
  - commercial_leads            BD lead inbox
  - report_jobs                 Report generation jobs (Phase RP fills schema)
  - crawl_requests              User-triggered manual crawls (Phase 4 wires Celery)

All tables include `org_id UUID` placeholder (Phase M ADR-005) — currently
nullable; Phase M will backfill + add NOT NULL once `organizations` table
exists.

ForeignKey targets `users.id`, `industries.id`, `brands.id`, `topics.id` —
of these, `users` is in alembic baseline (always present), but `industries`,
`brands`, `topics` are upstream Tracker-domain tables. Per ADR-002 + the
inspector-guard pattern from `20260504_legacy_sql`, we declare FK references
loosely (no FK constraint to upstream tables) so the migration runs cleanly
on fresh CI/test DB without `industries`/`brands`/`topics`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260504_phase0_app"
down_revision: str | Sequence[str] | None = "20260504_legacy_sql"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create 6 Phase 0 tables."""

    # ───────────────────────────────────────────────────────────────────
    # projects
    # ───────────────────────────────────────────────────────────────────
    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("org_id", sa.String(36), nullable=True),  # Phase M
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("industry_id", sa.Integer, nullable=True),
        sa.Column("primary_brand_id", sa.Integer, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("preferred_engines", sa.JSON, nullable=True),
        sa.Column("default_profile_group_id", sa.String(64), nullable=True),
        sa.Column("preferences", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("user_id", "name", name=op.f("uq_projects_user_id_name")),
    )
    op.create_index(
        "projects_user_active_idx",
        "projects",
        ["user_id", "is_active", "created_at"],
    )

    # ───────────────────────────────────────────────────────────────────
    # project_competitors  (M:N, capacity 10 in service layer)
    # ───────────────────────────────────────────────────────────────────
    op.create_table(
        "project_competitors",
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("brand_id", sa.Integer, primary_key=True),
        sa.Column("pinned_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("pinned_by", sa.String(36), nullable=True),
    )

    # ───────────────────────────────────────────────────────────────────
    # project_topic_pins
    # ───────────────────────────────────────────────────────────────────
    op.create_table(
        "project_topic_pins",
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("topic_id", sa.BigInteger, primary_key=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("pinned_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("state IN ('tracked', 'ignored')", name=op.f("ck_project_topic_pins_state")),
    )

    # ───────────────────────────────────────────────────────────────────
    # commercial_leads
    # ───────────────────────────────────────────────────────────────────
    op.create_table(
        "commercial_leads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("org_id", sa.String(36), nullable=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("context", sa.JSON, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('new', 'contacted', 'closed', 'ignored')",
            name=op.f("ck_commercial_leads_status"),
        ),
    )
    op.create_index(
        "commercial_leads_status_idx",
        "commercial_leads",
        ["status", "created_at"],
    )

    # ───────────────────────────────────────────────────────────────────
    # report_jobs
    # ───────────────────────────────────────────────────────────────────
    op.create_table(
        "report_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("scope", sa.JSON, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("output_url", sa.Text, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("scheduled_cron", sa.String(64), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.CheckConstraint(
            "type IN ('pdf', 'csv', 'markdown', 'json')",
            name=op.f("ck_report_jobs_type"),
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed', 'cancelled')",
            name=op.f("ck_report_jobs_status"),
        ),
    )
    op.create_index(
        "report_jobs_project_status_idx",
        "report_jobs",
        ["project_id", "status", "created_at"],
    )

    # ───────────────────────────────────────────────────────────────────
    # crawl_requests
    # ───────────────────────────────────────────────────────────────────
    op.create_table(
        "crawl_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("brand_id", sa.Integer, nullable=True),
        sa.Column("scope", sa.JSON, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("result_summary", sa.JSON, nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')",
            name=op.f("ck_crawl_requests_status"),
        ),
    )
    op.create_index(
        "crawl_requests_project_status_idx",
        "crawl_requests",
        ["project_id", "status", "created_at"],
    )


def downgrade() -> None:
    """Reverse Phase 0 tables creation."""
    op.drop_index("crawl_requests_project_status_idx", table_name="crawl_requests")
    op.drop_table("crawl_requests")
    op.drop_index("report_jobs_project_status_idx", table_name="report_jobs")
    op.drop_table("report_jobs")
    op.drop_index("commercial_leads_status_idx", table_name="commercial_leads")
    op.drop_table("commercial_leads")
    op.drop_table("project_topic_pins")
    op.drop_table("project_competitors")
    op.drop_index("projects_user_active_idx", table_name="projects")
    op.drop_table("projects")
