"""Phase O — Admin operations 8 tables.

Revision ID: 20260505_phase_o
Revises: 20260505_phase_rp
Create Date: 2026-05-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20260505_phase_o"
down_revision: str | Sequence[str] | None = "20260505_phase_rp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rename_legacy_admin_audit_log_if_present() -> None:
    """Production hosts running the legacy admin_console Flask have an
    `admin_audit_log` table with a DIFFERENT schema (target_type/target_id/
    diff_json/created_at) created at process startup via `CREATE TABLE
    IF NOT EXISTS`. To avoid `DuplicateTable` errors when this migration
    runs for the first time on those hosts, rename the legacy table out
    of the way to `admin_audit_log_legacy`. Fresh DBs (CI / dev) skip
    this branch since the table doesn't exist there yet.
    """
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite tests use fresh DBs, never have the legacy table
        return
    insp = inspect(bind)
    if "admin_audit_log" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("admin_audit_log")}
    legacy_fingerprint = {"target_type", "diff_json", "created_at"}
    if legacy_fingerprint.issubset(cols):
        op.execute("ALTER TABLE admin_audit_log RENAME TO admin_audit_log_legacy")


def upgrade() -> None:
    _rename_legacy_admin_audit_log_if_present()

    op.create_table(
        "engine_health_daily",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("engine", sa.String(64), nullable=False),
        sa.Column("date", sa.DateTime, nullable=False),
        sa.Column("total_attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("success_rate", sa.Float, nullable=True),
        sa.Column("p50_latency_ms", sa.Integer, nullable=True),
        sa.Column("p95_latency_ms", sa.Integer, nullable=True),
        sa.Column("cookie_status", sa.String(16), nullable=True),
        sa.Column("captcha_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ip_blocked_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rate_limited_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_updated", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("engine", "date", name=op.f("uq_engine_health_engine_date")),
    )
    op.create_index(
        "engine_health_daily_engine_idx", "engine_health_daily", ["engine", "date"]
    )

    op.create_table(
        "proxy_health_daily",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("proxy_id", sa.Integer, nullable=False),
        sa.Column("date", sa.DateTime, nullable=False),
        sa.Column("total_requests", sa.Integer, nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("success_rate", sa.Float, nullable=True),
        sa.Column("avg_latency_ms", sa.Integer, nullable=True),
        sa.Column("is_blocked", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.UniqueConstraint("proxy_id", "date", name=op.f("uq_proxy_health_proxy_date")),
    )

    op.create_table(
        "discovery_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("candidate_id", sa.String(36), nullable=True),
        sa.Column("llm_model", sa.String(64), nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("hallucination_flag", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("hallucination_evidence", sa.JSON, nullable=True),
        sa.Column("occurred_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "discovery_log_source_time_idx", "discovery_log", ["source", "occurred_at"]
    )
    op.create_index(
        "discovery_log_hallucination_idx",
        "discovery_log",
        ["hallucination_flag", "occurred_at"],
    )

    op.create_table(
        "cost_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("amount", sa.Numeric(10, 4), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("reference_id", sa.String(64), nullable=True),
        sa.Column("event_metadata", sa.JSON, nullable=True),
        sa.Column("occurred_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "scope IN ('pipeline', 'kg', 'mcp', 'reports')",
            name=op.f("ck_cost_events_scope"),
        ),
    )
    op.create_index("cost_events_scope_time_idx", "cost_events", ["scope", "occurred_at"])
    op.create_index("cost_events_source_time_idx", "cost_events", ["source", "occurred_at"])

    op.create_table(
        "budget_thresholds",
        sa.Column("scope", sa.String(16), primary_key=True),
        sa.Column("daily_limit_cny", sa.Numeric(10, 2), nullable=True),
        sa.Column("weekly_limit_cny", sa.Numeric(10, 2), nullable=True),
        sa.Column("monthly_limit_cny", sa.Numeric(10, 2), nullable=True),
        sa.Column("alert_at_pct", sa.Integer, nullable=False, server_default="80"),
        sa.Column("hard_stop_at_pct", sa.Integer, nullable=False, server_default="100"),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "scope IN ('pipeline', 'kg', 'mcp', 'reports')",
            name=op.f("ck_budget_thresholds_scope"),
        ),
    )

    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "operator_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=True),
        sa.Column("severity", sa.String(8), nullable=False),
        sa.Column("before", sa.JSON, nullable=True),
        sa.Column("after", sa.JSON, nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("occurred_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "severity IN ('low', 'med', 'high')",
            name=op.f("ck_admin_audit_log_severity"),
        ),
    )
    op.create_index(
        "admin_audit_log_operator_idx", "admin_audit_log", ["operator_id", "occurred_at"]
    )
    op.create_index(
        "admin_audit_log_action_idx",
        "admin_audit_log",
        ["action", "severity", "occurred_at"],
    )
    op.create_index(
        "admin_audit_log_resource_idx",
        "admin_audit_log",
        ["resource_type", "resource_id"],
    )

    op.create_table(
        "comms_announcements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title_zh", sa.String(256), nullable=True),
        sa.Column("title_en", sa.String(256), nullable=True),
        sa.Column("body_zh", sa.Text, nullable=True),
        sa.Column("body_en", sa.Text, nullable=True),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("audience", sa.String(64), nullable=False),
        sa.Column("scheduled_at", sa.DateTime, nullable=True),
        sa.Column("sent_at", sa.DateTime, nullable=True),
        sa.Column("sent_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "channel IN ('inapp', 'email', 'both')",
            name=op.f("ck_comms_announcements_channel"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'scheduled', 'sending', 'sent', 'cancelled')",
            name=op.f("ck_comms_announcements_status"),
        ),
    )

    op.create_table(
        "mcp_call_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("api_key_id", sa.String(36), nullable=True),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("tool", sa.String(64), nullable=True),
        sa.Column("resource_uri", sa.String(512), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("http_status", sa.Integer, nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("cost_estimate_cny", sa.Numeric(10, 4), nullable=True),
        sa.Column("request_size_bytes", sa.Integer, nullable=True),
        sa.Column("response_size_bytes", sa.Integer, nullable=True),
        sa.Column("occurred_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "mcp_call_log_api_key_time_idx", "mcp_call_log", ["api_key_id", "occurred_at"]
    )


def downgrade() -> None:
    op.drop_index("mcp_call_log_api_key_time_idx", table_name="mcp_call_log")
    op.drop_table("mcp_call_log")
    op.drop_table("comms_announcements")
    op.drop_index("admin_audit_log_resource_idx", table_name="admin_audit_log")
    op.drop_index("admin_audit_log_action_idx", table_name="admin_audit_log")
    op.drop_index("admin_audit_log_operator_idx", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")
    op.drop_table("budget_thresholds")
    op.drop_index("cost_events_source_time_idx", table_name="cost_events")
    op.drop_index("cost_events_scope_time_idx", table_name="cost_events")
    op.drop_table("cost_events")
    op.drop_index("discovery_log_hallucination_idx", table_name="discovery_log")
    op.drop_index("discovery_log_source_time_idx", table_name="discovery_log")
    op.drop_table("discovery_log")
    op.drop_table("proxy_health_daily")
    op.drop_index("engine_health_daily_engine_idx", table_name="engine_health_daily")
    op.drop_table("engine_health_daily")
