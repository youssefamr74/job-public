import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import date, datetime, timedelta, timezone
from auth.models import User
from applications.models import Application
from goals.models import Goal
from goals.service import get_streak
from companion.prompts import WEEKLY_REVIEW_SYSTEM, build_weekly_review_prompt
from constants.email_signals import INVALID_ROLES
from constants.job_statuses import RESPONSE_STATUSES
from ai.clients import AIError
from ai.service import ai_configured, complete_text
from utils.timeutil import local_date, local_day

logger = logging.getLogger(__name__)


# In-process cache of (payload, generated_at) per user, so the review is regenerated at most every 6 hours.
_weekly_review_cache: dict = {}
WEEKLY_REVIEW_CACHE_HOURS = 6


async def get_summary(user: User, db: AsyncSession) -> dict:
    result = await db.execute(
        select(Application.status, func.count(Application.id))
        .where(Application.user_id == user.id)
        .group_by(Application.status)
    )
    rows = result.all()

    summary = {
        "Applied": 0,
        "Assessment": 0,
        "Interview": 0,
        "Rejected": 0,
        "Offer": 0,
        "Needs Review": 0,
    }
    for status, count in rows:
        if status in summary:
            summary[status] = count

    total = sum(summary.values())

    return {
        "total": total,
        "applied": summary["Applied"],
        "assessment": summary["Assessment"],
        "interview": summary["Interview"],
        "rejected": summary["Rejected"],
        "offer": summary["Offer"],
        "needs_review": summary["Needs Review"],
    }


async def get_response_rate(user: User, db: AsyncSession) -> dict:
    total_result = await db.execute(
        select(func.count(Application.id))
        .where(Application.user_id == user.id)
    )
    total = total_result.scalar() or 0

    responded_result = await db.execute(
        select(func.count(Application.id))
        .where(
            Application.user_id == user.id,
            Application.status.in_(RESPONSE_STATUSES)
        )
    )
    responded = responded_result.scalar() or 0

    rate = round(responded / total * 100, 1) if total > 0 else 0

    return {
        "response_rate": rate,
        "responded": responded,
        "no_response": total - responded,
        "total": total,
    }


async def get_best_time(user: User, db: AsyncSession) -> dict:
    result = await db.execute(
        select(
            Application.applied_date,
            Application.status
        ).where(
            Application.user_id == user.id,
            Application.applied_date.isnot(None)
        )
    )
    rows = result.all()

    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_stats = {d: {"total": 0, "responded": 0} for d in days}

    for applied_date, status in rows:
        if applied_date:
            day_name = days[local_date(applied_date).weekday()]
            day_stats[day_name]["total"] += 1
            if status in RESPONSE_STATUSES:
                day_stats[day_name]["responded"] += 1

    breakdown = []
    for day, stats in day_stats.items():
        total = stats["total"]
        responded = stats["responded"]
        rate = round(responded / total * 100, 1) if total > 0 else 0
        breakdown.append({
            "day": day,
            "total": total,
            "responded": responded,
            "response_rate": rate
        })

    days_with_data = [b for b in breakdown if b["total"] >= 10]
    best_day = max(days_with_data, key=lambda x: x["response_rate"])["day"] if days_with_data else "Not enough data yet"
    worst_day = min(days_with_data, key=lambda x: x["response_rate"])["day"] if days_with_data else "Not enough data yet"
    return {
        "best_day": best_day,
        "worst_day": worst_day,
        "breakdown_by_day": breakdown
    }


async def get_timeline(user: User, db: AsyncSession) -> dict:
    today = date.today()
    thirty_days_ago = today - timedelta(days=30)

    result = await db.execute(
        select(
            local_day(Application.applied_date).label("day"),
            func.count(Application.id).label("count")
        ).where(
            Application.user_id == user.id,
            local_day(Application.applied_date) >= thirty_days_ago,
            Application.raw_metadata[("history", 0, "status")].as_string() == "Applied",
        ).group_by(
            local_day(Application.applied_date)
        ).order_by(
            local_day(Application.applied_date)
        )
    )
    rows = result.all()

    return {
        "timeline": [
            {"date": str(row.day), "count": row.count}
            for row in rows
        ]
    }


async def get_role_performance(user: User, db: AsyncSession) -> dict:
    result = await db.execute(
        select(
            Application.role,
            Application.status
        ).where(
            Application.user_id == user.id,
            Application.role.isnot(None),
            Application.role != "Unknown"
        )
    )
    rows = result.all()

    role_stats = {}
    for role, status in rows:
        if role not in role_stats:
            role_stats[role] = {"total": 0, "responded": 0}
        role_stats[role]["total"] += 1
        if status in RESPONSE_STATUSES:
            role_stats[role]["responded"] += 1

    roles = []
    for role, stats in role_stats.items():
        total = stats["total"]
        responded = stats["responded"]
        rate = round(responded / total * 100, 1) if total > 0 else 0
        roles.append({
            "role": role,
            "total": total,
            "responses": responded,
            "response_rate": rate
        })
    roles = [
    r for r in roles
    if r["total"] >= 2
    and r["role"].lower() not in INVALID_ROLES
    and r["role"] != "Unknown"
]

    roles.sort(key=lambda x: (x["total"], x["response_rate"]), reverse=True)

    return {"roles": roles}


