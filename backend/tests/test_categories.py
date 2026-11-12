"""Generic email categories: calendar invites, account mail, surveys, outreach, marketing, Pracuj.pl statuses."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from applications.models import Application
from applications.sync_service import sync_applications
from auth.models import User
from classifier.ats_intelligence import _template_cache, classify_email_deterministic
from classifier.categories import parse_invite_date
from classifier.heuristics import filter_reason
from diagnostics.models import DroppedEmail
from mail.fetch import FetchResult
from opportunities.models import Opportunity
from tests.conftest import create_test_application, make_client

DATE = "Mon, 15 Jan 2024 10:00:00 +0000"


@pytest.fixture(autouse=True)
def clear_template_cache():
    _template_cache.clear()
    yield
    _template_cache.clear()


async def _sync(db, user, emails):
    connection = MagicMock()
    connection.source.close = AsyncMock()
    connection.cursor = None
    patches = [
        patch("applications.sync_service.open_mail_source", new=AsyncMock(return_value=connection)),
        patch("applications.sync_service.fetch_new_emails",
              new=AsyncMock(return_value=FetchResult(emails=emails, cursor={"n": 1}, failed=0))),
        patch("applications.sync_service._save_cursor", new=AsyncMock()),
    ]
    for p in patches:
        p.start()
    try:
        return await sync_applications(user, db)
    finally:
        for p in reversed(patches):
            p.stop()


def mail(id, sender, subject, body="", thread=None):
    return {"id": id, "thread_id": thread or f"t-{id}", "date": DATE, "sender": sender, "subject": subject, "body": body}


async def apps(db) -> list[Application]:
    return list((await db.execute(select(Application))).scalars().all())


# --- filters: marketing and surveys ------------------------------------------------------------------

@pytest.mark.parametrize("sender,subject,expected", [
    ("FlexJobs <notify@mg.flexjobs.com>", "Your Dream Job Might Be Just a Click Away", "job_alert"),
    ("Careers Weekly <hello@careers.example>", "Explore 30 new roles that match you", "job_alert"),
    ("Jobs Board <hello@board.example>", "You'd be a top applicant - Data Engineer", "job_alert"),
    ("Brightwave Careers <jobs@brightwave.example>", "Hi, please share your experience with us!", "survey"),
    ("Brightwave Careers <jobs@brightwave.example>", "Feedback survey about your application", "survey"),
    ("Brightwave Careers <jobs@brightwave.example>", "Interview feedback - share your opinion", "survey"),
    ("Brightwave Careers <jobs@brightwave.example>", "Update on your application", None),
])
def test_marketing_and_surveys_are_filtered(sender, subject, expected):
    decision = filter_reason(sender, subject, "Thank you for your application.")
    assert (decision[0] if decision else None) == expected


# --- calendar dates ----------------------------------------------------------------------------------

@pytest.mark.parametrize("subject,expected", [
    ("Invitation: Interview @ Fri 9 Oct 2026 5:30pm - 5:45pm (GMT+3) (me@example.com)", (2026, 10, 9, 14, 30)),
    ("Updated invitation: Intro call @ Mon Oct 12, 2026 10am - 10:30am (CET)", (2026, 10, 12, 9, 0)),
    ("Invitation: Chat - Thu Nov 5, 2026 14:00 - 14:30 (UTC)", (2026, 11, 5, 14, 0)),
    ("Accepted: Interview @ Tue 3 Nov 2026 12pm (GMT-5)", (2026, 11, 3, 17, 0)),
])
def test_invite_dates(subject, expected):
    assert parse_invite_date(subject) == datetime(*expected, tzinfo=timezone.utc)


def test_invite_date_from_ics_body():
    assert parse_invite_date("Invitation", "BEGIN:VCALENDAR\nDTSTART:20261009T143000Z\nEND:VCALENDAR") == \
        datetime(2026, 10, 9, 14, 30, tzinfo=timezone.utc)
    assert parse_invite_date("Invitation: Interview", "no date here") is None


# --- Pracuj.pl ---------------------------------------------------------------------------------------

PRACUJ = '"Pracuj.pl - Status aplikacji" <noreply@aplikacje.pracuj.pl>'
PRACUJ_BODY = "Junior Backend Engineer Brightwave Sp. z o.o. Warszawa, mazowieckie Zarządzaj aplikacjami"


def test_pracuj_process_ended_is_a_rejection():
    result = classify_email_deterministic(PRACUJ, "Junior Backend Engineer: pracodawca zakończył rekrutację.", PRACUJ_BODY)
    assert result["status"] == "Rejected"
    assert result["status_confidence"] >= 0.65
    assert not result["action_needed"]


def test_pracuj_waiting_for_information_flags_action_needed_without_a_status():
    result = classify_email_deterministic(
        PRACUJ, "Junior Backend Engineer: pracodawca czeka na dodatkowe informacje od Ciebie.", PRACUJ_BODY)
    assert result["action_needed"] is True
    assert result["status_confidence"] < 0.65


@pytest.mark.asyncio
async def test_action_needed_keeps_the_status_and_is_exposed(db: AsyncSession, mock_user: User, ai_off):
    app = await create_test_application(db, mock_user, "Brightwave", "Junior Backend Engineer", "Interview")
    await _sync(db, mock_user, [mail(
        "p1", PRACUJ, "Junior Backend Engineer: pracodawca czeka na dodatkowe informacje od Ciebie.", PRACUJ_BODY)])
    await db.refresh(app)
    assert app.status == "Interview"
    assert app.action_needed is True
    async with make_client(mock_user, db) as client:
        body = (await client.get(f"/applications/{app.id}")).json()
        assert body["action_needed"] is True
        assert (await client.patch(f"/applications/{app.id}", json={"action_needed": False})).status_code == 200
        assert (await client.get(f"/applications/{app.id}")).json()["action_needed"] is False


@pytest.mark.asyncio
async def test_pracuj_process_ended_rejects_the_application(db: AsyncSession, mock_user: User, ai_off):
    app = await create_test_application(db, mock_user, "Brightwave", "Junior Backend Engineer", "Applied")
    await _sync(db, mock_user, [mail(
        "p2", PRACUJ, "Junior Backend Engineer: pracodawca zakończył rekrutację.", PRACUJ_BODY)])
    await db.refresh(app)
    assert app.status == "Rejected"


# --- calendar invites and interviews ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_calendar_invite_from_a_tracked_company_is_an_interview(db: AsyncSession, mock_user: User, ai_off):
    app = await create_test_application(db, mock_user, "Brightwave", "Data Analyst", "Applied")
    await _sync(db, mock_user, [mail(
        "c1", "Jordan Lee <jordan@brightwave.example>",
        "Invitation: Intro call @ Fri 9 Oct 2026 5:30pm - 6:00pm (GMT+3) (me@example.com)", "Join with Google Meet")])
    await db.refresh(app)
    assert app.status == "Interview"
    assert app.interview_date.replace(tzinfo=timezone.utc) == datetime(2026, 10, 9, 14, 30, tzinfo=timezone.utc)
    assert len(await apps(db)) == 1


@pytest.mark.asyncio
async def test_calendar_invite_from_a_recruiter_creates_an_interview(db: AsyncSession, mock_user: User, ai_off):
    await _sync(db, mock_user, [mail(
        "c2", "Sam Rivera <sam@talentpartners.example>",
        "Updated invitation: Interview with Sam @ Mon Oct 12, 2026 10am - 10:30am (CET)",
        "Talent Partners recruiting team invites you. invite.ics")])
    [created] = await apps(db)
    assert created.status == "Interview"
    assert created.interview_date is not None


@pytest.mark.asyncio
async def test_calendar_invite_from_an_unknown_non_recruiter_is_not_an_interview(db: AsyncSession, mock_user: User, ai_off):
    await _sync(db, mock_user, [mail(
        "c3", "Pat <pat@friends.example>", "Invitation: Board games night @ Sat 10 Oct 2026 7pm - 10pm (CET)",
        "Bring snacks.")])
    assert await apps(db) == []


@pytest.mark.asyncio
async def test_interview_in_the_subject_from_a_tracked_company(db: AsyncSession, mock_user: User, ai_off):
    app = await create_test_application(db, mock_user, "Northwind Labs", "Data Analyst", "Applied")
    await _sync(db, mock_user, [mail(
        "i1", "Northwind Labs Careers <jobs@northwindlabs.example>", "Interview next week", "See you soon.")])
    await db.refresh(app)
    assert app.status == "Interview"


@pytest.mark.asyncio
async def test_a_rejected_application_stays_rejected_after_an_invite(db: AsyncSession, mock_user: User, ai_off):
    app = await create_test_application(db, mock_user, "Brightwave", "Data Analyst", "Rejected")
    await _sync(db, mock_user, [mail(
        "c4", "Jordan <jordan@brightwave.example>", "Invitation: Chat @ Fri 9 Oct 2026 5pm - 5:30pm (GMT+3)", "")])
    await db.refresh(app)
    assert app.status == "Rejected"


# --- account and admin mail ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_account_mail_is_attached_to_the_tracked_application(db: AsyncSession, mock_user: User, ai_off):
    app = await create_test_application(db, mock_user, "Brightwave", "Data Analyst", "Applied")
    result = await _sync(db, mock_user, [mail(
        "a1", "Brightwave Careers <jobs@brightwave.example>", "Verify your candidate account",
        "Click to verify your account for the Data Analyst role.")])
    await db.refresh(app)
    assert app.status == "Applied"
    assert [e["message_id"] for e in app.raw_metadata["history"]] == ["a1"]
    assert result["stats"]["account_attached"] == 1
    assert len(await apps(db)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("subject", [
    "You have created an account on Fabrikam's Career Site",
    "Privacy and Compliance Notification",
    "Can we keep your information? (data retention)",
    "Your one-time password",
])
async def test_account_mail_without_a_tracked_application_is_filtered(db: AsyncSession, mock_user: User, ai_off, subject):
    result = await _sync(db, mock_user, [mail("a2", "Fabrikam Talent <talent@fabrikam.example>", subject, "Welcome.")])
    assert await apps(db) == []
    assert result["stats"]["account_filtered"] == 1
    dropped = (await db.execute(select(DroppedEmail))).scalars().all()
    assert [d.reason for d in dropped] == ["account"]


@pytest.mark.asyncio
async def test_a_gdpr_footer_in_a_rejection_is_still_a_rejection(db: AsyncSession, mock_user: User, ai_off):
    app = await create_test_application(db, mock_user, "Brightwave", "Data Analyst", "Applied")
    await _sync(db, mock_user, [mail(
        "a3", "Brightwave Careers <jobs@brightwave.example>", "Update on your application",
        "Unfortunately we will not be moving forward with your application. Your data is kept under GDPR.")])
    await db.refresh(app)
    assert app.status == "Rejected"


@pytest.mark.asyncio
async def test_survey_is_filtered_with_its_own_reason(db: AsyncSession, mock_user: User, ai_off):
    app = await create_test_application(db, mock_user, "Brightwave", "Data Analyst", "Applied")
    result = await _sync(db, mock_user, [mail(
        "s1", "Brightwave Careers <jobs@brightwave.example>", "Please share your experience with us", "Take our survey.")])
    await db.refresh(app)
    assert app.status == "Applied"
    assert result["stats"]["surveys"] == 1
    assert [d.reason for d in (await db.execute(select(DroppedEmail))).scalars().all()] == ["survey"]


# --- recruiter outreach and opportunities -------------------------------------------------------------

OUTREACH = ("Riley Chen <inmail-hit-reply@linkedin.com>", "Exciting opportunity at Contoso",
            "Hi Jordan, we are hiring a Data Engineer at Contoso. Interested?")


@pytest.mark.asyncio
async def test_outreach_becomes_an_opportunity_not_an_application(db: AsyncSession, mock_user: User, ai_off):
    result = await _sync(db, mock_user, [mail("o1", *OUTREACH, thread="th-1")])
    assert await apps(db) == []
    assert result["stats"]["opportunities"] == 1
    async with make_client(mock_user, db) as client:
        listed = (await client.get("/opportunities/")).json()
    assert len(listed) == 1
    assert listed[0]["subject"] == OUTREACH[1]
    assert listed[0]["sender"] == OUTREACH[0]
    assert listed[0]["thread_id"] == "th-1"
    assert listed[0]["status"] == "open"
    assert {"company", "role", "date"} <= set(listed[0])


@pytest.mark.asyncio
@pytest.mark.parametrize("subject", [
    "Python Contract Opportunity | Remote", "New job opportunity for you", "Invitation to apply to Fabrikam",
    "Taylor has referred you to a new role at Fabrikam",
])
async def test_outreach_phrases(db: AsyncSession, mock_user: User, ai_off, subject):
    await _sync(db, mock_user, [mail("o2", "Recruiter <r@agency.example>", subject, "Hello!")])
    assert await apps(db) == []
    assert len((await db.execute(select(Opportunity))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_convert_endpoint_turns_an_opportunity_into_an_application(db: AsyncSession, mock_user: User, ai_off):
    await _sync(db, mock_user, [mail("o3", *OUTREACH, thread="th-3")])
    async with make_client(mock_user, db) as client:
        [opportunity] = (await client.get("/opportunities/")).json()
        response = await client.post(f"/opportunities/{opportunity['id']}/convert")
        assert response.status_code == 200
        assert response.json()["status"] == "Applied"
        assert (await client.post(f"/opportunities/{opportunity['id']}/convert")).status_code == 409
        assert (await client.get("/opportunities/", params={"status": "converted"})).json()[0]["application_id"] == \
            response.json()["id"]
    [created] = await apps(db)
    assert created.email_thread_id == "th-3"


@pytest.mark.asyncio
async def test_a_later_email_showing_i_applied_converts_the_opportunity(db: AsyncSession, mock_user: User, ai_off):
    await _sync(db, mock_user, [mail("o4", *OUTREACH, thread="th-4")])
    assert await apps(db) == []
    await _sync(db, mock_user, [mail(
        "o5", "Contoso Careers <jobs@contoso.example>", "Thank you for applying",
        "We received your application for the Data Engineer position.", thread="th-4")])
    [created] = await apps(db)
    assert (created.company, created.status) == ("Contoso", "Applied")
    [opportunity] = (await db.execute(select(Opportunity))).scalars().all()
    await db.refresh(opportunity)
    assert opportunity.status == "converted"
    assert opportunity.application_id == created.id


@pytest.mark.asyncio
async def test_a_follow_up_without_an_application_does_not_convert(db: AsyncSession, mock_user: User, ai_off):
    await _sync(db, mock_user, [mail("o6", *OUTREACH, thread="th-6")])
    await _sync(db, mock_user, [mail(
        "o7", "Riley Chen <hit-reply@linkedin.com>", "Message replied: Exciting opportunity at Contoso",
        "Just checking in!", thread="th-6")])
    assert await apps(db) == []
    [opportunity] = (await db.execute(select(Opportunity))).scalars().all()
    assert opportunity.status == "open"


@pytest.mark.asyncio
async def test_outreach_in_a_tracked_application_thread_stays_in_the_application(db: AsyncSession, mock_user: User, ai_off):
    app = await create_test_application(db, mock_user, "Contoso", "Data Engineer", "Applied")
    app.email_thread_id = "th-8"
    await db.commit()
    await _sync(db, mock_user, [mail("o8", *OUTREACH, thread="th-8")])
    assert (await db.execute(select(Opportunity))).scalars().all() == []
