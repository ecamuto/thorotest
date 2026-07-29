"""api_tokens: expiry + token_version for revocation (SECURITY H-2)

API tokens previously never expired and were not invalidated by "log out
everywhere" or a password reset, so a leaked CI token stayed valid until
someone remembered to delete the row.

- expires_at: ISO UTC string, NULL for existing rows (kept valid; the API sets
  an expiry on every newly minted token).
- token_version: snapshot of users.token_version at mint time. Existing rows are
  backfilled from their owner so they keep working until the owner's counter is
  next bumped, at which point they are revoked along with that user's sessions.

Revision ID: c1f6b2a34d70
Revises: b9e4d7c15a83
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c1f6b2a34d70'
down_revision = 'b9e4d7c15a83'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'api_tokens' not in inspector.get_table_names():
        return
    existing = {c['name'] for c in inspector.get_columns('api_tokens')}

    if 'expires_at' not in existing:
        op.add_column('api_tokens', sa.Column('expires_at', sa.String(64), nullable=True))
    if 'token_version' not in existing:
        op.add_column(
            'api_tokens',
            sa.Column('token_version', sa.Integer(), nullable=True, server_default='0'),
        )
        # Backfill from the owning user so tokens minted before this revision
        # are not revoked the moment it lands.
        op.execute(sa.text(
            "UPDATE api_tokens SET token_version = COALESCE("
            "(SELECT u.token_version FROM users u WHERE u.id = api_tokens.user_id), 0)"
        ))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'api_tokens' not in inspector.get_table_names():
        return
    existing = {c['name'] for c in inspector.get_columns('api_tokens')}
    if 'token_version' in existing:
        op.drop_column('api_tokens', 'token_version')
    if 'expires_at' in existing:
        op.drop_column('api_tokens', 'expires_at')
