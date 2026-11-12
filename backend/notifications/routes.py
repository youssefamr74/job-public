import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from auth.models import User
from database import get_db
from notifications import service
from notifications.models import Notification

router = APIRouter()


class NotificationResponse(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: Optional[str] = None
    link: Optional[str] = None
    application_id: Optional[uuid.UUID] = None
    created_at: datetime
    read_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("created_at", "read_at", mode="after")
    @classmethod
    def as_utc(cls, value: Optional[datetime]) -> Optional[datetime]:
        return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


class UnreadCount(BaseModel):
    unread: int


class MarkedRead(BaseModel):
    marked: int


@router.get("/", response_model=list[NotificationResponse])
async def list_notifications(
    limit: int = Query(default=50, ge=1, le=500),
    unread: bool = Query(default=False, description="Only unread notifications"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_notifications(db, user, limit, unread)


@router.get("/unread-count", response_model=UnreadCount)
async def unread_count(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> UnreadCount:
    return UnreadCount(unread=await service.unread_count(db, user))


@router.post("/read-all", response_model=MarkedRead)
async def mark_all_read(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> MarkedRead:
    return MarkedRead(marked=await service.mark_read(db, user))


@router.post("/{notification_id}/read", response_model=NotificationResponse)
async def mark_read(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await service.mark_read(db, user, notification_id)
    notification = (await db.execute(select(Notification).where(
        Notification.id == notification_id, Notification.user_id == user.id
    ))).scalar_one_or_none()
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    await db.refresh(notification)
    return notification
