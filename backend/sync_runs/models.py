from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from utils.timeutil import utc_now

TRIGGER_MANUAL = "manual"
TRIGGER_SCHEDULED = "scheduled"
TRIGGER_BATCH_DONE = "batch_done"

RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"
CANCELLED = "cancelled"
WAITING_FOR_AI = "waiting_for_ai"

STAGE_FETCHING = "fetching"
STAGE_FILTERING = "filtering"
STAGE_CLASSIFYING = "classifying"
STAGE_SAVING = "saving"

ERR_NOT_CONNECTED = "mail_not_connected"
ERR_NEEDS_RELINK = "mail_needs_relink"
ERR_AUTH_FAILED = "mail_auth_failed"
ERR_UNREACHABLE = "mail_unreachable"
ERR_AI_UNAVAILABLE = "ai_unavailable"
ERR_INTERRUPTED = "interrupted"
ERR_INTERNAL = "internal"

ERROR_MESSAGES = {
    ERR_NOT_CONNECTED: "No mail account is connected.",
    ERR_NEEDS_RELINK: "The mail account needs to be reconnected.",
    ERR_AUTH_FAILED: "The mail provider rejected the saved credentials.",
    ERR_UNREACHABLE: "The mail provider could not be reached.",
    ERR_AI_UNAVAILABLE: "The AI provider was unavailable; the rules result was used.",
    ERR_INTERRUPTED: "The app was closed or crashed while the sync was running.",
    ERR_INTERNAL: "The sync failed unexpectedly. See the log for details.",
}

KEEP_RUNS = 100


class SyncRun(Base):
    __tablename__ = "sync_runs"
    __table_args__ = (
        Index("uq_sync_runs_one_running", "user_id", unique=True, sqlite_where=text("status = 'running'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=RUNNING)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    stage: Mapped[Optional[str]] = mapped_column(String(20))
    progress_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_total: Mapped[Optional[int]] = mapped_column(Integer)
    funnel: Mapped[Optional[dict]] = mapped_column(JSON)
    summary: Mapped[Optional[dict]] = mapped_column(JSON)
    error_code: Mapped[Optional[str]] = mapped_column(String(40))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
