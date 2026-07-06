"""requirements + coverage, external tracker links on defects

Revision ID: c3d1f7a90b21
Revises: a41f9c2d7b10
Create Date: 2026-07-06

Phase 1 (v1.1): Requirement entity + requirement_tests bridge (many-to-many with
tests), plus external_* tracker-link columns on defects (mirrors requirements) to
pre-shape the Phase 2 Jira integration.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d1f7a90b21'
down_revision = 'a41f9c2d7b10'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'requirements',
        sa.Column('id', sa.String(length=255), primary_key=True),
        sa.Column('title', sa.String(length=512), nullable=False),
        sa.Column('type', sa.String(length=32), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=True),
        sa.Column('priority', sa.String(length=32), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('owner', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.String(length=64), nullable=True),
        sa.Column('created_by', sa.String(length=255), nullable=True),
        sa.Column('external_provider', sa.String(length=64), nullable=True),
        sa.Column('external_key', sa.String(length=128), nullable=True),
        sa.Column('external_url', sa.String(length=512), nullable=True),
    )
    op.create_table(
        'requirement_tests',
        sa.Column('requirement_id', sa.String(length=255), sa.ForeignKey('requirements.id', ondelete='CASCADE')),
        sa.Column('test_id', sa.String(length=255), sa.ForeignKey('tests.id', ondelete='CASCADE')),
        sa.UniqueConstraint('requirement_id', 'test_id', name='uq_requirement_test'),
    )
    op.add_column('defects', sa.Column('external_provider', sa.String(length=64), nullable=True))
    op.add_column('defects', sa.Column('external_key', sa.String(length=128), nullable=True))
    op.add_column('defects', sa.Column('external_url', sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column('defects', 'external_url')
    op.drop_column('defects', 'external_key')
    op.drop_column('defects', 'external_provider')
    op.drop_table('requirement_tests')
    op.drop_table('requirements')
