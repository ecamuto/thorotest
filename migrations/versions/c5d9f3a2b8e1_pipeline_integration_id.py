"""pipelines.integration_id — source integration, for stateless reconcile polling

Revision ID: c5d9f3a2b8e1
Revises: b4c8e2f1a9d3
Create Date: 2026-07-14 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c5d9f3a2b8e1'
down_revision = 'b4c8e2f1a9d3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('pipelines', sa.Column('integration_id', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('pipelines', 'integration_id')
