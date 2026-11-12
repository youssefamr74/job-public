"""Notifications: which events create one, no duplicates, cleanup after 90 days, and the endpoints."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from applications.models import Application
from applications.schemas import ApplicationResponse
from auth.models import User
from mail.models import STATUS_NEEDS_RELINK
from notifications.models import Notification
from notifications.service import (
    interview_notifications,
    no_reply_notification,
    run_checks,
    status_notifications,
    weekly_notification,
)
from tests.conftest import make_client

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)  # a Wednesday


def response(days_ago=3, status="Applied", history=(), **extra) -> ApplicationResponse:
    return ApplicationResponse(
        id="00000000-0000-0000-0000-00000000000a", company=extra.pop("company", "Contoso"),
        role=extra.pop("role", "Data Engineer"), status=status, applied_date=NOW - timedelta(days=days_ago),
        source="gmail", notes=None, raw_metadata={"history": list(history)}, **extra,
    )


def event(days_ago: float, status: str) -> dict:
    return {"date": (NOW - timedelta(days=days_ago)).isoformat(), "status": status}


def test_recent_status_emails_notify_once_per_status():
    app = response(status="Rejected", history=[event(9, "Applied"), event(2, "Interview"), event(1, "Rejected"),
                                               event(0.5, "Rejected")])
    found = status_notifications([app], NOW)
    assert [(n["kind"], n["title"]) for n in found] == [
        ("interview", "Interview invite from Contoso"), ("rejection", "Rejection from Contoso")]
    assert found[0]["link"] == f"/applications?id={app.id}"


def test_old_status_emails_and_own_edits_do_not_notify():
    old = response(status="Rejected", history=[event(30, "Rejected")])
    edited = response(status="Offer", history=[event(20, "Applied")])
    assert status_notifications([old, edited], NOW) == []


def test_interview_tomorrow_and_held_interview_without_news():
    tomorrow = response(status="Interview", interview_date=NOW + timedelta(days=1))
    held = response(status="Interview", company="Fabrikam", interview_date=NOW - timedelta(days=4))
    found = interview_notifications([tomorrow, held], NOW)
    kinds = {n["kind"]: n for n in found}
    assert kinds["interview_tomorrow"]["title"].startswith("Interview with Contoso tomorrow")
    assert kinds["no_news"]["title"] == "No news after your Fabrikam interview"


def test_no_reply_is_one_summary():
    waiting = [response(days_ago=20 + i, history=[event(20 + i, "Applied")]) for i in range(3)]
    [summary] = no_reply_notification(waiting, NOW)
    assert summary["title"] == "3 applications have had no reply for 14 days or more"
    assert summary["key"] == "no_reply:2026-11-09"
    assert no_reply_notification([response(days_ago=2)], NOW) == []


def test_weekly_summary_covers_last_week():
    apps = [
        response(days_ago=5, history=[event(5, "Applied"), event(4, "Interview")]),
        response(days_ago=6, status="Rejected", history=[event(6, "Applied"), event(5, "Rejected")]),
        response(days_ago=1),
    ]
    [summary] = weekly_notification(apps, NOW)
    assert summary["key"] == "weekly:2026-11-02"
    assert summary["title"] == "Last week: 2 applied, 2 replies, 1 interview"


async def add_app(db, user, **fields) -> Application:
    app = Application(user_id=user.id, company="Contoso", role="Data Engineer", source="gmail", **fields)
    db.add(app)
    await db.commit()
    return app


@pytest.mark.asyncio
async def test_run_checks_never_duplicates_and_cleans_up(db: AsyncSession, mock_user: User):
    now = datetime.now(timezone.utc)
    await add_app(db, mock_user, status="Rejected", applied_date=now - timedelta(days=3),
                  raw_metadata={"history": [{"date": (now - timedelta(days=1)).isoformat(), "status": "Rejected"}]})
    first = await run_checks(db, mock_user, now)
    assert first >= 2  # the rejection and the weekly summary
    assert await run_checks(db, mock_user, now) == 0

    old = Notification(user_id=mock_user.id, key="old", kind="weekly_summary", title="Old",
                       created_at=now - timedelta(days=91))
    db.add(old)
    await db.commit()
    await run_checks(db, mock_user, now)
    keys = (await db.execute(select(Notification.key))).scalars().all()
    assert "old" not in keys and len(keys) == first


@pytest.mark.asyncio
async def test_mail_needing_reconnect_notifies_once(db: AsyncSession, mock_user_with_gmail: User):
    from mail.service import get_mail_account

    account = await get_mail_account(db, mock_user_with_gmail)
    account.status = STATUS_NEEDS_RELINK
    account.connected_at = datetime(2026, 11, 1, tzinfo=timezone.utc)
    await db.commit()
    await run_checks(db, mock_user_with_gmail)
    await run_checks(db, mock_user_with_gmail)
    rows = (await db.execute(select(Notification).where(Notification.kind == "mail_reconnect"))).scalars().all()
    assert len(rows) == 1 and rows[0].link == "/settings#mail"


@pytest.mark.asyncio
async def test_endpoints_list_count_and_mark_read(db: AsyncSession, mock_user: User):
    now = datetime.now(timezone.utc)
    for i in range(3):
        db.add(Notification(user_id=mock_user.id, key=f"k{i}", kind="rejection", title=f"N{i}",
                            created_at=now - timedelta(minutes=i)))
    await db.commit()
    async with make_client(mock_user, db) as client:
        assert (await client.get("/notifications/unread-count")).json() == {"unread": 3}
        listed = (await client.get("/notifications/", params={"limit": 2})).json()
        assert [n["title"] for n in listed] == ["N0", "N1"]
        marked = (await client.post(f"/notifications/{listed[0]['id']}/read")).json()
        assert marked["read_at"] is not None
        assert (await client.get("/notifications/unread-count")).json() == {"unread": 2}
        assert len((await client.get("/notifications/", params={"unread": True})).json()) == 2
        assert (await client.post("/notifications/read-all")).json() == {"marked": 2}
        assert (await client.get("/notifications/unread-count")).json() == {"unread": 0}
        missing = await client.post("/notifications/00000000-0000-0000-0000-000000000000/read")
        assert missing.status_code == 404
