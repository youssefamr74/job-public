"""role cleanup: recompute role groups with the stricter role checks

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-12 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from applications.role_groups import role_group


revision: str = '0010'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Sentences, company names and departments extracted as roles now count as "Role not found".
    # Stored roles are left as they are; only the Analytics group changes.
    bind = op.get_bind()
    for app_id, role, company in bind.execute(sa.text("SELECT id, role, company FROM applications")).all():
        bind.execute(sa.text("UPDATE applications SET role_group = :group WHERE id = :id"),
                     {"group": role_group(role, company), "id": app_id})


def downgrade() -> None:
    pass
