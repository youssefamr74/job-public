"""Export the user's applications, and delete everything Jōb stored for them."""

from __future__ import annotations

import csv
import io
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from ai.service import delete_config
from analytics import service as analytics_service
from applications.schemas import ApplicationResponse
from applications.service import get_user_applications
from auth.models import User
from database import Base
from mail.service import disconnect

EXPORT_FIELDS = (
    "id", "company", "role", "status", "applied_date", "interview_date", "location", "source",
    "last_activity_at", "email_count", "action_needed", "notes",
)


def _plain(value: Any) -> Any:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value) if not isinstance(value, (bool, int, float, str)) else value


async def export_rows(db: AsyncSession, user: User) -> list[ApplicationResponse]:
    return [ApplicationResponse.model_validate(app) for app in await get_user_applications(user=user, db=db)]


def to_csv(apps: list[ApplicationResponse]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_FIELDS)
    for app in apps:
        writer.writerow([_plain(getattr(app, field)) for field in EXPORT_FIELDS])
    # A BOM so spreadsheet apps read the file as UTF-8.
    return "﻿" + buffer.getvalue()


def to_json(apps: list[ApplicationResponse]) -> list[dict]:
    return [
        {**{field: getattr(app, field) for field in EXPORT_FIELDS},
         "timeline": [event.model_dump() for event in app.timeline]}
        for app in apps
    ]


async def delete_all(db: AsyncSession, user: User) -> None:
    """Disconnects mail (revoking Google access), removes AI settings and every stored row. The local
    user stays, back to its first-run state."""
    await disconnect(db, user)
    await delete_config(db, user)
    for table in reversed(Base.metadata.sorted_tables):
        if table.name != "users" and "user_id" in table.c:
            await db.execute(delete(table).where(table.c.user_id == user.id))
    user.last_sync_at = None
    user.streak_count = 0
    user.streak_last_date = None
    await db.commit()
    analytics_service._weekly_review_cache.pop(user.id, None)
