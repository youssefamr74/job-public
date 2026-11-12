from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from constants.app_config import DROPPED_EMAILS_KEEP
from diagnostics.models import DroppedEmail


async def record_dropped(db: AsyncSession, user_id, entries: list[dict]) -> None:
    """Store dropped emails, one row per message, keeping only the most recent ones."""
    if entries:
        rows = [{**entry, "user_id": user_id} for entry in entries]
        statement = sqlite_insert(DroppedEmail).values(rows)
        await db.execute(statement.on_conflict_do_update(
            index_elements=["user_id", "gmail_message_id"],
            set_={
                "subject": statement.excluded.subject,
                "sender": statement.excluded.sender,
                "snippet": statement.excluded.snippet,
                "reason": statement.excluded.reason,
                "detail": statement.excluded.detail,
                "dropped_at": func.now(),
            },
        ))
    newest = (
        select(DroppedEmail.gmail_message_id)
        .where(DroppedEmail.user_id == user_id)
        .order_by(DroppedEmail.dropped_at.desc())
        .limit(DROPPED_EMAILS_KEEP)
    )
    await db.execute(delete(DroppedEmail).where(
        DroppedEmail.user_id == user_id, DroppedEmail.gmail_message_id.not_in(newest)
    ))
    await db.commit()


async def forget_dropped(db: AsyncSession, user_id, message_ids: list[str]) -> None:
    """A message that became an application is no longer dropped."""
    if message_ids:
        await db.execute(delete(DroppedEmail).where(
            DroppedEmail.user_id == user_id, DroppedEmail.gmail_message_id.in_(message_ids)
        ))
        await db.commit()


async def list_dropped(
    db: AsyncSession, user_id, reason: Optional[str], limit: int, offset: int
) -> tuple[int, dict[str, int], list[DroppedEmail]]:
    by_reason = dict((await db.execute(
        select(DroppedEmail.reason, func.count())
        .where(DroppedEmail.user_id == user_id)
        .group_by(DroppedEmail.reason)
    )).all())
    query = select(DroppedEmail).where(DroppedEmail.user_id == user_id)
    if reason:
        query = query.where(DroppedEmail.reason == reason)
    items = (await db.execute(
        query.order_by(DroppedEmail.dropped_at.desc()).limit(limit).offset(offset)
    )).scalars().all()
    total = by_reason.get(reason, 0) if reason else sum(by_reason.values())
    return total, by_reason, list(items)


async def clear_dropped(db: AsyncSession, user_id) -> int:
    result = await db.execute(delete(DroppedEmail).where(DroppedEmail.user_id == user_id))
    await db.commit()
    return result.rowcount or 0
