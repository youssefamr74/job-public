"""Tests for analytics service and routes."""

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.service import (
    get_best_time,
    get_response_rate,
    get_role_performance,
    get_summary,
    get_timeline,
)
from auth.models import User
from tests.conftest import create_test_application, make_client


@pytest.mark.asyncio
async def test_summary_empty(db: AsyncSession, mock_user: User):
    result = await get_summary(user=mock_user, db=db)
    assert result["total"] == 0
    assert result["applied"] == 0
    assert result["interview"] == 0
    assert result["rejected"] == 0
    assert result["offer"] == 0
    assert result["assessment"] == 0
    assert result["needs_review"] == 0


@pytest.mark.asyncio
async def test_summary_counts_by_status(db: AsyncSession, mock_user: User):
    await create_test_application(db, mock_user, "A", "Dev", "Applied")
    await create_test_application(db, mock_user, "B", "Dev", "Applied")
    await create_test_application(db, mock_user, "C", "Dev", "Interview")
    await create_test_application(db, mock_user, "D", "Dev", "Rejected")
    await create_test_application(db, mock_user, "E", "Dev", "Offer")
    await create_test_application(db, mock_user, "F", "Dev", "Needs Review")
    await create_test_application(db, mock_user, "G", "Dev", "Assessment")

    result = await get_summary(user=mock_user, db=db)
    assert result["total"] == 7
    assert result["applied"] == 2
    assert result["interview"] == 1
    assert result["rejected"] == 1
    assert result["offer"] == 1
    assert result["needs_review"] == 1
    assert result["assessment"] == 1


@pytest.mark.asyncio
async def test_summary_only_own_applications(db: AsyncSession, mock_user: User, mock_user_with_gmail: User):
    await create_test_application(db, mock_user, "OwnCo", "Dev", "Applied")
    await create_test_application(db, mock_user_with_gmail, "OtherCo", "PM", "Interview")

    result = await get_summary(user=mock_user, db=db)
    assert result["total"] == 1
    assert result["applied"] == 1
    assert result["interview"] == 0


@pytest.mark.asyncio
async def test_summary_total_equals_sum_of_statuses(db: AsyncSession, mock_user: User):
    await create_test_application(db, mock_user, "A", "Dev", "Applied")
    await create_test_application(db, mock_user, "B", "Dev", "Rejected")
    await create_test_application(db, mock_user, "C", "Dev", "Offer")

    result = await get_summary(user=mock_user, db=db)
    statuses = ("applied", "assessment", "interview", "rejected", "offer", "needs_review")
    assert result["total"] == sum(result[s] for s in statuses)


@pytest.mark.asyncio
async def test_response_rate_no_applications(db: AsyncSession, mock_user: User):
    result = await get_response_rate(user=mock_user, db=db)
    assert result["response_rate"] == 0
    assert result["total"] == 0
    assert result["responded"] == 0
    assert result["no_response"] == 0


@pytest.mark.asyncio
async def test_response_rate_all_waiting_no_response(db: AsyncSession, mock_user: User):
    await create_test_application(db, mock_user, "A", "Dev", "Applied")
    await create_test_application(db, mock_user, "B", "Dev", "Applied")

    result = await get_response_rate(user=mock_user, db=db)
    assert result["response_rate"] == 0.0
    assert result["responded"] == 0
    assert result["no_response"] == 2


@pytest.mark.asyncio
async def test_response_rate_all_responded(db: AsyncSession, mock_user: User):
    await create_test_application(db, mock_user, "A", "Dev", "Interview")
    await create_test_application(db, mock_user, "B", "Dev", "Rejected")

    result = await get_response_rate(user=mock_user, db=db)
    assert result["response_rate"] == 100.0
    assert result["responded"] == 2
    assert result["no_response"] == 0


@pytest.mark.asyncio
async def test_response_rate_partial(db: AsyncSession, mock_user: User):
    await create_test_application(db, mock_user, "A", "Dev", "Applied")
    await create_test_application(db, mock_user, "B", "Dev", "Applied")
    await create_test_application(db, mock_user, "C", "Dev", "Applied")
    await create_test_application(db, mock_user, "D", "Dev", "Interview")

    result = await get_response_rate(user=mock_user, db=db)
    assert result["response_rate"] == 25.0
    assert result["responded"] == 1
    assert result["no_response"] == 3
    assert result["total"] == 4


