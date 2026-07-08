"""api_token user_id + hash index

Revision ID: 109d742308e8
Revises: 48e00f947dec
Create Date: 2026-07-08 13:20:05.803200

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '109d742308e8'
down_revision = '48e00f947dec'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # batch_alter_table: SQLite can't ALTER-ADD a foreign key in place, so
    # alembic rebuilds the table via copy-and-move. No-op difference on
    # Postgres/MySQL, which support the ALTER directly.
    with op.batch_alter_table("api_tokens", schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_api_tokens_token_hash"), ["token_hash"], unique=False)
        batch_op.create_foreign_key("fk_api_tokens_user_id_users", "users", ["user_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("api_tokens", schema=None) as batch_op:
        batch_op.drop_constraint("fk_api_tokens_user_id_users", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_api_tokens_token_hash"))
        batch_op.drop_column("user_id")
