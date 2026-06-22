"""restore tables

Revision ID: f630ce6734b3
Revises: 5598c96562d9
Create Date: 2026-04-30 01:42:51.802607

"""

# revision identifiers, used by Alembic.
revision = 'f630ce6734b3'
down_revision = '5598c96562d9'
branch_labels = None
depends_on = None


def upgrade():
    # Tables already created in initial migration (5598c96562d9).
    # This migration is intentionally a no-op.
    pass


def downgrade():
    pass