def _week_bounds(today: date) -> tuple[date, date]:
    start = today - timedelta(days=today.weekday())  # Monday
    end = start + timedelta(days=6)  # Sunday
    return start, end


async def _generate_weekly_review_text(
    applications_this_week: int,
    applications_last_week: int,
    responses_this_week: int,
    goals_met_this_week: int,
    streak: int,
    pipeline: dict,
) -> tuple[str, str, list[str]] | None:
    prompt = build_weekly_review_prompt(
        applications_this_week=applications_this_week,
        applications_last_week=applications_last_week,
        responses_this_week=responses_this_week,
        goals_met_this_week=goals_met_this_week,
        streak=streak,
        pipeline=pipeline,
    )

    try:
        text = await complete_text(WEEKLY_REVIEW_SYSTEM, [{"role": "user", "content": prompt}], 250)
    except AIError as exc:
        logger.warning(f"Weekly review generation failed: {exc.code}")
        return None
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if len(lines) >= 5:
        return lines[0], lines[1], lines[2:5]
    logger.warning("Weekly review response had too few lines")
    return None


def _interview_booked_between(app: Application, start: date, end: date) -> bool:
    meta = app.raw_metadata or {}
    dates = [e.get("date") for e in meta.get("history") or [] if e.get("status") == "Interview"]
    dates += [e.get("date") for e in meta.get("edits") or [] if e.get("field") == "status" and e.get("to") == "Interview"]
    for value in dates:
        try:
            if value and start <= local_date(datetime.fromisoformat(value)) <= end:
                return True
        except (TypeError, ValueError):
            continue
    return False


async def goal_days_met_this_week(user: User, db: AsyncSession) -> int:
    week_start, week_end = _week_bounds(date.today())
    rows = await db.execute(select(Goal).where(
        Goal.user_id == user.id, Goal.date >= week_start, Goal.date <= week_end,
    ))
    return sum(1 for goal in rows.scalars().all() if goal.goal_met)


async def get_weekly_review(user: User, db: AsyncSession) -> dict:
    cached = _weekly_review_cache.get(user.id)
    if cached:
        payload, generated_at = cached
        if datetime.now(timezone.utc) - generated_at < timedelta(hours=WEEKLY_REVIEW_CACHE_HOURS):
            return payload

    today = date.today()
    week_start, week_end = _week_bounds(today)
    last_week_start = week_start - timedelta(days=7)
    last_week_end = week_end - timedelta(days=7)

    this_week_result = await db.execute(
        select(func.count(Application.id)).where(
            Application.user_id == user.id,
            local_day(Application.applied_date) >= week_start,
            local_day(Application.applied_date) <= week_end,
        )
    )
    applications_this_week = this_week_result.scalar() or 0

    last_week_result = await db.execute(
        select(func.count(Application.id)).where(
            Application.user_id == user.id,
            local_day(Application.applied_date) >= last_week_start,
            local_day(Application.applied_date) <= last_week_end,
        )
    )
    applications_last_week = last_week_result.scalar() or 0

    # Manual edits don't add a history event, so for those fall back to last_updated.
    all_apps_result = await db.execute(
        select(Application).where(Application.user_id == user.id)
    )
    all_apps = all_apps_result.scalars().all()

    responses_this_week = 0
    interviews_this_week = 0
    for app in all_apps:
        if _interview_booked_between(app, week_start, week_end):
            interviews_this_week += 1
        history = (app.raw_metadata or {}).get("history", [])
        matched = False
        for event in history:
            if event.get("status") not in RESPONSE_STATUSES:
                continue
            event_date_str = event.get("date")
            if not event_date_str:
                continue
            try:
                event_date = local_date(datetime.fromisoformat(event_date_str))
            except (ValueError, TypeError):
                continue
            if week_start <= event_date <= week_end:
                responses_this_week += 1
                matched = True
        if not matched and app.manually_modified and app.status in RESPONSE_STATUSES:
            last_updated = app.last_updated
            if last_updated and week_start <= local_date(last_updated) <= week_end:
                responses_this_week += 1

    goal_result = await db.execute(
        select(Goal).where(
            Goal.user_id == user.id,
            Goal.date >= week_start,
            Goal.date <= week_end,
        )
    )
    goals_met_this_week = sum(1 for g in goal_result.scalars().all() if g.goal_met)

    streak_info = await get_streak(user=user, db=db)
    streak = streak_info["streak"]

    pipeline = await get_summary(user=user, db=db)

    review_text = None
    if ai_configured():
        review_text = await _generate_weekly_review_text(
            applications_this_week=applications_this_week,
            applications_last_week=applications_last_week,
            responses_this_week=responses_this_week,
            goals_met_this_week=goals_met_this_week,
            streak=streak,
            pipeline=pipeline,
        )
    highlight, concern, focus_items = review_text or (None, None, None)

    payload = {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "applications_this_week": applications_this_week,
        "applications_last_week": applications_last_week,
        "responses_this_week": responses_this_week,
        "interviews_this_week": interviews_this_week,
        "ai_configured": ai_configured(),
        "goals_met_this_week": goals_met_this_week,
        "streak": streak,
        "highlight": highlight,
        "concern": concern,
        "focus_items": focus_items,
    }
    # Only cache AI text: the numbers are cheap, and a failed AI call should be retried.
    if review_text:
        _weekly_review_cache[user.id] = (payload, datetime.now(timezone.utc))
    return payload