@pytest.mark.asyncio
async def test_response_rate_all_responded_statuses_count(db: AsyncSession, mock_user: User):
    for status in ["Assessment", "Interview", "Rejected", "Offer"]:
        await create_test_application(db, mock_user, status, "Dev", status)
    await create_test_application(db, mock_user, "E", "Dev", "Applied")

    result = await get_response_rate(user=mock_user, db=db)
    assert result["responded"] == 4
    assert result["total"] == 5


@pytest.mark.asyncio
async def test_response_rate_needs_review_is_not_a_response(db: AsyncSession, mock_user: User):
    await create_test_application(db, mock_user, "A", "Dev", "Needs Review")
    await create_test_application(db, mock_user, "B", "Dev", "Applied")

    result = await get_response_rate(user=mock_user, db=db)
    assert result["responded"] == 0
    assert result["response_rate"] == 0


@pytest.mark.asyncio
async def test_best_time_no_applications(db: AsyncSession, mock_user: User):
    result = await get_best_time(user=mock_user, db=db)
    assert result["best_day"] == "Not enough data yet"
    assert result["worst_day"] == "Not enough data yet"
    assert len(result["breakdown_by_day"]) == 7


@pytest.mark.asyncio
async def test_best_time_breakdown_contains_all_weekdays(db: AsyncSession, mock_user: User):
    result = await get_best_time(user=mock_user, db=db)
    days = {entry["day"] for entry in result["breakdown_by_day"]}
    assert days == {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}


@pytest.mark.asyncio
async def test_best_time_insufficient_data_below_threshold(db: AsyncSession, mock_user: User):
    monday = datetime(2024, 1, 15, 12, 0, 0)  # a Monday
    for i in range(9):  # only 9 — below the 10-app threshold
        await create_test_application(db, mock_user, f"Co{i}", "Dev", "Interview", date_applied=monday)

    result = await get_best_time(user=mock_user, db=db)
    assert result["best_day"] == "Not enough data yet"


@pytest.mark.asyncio
async def test_best_time_identifies_best_and_worst_day(db: AsyncSession, mock_user: User):
    monday = datetime(2024, 1, 15, 12, 0, 0)    # Monday — 80% response rate
    wednesday = datetime(2024, 1, 17, 12, 0, 0)  # Wednesday — 20% response rate

    # 10 Monday applications: 8 responded
    for i in range(8):
        await create_test_application(db, mock_user, f"MonA{i}", "Dev", "Interview", date_applied=monday)
    for i in range(2):
        await create_test_application(db, mock_user, f"MonB{i}", "Dev", "Applied", date_applied=monday)

    # 10 Wednesday applications: 2 responded
    for i in range(2):
        await create_test_application(db, mock_user, f"WedA{i}", "Dev", "Rejected", date_applied=wednesday)
    for i in range(8):
        await create_test_application(db, mock_user, f"WedB{i}", "Dev", "Applied", date_applied=wednesday)

    result = await get_best_time(user=mock_user, db=db)
    assert result["best_day"] == "Monday"
    assert result["worst_day"] == "Wednesday"


@pytest.mark.asyncio
async def test_best_time_breakdown_response_rate_correct(db: AsyncSession, mock_user: User):
    monday = datetime(2024, 1, 15, 12, 0, 0)  # Monday
    for i in range(5):
        await create_test_application(db, mock_user, f"A{i}", "Dev", "Interview", date_applied=monday)
    for i in range(15):
        await create_test_application(db, mock_user, f"B{i}", "Dev", "Applied", date_applied=monday)

    result = await get_best_time(user=mock_user, db=db)
    monday_entry = next(e for e in result["breakdown_by_day"] if e["day"] == "Monday")
    assert monday_entry["total"] == 20
    assert monday_entry["responded"] == 5
    assert monday_entry["response_rate"] == 25.0


@pytest.mark.asyncio
async def test_timeline_returns_structure(db: AsyncSession, mock_user: User):
    result = await get_timeline(user=mock_user, db=db)
    assert "timeline" in result
    assert isinstance(result["timeline"], list)


