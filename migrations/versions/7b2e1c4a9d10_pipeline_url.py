"""pipelines.url — link to the run on GitHub/GitLab

Revision ID: 7b2e1c4a9d10
Revises: 109d742308e8
Create Date: 2026-07-09 17:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7b2e1c4a9d10'
down_revision = '109d742308e8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('pipelines', sa.Column('url', sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column('pipelines', 'url')
