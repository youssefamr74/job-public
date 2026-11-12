from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, ForeignKey, Integer, UniqueConstraint, Uuid, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from auth.models import User


class Goal(Base):
    __tablename__ = "goals"
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_goals_user_date"),
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
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    target: Mapped[int] = mapped_column(Integer, nullable=False)
    achieved: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    goal_met: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="goals")
