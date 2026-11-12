"""sync runs and sync interval

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-11 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sync_interval_minutes', sa.Integer(), server_default='60', nullable=False))

    op.create_table('sync_runs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('trigger', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('stage', sa.String(length=20), nullable=True),
    sa.Column('progress_done', sa.Integer(), nullable=False),
    sa.Column('progress_total', sa.Integer(), nullable=True),
    sa.Column('funnel', sa.JSON(), nullable=True),
    sa.Column('summary', sa.JSON(), nullable=True),
    sa.Column('error_code', sa.String(length=40), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('sync_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sync_runs_started_at'), ['started_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_sync_runs_user_id'), ['user_id'], unique=False)
    op.create_index(
        'uq_sync_runs_one_running', 'sync_runs', ['user_id'], unique=True, sqlite_where=sa.text("status = 'running'")
    )


def downgrade() -> None:
    op.drop_index('uq_sync_runs_one_running', table_name='sync_runs')
    op.drop_table('sync_runs')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('sync_interval_minutes')
