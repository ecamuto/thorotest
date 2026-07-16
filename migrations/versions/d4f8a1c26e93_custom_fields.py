"""custom field definitions + custom_fields JSON column on tests/defects/requirements

Revision ID: d4f8a1c26e93
Revises: c5d9f3a2b8e1
Create Date: 2026-07-15

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4f8a1c26e93'
down_revision = 'c5d9f3a2b8e1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'custom_field_defs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity_type', sa.String(length=32), nullable=False),
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=False),
        sa.Column('field_type', sa.String(length=16), nullable=False),
        sa.Column('options', sa.JSON(), nullable=True),
        sa.Column('required', sa.Boolean(), nullable=True),
        sa.Column('order', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('entity_type', 'key', name='uq_custom_field_entity_key'),
    )
    op.add_column('tests', sa.Column('custom_fields', sa.JSON(), nullable=True))
    op.add_column('defects', sa.Column('custom_fields', sa.JSON(), nullable=True))
    op.add_column('requirements', sa.Column('custom_fields', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('requirements', 'custom_fields')
    op.drop_column('defects', 'custom_fields')
    op.drop_column('tests', 'custom_fields')
    op.drop_table('custom_field_defs')
