"""Tests for goals service and routes."""

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.models import User
from goals.models import Goal
from goals.service import (
    get_streak,
    get_today_progress,
    get_weekly_summary,
    save_goal_record,
    update_daily_target,
    update_streak,
)
from tests.conftest import create_test_application, create_test_goal, make_client


@pytest.mark.asyncio
async def test_today_progress_no_applications(db: AsyncSession, mock_user: User):
    with patch("goals.service._count_today_applications", new=AsyncMock(return_value=0)):
        result = await get_today_progress(user=mock_user, db=db)

    assert result["target"] == 5
    assert result["achieved"] == 0
    assert result["remaining"] == 5
    assert result["goal_met"] is False


@pytest.mark.asyncio
async def test_today_progress_goal_exactly_met(db: AsyncSession, mock_user: User):
    with patch("goals.service._count_today_applications", new=AsyncMock(return_value=5)):
        result = await get_today_progress(user=mock_user, db=db)

    assert result["achieved"] == 5
    assert result["remaining"] == 0
    assert result["goal_met"] is True


@pytest.mark.asyncio
async def test_today_progress_over_goal_remaining_is_zero(db: AsyncSession, mock_user: User):
    with patch("goals.service._count_today_applications", new=AsyncMock(return_value=8)):
        result = await get_today_progress(user=mock_user, db=db)

    assert result["remaining"] == 0
    assert result["goal_met"] is True


@pytest.mark.asyncio
async def test_today_progress_zero_daily_goal_uses_one(db: AsyncSession):
    user = User(id=uuid.uuid4(), email="zero@example.com", daily_goal=0, streak_count=0)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    with patch("goals.service._count_today_applications", new=AsyncMock(return_value=1)):
        result = await get_today_progress(user=user, db=db)

    assert result["target"] == 1
    assert result["goal_met"] is True


@pytest.mark.asyncio
async def test_update_streak_skipped_on_saturday(db: AsyncSession, mock_user: User):
    mock_user.streak_count = 3
    await db.commit()

    with freeze_time("2024-01-13"):  # Saturday
        with patch("goals.service._count_today_applications", new=AsyncMock(return_value=5)):
            await update_streak(user=mock_user, db=db)

    assert mock_user.streak_count == 3  # unchanged


@pytest.mark.asyncio
async def test_update_streak_skipped_on_sunday(db: AsyncSession, mock_user: User):
    mock_user.streak_count = 2
    await db.commit()

    with freeze_time("2024-01-14"):  # Sunday
        with patch("goals.service._count_today_applications", new=AsyncMock(return_value=5)):
            await update_streak(user=mock_user, db=db)

    assert mock_user.streak_count == 2


@pytest.mark.asyncio
async def test_update_streak_goal_not_met_resets(db: AsyncSession, mock_user: User):
    mock_user.streak_count = 5
    mock_user.streak_last_date = date(2024, 1, 14)
    await db.commit()

    with freeze_time("2024-01-15"):  # Monday
        with patch("goals.service._count_today_applications", new=AsyncMock(return_value=2)):
            await update_streak(user=mock_user, db=db)

    assert mock_user.streak_count == 0
    assert mock_user.streak_last_date is None


@pytest.mark.asyncio
async def test_update_streak_first_goal_ever(db: AsyncSession, mock_user: User):
    mock_user.streak_count = 0
    mock_user.streak_last_date = None
    await db.commit()

    with freeze_time("2024-01-15"):  # Monday
        with patch("goals.service._count_today_applications", new=AsyncMock(return_value=5)):
            await update_streak(user=mock_user, db=db)

    assert mock_user.streak_count == 1
    assert mock_user.streak_last_date == date(2024, 1, 15)


@pytest.mark.asyncio
async def test_update_streak_consecutive_days(db: AsyncSession, mock_user: User):
    mock_user.streak_count = 3
    mock_user.streak_last_date = date(2024, 1, 15)  # Monday
    await db.commit()

    with freeze_time("2024-01-16"):  # Tuesday
        with patch("goals.service._count_today_applications", new=AsyncMock(return_value=5)):
            await update_streak(user=mock_user, db=db)

    assert mock_user.streak_count == 4
    assert mock_user.streak_last_date == date(2024, 1, 16)


@pytest.mark.asyncio
async def test_update_streak_monday_continues_from_friday(db: AsyncSession, mock_user: User):
    mock_user.streak_count = 4
    mock_user.streak_last_date = date(2024, 1, 12)  # last Friday
    await db.commit()

    with freeze_time("2024-01-15"):  # Monday (3 days after Friday)
        with patch("goals.service._count_today_applications", new=AsyncMock(return_value=5)):
            await update_streak(user=mock_user, db=db)

    assert mock_user.streak_count == 5


