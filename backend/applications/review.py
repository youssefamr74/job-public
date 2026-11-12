"""Decisions from the Needs review screen that take an application out of the list."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from applications.models import Application, EmailCache, IgnoredEmail
from applications.schemas import parse_dt
from auth.models import User
from opportunities.models import OPEN, Opportunity


def _history(app: Application) -> list[dict]:
    return [e for e in (app.raw_metadata or {}).get("history") or [] if isinstance(e, dict)]


def message_ids(app: Application) -> list[str]:
    return [e["message_id"] for e in _history(app) if e.get("message_id")]


def latest_message_id(app: Application) -> Optional[str]:
    ids = message_ids(app)
    return ids[-1] if ids else None


async def ignored_ids_and_threads(db: AsyncSession, user: User) -> tuple[set[str], set[str]]:
    rows = (await db.execute(select(IgnoredEmail.message_id, IgnoredEmail.thread_id).where(
        IgnoredEmail.user_id == user.id
    ))).all()
    return {m for m, _ in rows}, {t for _, t in rows if t}


async def mark_not_job(db: AsyncSession, user: User, app: Application) -> None:
    """Remove the application and remember its emails, so a sync never adds them back."""
    ids = message_ids(app)
    if ids:
        await db.execute(sqlite_insert(IgnoredEmail).values([
            {"user_id": user.id, "message_id": m, "thread_id": app.email_thread_id} for m in ids
        ]).on_conflict_do_nothing())
        await db.execute(sqlite_insert(EmailCache).values([
            {"user_id": user.id, "gmail_message_id": m, "processed": True} for m in ids
        ]).on_conflict_do_nothing())
    elif app.email_thread_id:
        await db.execute(sqlite_insert(IgnoredEmail).values(
            user_id=user.id, message_id=f"thread:{app.email_thread_id}", thread_id=app.email_thread_id,
        ).on_conflict_do_nothing())
    await db.delete(app)
    await db.commit()


async def move_to_opportunity(db: AsyncSession, user: User, app: Application) -> Opportunity:
    """A recruiter reaching out, not an application: it becomes an open opportunity instead."""
    meta = app.raw_metadata or {}
    history = _history(app)
    message_id = latest_message_id(app) or f"application:{app.id}"
    date = parse_dt(history[-1].get("date")) if history else None
    opportunity = (await db.execute(select(Opportunity).where(
        Opportunity.user_id == user.id, Opportunity.message_id == message_id
    ))).scalar_one_or_none()
    if opportunity is None:
        opportunity = Opportunity(user_id=user.id, message_id=message_id)
        db.add(opportunity)
    opportunity.company = None if app.company in (None, "Unknown") else app.company
    opportunity.role = None if app.role in (None, "Unknown") else app.role
    opportunity.sender = meta.get("sender")
    opportunity.subject = meta.get("subject") or (history[-1].get("subject") if history else None)
    opportunity.date = date or app.applied_date
    opportunity.thread_id = app.email_thread_id
    opportunity.status = OPEN
    opportunity.application_id = None
    await db.delete(app)
    await db.commit()
    await db.refresh(opportunity)
    return opportunity
