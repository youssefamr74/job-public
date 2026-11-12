"""opportunities and action_needed

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-10 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('applications', schema=None) as batch_op:
        batch_op.add_column(sa.Column('action_needed', sa.Boolean(), server_default=sa.false(), nullable=False))

    op.create_table('opportunities',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('company', sa.String(length=255), nullable=True),
    sa.Column('role', sa.String(length=255), nullable=True),
    sa.Column('sender', sa.Text(), nullable=True),
    sa.Column('subject', sa.Text(), nullable=True),
    sa.Column('date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('thread_id', sa.String(length=255), nullable=True),
    sa.Column('message_id', sa.String(length=255), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('application_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'message_id', name='uq_opportunity_message')
    )
    with op.batch_alter_table('opportunities', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_opportunities_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_opportunities_thread_id'), ['thread_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_opportunities_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_table('opportunities')
    with op.batch_alter_table('applications', schema=None) as batch_op:
        batch_op.drop_column('action_needed')
