import logging
import re
import datetime
import uuid as uuid_lib
from email.utils import parsedate_to_datetime

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.exc import IntegrityError

from auth.models import User
from applications.models import Application, EmailCache
from applications.role_groups import role_group
from applications.schemas import FOLLOWUP_SNOOZE_DAYS
from constants.job_statuses import TERMINAL_STATUSES, VALID_TRANSITIONS, MOMENT_TYPE_BY_STATUS
from companion.service import generate_moment
from goals.service import update_streak
from utils.timeutil import as_utc, utc_now


logger = logging.getLogger(__name__)

STALE_STATUSES = {"Applied", "Assessment"}
STALE_THRESHOLD_DAYS = 14
STALE_MAX_THRESHOLD_DAYS = 45


NEEDS_REVIEW_BELOW = 0.65


def stored_status(status: str, status_confidence: float) -> str:
    """Needs Review means the classifier isn't sure of the status; a missing company or role doesn't count."""
    return "Needs Review" if status_confidence < NEEDS_REVIEW_BELOW else status


def is_valid_transition(current: str, new: str) -> bool:
    if current == new:
        return False
    return new in VALID_TRANSITIONS.get(current, set())


def parse_email_date(date_str: str) -> datetime.datetime:
    try:
        return as_utc(parsedate_to_datetime(date_str))
    except Exception:
        return utc_now()


async def save_application(
    user, db, company, role, status, date, email_id,
    interview_date=None, confidence=1.0, raw_metadata=None, thread_id=None,
):
    is_new = False
    try:
        if email_id:
            cache_result = await db.execute(
                select(EmailCache).where(
                    EmailCache.gmail_message_id == email_id,
                    EmailCache.user_id == user.id,
                )
            )
            if cache_result.scalar_one_or_none():
                return
            db.add(EmailCache(
                gmail_message_id=email_id,
                user_id=user.id,
                processed=True,
            ))

        app_result = await db.execute(
            select(Application).where(
                Application.user_id == user.id,
                Application.company == company,
                Application.role == role,
            )
        )
        existing = app_result.scalar_one_or_none()

        if existing:
            if existing.status in TERMINAL_STATUSES and not existing.manually_modified:
                if confidence < 0.95:
                    await db.commit()
                    return
            if not existing.manually_modified:
                effective_status = stored_status(status, confidence)
                if is_valid_transition(existing.status, effective_status):
                    existing.status = effective_status
                if interview_date and not existing.interview_date:
                    existing.interview_date = interview_date
        else:
            is_new = True
            effective_status = stored_status(status, confidence)
            db.add(Application(
                user_id=user.id,
                company=company,
                role=role,
                status=effective_status,
                applied_date=parse_email_date(date) if date else utc_now(),
                source="manual" if not email_id else "gmail",
                interview_date=interview_date,
                raw_metadata=raw_metadata,
                email_thread_id=thread_id,
            ))

    except Exception:
        await db.rollback()
        raise

    try:
        await db.commit()
        if is_new:
            await update_streak(user=user, db=db)
    except IntegrityError:
        await db.rollback()
        logger.warning("Duplicate skipped")
    except Exception:
        await db.rollback()
        logger.error("DB error saving application", exc_info=True)
        raise HTTPException(status_code=500, detail="Database error")


