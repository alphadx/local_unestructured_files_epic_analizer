"""initial schema - phase 2

Revision ID: 001
Revises:
Create Date: 2026-04-06

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def _json_type():
    """Return JSONB for PostgreSQL, plain JSON for others (e.g. SQLite in tests)."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return postgresql.JSONB()
    return sa.JSON()


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("job_id", sa.String(36), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("progress_percent", sa.Integer, nullable=False, server_default="0"),
        sa.Column("message", sa.Text, nullable=False, server_default=""),
        sa.Column("documents_processed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("documents_total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("extra", _json_type(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "job_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_job_logs_job_id", "job_logs", ["job_id"])

    op.create_table(
        "reports",
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.job_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("data", _json_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "documents",
        sa.Column("documento_id", sa.String(100), nullable=False),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False),
        sa.Column("data", _json_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("job_id", "documento_id"),
    )

    op.create_table(
        "chunks",
        sa.Column("chunk_id", sa.String(100), nullable=False),
        sa.Column("job_id", sa.String(36), nullable=False),
        sa.Column("documento_id", sa.String(100), nullable=False),
        sa.Column("data", _json_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("job_id", "chunk_id"),
        sa.ForeignKeyConstraint(
            ["job_id", "documento_id"],
            ["documents.job_id", "documents.documento_id"],
            ondelete="CASCADE",
        ),
    )

    op.create_table(
        "group_analysis",
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.job_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("data", _json_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "audit_log",
        sa.Column("entry_id", sa.String(36), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("operation", sa.String(100), nullable=False),
        sa.Column("actor", sa.String(100), nullable=False, server_default="system"),
        sa.Column("resource_id", sa.String(200), nullable=True),
        sa.Column("resource_type", sa.String(100), nullable=True),
        sa.Column("details", _json_type(), nullable=False, server_default="{}"),
        sa.Column("outcome", sa.String(20), nullable=False, server_default="success"),
    )
    op.create_index("ix_audit_log_timestamp", "audit_log", ["timestamp"])
    op.create_index("ix_audit_log_operation", "audit_log", ["operation"])
    op.create_index("ix_audit_log_resource_id", "audit_log", ["resource_id"])
    op.create_index("ix_audit_log_resource_type", "audit_log", ["resource_type"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("group_analysis")
    op.drop_table("chunks")
    op.drop_table("documents")
    op.drop_table("reports")
    op.drop_table("job_logs")
    op.drop_table("jobs")
