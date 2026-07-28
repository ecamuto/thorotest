"""Scrub per-user SMTP credentials from notification_configs (SECURITY H-1)

Per-user SMTP settings let any authenticated user point the server at an
arbitrary host:port, and stored the relay password in plaintext where GET
/api/notifications/config echoed it straight back to the client. Outbound mail
now goes through the operator-configured relay (backend/emailer.py, SMTP_HOST
in the environment), so nothing reads these columns any more.

This clears the values rather than dropping the columns: the drop is not
reversible, several supported databases rebuild the whole table for it, and the
security benefit comes from removing the stored secret, not the column. The
columns are left in place as dead space and can be dropped in a later release.

Revision ID: b9e4d7c15a83
Revises: a7c3e9f14b02
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b9e4d7c15a83'
down_revision = 'a7c3e9f14b02'
branch_labels = None
depends_on = None


def upgrade():
    # Guard on the table existing: a database created before notification
    # configs shipped upgrades through this revision too.
    bind = op.get_bind()
    if 'notification_configs' not in sa.inspect(bind).get_table_names():
        return
    op.execute(
        sa.text(
            "UPDATE notification_configs "
            "SET smtp_host = NULL, smtp_user = NULL, smtp_pass = NULL, smtp_from = NULL"
        )
    )


def downgrade():
    # The credentials are gone by design — a downgrade cannot recover them.
    pass
