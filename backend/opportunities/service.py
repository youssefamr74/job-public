import uuid
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from applications.models import Application
from auth.models import User
from classifier.normalization import make_fingerprint
from opportunities.models import CONVERTED, DISMISSED, OPEN, Opportunity
from utils.timeutil import utc_now


async def open_by_thread(db: AsyncSession, user: User) -> dict[str, Opportunity]:
    rows = await db.execute(select(Opportunity).where(
        Opportunity.user_id == user.id, Opportunity.status == OPEN, Opportunity.thread_id.is_not(None)
    ))
    return {o.thread_id: o for o in rows.scalars().all()}


async def open_all(db: AsyncSession, user: User) -> list[Opportunity]:
    return list((await db.execute(select(Opportunity).where(
        Opportunity.user_id == user.id, Opportunity.status == OPEN
    ))).scalars().all())


async def list_opportunities(db: AsyncSession, user: User, status: Optional[str]) -> list[Opportunity]:
    query = select(Opportunity).where(Opportunity.user_id == user.id)
    if status:
        query = query.where(Opportunity.status == status)
    return list((await db.execute(query.order_by(Opportunity.date.desc()))).scalars().all())


async def get_opportunity(db: AsyncSession, user: User, opportunity_id: uuid.UUID) -> Optional[Opportunity]:
    return (await db.execute(select(Opportunity).where(
        Opportunity.id == opportunity_id, Opportunity.user_id == user.id
    ))).scalar_one_or_none()


async def mark_converted(db: AsyncSession, conversions: list[tuple[uuid.UUID, Optional[uuid.UUID]]]) -> None:
    for opportunity_id, application_id in conversions:
        await db.execute(update(Opportunity).where(Opportunity.id == opportunity_id).values(
            status=CONVERTED, application_id=application_id
        ))
    if conversions:
        await db.commit()


async def convert(db: AsyncSession, user: User, opportunity: Opportunity) -> Application:
    """Turn the opportunity into an application the user has applied to (or link the one in its thread)."""
    existing = None
    if opportunity.thread_id:
        existing = (await db.execute(select(Application).where(
            Application.user_id == user.id, Application.email_thread_id == opportunity.thread_id
        ))).scalars().first()
    if existing is None:
        company, role, now = opportunity.company or "Unknown", opportunity.role or "Unknown", utc_now()
        fingerprint = make_fingerprint(company, role, now)
        if fingerprint and (await db.execute(select(Application.id).where(
            Application.user_id == user.id, Application.application_fingerprint == fingerprint
        ))).first():
            fingerprint = None
        existing = Application(
            user_id=user.id, company=company, role=role, status="Applied", applied_date=now, source="opportunity",
            email_thread_id=opportunity.thread_id, application_fingerprint=fingerprint,
            raw_metadata={
                "subject": opportunity.subject, "sender": opportunity.sender, "source": "opportunity",
                "history": [{"message_id": opportunity.message_id, "date": now.isoformat(), "status": "Applied",
                             "confidence": 1.0, "reason": "converted from an opportunity",
                             "subject": opportunity.subject}],
            },
        )
        db.add(existing)
        await db.flush()
    opportunity.status = CONVERTED
    opportunity.application_id = existing.id
    await db.commit()
    await db.refresh(existing)
    return existing


async def dismissed_threads(db: AsyncSession, user: User) -> set[str]:
    rows = await db.execute(select(Opportunity.thread_id).where(
        Opportunity.user_id == user.id, Opportunity.status == DISMISSED, Opportunity.thread_id.is_not(None)
    ))
    return set(rows.scalars().all())


async def dismiss(db: AsyncSession, opportunity: Opportunity) -> Opportunity:
    """Not interested. Later emails in the same thread don't bring it back."""
    opportunity.status = DISMISSED
    await db.commit()
    await db.refresh(opportunity)
    return opportunity
