"""Person display names, places as companies, one opportunity per thread, enrollment mail, role template text."""

import pytest
from sqlalchemy import select

from applications.models import Application
from classifier.ats_intelligence import classify_status, extract_company
from classifier.normalization import display_role, normalize_company
from opportunities.models import Opportunity
from tests.conftest import create_test_application
from tests.test_categories import OUTREACH, _sync, apps, clear_template_cache, mail  # noqa: F401


@pytest.mark.parametrize("sender,expected", [
    ("Jordan Lee <jordan@acme-it.com>", "Acme IT"),           # first-name list
    ("Priya Nair <priya@globex.example>", "Globex"),          # two capitalised words, no company words
    ("Bending Spoons <talent@bendingspoons.com>", "Bending Spoons"),  # the domain spells the display name
    ("Northwind Labs <jobs@northwindlabs.example>", "Northwind Labs"),
])
def test_company_from_a_persons_display_name_uses_the_domain(sender, expected):
    assert extract_company(sender, "Quick question", "Hello there.")[0] == expected


@pytest.mark.parametrize("name", [
    "Wroclaw", "Wrocław", "Kraków", "Krakow", "Łódź", "Lodz", "Gdańsk", "Warsaw, Poland", "Poznań", "Egypt", "Berlin",
])
def test_a_place_is_never_a_company(name):
    assert normalize_company(name) == "Unknown"


def test_companies_are_not_mistaken_for_places():
    assert normalize_company("Orange") == "Orange"
    assert normalize_company("Warsaw Tech Labs") == "Warsaw Tech Labs"


@pytest.mark.asyncio
async def test_person_name_company_in_a_calendar_invite_and_an_opportunity(db, mock_user, ai_off):
    await _sync(db, mock_user, [
        mail("pc1", "Sam Rivera <sam@acme-it.com>", "Invitation: Interview @ Mon Oct 12, 2026 10am - 10:30am (CET)",
             "Our recruiting team invites you."),
        mail("pc2", "Riley Chen <riley@initech-labs.example>", "Python Developer job opportunity", "Interested?"),
    ])
    [created] = await apps(db)
    assert (created.company, created.status) == ("Acme IT", "Interview")
    [opportunity] = (await db.execute(select(Opportunity))).scalars().all()
    assert opportunity.company == "Initech Labs"


@pytest.mark.asyncio
async def test_one_opportunity_per_thread(db, mock_user, ai_off):
    await _sync(db, mock_user, [mail("t1", *OUTREACH, thread="th-1"),
                                mail("t2", OUTREACH[0], "Re: Exciting opportunity at Contoso", "Still hiring.", thread="th-1")])
    await _sync(db, mock_user, [mail("t3", OUTREACH[0], "Exciting opportunity at Contoso - reminder", "Ping.", thread="th-1"),
                                mail("t4", *OUTREACH, thread="th-2")])
    rows = {o.thread_id: o for o in (await db.execute(select(Opportunity))).scalars().all()}
    assert set(rows) == {"th-1", "th-2"}
    assert rows["th-1"].subject == "Exciting opportunity at Contoso - reminder"
    assert rows["th-1"].company == "Contoso"
    assert await apps(db) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("subject,body,status", [
    ("Interview invitation for Data Engineer", "We would like to invite you to an interview.", "Interview"),
    ("Your coding assessment", "Please complete the coding assessment within 5 days.", "Assessment"),
    ("Thank you for applying", "We received your application for the Data Engineer position.", "Applied"),
])
async def test_an_email_from_the_opportunitys_company_converts_it(db, mock_user, ai_off, subject, body, status):
    await _sync(db, mock_user, [mail("oc1", *OUTREACH, thread="th-out")])
    await _sync(db, mock_user, [mail("oc2", "Contoso Careers <jobs@contoso.example>", subject, body, thread="th-other")])
    [created] = await apps(db)
    assert (created.company, created.status) == ("Contoso", status)
    [opportunity] = (await db.execute(select(Opportunity))).scalars().all()
    assert opportunity.status == "converted" and opportunity.application_id == created.id


@pytest.mark.asyncio
async def test_an_unrelated_company_does_not_convert_the_opportunity(db, mock_user, ai_off):
    await _sync(db, mock_user, [mail("ou1", *OUTREACH, thread="th-out")])
    await _sync(db, mock_user, [mail("ou2", "Fabrikam Careers <jobs@fabrikam.example>", "Thank you for applying",
                                     "We received your application for the Data Engineer position.")])
    [opportunity] = (await db.execute(select(Opportunity))).scalars().all()
    assert opportunity.status == "open"


ENROLLED = ("Congratulations! You are now enrolled in our Data Engineering bootcamp",
            "Congratulations, you have been enrolled in the training program. We will send an invitation to the "
            "kickoff interview session and we are pleased to offer you a place.")


def test_enrollment_is_not_an_interview_or_an_offer():
    result = classify_status(*ENROLLED)
    assert result.status is None and result.keep_status


@pytest.mark.asyncio
async def test_enrollment_does_not_change_a_tracked_application(db, mock_user, ai_off):
    app = await create_test_application(db, mock_user, "Brightwave", "Data Analyst", "Applied")
    await _sync(db, mock_user, [mail("e1", "Brightwave Academy <academy@brightwave.example>", *ENROLLED)])
    await db.refresh(app)
    assert app.status == "Applied"


@pytest.mark.asyncio
async def test_enrollment_from_an_untracked_company_is_needs_review_at_most(db, mock_user, ai_off):
    await _sync(db, mock_user, [mail("e2", "Northwind Academy <academy@northwind.example>", *ENROLLED)])
    assert {a.status for a in await apps(db)} <= {"Needs Review"}


@pytest.mark.parametrize("raw,expected", [
    ("Data Engineer Acme Careers logo", "Data Engineer"),
    ("Acme Careers logo", "Unknown"),
    ("Jordan Lee wants to work at Acme", "Unknown"),
    ("Backend Developer Jordan wants to work with you", "Backend Developer"),
    ("Data Engineer", "Data Engineer"),
])
def test_template_text_is_dropped_from_roles(raw, expected):
    assert display_role(raw) == expected
