"""role groups

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-12 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from applications.role_groups import role_group


revision: str = '0009'
down_revision: Union[str, None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('applications', schema=None) as batch_op:
        batch_op.add_column(sa.Column('role_group', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('role_group_override', sa.String(length=255), nullable=True))
        batch_op.create_index(batch_op.f('ix_applications_role_group'), ['role_group'], unique=False)
    op.create_table('role_group_merges',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('source', sa.String(length=255), nullable=False),
    sa.Column('target', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'source')
    )

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, role FROM applications")).all()
    for app_id, role in rows:
        bind.execute(sa.text("UPDATE applications SET role_group = :group WHERE id = :id"),
                     {"group": role_group(role), "id": app_id})


def downgrade() -> None:
    op.drop_table('role_group_merges')
    with op.batch_alter_table('applications', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_applications_role_group'))
        batch_op.drop_column('role_group_override')
        batch_op.drop_column('role_group')
