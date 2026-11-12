import uuid

from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.models import User
from database import get_db

# Fixed id, so concurrent first requests can't create two users.
LOCAL_USER_ID = uuid.UUID(int=1)


async def get_local_user(db: AsyncSession) -> User:
    user = await db.get(User, LOCAL_USER_ID)
    if user:
        return user
    db.add(User(id=LOCAL_USER_ID))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
    return await db.get(User, LOCAL_USER_ID)


async def get_current_user(db: AsyncSession = Depends(get_db)) -> User:
    return await get_local_user(db)
