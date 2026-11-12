"""Rule-based classifier quality, on synthetic emails only (see tests/classifier_corpus.py)."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from applications.models import Application
from applications.reclassify import reclassify_applications
from applications.service import stored_status
from applications.sync_service import _find_existing, sync_applications
from auth.models import User
from classifier.ats_intelligence import _template_cache, classify_status
from classifier.batch_service import classify_emails_batch
from classifier.normalization import make_fingerprint
from classifier.text import clean_text
from mail.fetch import FetchResult
from tests.classifier_corpus import CASES
from tests.conftest import make_client


@pytest.fixture(autouse=True)
def clear_template_cache():
    _template_cache.clear()
    yield
    _template_cache.clear()


async def _as_stored(case: dict) -> dict:
    """What the sync would store for this email without AI."""
    existing = {}
    if case.get("thread"):
        context = MagicMock()
        context.company, context.role = case["thread"]["company"], case["thread"]["role"]
        context.status, context.raw_metadata = "Applied", {"history": []}
        existing = {"t1": context}
    email = {"id": "e1", "thread_id": "t1", "sender": case["sender"], "subject": case["subject"], "body": case["body"]}
    result = (await classify_emails_batch([email], existing))["e1"]
    assert result is not None, "dropped as not job-related"
    confidence = result.get("status_confidence", result["confidence"])
    return {"status": stored_status(result["status"], confidence), "company": result["company"], "role": result["role"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
async def test_corpus_case(case, ai_off):
    stored = await _as_stored(case)
    for field, expected in case["expect"].items():
        assert stored[field] == expected, f"{field}: {stored}"


def test_assessment_has_good_confidence():
    result = classify_status("Invitation to the online assessment", "")
    assert result.status == "Assessment" and result.confidence >= 0.8


def test_unclear_reply_is_needs_review():
    result = classify_status("Re: next steps", "Could you share your notice period and salary expectations?")
    assert result.status is None


# Merging

def _workable_rejection(email_id: str, company: str, role: str) -> dict:
    return {
        "id": email_id, "thread_id": f"thread-{email_id}",
        "sender": "Workable <noreply@candidates.workablemail.com>",
        "subject": f"Update on your application to {company}",
        "body": (f"Hi Jordan, thank you for your application for the role of {role}. "
                 "Unfortunately, we have decided to move forward with other candidates."),
        "date": "Mon, 15 Jan 2024 10:00:00 +0000",
    }


@pytest.mark.asyncio
async def test_three_companies_through_one_ats_stay_separate(db: AsyncSession, mock_user: User, ai_off):
    emails = [
        _workable_rejection("m1", "Brightwave", "Data Analyst"),
        _workable_rejection("m2", "Northwind Labs", "Data Engineer"),
        _workable_rejection("m3", "Lumen Analytics", "Backend Developer"),
    ]
    connection = MagicMock()
    connection.source.close = AsyncMock()
    connection.cursor = None
    with patch("applications.sync_service.open_mail_source", new=AsyncMock(return_value=connection)), \
         patch("applications.sync_service.fetch_new_emails",
               new=AsyncMock(return_value=FetchResult(emails=emails, cursor=None, failed=0))), \
         patch("applications.sync_service.mark_sync_ok", new=AsyncMock()):
        result = await sync_applications(mock_user, db)

    apps = (await db.execute(select(Application).where(Application.user_id == mock_user.id))).scalars().all()
    assert result["error"] is False
    assert sorted(a.company for a in apps) == ["Brightwave", "Lumen Analytics", "Northwind Labs"]
    assert {a.status for a in apps} == {"Rejected"}
    assert all("<" not in a.raw_metadata["snippet"] for a in apps)


def test_platform_or_unknown_company_never_matches_by_company():
    stats = {k: 0 for k in ("matched_by_thread", "matched_by_job_id", "matched_by_fingerprint", "matched_by_company")}
    platform_app = MagicMock(status="Applied", applied_date=datetime.now(timezone.utc))
    for company in ("Workable", "Unknown"):
        found = _find_existing(
            thread_id=None, job_id=None, fingerprint=None, company=company, role="Data Analyst",
            effective_status="Rejected", existing_by_thread={}, existing_by_job_id={},
            existing_by_fingerprint={}, existing_by_company={company.lower(): [platform_app]}, stats=stats,
        )
        assert found is None
    assert make_fingerprint("Workable", "Data Analyst") is None


# Cleanup

def test_clean_text_drops_template_markup_and_tracking_noise():
    raw = ("96 ​‌ <mj-text>Thank you&nbsp;for applying to Ernst &amp; Young</mj-text> "
           "ref aB3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY trackingend https://example.com/x?id=1")
    assert clean_text(raw) == "Thank you for applying to Ernst & Young ref trackingend https://example.com/x?id=1"


# Re-classify

def _stored_app(user: User, **fields) -> Application:
    defaults = dict(
        id=uuid.uuid4(), user_id=user.id, source="gmail", applied_date=datetime(2024, 1, 15, 12, tzinfo=timezone.utc),
        raw_metadata={
            "subject": "Thank you for applying",
            "sender": "Workable <noreply@candidates.workablemail.com>",
            "snippet": "<p>Thank you for your interest in Brightwave. If you are not selected, we will let you know.</p>",
            "history": [{"status": "Rejected", "subject": "Thank you for applying", "date": "2024-01-15T12:00:00+00:00"}],
        },
    )
    defaults.update(fields)
    return Application(**defaults)


@pytest.mark.asyncio
async def test_reclassify_dry_run_reports_without_saving(db: AsyncSession, mock_user: User):
    db.add(_stored_app(mock_user, company="Workable", role="Unknown", status="Rejected"))
    await db.commit()

    report = await reclassify_applications(db, mock_user, apply=False)
    app = (await db.execute(select(Application))).scalar_one()

    assert report["checked"] == 1 and report["changed"] == 1
    assert report["changes"][0]["after"] == {"company": "Brightwave", "role": "Unknown", "status": "Applied"}
    assert report["status_before"] == {"Rejected": 1} and report["status_after"] == {"Applied": 1}
    assert (app.company, app.status) == ("Workable", "Rejected")


@pytest.mark.asyncio
async def test_reclassify_apply_fixes_and_respects_manual_edits(db: AsyncSession, mock_user: User):
    db.add(_stored_app(mock_user, company="Workable", role="Unknown", status="Rejected"))
    db.add(_stored_app(mock_user, company="Workable", role="Unknown", status="Rejected", manually_modified=True))
    await db.commit()

    async with make_client(mock_user, db) as client:
        report = (await client.post("/applications/reclassify", params={"apply": "true"})).json()

    apps = {a.manually_modified: a for a in (await db.execute(select(Application))).scalars().all()}
    assert report["skipped_manual"] == 1 and report["changed"] == 1
    assert (apps[False].company, apps[False].status) == ("Brightwave", "Applied")
    assert "<p>" not in apps[False].raw_metadata["snippet"]
    assert apps[False].raw_metadata["history"][0]["status"] == "Applied"
    assert (apps[True].company, apps[True].status) == ("Workable", "Rejected")


@pytest.mark.asyncio
async def test_reclassify_keeps_status_when_stored_text_is_not_enough(db: AsyncSession, mock_user: User):
    db.add(_stored_app(
        mock_user, company="Northwind Labs", role="Data Engineer", status="Interview",
        raw_metadata={"subject": "Next steps", "sender": "Northwind Labs <jobs@northwind.example>",
                      "snippet": "Hi Jordan, see the details below.",
                      "history": [{"status": "Applied", "subject": "Application received"},
                                  {"status": "Interview", "subject": "Next steps"}]},
    ))
    await db.commit()

    report = await reclassify_applications(db, mock_user, apply=True)
    app = (await db.execute(select(Application))).scalar_one()
    assert report["changed"] == 0
    assert (app.company, app.role, app.status) == ("Northwind Labs", "Data Engineer", "Interview")


def test_a_story_about_an_offer_is_not_an_offer():
    result = classify_status("Hi all!", "So I got an offer from company A with a deadline to accept. Should I take it?")
    assert result.status != "Offer"
