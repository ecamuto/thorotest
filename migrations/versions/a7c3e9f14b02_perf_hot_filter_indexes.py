"""Add indexes for hot filters/joins: run_cases, tests, defects (PERF P-7)

Revision ID: a7c3e9f14b02
Revises: d4f8a1c26e93
Create Date: 2026-07-17
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'a7c3e9f14b02'
down_revision = 'd4f8a1c26e93'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('ix_run_cases_run_id', 'run_cases', ['run_id'])
    op.create_index('ix_run_cases_test_id', 'run_cases', ['test_id'])
    op.create_index('ix_tests_folder_status', 'tests', ['folder_id', 'status'])
    op.create_index('ix_defects_status_severity', 'defects', ['status', 'severity'])


def downgrade():
    op.drop_index('ix_defects_status_severity', table_name='defects')
    op.drop_index('ix_tests_folder_status', table_name='tests')
    op.drop_index('ix_run_cases_test_id', table_name='run_cases')
    op.drop_index('ix_run_cases_run_id', table_name='run_cases')
