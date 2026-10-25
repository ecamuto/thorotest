"""add provider job type

Revision ID: f3a1b2c4d5e6
Revises: e2a7c4d91f30
Create Date: 2026-10-25
"""

from alembic import op
import sqlalchemy as sa


revision = "f3a1b2c4d5e6"
down_revision = "e2a7c4d91f30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ci_jobs",
        sa.Column(
            "job_type",
            sa.String(length=32),
            nullable=False,
            server_default="ci_run",
        ),
    )


def downgrade() -> None:
    op.drop_column("ci_jobs", "job_type")
