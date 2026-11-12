import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from auth.models import User
from database import get_db
from users.service import update_profile
from ai.service import ai_configured

logger = logging.getLogger(__name__)

router = APIRouter()


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    daily_goal: Optional[int] = Field(None, ge=1, le=50)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("name must not be empty or whitespace")
        return v


@router.get("/me")
async def get_profile(user: User = Depends(get_current_user)) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "daily_goal": user.daily_goal,
        "streak_count": user.streak_count,
        "ai_configured": ai_configured(),
    }


@router.patch("/me")
async def update_profile_endpoint(
    body: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    updates = body.model_dump(exclude_none=True)
    if updates:
        await update_profile(user=user, db=db, **updates)
    return {"message": "Profile updated successfully"}