async def get_application_by_id(
    application_id: uuid_lib.UUID,
    user_id: uuid_lib.UUID,
    db: AsyncSession,
) -> Application | None:
    result = await db.execute(
        select(Application).where(
            Application.id == application_id,
            Application.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()
def make_dedup_key(company: str, role: str) -> str:
    c = re.sub(r"[^a-z0-9]", "", company.lower())
    r = re.sub(r"[^a-z0-9]", "", role.lower())
    return f"{c}_{r}"


async def get_user_applications(user, db, status=None, limit=None):
    query = select(Application).where(Application.user_id == user.id)
    if status:
        query = query.where(Application.status == status)
    query = query.order_by(Application.applied_date.desc())
    if limit:
        query = query.limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


async def update_application(
    user: User, db: AsyncSession,
    application_id: str, status: str = None, notes: str = None, action_needed: bool = None,
) -> None:
    app_uuid = uuid_lib.UUID(application_id) if isinstance(application_id, str) else application_id
    result = await db.execute(
        select(Application).where(
            Application.id == app_uuid,
            Application.user_id == user.id,
        )
    )
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    previous_status = application.status
    updates = {}
    if status is not None:
        updates["status"] = status
        updates["manually_modified"] = True
        if status != previous_status:
            updates["raw_metadata"] = with_edits(application.raw_metadata, [("status", previous_status, status)])
    if notes is not None:
        updates["notes"] = notes
    if action_needed is not None:
        updates["action_needed"] = action_needed

    if updates:
        await db.execute(
            update(Application)
            .where(Application.id == app_uuid, Application.user_id == user.id)
            .values(**updates)
        )

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        logger.error("DB error updating application", exc_info=True)
        raise HTTPException(status_code=500, detail="Database error")

    if status is not None and status != previous_status and status in MOMENT_TYPE_BY_STATUS:
        await db.refresh(application)
        try:
            await generate_moment(
                user=user, db=db, application=application,
                moment_type=MOMENT_TYPE_BY_STATUS[status],
            )
        except Exception:
            logger.warning("Failed to generate companion moment for manual status update", exc_info=True)


async def delete_application(
    user: User, db: AsyncSession, application_id: str,
) -> None:
    app_uuid = uuid_lib.UUID(application_id) if isinstance(application_id, str) else application_id
    result = await db.execute(
        select(Application).where(
            Application.id == app_uuid,
            Application.user_id == user.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Application not found")

    await db.execute(
        delete(Application).where(
            Application.id == app_uuid,
            Application.user_id == user.id,
        )
    )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        logger.error("DB error deleting application", exc_info=True)
        raise HTTPException(status_code=500, detail="Database error")


async def update_application_metadata(
    user: User, db: AsyncSession,
    application_id: str, data: dict,
) -> None:
    app_uuid = uuid_lib.UUID(application_id) if isinstance(application_id, str) else application_id
    result = await db.execute(
        select(Application).where(
            Application.id == app_uuid,
            Application.user_id == user.id,
        )
    )
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    allowed = {"company", "role", "interview_date", "raw_metadata"}
    updates = {k: v for k, v in data.items() if k in allowed}
    # "Count as" only changes Analytics, so it doesn't mark the application as edited (that stops syncs
    # from changing its status).
    if "role_group_override" in data:
        count_as = " ".join((data["role_group_override"] or "").split()) or None
        if count_as != application.role_group_override:
            await db.execute(
                update(Application)
                .where(Application.id == app_uuid, Application.user_id == user.id)
                .values(role_group_override=count_as)
            )
    if "role" in updates or "company" in updates:
        updates["role_group"] = role_group(updates.get("role", application.role),
                                           updates.get("company", application.company))
    if "interview_date" in updates and isinstance(updates["interview_date"], str):
        try:
            updates["interview_date"] = datetime.datetime.fromisoformat(updates["interview_date"])
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid interview_date format. Use YYYY-MM-DD.")
    edits = [
        (field, getattr(application, field), updates[field])
        for field in ("company", "role")
        if field in updates and updates[field] != getattr(application, field)
    ]
    if edits:
        updates["raw_metadata"] = with_edits(updates.get("raw_metadata", application.raw_metadata), edits)
    if updates:
        await db.execute(
            update(Application)
            .where(Application.id == app_uuid, Application.user_id == user.id)
            .values(**updates, manually_modified=True)
        )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database error")


async def record_interview_outcome(
    user: User, db: AsyncSession, application_id: uuid_lib.UUID, outcome: str,
) -> None:
    """The answer to "How did it go?" for an interview that was held."""
    application = await get_application_by_id(application_id, user.id, db)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    if outcome in ("rejected", "offer"):
        await update_application(
            user=user, db=db, application_id=application_id,
            status="Rejected" if outcome == "rejected" else "Offer",
        )
        return
    if outcome == "next_round":
        application.raw_metadata = with_edits(
            application.raw_metadata,
            [("interview", application.interview_date.isoformat() if application.interview_date else None, None)],
        )
        application.interview_date = None
    else:
        until = utc_now() + datetime.timedelta(days=FOLLOWUP_SNOOZE_DAYS)
        application.raw_metadata = {**(application.raw_metadata or {}), "followup_snoozed_until": until.isoformat()}
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        logger.error("DB error saving interview outcome", exc_info=True)
        raise HTTPException(status_code=500, detail="Database error")


def with_edits(raw_metadata: dict | None, edits: list[tuple[str, object, object]]) -> dict:
    """A copy of raw_metadata with the user's own edits appended, for the application timeline."""
    metadata = dict(raw_metadata or {})
    now = utc_now().isoformat()
    metadata["edits"] = [
        *(metadata.get("edits") or []),
        *({"date": now, "field": field, "from": old, "to": new} for field, old, new in edits),
    ]
    return metadata


async def create_manual_application(
    user: User, db: AsyncSession,
    company: str, role: str, status: str, applied_date: datetime.date | None,
) -> Application:
    existing = await db.execute(
        select(Application.id).where(
            Application.user_id == user.id,
            Application.company == company,
            Application.role == role,
        )
    )
    if existing.first():
        raise HTTPException(status_code=409, detail="An application for this company and role already exists")

    when = (
        datetime.datetime.combine(applied_date, datetime.time(12), tzinfo=datetime.timezone.utc)
        if applied_date else utc_now()
    )
    application = Application(
        user_id=user.id,
        company=company,
        role=role,
        status=status,
        applied_date=when,
        source="manual",
        manually_modified=True,
    )
    db.add(application)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="An application for this company and role already exists")
    await db.refresh(application)
    try:
        await update_streak(user=user, db=db)
    except Exception:
        logger.warning("Failed to update streak for a manual application", exc_info=True)
    return application


def _last_activity_date(app: Application):
    """Last dated status event from sync history, falling back to applied_date."""
    history = (app.raw_metadata or {}).get("history", [])
    if history:
        try:
            last_date = history[-1].get("date")
            if last_date:
                parsed = datetime.datetime.fromisoformat(last_date)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=datetime.timezone.utc)
        except (ValueError, TypeError):
            pass
    if app.applied_date:
        d = app.applied_date
        return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
    return None


async def get_stale_applications(user: User, db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(Application).where(
            Application.user_id == user.id,
            Application.status.in_(STALE_STATUSES),
            Application.manually_modified == False,  # noqa: E712
        )
    )
    apps = result.scalars().all()

    now = datetime.datetime.now(datetime.timezone.utc)
    stale = []
    for app in apps:
        last_activity = _last_activity_date(app)
        if not last_activity:
            continue
        days_since = (now - last_activity).days
        if STALE_THRESHOLD_DAYS < days_since <= STALE_MAX_THRESHOLD_DAYS:
            stale.append((app, last_activity, days_since))

    stale.sort(key=lambda item: item[2])

    return [
        {
            "id": app.id,
            "company": app.company,
            "role": app.role,
            "status": app.status,
            "applied_date": app.applied_date,
            "days_since_update": days_since,
        }
        for app, _, days_since in stale
    ]
