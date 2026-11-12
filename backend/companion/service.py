import logging
import uuid as uuid_lib
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select

from auth.models import User
from applications.models import Application
from analytics.service import get_summary, get_response_rate
from companion.models import ChatMessage, CompanionMoment
from companion.prompts import (
    build_chat_system_prompt,
    build_mood_insight_prompt,
    build_moment_prompt,
    MOOD_INSIGHT_SYSTEM,
    MOMENT_SYSTEM,
)
from goals.service import get_today_progress, get_streak
from cv.models import CV
from ai.clients import AIError
from utils.timeutil import utc_now
from ai.service import ai_configured, complete_text
from constants.app_config import CHAT_HISTORY_MESSAGES, CHAT_MESSAGE_MAX_CHARS

logger = logging.getLogger(__name__)

async def build_user_context(user: User, db: AsyncSession) -> str:
    
    summary = await get_summary(user=user, db=db)
    response_rate = await get_response_rate(user=user, db=db)
    today = await get_today_progress(user=user, db=db)
    streak = await get_streak(user=user, db=db)

    result = await db.execute(
        select(Application).where(
            Application.user_id == user.id,
            Application.status.in_(["Interview"]),
        )
    )
    active = result.scalars().all()
    active_list = (
        "\n".join([f"- {app.company} ({app.role}) — {app.status}" for app in active])
        or "None currently"
    )

    result = await db.execute(
        select(Application)
        .where(
            Application.user_id == user.id,
            Application.status == "Rejected",
        )
        .order_by(Application.last_updated.desc())
        .limit(3)
    )
    recent_rejections = result.scalars().all()
    rejections_list = (
        "\n".join([f"- {app.company} ({app.role})" for app in recent_rejections])
        or "None recently"
    )

    result_last = await db.execute(
        select(Application)
        .where(Application.user_id == user.id)
        .order_by(Application.applied_date.desc())
        .limit(1)
    )
    last_app = result_last.scalar_one_or_none()
    if last_app and last_app.applied_date:
        applied = last_app.applied_date
        if applied.tzinfo is None:
            applied = applied.replace(tzinfo=timezone.utc)
        days_since_last = (datetime.now(timezone.utc) - applied).days
    else:
        days_since_last = None

    cv_result = await db.execute(select(CV).where(CV.user_id == user.id))
    cv = cv_result.scalar_one_or_none()
    cv_section = f"\n\nUser's CV/Background:\n{cv.cv_summary}" if cv and cv.cv_summary else ""
    current_time = datetime.now().strftime('%A, %H:%M')

    context = f"""
User's Job Search Data:
- Total applications: {summary['total']}
- Applied (waiting): {summary['applied']}
- Interviews: {summary['interview']}
- Rejected: {summary['rejected']}
- Offers: {summary['offer']}
- Response rate: {response_rate['response_rate']}%
- Current streak: {streak['streak']} days
- Days since last application: {days_since_last if days_since_last is not None else 'unknown'}
- Today's goal: {today['achieved']} sent, {today['remaining']} remaining (target: {today['target']})
- Goal met today: {today['goal_met']}

Active Opportunities:
{active_list}

Recent Rejections (last 3):
{rejections_list}

Current time: {current_time}
{cv_section}
"""
    logger.debug("Built user context for companion")
    return context


