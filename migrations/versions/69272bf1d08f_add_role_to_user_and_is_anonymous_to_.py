"""add role to user and is_anonymous to event

Revision ID: 69272bf1d08f
Revises: 76df0f5d8e4d
Create Date: 2026-06-06 22:57:23.038803

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '69272bf1d08f'
down_revision = '76df0f5d8e4d'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('bookmarks', schema=None) as batch_op:
        batch_op.drop_constraint('fk_bookmarks_event_id_events', type_='foreignkey')
        batch_op.create_foreign_key(
            'fk_bookmarks_event_id_events_plain',
            'events', ['event_id'], ['id']
        )

    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_anonymous', sa.Boolean(), nullable=True))

    with op.batch_alter_table('participations', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_participations_event_id_cascade',
            'events', ['event_id'], ['id'], ondelete='CASCADE'
        )


def downgrade():
    with op.batch_alter_table('participations', schema=None) as batch_op:
        batch_op.drop_constraint('fk_participations_event_id_cascade', type_='foreignkey')

    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.drop_column('is_anonymous')

    with op.batch_alter_table('bookmarks', schema=None) as batch_op:
        batch_op.drop_constraint('fk_bookmarks_event_id_events_plain', type_='foreignkey')
        batch_op.create_foreign_key(
            'fk_bookmarks_event_id_events',
            'events', ['event_id'], ['id'], ondelete='CASCADE'
        )
