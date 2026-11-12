"""Works out which notifications are due. Run after every sync and by an hourly check.

Each event has a key, so running the checks again never makes a duplicate."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from applications.schemas import ApplicationResponse, parse_dt
from applications.service import get_user_applications
from auth.models import User
from constants.job_statuses import RESPONSE_STATUSES
from mail.models import STATUS_NEEDS_RELINK
from mail.service import get_mail_account
from notifications.models import (
    KIND_ASSESSMENT,
    KIND_INTERVIEW,
    KIND_INTERVIEW_TOMORROW,
    KIND_NO_NEWS,
    KIND_NO_REPLY,
    KIND_OFFER,
    KIND_RECONNECT,
    KIND_REJECTION,
    KIND_WEEKLY,
    Notification,
)
from utils.timeutil import local_date, utc_now

logger = logging.getLogger(__name__)

KEEP_DAYS = 90
RECENT_EVENT_DAYS = 7

STATUS_EVENTS = {
    "Rejected": (KIND_REJECTION, "Rejection from {company}"),
    "Interview": (KIND_INTERVIEW, "Interview invite from {company}"),
    "Assessment": (KIND_ASSESSMENT, "Assessment from {company}"),
    "Offer": (KIND_OFFER, "Offer from {company}"),
}


def _company(app: ApplicationResponse) -> str:
    return app.company if app.company and app.company != "Unknown" else "an employer"


def _role(app: ApplicationResponse) -> Optional[str]:
    return app.role if app.role and app.role != "Unknown" else None


def _link(app: ApplicationResponse) -> str:
    return f"/applications?id={app.id}"


def _history(app: ApplicationResponse) -> list[dict]:
    return [e for e in (app.raw_metadata or {}).get("history") or [] if isinstance(e, dict)]


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _time_text(when: datetime) -> str:
    local = when.astimezone()
    return "" if (local.hour, local.minute) == (0, 0) else f" at {local:%H:%M}"


def status_notifications(apps: Iterable[ApplicationResponse], now: datetime) -> list[dict]:
    """A status an email brought in the last week. The user's own edits don't notify."""
    found = []
    since = now - timedelta(days=RECENT_EVENT_DAYS)
    for app in apps:
        seen = set()
        for event in _history(app):
            status, when = event.get("status"), parse_dt(event.get("date"))
            if status not in STATUS_EVENTS or when is None or when < since or status in seen:
                continue
            seen.add(status)
            kind, title = STATUS_EVENTS[status]
            found.append({
                "key": f"status:{app.id}:{status}", "kind": kind, "title": title.format(company=_company(app)),
                "body": _role(app), "link": _link(app), "application_id": app.id,
            })
    return found


def interview_notifications(apps: Iterable[ApplicationResponse], now: datetime) -> list[dict]:
    found = []
    tomorrow = local_date(now) + timedelta(days=1)
    for app in apps:
        interview = parse_dt(app.interview_date)
        if app.status == "Interview" and interview and local_date(interview) == tomorrow:
            found.append({
                "key": f"tomorrow:{app.id}:{interview.isoformat()}", "kind": KIND_INTERVIEW_TOMORROW,
                "title": f"Interview with {_company(app)} tomorrow{_time_text(interview)}",
                "body": _role(app), "link": _link(app), "application_id": app.id,
            })
        if app.needs_followup and interview:
            days = app.no_news_days or 0
            found.append({
                "key": f"no_news:{app.id}:{interview.isoformat()}", "kind": KIND_NO_NEWS,
                "title": f"No news after your {_company(app)} interview",
                "body": "Did you hear back? Record how it went." if days < 2 else
                        f"It was {days} days ago. Did you hear back? Record how it went.",
                "link": _link(app), "application_id": app.id,
            })
    return found


def no_reply_notification(apps: Iterable[ApplicationResponse], now: datetime) -> list[dict]:
    """One summary a week, not one per application."""
    waiting = [app for app in apps if app.no_reply_days is not None]
    if not waiting:
        return []
    count = len(waiting)
    return [{
        "key": f"no_reply:{_monday(local_date(now)).isoformat()}", "kind": KIND_NO_REPLY,
        "title": f"{count} application{'s have' if count != 1 else ' has'} had no reply for 14 days or more",
        "body": "A short follow-up can help, or let them go.", "link": "/applications?noreply=1",
        "application_id": None,
    }]


def weekly_notification(apps: list[ApplicationResponse], now: datetime) -> list[dict]:
    """A summary of last week, from Monday on."""
    end = _monday(local_date(now))
    start = end - timedelta(days=7)

    def in_week(value) -> bool:
        when = parse_dt(value)
        return when is not None and start <= local_date(when) < end

    applied = sum(1 for app in apps if app.status != "Needs Review" and in_week(app.applied_date))
    replies = interviews = 0
    for app in apps:
        statuses = {e.get("status") for e in _history(app) if in_week(e.get("date"))}
        replies += bool(statuses & RESPONSE_STATUSES)
        interviews += "Interview" in statuses
    return [{
        "key": f"weekly:{start.isoformat()}", "kind": KIND_WEEKLY,
        "title": f"Last week: {applied} applied, {replies} {'reply' if replies == 1 else 'replies'}, "
                 f"{interviews} interview{'' if interviews == 1 else 's'}",
        "body": None, "link": "/analytics", "application_id": None,
    }]


def due_notifications(apps: list[ApplicationResponse], now: datetime) -> list[dict]:
    return (status_notifications(apps, now) + interview_notifications(apps, now)
            + no_reply_notification(apps, now) + weekly_notification(apps, now))


async def run_checks(db: AsyncSession, user: User, now: Optional[datetime] = None) -> int:
    """Adds the notifications that are due and removes old ones. Returns how many were added."""
    now = now or utc_now()
    apps = [ApplicationResponse.model_validate(a) for a in await get_user_applications(user=user, db=db)]
    due = due_notifications(apps, now)
    account = await get_mail_account(db, user)
    if account is not None and account.status == STATUS_NEEDS_RELINK:
        connected = account.connected_at.isoformat() if account.connected_at else "unknown"
        due.append({
            "key": f"reconnect:{connected}", "kind": KIND_RECONNECT, "title": "Gmail needs to be reconnected",
            "body": "Syncing has stopped until you reconnect.", "link": "/settings#mail", "application_id": None,
        })

    added = 0
    if due:
        rows = [{"id": uuid.uuid4(), "user_id": user.id, "created_at": now, **item} for item in due]
        result = await db.execute(
            sqlite_insert(Notification).values(rows).on_conflict_do_nothing(index_elements=["user_id", "key"])
        )
        added = max(result.rowcount or 0, 0)
    await db.execute(delete(Notification).where(
        Notification.user_id == user.id, Notification.created_at < now - timedelta(days=KEEP_DAYS)
    ))
    await db.commit()
    return added


async def run_checks_safely(session_factory) -> None:
    from auth.dependencies import get_local_user

    async with session_factory() as db:
        try:
            await run_checks(db, await get_local_user(db))
        except Exception:
            await db.rollback()
            logger.warning("Notification checks failed", exc_info=True)


async def list_notifications(db: AsyncSession, user: User, limit: int, unread_only: bool) -> list[Notification]:
    query = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    rows = await db.execute(query.order_by(Notification.created_at.desc(), Notification.kind).limit(limit))
    return list(rows.scalars().all())


async def unread_count(db: AsyncSession, user: User) -> int:
    return (await db.execute(select(func.count()).select_from(Notification).where(
        Notification.user_id == user.id, Notification.read_at.is_(None)
    ))).scalar_one()


async def mark_read(db: AsyncSession, user: User, notification_id: Optional[uuid.UUID] = None) -> int:
    query = update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if notification_id is not None:
        query = query.where(Notification.id == notification_id)
    result = await db.execute(query.values(read_at=datetime.now(timezone.utc)))
    await db.commit()
    return result.rowcount or 0
