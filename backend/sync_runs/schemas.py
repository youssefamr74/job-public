import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from constants.app_config import MAX_RESULTS
from sync_runs.service import MAX_INTERVAL_MINUTES
from utils.timeutil import local_date


class SyncOptions(BaseModel):
    """Only used by the first sync; later ones are incremental."""

    since_date: Optional[date] = None
    max_messages: Optional[int] = Field(default=None, ge=1, le=10 * MAX_RESULTS)

    @field_validator("since_date")
    @classmethod
    def not_in_the_future(cls, value: Optional[date]) -> Optional[date]:
        if value is not None and value > local_date(datetime.now().astimezone()):
            raise ValueError("since_date can't be in the future")
        return value


class SyncRunResponse(BaseModel):
    id: uuid.UUID
    trigger: str
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    stage: Optional[str] = None
    progress_done: int = 0
    progress_total: Optional[int] = None
    funnel: Optional[dict] = None
    summary: Optional[dict] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    cancel_requested: bool = False

    model_config = ConfigDict(from_attributes=True)


class SyncStatusResponse(BaseModel):
    running_run: Optional[SyncRunResponse] = None
    last_run: Optional[SyncRunResponse] = None
    last_success_at: Optional[datetime] = None
    next_scheduled_at: Optional[datetime] = None


class SyncSettings(BaseModel):
    interval_minutes: int = Field(ge=0, le=MAX_INTERVAL_MINUTES)
