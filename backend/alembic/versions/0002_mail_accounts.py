"""mail accounts

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-10 13:47:36.975537

"""
from typing import Sequence, Union

import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from pydantic_settings import BaseSettings, SettingsConfigDict

from config import BACKEND_DIR


revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


class _OldGoogleSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""


def _move_gmail_tokens(mail_accounts: sa.Table) -> None:
    """Existing Gmail tokens become an OAuth mail account, if the old client settings are still around."""
    rows = op.get_bind().execute(sa.text(
        "SELECT id, gmail_token, gmail_refresh_token, last_history_id FROM users "
        "WHERE gmail_refresh_token IS NOT NULL"
    )).fetchall()
    old = _OldGoogleSettings()
    if not rows or not (old.GOOGLE_CLIENT_ID and old.GOOGLE_CLIENT_SECRET):
        return

    from mail.crypto import encrypt_json

    now = datetime.now(timezone.utc)
    op.bulk_insert(mail_accounts, [
        {
            "id": uuid.uuid4(),
            "user_id": uuid.UUID(hex=str(row.id).replace("-", "")),
            "source_type": "oauth",
            "email": None,
            "credentials": encrypt_json({
                "client_id": old.GOOGLE_CLIENT_ID,
                "client_secret": old.GOOGLE_CLIENT_SECRET,
                "access_token": row.gmail_token,
                "refresh_token": row.gmail_refresh_token,
            }),
            "cursor": {"history_id": row.last_history_id} if row.last_history_id else None,
            "status": "connected",
            "connected_at": now,
            "updated_at": now,
        }
        for row in rows
    ])


def upgrade() -> None:
    mail_accounts = op.create_table('mail_accounts',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('source_type', sa.String(length=10), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('credentials', sa.Text(), nullable=False),
    sa.Column('cursor', sa.JSON(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('connected_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    _move_gmail_tokens(mail_accounts)
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('last_history_id')
        batch_op.drop_column('gmail_refresh_token')
        batch_op.drop_column('gmail_token')


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('gmail_token', sa.TEXT(), nullable=True))
        batch_op.add_column(sa.Column('gmail_refresh_token', sa.TEXT(), nullable=True))
        batch_op.add_column(sa.Column('last_history_id', sa.VARCHAR(length=50), nullable=True))

    op.drop_table('mail_accounts')
