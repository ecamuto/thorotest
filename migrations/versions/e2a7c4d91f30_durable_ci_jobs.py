"""durable CI orchestration jobs

Revision ID: e2a7c4d91f30
Revises: c1f6b2a34d70
Create Date: 2026-10-24
"""

from alembic import op
import sqlalchemy as sa


revision = "e2a7c4d91f30"
down_revision = "c1f6b2a34d70"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ci_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("integration_id", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("workflow", sa.String(255), nullable=False),
        sa.Column("ref", sa.String(255), nullable=False),
        sa.Column("artifact", sa.String(255), nullable=True),
        sa.Column("run_name", sa.String(512), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("queue_status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("external_run_id", sa.String(255), nullable=True),
        sa.Column("external_url", sa.String(512), nullable=True),
        sa.Column("pipeline_row_id", sa.String(255), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.String(64), nullable=False),
        sa.Column("lease_until", sa.String(64), nullable=True),
        sa.Column("worker_id", sa.String(64), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_ci_jobs_integration_id", "ci_jobs", ["integration_id"])
    op.create_index("ix_ci_jobs_queue_status", "ci_jobs", ["queue_status"])
    op.create_index("ix_ci_jobs_lease_until", "ci_jobs", ["lease_until"])
    op.create_index(
        "ix_ci_jobs_claim", "ci_jobs", ["queue_status", "lease_until", "started_at"]
    )


def downgrade():
    op.drop_table("ci_jobs")
