"""add actor_user_id to notifications

Revision ID: c9b4a0b7e2f1
Revises: 02e7b6c7b0ac
Create Date: 2026-06-20 22:45:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'c9b4a0b7e2f1'
down_revision = '02e7b6c7b0ac'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.add_column(sa.Column('actor_user_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_notifications_actor_user_id_users',
            'users',
            ['actor_user_id'],
            ['id']
        )


def downgrade():
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_constraint('fk_notifications_actor_user_id_users', type_='foreignkey')
        batch_op.drop_column('actor_user_id')
