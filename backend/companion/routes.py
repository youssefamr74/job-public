from datetime import datetime
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict, Field
from database import get_db
from auth.dependencies import get_current_user
from auth.models import User
from ai.service import ai_configured
from companion.service import chat, clear_chat, generate_mood_insight, get_next_moment, mark_moment_seen
from constants.app_config import CHAT_MESSAGE_MAX_CHARS
from analytics.service import get_summary, get_response_rate

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=CHAT_MESSAGE_MAX_CHARS)


class ChatResponse(BaseModel):
    response: str


class MoodRequest(BaseModel):
    mood: str


class MomentResponse(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    moment_type: str
    title: str
    body: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


@router.post("/chat", response_model=ChatResponse)
async def companion_chat(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    if not ai_configured():
        raise HTTPException(status_code=403, detail="AI is not configured")
    result = await chat(user=user, db=db, message=body.message)
    return ChatResponse(**result)


@router.delete("/chat", status_code=204)
async def companion_chat_clear(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await clear_chat(user=user, db=db)


@router.post("/mood-insight")
async def mood_insight(
    body: MoodRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if body.mood not in ("good", "okay", "rough"):
        raise HTTPException(status_code=400, detail="mood must be 'good', 'okay', or 'rough'")
    if not ai_configured():
        raise HTTPException(status_code=403, detail="AI is not configured")
    summary = await get_summary(user=user, db=db)
    response_rate = await get_response_rate(user=user, db=db)
    return await generate_mood_insight(summary=summary, response_rate=response_rate, mood=body.mood)


@router.get("/moment", response_model=Optional[MomentResponse])
async def get_moment(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Optional[MomentResponse]:
    moment = await get_next_moment(user=user, db=db)
    return MomentResponse.model_validate(moment) if moment else None


@router.post("/moment/{moment_id}/seen", status_code=204)
async def moment_seen(
    moment_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await mark_moment_seen(user=user, db=db, moment_id=moment_id)