"""add created_at to activity and runs

Revision ID: a41f9c2d7b10
Revises: e8e566ab263b
Create Date: 2026-07-04

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a41f9c2d7b10'
down_revision = 'e8e566ab263b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('activity', sa.Column('created_at', sa.String(length=64), nullable=True))
    op.add_column('runs', sa.Column('created_at', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column('runs', 'created_at')
    op.drop_column('activity', 'created_at')
