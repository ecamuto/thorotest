"""add record_history table for per-record change tracking

Revision ID: f1a2b3c4d5e6
Revises: 7b2e1c4a9d10
Create Date: 2026-07-10

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = '7b2e1c4a9d10'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'record_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity_type', sa.String(length=32), nullable=False),
        sa.Column('entity_id', sa.String(length=255), nullable=False),
        sa.Column('action', sa.String(length=16), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('actor_name', sa.String(length=255), nullable=False),
        sa.Column('changes', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_record_history_entity', 'record_history', ['entity_type', 'entity_id'])


def downgrade() -> None:
    op.drop_index('ix_record_history_entity', table_name='record_history')
    op.drop_table('record_history')
