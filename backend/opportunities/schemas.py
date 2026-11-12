import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class OpportunityResponse(BaseModel):
    id: uuid.UUID
    company: Optional[str]
    role: Optional[str]
    sender: Optional[str]
    subject: Optional[str]
    date: Optional[datetime]
    thread_id: Optional[str]
    message_id: Optional[str] = None
    status: str
    application_id: Optional[uuid.UUID] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("date", mode="after")
    @classmethod
    def as_utc(cls, value: Optional[datetime]) -> Optional[datetime]:
        return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value

    @field_validator("message_id", mode="after")
    @classmethod
    def mail_ids_only(cls, value: Optional[str]) -> Optional[str]:
        """Opportunities moved from an application without an email get a made-up id; it can't be opened."""
        return value if value and ":" not in value else None
