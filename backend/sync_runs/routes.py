import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from auth.models import User
from database import get_db
from sync_runs import scheduler, service
from sync_runs.models import RUNNING, SyncRun
from sync_runs.schemas import SyncRunResponse, SyncSettings, SyncStatusResponse

router = APIRouter()
settings_router = APIRouter()


def _response(run: Optional[SyncRun]) -> Optional[SyncRunResponse]:
    if run is None:
        return None
    return SyncRunResponse.model_validate(run).model_copy(update={"cancel_requested": run.id in service.cancel_requests})


@router.get("/status", response_model=SyncStatusResponse)
async def sync_status(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> SyncStatusResponse:
    runs = await service.list_runs(db, user, 1)
    return SyncStatusResponse(
        running_run=_response(await service.get_running(db, user)),
        last_run=_response(runs[0] if runs else None),
        last_success_at=await service.last_success_at(db, user),
        next_scheduled_at=scheduler.next_run_at,
    )


@router.get("/runs", response_model=list[SyncRunResponse])
async def sync_runs(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return [_response(run) for run in await service.list_runs(db, user, limit)]


@router.get("/runs/{run_id}", response_model=SyncRunResponse)
async def sync_run(run_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    run = await service.get_run(db, user, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Sync run not found")
    return _response(run)


@router.post("/runs/{run_id}/cancel", response_model=SyncRunResponse)
async def cancel_run(run_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    run = await service.get_run(db, user, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Sync run not found")
    if run.status != RUNNING:
        raise HTTPException(status_code=409, detail="The sync run is not running")
    service.request_cancel(run.id)
    return _response(run)


@settings_router.get("/sync", response_model=SyncSettings)
async def get_sync_settings(user: User = Depends(get_current_user)) -> SyncSettings:
    return SyncSettings(interval_minutes=user.sync_interval_minutes)


@settings_router.put("/sync", response_model=SyncSettings)
async def put_sync_settings(
    body: SyncSettings, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> SyncSettings:
    user.sync_interval_minutes = body.interval_minutes
    await db.commit()
    scheduler.settings_changed.set()
    return body
