import logging

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from auth.models import User

logger = logging.getLogger(__name__)


async def update_profile(user: User, db: AsyncSession, **kwargs) -> User:
    try:
        await db.execute(
            update(User)
            .where(User.id == user.id)
            .values(**kwargs)
        )
        await db.commit()
        await db.refresh(user)
        return user
    except Exception:
        logger.error("Failed to update profile for user %s", user.id, exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update profile")
