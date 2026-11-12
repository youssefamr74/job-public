"""Recall diagnostics: the sync funnel, dropped emails with reasons, and GET /debug/dropped."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from applications.models import Application
from applications.sync_service import sync_applications
from auth.models import User
from classifier.ats_intelligence import _template_cache
from diagnostics import service as diagnostics_service
from diagnostics.models import DroppedEmail
from diagnostics.service import record_dropped
from mail.fetch import FetchResult
from tests.conftest import make_client

DATE = "Mon, 15 Jan 2024 10:00:00 +0000"
EMAILS = {
    "filtered": dict(sender="Shop <orders@shop.example>", subject="Your order has shipped",
                     body="Your parcel is on its way."),
    "not_job": dict(sender="news@shop.example", subject="New position available",
                    body="We have a new position open in our store."),
    "no_company_or_role": dict(sender="someone@gmail.com", subject="About your application",
                               body="Unfortunately the position is closed now."),
    "unknown_company": dict(sender="someone@gmail.com", subject="Thank you for applying",
                            body="We received your application."),
    "maybe_job": dict(sender="Brightwave Careers <jobs@brightwave.example>", subject="Quick update",
                      body="Hi Jordan, the hiring team wanted to share an update about your application "
                           "for the Data Analyst role."),
    "confirmed": dict(sender="Northwind Labs Careers <jobs@northwindlabs.example>", subject="Application received",
                      body="Thank you for applying for the Data Analyst position."),
}


def _email(name: str) -> dict:
    return {"id": name, "thread_id": f"t-{name}", "date": DATE, **EMAILS[name]}


@pytest.fixture(autouse=True)
def clear_template_cache():
    _template_cache.clear()
    yield
    _template_cache.clear()


async def _sync(db, user, emails, classify=None):
    connection = MagicMock()
    connection.source.close = AsyncMock()
    connection.cursor = None
    patches = [
        patch("applications.sync_service.open_mail_source", new=AsyncMock(return_value=connection)),
        patch("applications.sync_service.fetch_new_emails",
              new=AsyncMock(return_value=FetchResult(emails=emails, cursor={"n": 1}, failed=0))),
        patch("applications.sync_service._save_cursor", new=AsyncMock()),
    ]
    if classify is not None:
        patches.append(patch("applications.sync_service.classify_emails_batch", new=AsyncMock(return_value=classify)))
    for p in patches:
        p.start()
    try:
        from applications import sync_service
        result = await sync_applications(user, db)
        return result, sync_service._save_cursor
    finally:
        for p in reversed(patches):
            p.stop()


@pytest.mark.asyncio
async def test_funnel_counts_and_dropped_reasons(db: AsyncSession, mock_user: User, ai_off, caplog):
    with caplog.at_level(logging.INFO, logger="applications.sync_service"):
        result, save_cursor = await _sync(db, mock_user, [_email(n) for n in EMAILS])

    stats = result["stats"]
    assert result["error"] is False and result["ai_used"] is False
    assert not [k for k in stats if "batch" in k or "claude" in k]
    assert (stats["fetched"], stats["blocked_by_filter"], stats["classified"]) == (6, 1, 5)
    assert (stats["not_job"], stats["no_company_or_role"], stats["kept"]) == (1, 1, 3)
    assert (stats["saved_new"], stats["needs_review"], stats["classified_by_ai"]) == (3, 1, 0)
    assert stats["kept_without_company"] == 1
    save_cursor.assert_awaited_once()

    funnel = next(r.getMessage() for r in caplog.records if "SYNC COMPLETE" in r.getMessage())
    assert "rules only, no AI" in funnel and "claude" not in funnel.lower()

    dropped = {d.gmail_message_id: d for d in (await db.execute(select(DroppedEmail))).scalars().all()}
    assert {k: v.reason for k, v in dropped.items()} == {
        "filtered": "filtered_out", "not_job": "not_job", "no_company_or_role": "no_company_or_role",
    }
    assert dropped["filtered"].detail == "no_job_signal"
    assert dropped["not_job"].detail.startswith("rules:")

    apps = {a.company: a.status for a in (await db.execute(select(Application))).scalars().all()}
    assert apps == {"Brightwave": "Needs Review", "Northwind Labs": "Applied", "Unknown": "Applied"}


@pytest.mark.asyncio
async def test_linkedin_and_unknown_company_emails_are_saved_and_threaded(db: AsyncSession, mock_user: User, ai_off):
    easy_apply = dict(id="li1", thread_id="t-li1", date=DATE, sender="LinkedIn <jobs-noreply@linkedin.com>",
                      subject="Jordan, your application was sent to Brightwave",
                      body="Your application was sent to Brightwave Data Engineer Brightwave Warsaw View job: x")
    alert = dict(id="li2", thread_id="t-li2", date=DATE, sender="LinkedIn <jobs-noreply@linkedin.com>",
                 subject="New jobs similar to Data Engineer at Brightwave", body="See jobs")
    inmail = dict(id="li3", thread_id="t-li3", date=DATE, sender="Taylor Reed via LinkedIn <hit-reply@linkedin.com>",
                  subject="Message replied: Data Engineer opportunity", body="Are you open to a quick chat?")
    unknown = dict(id="u1", thread_id="t-u1", date=DATE, sender="someone@gmail.com",
                   subject="Thank you for applying", body="We received your application.")
    result, _ = await _sync(db, mock_user, [easy_apply, alert, inmail, unknown])
    later = dict(id="u2", thread_id="t-u1", date=DATE, sender="someone@gmail.com", subject="Re: Thank you for applying",
                 body="Unfortunately, we have decided to move forward with other candidates.")
    await _sync(db, mock_user, [later])

    apps = sorted((a.company, a.role, a.status) for a in (await db.execute(select(Application))).scalars().all())
    assert result["stats"]["job_alerts"] == 1
    assert apps == [
        ("Brightwave", "Data Engineer", "Applied"),
        ("Unknown", "Unknown", "Rejected"),
    ]
    # The InMail is recruiter outreach: an opportunity, not an application.
    assert result["stats"]["opportunities"] == 1
    dropped = (await db.execute(select(DroppedEmail))).scalar_one()
    assert (dropped.gmail_message_id, dropped.reason) == ("li2", "job_alert")


@pytest.mark.asyncio
async def test_rules_finding_nothing_is_not_an_ai_failure(db: AsyncSession, mock_user: User, ai_off):
    result, save_cursor = await _sync(db, mock_user, [_email("not_job")])
    assert result["error"] is False
    save_cursor.assert_awaited_once()


@pytest.mark.asyncio
async def test_ai_failure_keeps_the_rules_result_and_advances(db: AsyncSession, mock_user: User):
    classify = {
        "confirmed": {"company": "Northwind Labs", "role": "Data Analyst", "status": "Applied",
                      "confidence": 0.9, "status_confidence": 0.85, "source": "ai"},
        "maybe_job": {"company": "Brightwave", "role": "Unknown", "status": "Applied",
                      "confidence": 0.6, "status_confidence": 0.85, "source": "deterministic", "ai_error": True},
    }
    result, save_cursor = await _sync(db, mock_user, [_email("confirmed"), _email("maybe_job")], classify)

    assert result["error"] is False
    assert (result["stats"]["classified_by_ai"], result["stats"]["ai_failed"]) == (1, 1)
    assert result["stats"]["saved_new"] == 2
    save_cursor.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_saved_email_is_no_longer_listed_as_dropped(db: AsyncSession, mock_user: User, ai_off):
    await record_dropped(db, mock_user.id, [{"gmail_message_id": "confirmed", "subject": "s", "sender": "x",
                                              "snippet": "", "reason": "not_job", "detail": ""}])
    await _sync(db, mock_user, [_email("confirmed")])
    assert (await db.execute(select(DroppedEmail))).scalars().all() == []


@pytest.mark.asyncio
async def test_already_processed_emails_are_counted(db: AsyncSession, mock_user: User, ai_off):
    await _sync(db, mock_user, [_email("confirmed")])
    result, _ = await _sync(db, mock_user, [_email("confirmed")])
    assert result["stats"]["already_processed"] == 1


@pytest.mark.asyncio
async def test_debug_dropped_endpoint_lists_filters_and_clears(db: AsyncSession, mock_user: User, ai_off):
    await _sync(db, mock_user, [_email(n) for n in EMAILS])
    async with make_client(mock_user, db) as client:
        everything = (await client.get("/debug/dropped")).json()
        only_filtered = (await client.get("/debug/dropped", params={"reason": "filtered_out"})).json()
        bad_reason = await client.get("/debug/dropped", params={"reason": "nope"})
        cleared = (await client.delete("/debug/dropped")).json()
        after = (await client.get("/debug/dropped")).json()

    assert everything["total"] == 3
    assert everything["by_reason"] == {"filtered_out": 1, "not_job": 1, "no_company_or_role": 1}
    assert {"message_id", "subject", "sender", "snippet", "reason", "detail", "dropped_at"} <= set(everything["items"][0])
    assert only_filtered["total"] == 1 and only_filtered["items"][0]["subject"] == "Your order has shipped"
    assert bad_reason.status_code == 422
    assert cleared == {"deleted": 3} and after["total"] == 0


@pytest.mark.asyncio
async def test_dropped_emails_are_capped(db: AsyncSession, mock_user: User):
    rows = [{"gmail_message_id": f"m{i}", "subject": "", "sender": "", "snippet": "", "reason": "not_job", "detail": ""}
            for i in range(3)]
    with patch.object(diagnostics_service, "DROPPED_EMAILS_KEEP", 2):
        await record_dropped(db, mock_user.id, rows)
    assert len((await db.execute(select(DroppedEmail))).scalars().all()) == 2
