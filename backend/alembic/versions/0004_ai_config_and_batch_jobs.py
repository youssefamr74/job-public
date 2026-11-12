"""ai config and batch jobs

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-10 16:27:18.580403

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('ai_batch_jobs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('provider', sa.String(length=30), nullable=False),
    sa.Column('model', sa.String(length=200), nullable=False),
    sa.Column('remote_id', sa.String(length=200), nullable=False),
    sa.Column('purpose', sa.String(length=20), nullable=False),
    sa.Column('items', sa.JSON(), nullable=False),
    sa.Column('results', sa.JSON(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('ai_batch_jobs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ai_batch_jobs_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_batch_jobs_user_id'), ['user_id'], unique=False)

    op.create_table('ai_configs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('provider', sa.String(length=30), nullable=False),
    sa.Column('model', sa.String(length=200), nullable=False),
    sa.Column('base_url', sa.String(length=500), nullable=True),
    sa.Column('credentials', sa.Text(), nullable=False),
    sa.Column('privacy_mode', sa.String(length=20), nullable=False),
    sa.Column('body_chars', sa.Integer(), nullable=False),
    sa.Column('use_batch', sa.Boolean(), server_default=sa.text('1'), nullable=False),
    sa.Column('batch_threshold', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    op.create_table('companion_chat_messages',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('companion_chat_messages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_companion_chat_messages_user_id'), ['user_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('companion_chat_messages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_companion_chat_messages_user_id'))

    op.drop_table('companion_chat_messages')
    op.drop_table('ai_configs')
    with op.batch_alter_table('ai_batch_jobs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ai_batch_jobs_user_id'))
        batch_op.drop_index(batch_op.f('ix_ai_batch_jobs_status'))

    op.drop_table('ai_batch_jobs')
