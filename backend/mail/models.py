from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base

SOURCE_IMAP = "imap"
SOURCE_OAUTH = "oauth"

STATUS_CONNECTED = "connected"
STATUS_NEEDS_RELINK = "needs_relink"
STATUS_ERROR = "error"


class MailAccount(Base):
    __tablename__ = "mail_accounts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    source_type: Mapped[str] = mapped_column(String(10), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    # Fernet token of a JSON object; see mail/crypto.py.
    credentials: Mapped[str] = mapped_column(Text, nullable=False)
    cursor: Mapped[Optional[dict]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=STATUS_CONNECTED)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    connected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
