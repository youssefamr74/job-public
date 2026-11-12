"""dropped emails

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-10 15:18:29.038759

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('dropped_emails',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('gmail_message_id', sa.String(length=255), nullable=False),
    sa.Column('subject', sa.Text(), nullable=True),
    sa.Column('sender', sa.Text(), nullable=True),
    sa.Column('snippet', sa.Text(), nullable=True),
    sa.Column('reason', sa.String(length=40), nullable=False),
    sa.Column('detail', sa.Text(), nullable=True),
    sa.Column('dropped_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'gmail_message_id')
    )
    with op.batch_alter_table('dropped_emails', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_dropped_emails_reason'), ['reason'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('dropped_emails', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_dropped_emails_reason'))

    op.drop_table('dropped_emails')
