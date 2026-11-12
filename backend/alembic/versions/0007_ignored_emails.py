"""ignored emails

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-11 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('ignored_emails',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('message_id', sa.String(length=255), nullable=False),
    sa.Column('thread_id', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'message_id')
    )
    with op.batch_alter_table('ignored_emails', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ignored_emails_thread_id'), ['thread_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('ignored_emails', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ignored_emails_thread_id'))
    op.drop_table('ignored_emails')
