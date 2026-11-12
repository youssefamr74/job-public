from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid, func, true
from sqlalchemy.orm import Mapped, mapped_column

from database import Base

PRIVACY_SUBJECT_SENDER = "subject_sender"
PRIVACY_WITH_BODY = "with_body"

BATCH_PENDING = "pending"
BATCH_COMPLETED = "completed"
BATCH_FAILED = "failed"

PURPOSE_CLASSIFY = "classify"
PURPOSE_REVIEW = "review"


class AIConfig(Base):
    __tablename__ = "ai_configs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    base_url: Mapped[Optional[str]] = mapped_column(String(500))
    # Fernet token of {"api_key": ...}; see mail/crypto.py.
    credentials: Mapped[str] = mapped_column(Text, nullable=False)
    privacy_mode: Mapped[str] = mapped_column(String(20), nullable=False, default=PRIVACY_SUBJECT_SENDER)
    body_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    use_batch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    batch_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AIBatchJob(Base):
    """A batch sent to the provider. Holds message ids and parsed answers only, never email text."""

    __tablename__ = "ai_batch_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    remote_id: Mapped[str] = mapped_column(String(200), nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    # [{"custom_id", "message_id", "application_id"?}]
    items: Mapped[list] = mapped_column(JSON, nullable=False)
    # {message_id: parsed answer or null}
    results: Mapped[Optional[dict]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=BATCH_PENDING, index=True)
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