async def chat_history(user: User, db: AsyncSession) -> list[dict]:
    rows = (await db.execute(
        select(ChatMessage).where(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(CHAT_HISTORY_MESSAGES)
    )).scalars().all()
    history = [{"role": m.role, "content": m.content[:CHAT_MESSAGE_MAX_CHARS]} for m in reversed(rows)]
    while history and history[0]["role"] != "user":
        history.pop(0)
    return history


async def clear_chat(user: User, db: AsyncSession) -> None:
    await db.execute(delete(ChatMessage).where(ChatMessage.user_id == user.id))
    await db.commit()


async def chat(user: User, db: AsyncSession, message: str) -> dict:
    message = message.strip()[:CHAT_MESSAGE_MAX_CHARS]
    if not message:
        raise HTTPException(status_code=400, detail="The message is empty.")
    context = await build_user_context(user=user, db=db)
    system_prompt = build_chat_system_prompt(context)
    messages = await chat_history(user, db) + [{"role": "user", "content": message}]

    try:
        reply = await complete_text(system_prompt, messages, 300)
    except AIError as exc:
        logger.warning(f"Companion chat failed: {exc.code}")
        raise HTTPException(status_code=503, detail="AI service temporarily unavailable")
    now = utc_now()
    db.add(ChatMessage(user_id=user.id, role="user", content=message, created_at=now))
    db.add(ChatMessage(user_id=user.id, role="assistant", content=reply[:CHAT_MESSAGE_MAX_CHARS],
                       created_at=now + timedelta(microseconds=1)))
    await db.commit()
    return {"response": reply}


async def generate_mood_insight(summary: dict, response_rate: dict, mood: str) -> dict:
    prompt = build_mood_insight_prompt(summary, response_rate, mood)

    try:
        insight = await complete_text(MOOD_INSIGHT_SYSTEM, [{"role": "user", "content": prompt}], 150)
    except AIError as exc:
        logger.warning(f"Mood insight failed: {exc.code}")
        return {"insight": "", "mood": mood}
    return {"insight": insight, "mood": mood}


async def _generate_moment_text(
    company: str, role: str, moment_type: str,
    history_length: int, total_apps: int, response_rate: float,
) -> tuple[str, str] | None:
    prompt = build_moment_prompt(
        company=company, role=role, moment_type=moment_type,
        history_length=history_length, total_apps=total_apps,
        response_rate=response_rate,
    )

    try:
        text = await complete_text(MOMENT_SYSTEM, [{"role": "user", "content": prompt}], 120)
    except AIError as exc:
        logger.warning(f"Companion moment generation failed ({exc.code}), skipping it")
        return None
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if len(lines) >= 2:
        return lines[0], lines[1]
    logger.warning("Companion moment response had too few lines, skipping it")
    return None


async def generate_moment(
    user: User, db: AsyncSession, application: Application, moment_type: str,
) -> CompanionMoment | None:
    if not ai_configured():
        return None

    company = application.company or "Unknown"
    role = application.role or "the role"
    history_length = len((application.raw_metadata or {}).get("history", []))

    summary = await get_summary(user=user, db=db)
    response_rate = await get_response_rate(user=user, db=db)

    text = await _generate_moment_text(
        company=company, role=role, moment_type=moment_type,
        history_length=history_length,
        total_apps=summary["total"],
        response_rate=response_rate["response_rate"],
    )
    if text is None:
        return None
    title, body = text

    moment = CompanionMoment(
        user_id=user.id,
        application_id=application.id,
        moment_type=moment_type,
        title=title,
        body=body,
    )
    db.add(moment)
    await db.commit()
    await db.refresh(moment)
    return moment


async def get_next_moment(user: User, db: AsyncSession) -> CompanionMoment | None:
    result = await db.execute(
        select(CompanionMoment)
        .where(CompanionMoment.user_id == user.id, CompanionMoment.seen_at.is_(None))
        .order_by(CompanionMoment.created_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def mark_moment_seen(user: User, db: AsyncSession, moment_id: str) -> None:
    moment_uuid = uuid_lib.UUID(moment_id) if isinstance(moment_id, str) else moment_id
    result = await db.execute(
        select(CompanionMoment).where(
            CompanionMoment.id == moment_uuid,
            CompanionMoment.user_id == user.id,
        )
    )
    moment = result.scalar_one_or_none()
    if not moment:
        raise HTTPException(status_code=404, detail="Moment not found")

    moment.seen_at = datetime.now(timezone.utc)
    await db.commit()