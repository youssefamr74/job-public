from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base

KIND_REJECTION = "rejection"
KIND_INTERVIEW = "interview"
KIND_ASSESSMENT = "assessment"
KIND_OFFER = "offer"
KIND_INTERVIEW_TOMORROW = "interview_tomorrow"
KIND_NO_NEWS = "no_news"
KIND_NO_REPLY = "no_reply"
KIND_WEEKLY = "weekly_summary"
KIND_RECONNECT = "mail_reconnect"


class Notification(Base):
    """Shown in the app only; nothing is sent anywhere. One row per event, found by its key."""

    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_notification_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text)
    link: Mapped[Optional[str]] = mapped_column(String(500))
    application_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
