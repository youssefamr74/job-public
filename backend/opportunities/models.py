from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base

OPEN = "open"
CONVERTED = "converted"
DISMISSED = "dismissed"
STATUSES = (OPEN, CONVERTED, DISMISSED)


class Opportunity(Base):
    """A recruiter reaching out. It becomes an application only once the user applies."""

    __tablename__ = "opportunities"
    __table_args__ = (UniqueConstraint("user_id", "message_id", name="uq_opportunity_message"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company: Mapped[Optional[str]] = mapped_column(String(255))
    role: Mapped[Optional[str]] = mapped_column(String(255))
    sender: Mapped[Optional[str]] = mapped_column(Text)
    subject: Mapped[Optional[str]] = mapped_column(Text)
    date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    thread_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=OPEN, nullable=False, index=True)
    application_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
