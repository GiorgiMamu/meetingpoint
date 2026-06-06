"""cascade delete bookmarks when event deleted

Revision ID: 76df0f5d8e4d
Revises: 4b8c38002f69
Create Date: 2026-06-06 20:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '76df0f5d8e4d'
down_revision = '4b8c38002f69'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    foreign_keys = inspector.get_foreign_keys('bookmarks')
    event_fk_name = next(
        (
            fk['name'] for fk in foreign_keys
            if fk.get('referred_table') == 'events' and fk.get('constrained_columns') == ['event_id']
        ),
        None
    )

    with op.batch_alter_table('bookmarks', schema=None) as batch_op:
        if event_fk_name:
            batch_op.drop_constraint(event_fk_name, type_='foreignkey')
        batch_op.create_foreign_key(
            'fk_bookmarks_event_id_events',
            'events',
            ['event_id'],
            ['id'],
            ondelete='CASCADE'
        )


def downgrade():
    with op.batch_alter_table('bookmarks', schema=None) as batch_op:
        batch_op.drop_constraint('fk_bookmarks_event_id_events', type_='foreignkey')
        batch_op.create_foreign_key(
            'fk_bookmarks_event_id_events',
            'events',
            ['event_id'],
            ['id']
        )
