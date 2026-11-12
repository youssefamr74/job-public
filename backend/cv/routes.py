from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from auth.dependencies import get_current_user
from auth.models import User
from cv.service import upload_cv, delete_cv, get_cv_status
from ai.service import ai_configured

router = APIRouter()


@router.post("/upload")
async def upload_cv_endpoint(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not ai_configured():
        raise HTTPException(status_code=403, detail="AI is not configured")
    return await upload_cv(user=user, file=file, db=db)


@router.delete("/")
async def delete_cv_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await delete_cv(user=user, db=db)


@router.get("/status")
async def cv_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await get_cv_status(user=user, db=db)