from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base

REASON_FILTERED_OUT = "filtered_out"
REASON_JOB_ALERT = "job_alert"
REASON_SOCIAL = "social"
REASON_NOT_JOB = "not_job"
REASON_SURVEY = "survey"
REASON_ACCOUNT = "account"
REASON_NO_COMPANY_OR_ROLE = "no_company_or_role"


class DroppedEmail(Base):
    """An email the sync looked at and didn't turn into an application, kept to check recall."""

    __tablename__ = "dropped_emails"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    gmail_message_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    subject: Mapped[Optional[str]] = mapped_column(Text)
    sender: Mapped[Optional[str]] = mapped_column(Text)
    snippet: Mapped[Optional[str]] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    detail: Mapped[Optional[str]] = mapped_column(Text)
    dropped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