@pytest.mark.asyncio
async def test_update_streak_not_incremented_twice_same_day(db: AsyncSession, mock_user: User):
    mock_user.streak_count = 3
    mock_user.streak_last_date = date(2024, 1, 16)  # already today
    await db.commit()

    with freeze_time("2024-01-16"):  # Tuesday
        with patch("goals.service._count_today_applications", new=AsyncMock(return_value=5)):
            await update_streak(user=mock_user, db=db)

    assert mock_user.streak_count == 3  # not incremented again


@pytest.mark.asyncio
async def test_update_streak_gap_resets_to_one(db: AsyncSession, mock_user: User):
    mock_user.streak_count = 10
    mock_user.streak_last_date = date(2024, 1, 10)  # 5 days ago, not consecutive
    await db.commit()

    with freeze_time("2024-01-15"):  # Monday (Jan 10 was Wed — not consecutive)
        with patch("goals.service._count_today_applications", new=AsyncMock(return_value=5)):
            await update_streak(user=mock_user, db=db)

    assert mock_user.streak_count == 1


@pytest.mark.asyncio
async def test_get_streak_no_history(db: AsyncSession, mock_user: User):
    result = await get_streak(user=mock_user, db=db)
    assert result["streak"] == 0
    assert result["last_date"] is None
    assert result["longest_streak"] == 0


@pytest.mark.asyncio
async def test_get_streak_with_goals(db: AsyncSession, mock_user: User):
    mock_user.streak_count = 5
    mock_user.streak_last_date = date(2024, 1, 15)
    await db.commit()

    await create_test_goal(db, mock_user, date(2024, 1, 13), achieved=7, goal_met=True)
    await create_test_goal(db, mock_user, date(2024, 1, 14), achieved=3, goal_met=False)
    await create_test_goal(db, mock_user, date(2024, 1, 15), achieved=5, goal_met=True)

    result = await get_streak(user=mock_user, db=db)
    assert result["streak"] == 5
    assert result["last_date"] == date(2024, 1, 15)
    assert result["longest_streak"] == 7  # max achieved where goal_met=True


@pytest.mark.asyncio
async def test_get_streak_longest_ignores_unmet_days(db: AsyncSession, mock_user: User):
    await create_test_goal(db, mock_user, date(2024, 1, 13), achieved=10, goal_met=False)
    await create_test_goal(db, mock_user, date(2024, 1, 14), achieved=3, goal_met=True)

    result = await get_streak(user=mock_user, db=db)
    assert result["longest_streak"] == 3  # 10 excluded because goal_met=False


@pytest.mark.asyncio
async def test_update_daily_target_persists(db: AsyncSession, mock_user: User):
    await update_daily_target(user=mock_user, db=db, target=10)
    await db.refresh(mock_user)
    assert mock_user.daily_goal == 10


@pytest.mark.asyncio
async def test_update_daily_target_minimum_value(db: AsyncSession, mock_user: User):
    await update_daily_target(user=mock_user, db=db, target=1)
    await db.refresh(mock_user)
    assert mock_user.daily_goal == 1


@pytest.mark.asyncio
async def test_weekly_summary_empty(db: AsyncSession, mock_user: User):
    with freeze_time("2024-01-15"):
        result = await get_weekly_summary(user=mock_user, db=db)

    assert result["total_this_week"] == 0
    assert result["days_goal_met"] == 0
    assert result["daily_breakdown"] == []
    assert result["daily_goal"] == mock_user.daily_goal


@pytest.mark.asyncio
async def test_weekly_summary_aggregates_last_seven_days(db: AsyncSession, mock_user: User):
    await create_test_goal(db, mock_user, date(2024, 1, 10), achieved=5, goal_met=True)
    await create_test_goal(db, mock_user, date(2024, 1, 12), achieved=3, goal_met=False)
    await create_test_goal(db, mock_user, date(2024, 1, 1), achieved=9, goal_met=True)  # outside window

    with freeze_time("2024-01-15"):
        result = await get_weekly_summary(user=mock_user, db=db)

    assert result["total_this_week"] == 8  # 5 + 3 only
    assert result["days_goal_met"] == 1
    assert len(result["daily_breakdown"]) == 2


@pytest.mark.asyncio
async def test_weekly_summary_breakdown_sorted_by_date(db: AsyncSession, mock_user: User):
    await create_test_goal(db, mock_user, date(2024, 1, 12), achieved=3, goal_met=False)
    await create_test_goal(db, mock_user, date(2024, 1, 10), achieved=5, goal_met=True)

    with freeze_time("2024-01-15"):
        result = await get_weekly_summary(user=mock_user, db=db)

    dates = [row["date"] for row in result["daily_breakdown"]]
    assert dates == sorted(dates)


