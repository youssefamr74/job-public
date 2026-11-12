import logging
from typing import Optional
from fastapi import APIRouter, Body, Depends, BackgroundTasks, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db, AsyncSessionLocal
from auth.dependencies import get_current_user, get_local_user
from mail.models import STATUS_NEEDS_RELINK
from mail.service import get_mail_account
from auth.models import User
import uuid as uuid_lib
from applications.service import (
    create_manual_application,
    get_user_applications,
    update_application,
    update_application_metadata,
    delete_application,
    get_stale_applications,
    get_application_by_id,
    record_interview_outcome,
)
from applications.today import build_today
from sync_runs import service as sync_run_service
from sync_runs.models import TRIGGER_MANUAL
from sync_runs.runner import run_in_background
from sync_runs.schemas import SyncOptions
from applications.reclassify import reclassify_applications
from applications.ai_review import ai_review
from applications.review import mark_not_job, move_to_opportunity
from opportunities.schemas import OpportunityResponse
from ai.clients import AIError
from ai.routes import ai_error
from ai.schemas import AIReviewResponse
from mail.base import MailError
from applications.schemas import (
    ApplicationCreate,
    ApplicationMetadataUpdate,
    ApplicationResponse,
    ApplicationUpdate,
    InterviewOutcome,
    StaleApplicationResponse,
    TodayResponse,
)
from pydantic import BaseModel
from constants.job_statuses import VALID_STATUSES

logger = logging.getLogger(__name__)

router = APIRouter()


class SyncStarted(BaseModel):
    run_id: str


async def _get_or_404(application_id: uuid_lib.UUID, user: User, db: AsyncSession):
    application = await get_application_by_id(application_id, user.id, db)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    return application


@router.post("/sync", response_model=SyncStarted)
async def sync(
    background_tasks: BackgroundTasks,
    options: Optional[SyncOptions] = Body(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SyncStarted:
    account = await get_mail_account(db, user)
    if account is None:
        raise HTTPException(
            status_code=400,
            detail="No mail account connected. Connect Gmail in setup first.",
        )
    if account.status == STATUS_NEEDS_RELINK:
        raise HTTPException(
            status_code=400,
            detail=account.last_error or "Gmail needs to be reconnected in setup.",
        )
    try:
        run = await sync_run_service.create_run(db, user, TRIGGER_MANUAL)
    except sync_run_service.SyncAlreadyRunning:
        raise HTTPException(status_code=409, detail="A sync is already running")

    background_tasks.add_task(run_in_background, AsyncSessionLocal, run.id, TRIGGER_MANUAL, options)
    return SyncStarted(run_id=str(run.id))


@router.post("/reclassify")
async def reclassify(
    apply: bool = Query(default=False, description="Save the changes; by default only a report is returned"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await reclassify_applications(db, user, apply=apply)


@router.post("/ai-review", response_model=AIReviewResponse)
async def review_with_ai(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AIReviewResponse:
    try:
        return AIReviewResponse(**await ai_review(db, user))
    except AIError as exc:
        raise ai_error(exc)
    except MailError as exc:
        raise HTTPException(status_code=502, detail={"code": exc.code, "message": exc.message})


@router.get("/")
async def get_applications(
    status: Optional[str] = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ApplicationResponse]:
    if status and status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status. Must be one of: {', '.join(sorted(VALID_STATUSES))}",
        )
    return await get_user_applications(user=user, db=db, status=status)

@router.get("/today", response_model=TodayResponse)
async def get_today(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TodayResponse:
    apps = await get_user_applications(user=user, db=db)
    return build_today(ApplicationResponse.model_validate(app) for app in apps)


@router.post("/{application_id}/interview-outcome", response_model=ApplicationResponse)
async def interview_outcome(
    application_id: uuid_lib.UUID,
    body: InterviewOutcome,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationResponse:
    await record_interview_outcome(user=user, db=db, application_id=application_id, outcome=body.outcome)
    application = await _get_or_404(application_id, user, db)
    await db.refresh(application)
    return application


@router.get("/stale")
async def get_stale(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[StaleApplicationResponse]:
    return await get_stale_applications(user=user, db=db)

@router.get("/{application_id}", response_model=ApplicationResponse)
async def get_application(
    application_id: uuid_lib.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationResponse:
    return await _get_or_404(application_id, user, db)


@router.post("/", status_code=201, response_model=ApplicationResponse)
async def create_application(
    body: ApplicationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationResponse:
    return await create_manual_application(
        user=user, db=db, company=body.company, role=body.role,
        status=body.status, applied_date=body.applied_date,
    )


@router.patch("/{application_id}", response_model=ApplicationResponse)
async def update(
    application_id: uuid_lib.UUID,
    body: ApplicationUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationResponse:
    await update_application(
        application_id=application_id,
        status=body.status,
        notes=body.notes,
        action_needed=body.action_needed,
        user=user,
        db=db,
    )
    application = await _get_or_404(application_id, user, db)
    await db.refresh(application)
    return application


@router.delete("/{application_id}")
async def delete(
    application_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await delete_application(application_id=application_id, user=user, db=db)
    return {"message": "Application deleted successfully"}


@router.patch("/{application_id}/metadata", response_model=ApplicationResponse)
async def update_metadata(
    application_id: uuid_lib.UUID,
    body: ApplicationMetadataUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationResponse:
    await update_application_metadata(
        user=user, db=db, application_id=application_id, data=body.model_dump(exclude_unset=True),
    )
    application = await _get_or_404(application_id, user, db)
    await db.refresh(application)
    return application


@router.post("/{application_id}/not-job", status_code=204)
async def not_a_job_email(
    application_id: uuid_lib.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Removes the application and remembers its emails, so a sync never adds them back."""
    await mark_not_job(db, user, await _get_or_404(application_id, user, db))


@router.post("/{application_id}/to-opportunity", response_model=OpportunityResponse)
async def to_opportunity(
    application_id: uuid_lib.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OpportunityResponse:
    """A recruiter reaching out: the application becomes an open opportunity."""
    return await move_to_opportunity(db, user, await _get_or_404(application_id, user, db))
