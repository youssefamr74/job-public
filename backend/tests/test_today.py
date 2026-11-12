"""The Today overview, past interviews, the interview outcome and the progress step."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from applications.models import Application
from applications.schemas import ApplicationResponse
from applications.today import build_today, week_start
from auth.models import User
from tests.conftest import make_client

NOW = datetime.now(timezone.utc)


def app(status="Applied", history=(), edits=(), **fields) -> ApplicationResponse:
    data = {
        "id": uuid.uuid4(), "company": "Kestrel Pay", "role": "Java Developer", "status": status,
        "applied_date": NOW - timedelta(days=3), "source": "gmail", "notes": None,
        "raw_metadata": {"history": list(history), "edits": list(edits)},
    }
    data.update(fields)
    return ApplicationResponse(**data)


def event(days_ago: float, status: str) -> dict:
    return {"date": (NOW - timedelta(days=days_ago)).isoformat(), "status": status, "subject": "x"}


def test_past_interview_is_held_with_days_of_no_news():
    held = app("Interview", interview_date=NOW - timedelta(days=4), history=[event(10, "Interview")])
    assert held.interview_held is True
    assert held.no_news_days == 4
    assert held.needs_followup is True

    upcoming = app("Interview", interview_date=NOW + timedelta(days=2))
    assert upcoming.interview_held is False
    assert upcoming.no_news_days is None

    after_rejection = app("Rejected", interview_date=NOW - timedelta(days=4))
    assert after_rejection.interview_held is False


def test_a_later_email_resets_no_news_and_snooze_hides_the_prompt():
    held = app("Interview", interview_date=NOW - timedelta(days=6), history=[event(1, "Interview")])
    assert held.no_news_days == 1
    snoozed = app(
        "Interview", interview_date=NOW - timedelta(days=6),
        raw_metadata={"followup_snoozed_until": (NOW + timedelta(days=3)).isoformat()},
    )
    assert snoozed.interview_held is True
    assert snoozed.needs_followup is False


@pytest.mark.parametrize("status, history, edits, interview, step", [
    ("Applied", [], [], None, 1),
    ("Assessment", [], [], None, 2),
    ("Offer", [], [], None, 4),
    ("Rejected", [event(9, "Applied"), event(2, "Rejected")], [], None, 1),
    ("Rejected", [event(9, "Applied"), event(5, "Assessment"), event(2, "Rejected")], [], None, 2),
    ("Rejected", [event(9, "Applied")], [], NOW - timedelta(days=4), 3),
    ("Rejected", [], [{"field": "status", "from": "Interview", "to": "Rejected", "date": NOW.isoformat()}], None, 3),
])
def test_progress_step(status, history, edits, interview, step):
    assert app(status, history=history, edits=edits, interview_date=interview).progress_step == step


def test_today_overview():
    soon = app("Interview", company="Northwind", interview_date=NOW + timedelta(days=1))
    later = app("Interview", company="Fieldnote", interview_date=NOW + timedelta(days=5))
    held = app("Interview", company="Brightwave", interview_date=NOW - timedelta(days=3))
    waiting = app(company="Pracuj", action_needed=True)
    stale = [
        app(company=f"Old {d}", applied_date=NOW - timedelta(days=d), raw_metadata={"history": []})
        for d in (15, 40, 20, 30, 50, 25)
    ]
    review = app("Needs Review", company="Tidewater", interview_date=NOW + timedelta(hours=3))
    today = build_today([later, soon, held, waiting, review, *stale], NOW)

    assert [i.company for i in today.coming_up] == ["Northwind", "Fieldnote"]
    reasons = [(i.reason, i.company) for i in today.attention]
    assert reasons[:2] == [("interview_held", "Brightwave"), ("action_needed", "Pracuj")]
    assert [c for r, c in reasons if r == "no_reply"] == ["Old 50", "Old 40", "Old 30", "Old 25", "Old 20"]
    assert today.attention[0].days == 3


def test_this_week_numbers():
    start = week_start(NOW)
    inside = start + timedelta(hours=1)
    before = start - timedelta(days=2)
    apps = [
        app(applied_date=inside, raw_metadata={"history": [
            {"date": inside.isoformat(), "status": "Applied"},
            {"date": inside.isoformat(), "status": "Rejected"},
        ]}),
        app("Interview", applied_date=before, interview_date=inside, raw_metadata={"history": [
            {"date": before.isoformat(), "status": "Assessment"},
        ]}),
    ]
    week = build_today(apps, inside + timedelta(minutes=1)).this_week
    assert (week.applied, week.replies, week.interviews) == (1, 1, 1)


async def _interview_app(db: AsyncSession, user: User) -> Application:
    obj = Application(
        user_id=user.id, company="Northwind", role="Data Engineer", status="Interview",
        applied_date=NOW - timedelta(days=20), interview_date=NOW - timedelta(days=2), source="gmail",
        raw_metadata={"history": [event(10, "Interview")]},
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@pytest.mark.asyncio
async def test_interview_outcomes(db: AsyncSession, mock_user: User):
    obj = await _interview_app(db, mock_user)
    async with make_client(mock_user, db) as client:
        today = (await client.get("/applications/today")).json()
        assert today["attention"][0]["reason"] == "interview_held"

        snoozed = (await client.post(f"/applications/{obj.id}/interview-outcome", json={"outcome": "no_answer"})).json()
        assert snoozed["needs_followup"] is False
        assert snoozed["status"] == "Interview"
        assert (await client.get("/applications/today")).json()["attention"] == []

        next_round = (await client.post(f"/applications/{obj.id}/interview-outcome", json={"outcome": "next_round"})).json()
        assert next_round["interview_date"] is None
        assert next_round["interview_held"] is False
        assert next_round["timeline"][-1]["subject"] == "Interview went on to a next round"

        offer = (await client.post(f"/applications/{obj.id}/interview-outcome", json={"outcome": "offer"})).json()
        assert offer["status"] == "Offer"
        assert offer["progress_step"] == 4

        bad = await client.post(f"/applications/{obj.id}/interview-outcome", json={"outcome": "ghosted"})
        assert bad.status_code == 422
        missing = await client.post(f"/applications/{uuid.uuid4()}/interview-outcome", json={"outcome": "offer"})
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_rejected_outcome_is_a_manual_status_change(db: AsyncSession, mock_user: User):
    obj = await _interview_app(db, mock_user)
    async with make_client(mock_user, db) as client:
        body = (await client.post(f"/applications/{obj.id}/interview-outcome", json={"outcome": "rejected"})).json()
    assert body["status"] == "Rejected"
    assert body["manually_modified"] is True
    assert body["progress_step"] == 3
    assert body["timeline"][-1]["change"] == "Interview to Rejected"