@pytest.mark.asyncio
async def test_weekly_summary_only_own_goals(db: AsyncSession, mock_user: User, mock_user_with_gmail: User):
    await create_test_goal(db, mock_user, date(2024, 1, 12), achieved=5, goal_met=True)
    await create_test_goal(db, mock_user_with_gmail, date(2024, 1, 12), achieved=8, goal_met=True)

    with freeze_time("2024-01-15"):
        result = await get_weekly_summary(user=mock_user, db=db)

    assert result["total_this_week"] == 5  # not 13


async def _apps_on(db, user, day: date, count: int):
    noon_utc = datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc)
    for i in range(count):
        await create_test_application(db, user, f"Co{i}", "Data Engineer", "Applied", noon_utc)


@pytest.mark.asyncio
async def test_save_goal_record_creates_new(db: AsyncSession, mock_user: User):
    await _apps_on(db, mock_user, date(2024, 1, 15), 3)
    await save_goal_record(user=mock_user, db=db)

    result = await db.execute(
        select(Goal).where(Goal.user_id == mock_user.id, Goal.date == date(2024, 1, 15))
    )
    goal = result.scalar_one()
    assert goal.achieved == 3
    assert goal.target == 5
    assert goal.goal_met is False


@pytest.mark.asyncio
async def test_save_goal_record_marks_goal_met(db: AsyncSession, mock_user: User):
    await _apps_on(db, mock_user, date(2024, 1, 15), 5)
    await save_goal_record(user=mock_user, db=db)

    result = await db.execute(
        select(Goal).where(Goal.user_id == mock_user.id, Goal.date == date(2024, 1, 15))
    )
    assert result.scalar_one().goal_met is True


@pytest.mark.asyncio
async def test_save_goal_record_updates_existing(db: AsyncSession, mock_user: User):
    await create_test_goal(db, mock_user, date(2024, 1, 15), achieved=2, goal_met=False)
    await _apps_on(db, mock_user, date(2024, 1, 15), 6)
    await save_goal_record(user=mock_user, db=db)

    result = await db.execute(
        select(Goal).where(Goal.user_id == mock_user.id, Goal.date == date(2024, 1, 15))
    )
    goals = result.scalars().all()
    assert len(goals) == 1  # still one record, updated in place
    assert goals[0].achieved == 6
    assert goals[0].goal_met is True


@pytest.mark.asyncio
async def test_save_goal_record_only_affected_dates(db: AsyncSession, mock_user: User):
    await _apps_on(db, mock_user, date(2024, 1, 15), 2)
    await _apps_on(db, mock_user, date(2024, 1, 16), 1)
    await save_goal_record(user=mock_user, db=db, affected_dates={date(2024, 1, 16)})

    result = await db.execute(select(Goal).where(Goal.user_id == mock_user.id))
    assert [(g.date, g.achieved) for g in result.scalars().all()] == [(date(2024, 1, 16), 1)]


@pytest.mark.asyncio
async def test_route_today_returns_progress(db: AsyncSession, mock_user: User):
    with patch("goals.service._count_today_applications", new=AsyncMock(return_value=2)):
        async with make_client(mock_user, db) as client:
            response = await client.get("/goals/today")

    assert response.status_code == 200
    data = response.json()
    assert data["target"] == 5
    assert data["achieved"] == 2
    assert data["remaining"] == 3
    assert data["goal_met"] is False


@pytest.mark.asyncio
async def test_route_streak_returns_fields(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.get("/goals/streak")

    assert response.status_code == 200
    data = response.json()
    assert "streak" in data
    assert "last_date" in data
    assert "longest_streak" in data


@pytest.mark.asyncio
async def test_route_target_update(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.patch("/goals/target?daily_goal=10")

    assert response.status_code == 200
    assert response.json()["message"] == "Daily goal updated successfully"


@pytest.mark.asyncio
async def test_route_target_zero_rejected(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.patch("/goals/target?daily_goal=0")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_route_target_over_fifty_rejected(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.patch("/goals/target?daily_goal=51")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_route_weekly_returns_summary(db: AsyncSession, mock_user: User):
    with freeze_time("2024-01-15"):
        async with make_client(mock_user, db) as client:
            response = await client.get("/goals/weekly")

    assert response.status_code == 200
    data = response.json()
    assert "total_this_week" in data
    assert "days_goal_met" in data
    assert "daily_breakdown" in data
    assert "daily_goal" in data
