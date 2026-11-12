"""The "Today" overview: coming interviews, what needs the user, and this week's numbers."""

from datetime import datetime, timedelta, timezone
from typing import Iterable

from applications.schemas import (
    ApplicationResponse,
    AttentionItem,
    TodayItem,
    TodayResponse,
    WeekNumbers,
    parse_dt,
)
from constants.job_statuses import RESPONSE_STATUSES

COMING_UP_LIMIT = 5
NO_REPLY_LIMIT = 5


def week_start(now: datetime) -> datetime:
    """Monday 00:00 of the current week in local time, as a UTC datetime."""
    local = now.astimezone()
    monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday.astimezone(timezone.utc)


def _item(app: ApplicationResponse, **extra) -> dict:
    return {"id": app.id, "company": app.company, "role": app.role, **extra}


def build_today(apps: Iterable[ApplicationResponse], now: datetime | None = None) -> TodayResponse:
    now = now or datetime.now(timezone.utc)
    tracked = [app for app in apps if app.status != "Needs Review"]
    start = week_start(now)
    end = start + timedelta(days=7)

    upcoming = sorted(
        (app for app in tracked if app.interview_date and parse_dt(app.interview_date) >= now
         and app.status not in ("Rejected", "Offer")),
        key=lambda app: parse_dt(app.interview_date),
    )
    coming_up = [TodayItem(**_item(app, date=app.interview_date)) for app in upcoming[:COMING_UP_LIMIT]]

    attention: list[AttentionItem] = []
    held = sorted((app for app in tracked if app.needs_followup), key=lambda app: parse_dt(app.interview_date))
    attention += [
        AttentionItem(**_item(app, reason="interview_held", date=app.interview_date, days=app.no_news_days))
        for app in held
    ]
    attention += [
        AttentionItem(**_item(app, reason="action_needed", date=app.last_activity_at))
        for app in tracked if app.action_needed
    ]
    waiting = sorted((app for app in tracked if app.no_reply_days is not None), key=lambda app: -app.no_reply_days)
    attention += [
        AttentionItem(**_item(app, reason="no_reply", date=app.last_activity_at, days=app.no_reply_days))
        for app in waiting[:NO_REPLY_LIMIT]
    ]

    applied = sum(1 for app in tracked if (d := parse_dt(app.applied_date)) and start <= d < end)
    replies = sum(
        1
        for app in tracked
        for event in (app.raw_metadata or {}).get("history") or []
        if isinstance(event, dict) and event.get("status") in RESPONSE_STATUSES
        and (d := parse_dt(event.get("date"))) and start <= d < end
    )
    interviews = sum(1 for app in tracked if (d := parse_dt(app.interview_date)) and start <= d < end)

    return TodayResponse(
        coming_up=coming_up,
        attention=attention,
        this_week=WeekNumbers(applied=applied, replies=replies, interviews=interviews),
    )
