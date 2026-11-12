from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid, event, false, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from applications import role_groups
from constants.job_statuses import ApplicationStatus
from database import Base

if TYPE_CHECKING:
    from auth.models import User


class Application(Base):
    __tablename__ = "applications"
    # The sync inserts with ON CONFLICT DO NOTHING on this pair.
    __table_args__ = (
        UniqueConstraint("user_id", "application_fingerprint", name="uq_user_fingerprint"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company: Mapped[Optional[str]] = mapped_column(String(255))
    role: Mapped[Optional[str]] = mapped_column(String(255))
    # The role's core title, for grouping in Analytics (applications/role_groups.py). None: no role found.
    # Set when the role is set through the ORM; statements that bypass it (the sync's bulk insert,
    # update_application_metadata) set it themselves.
    role_group: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    # What the user said this application counts as in Analytics. Syncs never change it.
    role_group_override: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default=ApplicationStatus.APPLIED, nullable=False, index=True
    )
    applied_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    interview_date: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True),
    nullable=True,
    index=True,
)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    source: Mapped[Optional[str]] = mapped_column(String(50))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    raw_metadata: Mapped[Optional[dict]] = mapped_column(JSON)
    manually_modified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    email_thread_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    job_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    application_fingerprint: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, index=True)
    # The employer is waiting for something from the user (e.g. a Pracuj.pl request for more information).
    action_needed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="applications")


@event.listens_for(Application.role, "set")
def _recompute_role_group(target: Application, value, oldvalue, initiator) -> None:
    target.role_group = role_groups.role_group(value, target.company)


@event.listens_for(Application.company, "set")
def _recompute_role_group_for_company(target: Application, value, oldvalue, initiator) -> None:
    # A role equal to the company's name is no role.
    target.role_group = role_groups.role_group(target.role, value)


class RoleGroupMerge(Base):
    """A user's rule: applications in group `source` count in group `target`. Applies to new ones too."""

    __tablename__ = "role_group_merges"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(255), primary_key=True)
    target: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

class EmailCache(Base):
    __tablename__ = "email_cache"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    gmail_message_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    processed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IgnoredEmail(Base):
    """A message the user marked as not a job email. The sync skips it, and its thread, from then on."""

    __tablename__ = "ignored_emails"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    message_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    thread_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
