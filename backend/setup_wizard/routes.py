from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from auth.models import User
from database import get_db
from mail.schemas import SetupStatusResponse
from mail.service import get_mail_account
from ai.service import ai_configured
from sync_runs import service as sync_runs

router = APIRouter()


@router.get("/status", response_model=SetupStatusResponse)
async def setup_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SetupStatusResponse:
    account = await get_mail_account(db, user)
    return SetupStatusResponse(
        mail=account.status if account else "none",
        mail_source=account.source_type if account else None,
        mail_email=account.email if account else None,
        ai_configured=ai_configured(),
        first_sync_done=await sync_runs.first_sync_done(db, user),
        sync_running=await sync_runs.get_running(db, user) is not None,
        last_sync_at=await sync_runs.last_success_at(db, user) or user.last_sync_at,
    )
