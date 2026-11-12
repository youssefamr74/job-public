"""Needs review: reading an email on demand, "Not a job email" and "It's a recruiter reaching out"."""

import logging
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from applications.models import Application, IgnoredEmail
from applications.sync_service import sync_applications
from auth.models import User
from classifier.text import readable_text
from mail import retry
from mail.parsing import parse_rfc822
from opportunities.models import Opportunity
from tests.conftest import make_client
from tests.fakes import FakeGmailApi, FakeIMAPClient, FakeImapMessage, api_message, raw_email
from tests.test_mail_routes import fake_google, fake_imap
from tests.test_sync_runs import Harness, fetched

BODY = "Hi Jordan,\n\nThank you for the time you spent with us.\n\nBest regards,\nTidewater Recruiting"


@pytest.fixture(autouse=True)
def no_retry_delays():
    with patch.object(retry, "sleep", new=AsyncMock()):
        yield


def review_app(user: User, message_ids=("m1",), thread_id="t1", **fields) -> Application:
    history = [{"message_id": m, "date": "2026-11-09T13:15:00+00:00", "status": "Needs Review",
                "subject": "Thank you for taking part in our process"} for m in message_ids]
    return Application(
        user_id=user.id, company=fields.get("company", "Tidewater"), role=fields.get("role", "Master Data Intern"),
        status="Needs Review", source="gmail", email_thread_id=thread_id,
        raw_metadata={"subject": "Thank you for taking part in our process",
                      "sender": "Tidewater Recruiting <careers@tidewater.example>", "history": history},
    )


# Readable text

def test_readable_text_keeps_paragraphs_and_drops_markup():
    html = ("<html><head><style>p{}</style></head><body><p>Hi Jordan,</p><p>We&#39;d like to talk.</p>"
            "<div>Track: aB3dE5fG7hJ9kL1mN3pQ5rS7tU9vW</div></body></html>")
    text = readable_text(html)
    assert text == "Hi Jordan,\nWe'd like to talk.\nTrack:"


def test_readable_text_collapses_blank_runs_but_not_paragraphs():
    assert readable_text("One  line\n\n\n\n\nTwo​ lines   \n") == "One line\n\nTwo lines"


def test_readable_parse_is_not_cut_short():
    long_body = "word " * 2000
    raw = raw_email("Subject", long_body)
    assert len(parse_rfc822(raw, "a1", None).body) == 3000
    assert len(parse_rfc822(raw, "a1", None, readable=True).body) > 9000


# GET /mail/messages/{id}

@pytest.mark.asyncio
async def test_read_message_from_gmail_api(db: AsyncSession, mock_user_with_gmail: User, caplog):
    fake = FakeGmailApi(messages=[api_message(
        "18c2a", "t1", raw_email("Thank you for taking part in our process", BODY,
                                 sender="Tidewater Recruiting <careers@tidewater.example>",
                                 date="Sun, 09 Nov 2026 13:15:00 +0000"),
    )], access_token="fake_access_token")
    caplog.set_level(logging.DEBUG)
    with fake_google(fake):
        async with make_client(mock_user_with_gmail, db) as client:
            response = await client.get("/mail/messages/18c2a")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["subject"] == "Thank you for taking part in our process"
    assert data["sender"] == "Tidewater Recruiting <careers@tidewater.example>"
    assert data["date"].startswith("2026-11-09T13:15:00")
    assert data["body"] == BODY
    assert "time you spent" not in caplog.text


@pytest.mark.asyncio
async def test_read_message_over_imap(db: AsyncSession, mock_user: User):
    fake = FakeIMAPClient([FakeImapMessage(1, 0x18C2A, 0x77, raw_email("Hello", BODY))])
    async with make_client(mock_user, db) as client:
        with fake_imap(fake):
            await client.post("/mail/imap", json={"email": "me@gmail.com", "app_password": "abcd abcd abcd abcd"})
            response = await client.get("/mail/messages/18c2a")
    assert response.status_code == 200
    assert response.json()["body"] == BODY


@pytest.mark.asyncio
async def test_read_message_errors(db: AsyncSession, mock_user: User, mock_user_with_gmail: User):
    async with make_client(mock_user, db) as client:
        assert (await client.get("/mail/messages/abc")).json()["detail"]["code"] == "not_connected"
        assert (await client.get("/mail/messages/not-an-id")).status_code == 422
    with fake_google(FakeGmailApi(access_token="fake_access_token")):
        async with make_client(mock_user_with_gmail, db) as client:
            response = await client.get("/mail/messages/abc")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "message_gone"


# Not a job email

@pytest.mark.asyncio
async def test_not_a_job_email_removes_it_and_a_sync_never_adds_it_back(db: AsyncSession, mock_user: User):
    app = review_app(mock_user, message_ids=("e0", "e9"), thread_id="t0")
    db.add(app)
    await db.commit()

    async with make_client(mock_user, db) as client:
        response = await client.post(f"/applications/{app.id}/not-job")
        assert response.status_code == 204
        assert (await client.post(f"/applications/{app.id}/not-job")).status_code == 404

    ignored = (await db.execute(select(IgnoredEmail.message_id, IgnoredEmail.thread_id))).all()
    assert sorted(ignored) == [("e0", "t0"), ("e9", "t0")]

    # e0 is the same message; e1 shares nothing with it and is saved as usual.
    result = fetched(2)
    with Harness(fetch_result=result):
        outcome = await sync_applications(mock_user, db)
    assert outcome["stats"]["ignored_by_you"] == 1
    companies = (await db.execute(select(Application.company))).scalars().all()
    assert companies == ["Northwind Labs"]


@pytest.mark.asyncio
async def test_a_later_email_in_an_ignored_thread_is_skipped(db: AsyncSession, mock_user: User):
    app = review_app(mock_user, message_ids=("old",), thread_id="t0")
    db.add(app)
    await db.commit()
    async with make_client(mock_user, db) as client:
        await client.post(f"/applications/{app.id}/not-job")

    with Harness(fetch_result=fetched(1)):
        outcome = await sync_applications(mock_user, db)
    assert outcome["stats"]["ignored_by_you"] == 1
    assert (await db.execute(select(Application))).first() is None


# It's a recruiter reaching out

@pytest.mark.asyncio
async def test_recruiter_outreach_moves_to_opportunities(db: AsyncSession, mock_user: User):
    app = review_app(mock_user, message_ids=("a1", "b2"), company="Unknown")
    db.add(app)
    await db.commit()

    async with make_client(mock_user, db) as client:
        response = await client.post(f"/applications/{app.id}/to-opportunity")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "open" and data["message_id"] == "b2" and data["thread_id"] == "t1"
        assert data["company"] is None and data["role"] == "Master Data Intern"
        assert data["sender"] == "Tidewater Recruiting <careers@tidewater.example>"
        assert data["date"].startswith("2026-11-09T13:15:00")
        listed = (await client.get("/opportunities/", params={"status": "open"})).json()

    assert [o["id"] for o in listed] == [data["id"]]
    assert (await db.execute(select(Application))).first() is None


@pytest.mark.asyncio
async def test_outreach_without_a_message_id_cannot_be_opened(db: AsyncSession, mock_user: User):
    app = review_app(mock_user, message_ids=(), thread_id=None)
    db.add(app)
    await db.commit()
    async with make_client(mock_user, db) as client:
        data = (await client.post(f"/applications/{app.id}/to-opportunity")).json()
    assert data["message_id"] is None
    stored = (await db.execute(select(Opportunity))).scalar_one()
    assert stored.message_id == f"application:{app.id}"
