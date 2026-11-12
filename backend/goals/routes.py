import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from auth.dependencies import get_current_user
from auth.models import User
from goals.service import (
    get_today_progress,
    get_streak,
    update_daily_target,
    get_weekly_summary,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/today")
async def today(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await get_today_progress(user=user, db=db)


@router.get("/streak")
async def streak(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await get_streak(user=user, db=db)


@router.patch("/target")
async def target(
    daily_goal: int = Query(..., ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await update_daily_target(user=user, db=db, target=daily_goal)
    return {"message": "Daily goal updated successfully"}


@router.get("/weekly")
async def weekly(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await get_weekly_summary(user=user, db=db)
