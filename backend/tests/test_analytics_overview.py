"""The Analytics page numbers: GET /analytics/overview and the weekly review additions."""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.overview import build_overview
from applications.models import Application
from applications.schemas import ApplicationResponse
from auth.models import User
from tests.conftest import create_test_goal, make_client

# Wednesday at noon UTC, far from midnight in any timezone the tests run in.
NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def app(days_ago: float, status="Applied", role="Data Engineer", reply_after: float | None = None,
        reply_status="Rejected", interview=False, **extra) -> ApplicationResponse:
    applied = NOW - timedelta(days=days_ago)
    history = [{"date": applied.isoformat(), "status": "Applied"}]
    if reply_after is not None:
        history.append({"date": (applied + timedelta(days=reply_after)).isoformat(), "status": reply_status})
    if interview:
        history.append({"date": (applied + timedelta(days=(reply_after or 0) + 1)).isoformat(), "status": "Interview"})
    return ApplicationResponse(
        id="00000000-0000-0000-0000-000000000001", company="Contoso", role=role, status=status,
        applied_date=applied, source="gmail", notes=None, raw_metadata={"history": history}, **extra,
    )


def test_headline_counts_only_the_range_and_skips_needs_review():
    apps = [
        app(1), app(10, status="Rejected", reply_after=4), app(20, status="Assessment", reply_after=8, reply_status="Assessment"),
        app(45), app(3, status="Needs Review"),
    ]
    thirty = build_overview(apps, "30", goal_days_met=4, daily_goal=5, now=NOW)
    assert thirty.headline.applications == 3
    assert thirty.headline.replied == 2
    assert thirty.headline.response_rate == pytest.approx(66.7)
    assert thirty.headline.median_days_to_reply == 6
    assert thirty.headline.per_week == round(3 / (30 / 7), 1)
    assert (thirty.headline.goal_days_met, thirty.headline.goal_days, thirty.headline.daily_goal) == (4, 7, 5)
    assert build_overview(apps, "60", 0, 5, now=NOW).headline.applications == 4
    assert build_overview(apps, "all", 0, 5, now=NOW).since is None


def test_a_reply_that_was_the_first_email_has_no_reply_time():
    first_seen_as_rejection = ApplicationResponse(
        id="00000000-0000-0000-0000-000000000002", company="Contoso", role="Data Engineer", status="Rejected",
        applied_date=NOW - timedelta(days=3), source="gmail", notes=None,
        raw_metadata={"history": [{"date": (NOW - timedelta(days=3)).isoformat(), "status": "Rejected"}]},
    )
    overview = build_overview([first_seen_as_rejection, app(10, status="Rejected", reply_after=12)], "30", 0, 5, now=NOW)
    assert overview.headline.replied == 2
    assert overview.headline.median_days_to_reply == 12 and overview.headline.replies_timed == 1


def test_empty_range_has_no_rates():
    overview = build_overview([], "30", 0, 5, now=NOW)
    assert overview.headline.response_rate is None and overview.headline.median_days_to_reply is None
    assert [step.count for step in overview.funnel] == [0, 0, 0, 0, 0]
    assert overview.by_role == []
    assert all(not row.enough for row in overview.by_weekday)


def test_weeks_start_on_monday_and_include_empty_weeks():
    overview = build_overview([app(0), app(1), app(15)], "30", 0, 5, now=NOW)
    weeks = overview.per_week
    assert all(week.week_start.weekday() == 0 for week in weeks)
    assert weeks[-1].week_start == date(2026, 11, 9) and weeks[-1].count == 2
    assert [w.count for w in weeks].count(0) >= 2
    assert sum(w.count for w in weeks) == 3


def test_funnel_counts_each_step_reached():
    apps = [
        app(5), app(6, status="Rejected", reply_after=2),
        app(7, status="Assessment", reply_after=1, reply_status="Assessment"),
        app(8, status="Rejected", reply_after=1, reply_status="Assessment", interview=True),
        app(9, status="Offer", reply_after=1, reply_status="Interview"),
    ]
    funnel = {step.step: (step.count, step.rate) for step in build_overview(apps, "30", 0, 5, now=NOW).funnel}
    assert funnel == {"Applied": (5, 100.0), "Got a reply": (4, 80.0), "Assessment": (3, 60.0),
                      "Interview": (2, 40.0), "Offer": (1, 20.0)}


def test_roles_are_grouped_and_small_groups_are_marked():
    apps = [app(i % 25, role="Data Engineer", status="Rejected" if i < 4 else "Applied", reply_after=1 if i < 4 else None)
            for i in range(12)]
    apps += [app(2, role="data  engineer")]
    apps += [app(3, role=f"Analyst {i}") for i in range(5)]
    apps += [app(3, role="Unknown")]
    overview = build_overview(apps, "30", 0, 5, now=NOW)
    assert overview.role_min_applications == 3
    assert [(r.label, r.applied, r.replied) for r in overview.by_role if r.enough] == [("Data Engineer", 13, 4)]
    assert sorted(r.label for r in overview.by_role if not r.enough) == [
        "Analyst 0", "Analyst 1", "Analyst 2", "Analyst 3", "Analyst 4", "Role not found"]


def test_weekdays_with_fewer_than_ten_applications_are_too_few():
    apps = [app(7 * week) for week in range(10)]  # ten Wednesdays
    apps += [app(1)]
    rows = {row.label: row for row in build_overview(apps, "all", 0, 5, now=NOW).by_weekday}
    assert rows["Wed"].enough and rows["Wed"].applied == 10 and rows["Wed"].response_rate == 0
    assert not rows["Tue"].enough and rows["Tue"].response_rate is None and rows["Tue"].applied == 1


@pytest.mark.asyncio
async def test_overview_endpoint(db: AsyncSession, mock_user: User):
    now = datetime.now(timezone.utc)
    db.add(Application(user_id=mock_user.id, company="Contoso", role="Data Engineer", status="Applied",
                       applied_date=now - timedelta(days=2), source="gmail"))
    await db.commit()
    await create_test_goal(db, mock_user, date.today(), achieved=5, goal_met=True)
    async with make_client(mock_user, db) as client:
        response = await client.get("/analytics/overview", params={"range": "30"})
        assert (await client.get("/analytics/overview", params={"range": "7"})).status_code == 422
    assert response.status_code == 200
    data = response.json()
    assert data["headline"]["applications"] == 1
    assert data["headline"]["goal_days_met"] == 1
    assert len(data["by_weekday"]) == 7


@pytest.mark.asyncio
async def test_weekly_review_counts_interviews_and_reports_ai(db: AsyncSession, mock_user: User, ai_off):
    now = datetime.now(timezone.utc)
    db.add(Application(user_id=mock_user.id, company="Contoso", role="Data Engineer", status="Interview",
                       applied_date=now - timedelta(days=20), source="gmail",
                       raw_metadata={"history": [{"date": now.isoformat(), "status": "Interview"}]}))
    await db.commit()
    async with make_client(mock_user, db) as client:
        data = (await client.get("/analytics/weekly-review")).json()
    assert data["interviews_this_week"] == 1
    assert data["ai_configured"] is False and data["highlight"] is None