@pytest.mark.asyncio
async def test_timeline_empty_when_no_applications(db: AsyncSession, mock_user: User):
    result = await get_timeline(user=mock_user, db=db)
    assert result["timeline"] == []


@pytest.mark.asyncio
async def test_timeline_entries_have_date_and_count(db: AsyncSession, mock_user: User):
    await create_test_application(db, mock_user, "Co", "Dev", "Applied")
    result = await get_timeline(user=mock_user, db=db)
    if result["timeline"]:
        entry = result["timeline"][0]
        assert "date" in entry
        assert "count" in entry


@pytest.mark.asyncio
async def test_role_performance_empty(db: AsyncSession, mock_user: User):
    result = await get_role_performance(user=mock_user, db=db)
    assert result["roles"] == []


@pytest.mark.asyncio
async def test_role_performance_excludes_unknown_role(db: AsyncSession, mock_user: User):
    await create_test_application(db, mock_user, "Corp", "Unknown", "Applied")
    await create_test_application(db, mock_user, "Corp", "Unknown", "Applied")
    await create_test_application(db, mock_user, "Corp", "Data Engineer", "Applied")
    await create_test_application(db, mock_user, "Other", "Data Engineer", "Applied")

    result = await get_role_performance(user=mock_user, db=db)
    role_names = [r["role"] for r in result["roles"]]
    assert "Unknown" not in role_names
    assert "Data Engineer" in role_names


@pytest.mark.asyncio
async def test_role_performance_sorted_by_response_rate_descending(db: AsyncSession, mock_user: User):
    # Data Engineer: 1/2 = 50%
    await create_test_application(db, mock_user, "A", "Data Engineer", "Interview")
    await create_test_application(db, mock_user, "B", "Data Engineer", "Applied")
    # Product Manager: 2/2 = 100%
    await create_test_application(db, mock_user, "C", "Product Manager", "Rejected")
    await create_test_application(db, mock_user, "D", "Product Manager", "Offer")

    result = await get_role_performance(user=mock_user, db=db)
    assert result["roles"][0]["role"] == "Product Manager"
    assert result["roles"][1]["role"] == "Data Engineer"
    assert result["roles"][0]["response_rate"] == 100.0
    assert result["roles"][1]["response_rate"] == 50.0


@pytest.mark.asyncio
async def test_role_performance_rate_calculation(db: AsyncSession, mock_user: User):
    await create_test_application(db, mock_user, "A", "Dev", "Interview")
    await create_test_application(db, mock_user, "B", "Dev", "Applied")
    await create_test_application(db, mock_user, "C", "Dev", "Applied")
    await create_test_application(db, mock_user, "D", "Dev", "Applied")

    result = await get_role_performance(user=mock_user, db=db)
    dev = next(r for r in result["roles"] if r["role"] == "Dev")
    assert dev["total"] == 4
    assert dev["responses"] == 1
    assert dev["response_rate"] == 25.0


@pytest.mark.asyncio
async def test_role_performance_zero_response_rate(db: AsyncSession, mock_user: User):
    await create_test_application(db, mock_user, "A", "Dev", "Applied")
    await create_test_application(db, mock_user, "B", "Dev", "Applied")

    result = await get_role_performance(user=mock_user, db=db)
    dev = next(r for r in result["roles"] if r["role"] == "Dev")
    assert dev["response_rate"] == 0.0


@pytest.mark.asyncio
async def test_route_summary(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.get("/analytics/summary")

    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "applied" in data
    assert "interview" in data


@pytest.mark.asyncio
async def test_route_response_rate(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.get("/analytics/response-rate")

    assert response.status_code == 200
    data = response.json()
    assert "response_rate" in data
    assert "responded" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_route_best_time(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.get("/analytics/best-time")

    assert response.status_code == 200
    data = response.json()
    assert "best_day" in data
    assert "worst_day" in data
    assert "breakdown_by_day" in data


@pytest.mark.asyncio
async def test_route_timeline(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.get("/analytics/timeline")

    assert response.status_code == 200
    assert "timeline" in response.json()


@pytest.mark.asyncio
async def test_route_role_performance(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.get("/analytics/role-performance")

    assert response.status_code == 200
    assert "roles" in response.json()
