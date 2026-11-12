from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Date, DateTime, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from applications.models import Application
    from goals.models import Goal
    from cv.models import CV


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    daily_goal: Mapped[int] = mapped_column(
        Integer, default=5, server_default="5", nullable=False
    )
    streak_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    streak_last_date: Mapped[Optional[date]] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sync_interval_minutes: Mapped[int] = mapped_column(Integer, default=60, server_default="60", nullable=False)

    applications: Mapped[List["Application"]] = relationship(
        "Application", back_populates="user", cascade="all, delete-orphan"
    )
    goals: Mapped[List["Goal"]] = relationship(
        "Goal", back_populates="user", cascade="all, delete-orphan"
    )
    cv: Mapped[Optional["CV"]] = relationship(
        "CV", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
   