from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from auth.models import User
from database import get_db
from diagnostics.service import clear_dropped, list_dropped

router = APIRouter()

Reason = Literal["filtered_out", "job_alert", "social", "not_job", "no_company_or_role"]


class DroppedEmailItem(BaseModel):
    message_id: str
    subject: Optional[str]
    sender: Optional[str]
    snippet: Optional[str]
    reason: str
    detail: Optional[str]
    dropped_at: datetime


class DroppedEmailsResponse(BaseModel):
    total: int
    by_reason: dict[str, int]
    items: list[DroppedEmailItem]


class ClearedResponse(BaseModel):
    deleted: int


@router.get("/dropped", response_model=DroppedEmailsResponse)
async def dropped_emails(
    reason: Optional[Reason] = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DroppedEmailsResponse:
    total, by_reason, items = await list_dropped(db, user.id, reason, limit, offset)
    return DroppedEmailsResponse(
        total=total,
        by_reason=by_reason,
        items=[
            DroppedEmailItem(
                message_id=item.gmail_message_id, subject=item.subject, sender=item.sender,
                snippet=item.snippet, reason=item.reason, detail=item.detail, dropped_at=item.dropped_at,
            )
            for item in items
        ],
    )


@router.delete("/dropped", response_model=ClearedResponse)
async def delete_dropped_emails(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ClearedResponse:
    return ClearedResponse(deleted=await clear_dropped(db, user.id))
