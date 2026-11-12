"""baseline

Revision ID: 0001
Revises: 
Create Date: 2026-11-10 13:21:20.504493

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('gmail_token', sa.Text(), nullable=True),
    sa.Column('gmail_refresh_token', sa.Text(), nullable=True),
    sa.Column('daily_goal', sa.Integer(), server_default='5', nullable=False),
    sa.Column('streak_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('streak_last_date', sa.Date(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_history_id', sa.String(length=50), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('applications',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('company', sa.String(length=255), nullable=True),
    sa.Column('role', sa.String(length=255), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('applied_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('interview_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('source', sa.String(length=50), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('raw_metadata', sa.JSON(), nullable=True),
    sa.Column('manually_modified', sa.Boolean(), server_default=sa.text('0'), nullable=False),
    sa.Column('email_thread_id', sa.String(length=255), nullable=True),
    sa.Column('job_id', sa.String(length=255), nullable=True),
    sa.Column('location', sa.String(length=255), nullable=True),
    sa.Column('application_fingerprint', sa.String(length=16), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'application_fingerprint', name='uq_user_fingerprint')
    )
    with op.batch_alter_table('applications', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_applications_application_fingerprint'), ['application_fingerprint'], unique=False)
        batch_op.create_index(batch_op.f('ix_applications_email_thread_id'), ['email_thread_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_applications_interview_date'), ['interview_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_applications_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_applications_user_id'), ['user_id'], unique=False)

    op.create_table('cvs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('cv_summary', sa.Text(), nullable=True),
    sa.Column('cv_uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('cvs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_cvs_user_id'), ['user_id'], unique=True)

    op.create_table('email_cache',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('gmail_message_id', sa.String(length=255), nullable=False),
    sa.Column('processed', sa.Boolean(), server_default=sa.text('0'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'gmail_message_id')
    )
    op.create_table('goals',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('target', sa.Integer(), nullable=False),
    sa.Column('achieved', sa.Integer(), server_default='0', nullable=False),
    sa.Column('goal_met', sa.Boolean(), server_default=sa.text('0'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'date', name='uq_goals_user_date')
    )
    with op.batch_alter_table('goals', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_goals_date'), ['date'], unique=False)
        batch_op.create_index(batch_op.f('ix_goals_user_id'), ['user_id'], unique=False)

    op.create_table('companion_moments',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('application_id', sa.Uuid(), nullable=False),
    sa.Column('moment_type', sa.String(length=50), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('companion_moments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_companion_moments_application_id'), ['application_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_companion_moments_user_id'), ['user_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('companion_moments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_companion_moments_user_id'))
        batch_op.drop_index(batch_op.f('ix_companion_moments_application_id'))

    op.drop_table('companion_moments')
    with op.batch_alter_table('goals', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_goals_user_id'))
        batch_op.drop_index(batch_op.f('ix_goals_date'))

    op.drop_table('goals')
    op.drop_table('email_cache')
    with op.batch_alter_table('cvs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_cvs_user_id'))

    op.drop_table('cvs')
    with op.batch_alter_table('applications', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_applications_user_id'))
        batch_op.drop_index(batch_op.f('ix_applications_status'))
        batch_op.drop_index(batch_op.f('ix_applications_interview_date'))
        batch_op.drop_index(batch_op.f('ix_applications_email_thread_id'))
        batch_op.drop_index(batch_op.f('ix_applications_application_fingerprint'))

    op.drop_table('applications')
    op.drop_table('users')
