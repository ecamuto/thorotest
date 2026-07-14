"""pipelines.run_id — link a pipeline to the imported Run holding its test cases

Revision ID: b4c8e2f1a9d3
Revises: 07ab187d3790
Create Date: 2026-07-14 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b4c8e2f1a9d3'
down_revision = '07ab187d3790'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('pipelines', sa.Column('run_id', sa.String(length=255), nullable=True))
    # No FK constraint added: SQLite can't ALTER-add one, and the app treats a
    # dangling run_id as "no cases" anyway.


def downgrade() -> None:
    op.drop_column('pipelines', 'run_id')
