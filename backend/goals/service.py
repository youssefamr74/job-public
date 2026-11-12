import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from datetime import datetime, date, timedelta
from auth.models import User
from applications.models import Application
from goals.models import Goal
from utils.timeutil import local_day

logger = logging.getLogger(__name__)


async def _count_today_applications(user: User, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count(Application.id)).where(
            Application.user_id == user.id,
            local_day(Application.applied_date) == date.today(),
        )
    )
    return result.scalar() or 0


async def _get_today_goal_record(user: User, db: AsyncSession) -> Goal | None:
    result = await db.execute(
        select(Goal).where(
            Goal.user_id == user.id,
            Goal.date == date.today(),
        )
    )
    return result.scalar_one_or_none()


async def get_today_progress(user: User, db: AsyncSession) -> dict:
    count = await _count_today_applications(user, db)
    # A daily goal of 0 would count as met every day, so treat it as 1.
    effective_goal = user.daily_goal if user.daily_goal > 0 else 1
    return {
        "target": effective_goal,
        "achieved": count,
        "remaining": max(0, effective_goal - count),
        "goal_met": count >= effective_goal,
    }


async def update_streak(user: User, db: AsyncSession) -> None:
    today = date.today()
    # Weekends don't count towards or break a streak; on Monday, Friday counts as the previous day.
    if today.weekday() >= 5:
        return

    count = await _count_today_applications(user, db)
    effective_goal = user.daily_goal if user.daily_goal > 0 else 1
    goal_met = count >= effective_goal

    if goal_met:
        last = user.streak_last_date
        yesterday = today - timedelta(days=1)

        if last == today:
            return
        elif last == yesterday or (
            today.weekday() == 0 and last == today - timedelta(days=3)
        ):
            user.streak_count += 1
            user.streak_last_date = today
        else:
            user.streak_count = 1
            user.streak_last_date = today
    else:
        user.streak_count = 0
        user.streak_last_date = None

    await db.commit()


async def get_streak(user: User, db: AsyncSession) -> dict:
    result = await db.execute(
        select(func.max(Goal.achieved)).where(
            Goal.user_id == user.id,
            Goal.goal_met == True,
        )
    )
    longest = result.scalar() or 0

    return {
        "streak": user.streak_count,
        "last_date": user.streak_last_date,
        "longest_streak": longest,
    }


async def update_daily_target(user: User, db: AsyncSession, target: int) -> None:
    await db.execute(
        update(User).where(User.id == user.id).values(daily_goal=target)
    )
    await db.commit()


async def get_weekly_summary(user: User, db: AsyncSession) -> dict:
    today = date.today()
    week_ago = today - timedelta(days=7)

    result = await db.execute(
        select(Goal)
        .where(Goal.user_id == user.id, Goal.date >= week_ago)
        .order_by(Goal.date)
    )
    goals = result.scalars().all()

    total_this_week = sum(g.achieved for g in goals)
    days_goal_met = sum(1 for g in goals if g.goal_met)

    daily_breakdown = [
        {"date": str(g.date), "count": g.achieved, "goal_met": g.goal_met}
        for g in goals
    ]

    return {
        "total_this_week": total_this_week,
        "days_goal_met": days_goal_met,
        "daily_goal": user.daily_goal,
        "daily_breakdown": daily_breakdown,
    }


async def save_goal_record(user: User, db: AsyncSession, affected_dates: set[date] = None) -> None:
    effective_goal = user.daily_goal if user.daily_goal > 0 else 1

    # An incremental sync passes the days it touched; otherwise every day is rebuilt.
    if affected_dates:
        dates_to_process = affected_dates
    else:
        result = await db.execute(
            select(local_day(Application.applied_date).label("day"))
            .where(Application.user_id == user.id)
            .group_by(local_day(Application.applied_date))
        )
        dates_to_process = {row.day for row in result.fetchall() if row.day}

    for day in dates_to_process:
        count_result = await db.execute(
            select(func.count(Application.id)).where(
                Application.user_id == user.id,
                local_day(Application.applied_date) == day,
            )
        )
        count = count_result.scalar() or 0

        existing = await db.execute(
            select(Goal).where(Goal.user_id == user.id, Goal.date == day)
        )
        existing = existing.scalar_one_or_none()

        if existing:
            existing.achieved = count
            existing.goal_met = count >= effective_goal
        else:
            db.add(Goal(
                user_id=user.id,
                date=day,
                target=effective_goal,
                achieved=count,
                goal_met=count >= effective_goal,
            ))

    await db.commit()