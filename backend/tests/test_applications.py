"""Tests for application service and routes."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from applications.models import Application, EmailCache
from applications.service import (
    delete_application,
    get_user_applications,
    is_valid_transition,
    make_dedup_key,
    save_application,
    update_application,
)
from applications.sync_service import _find_existing, sync_applications
from classifier.batch_service import AiPending
from mail.base import MessageList, MessageRef
from mail.fetch import FetchResult
from auth.models import User
from tests.conftest import create_test_application, make_client


@pytest.mark.asyncio
async def test_save_application_new(db: AsyncSession, mock_user: User):
    await save_application(
        user=mock_user,
        db=db,
        company="Acme Corp",
        role="Engineer",
        status="Applied",
        date=None,
        email_id=None,
    )

    result = await db.execute(
        select(Application).where(Application.user_id == mock_user.id)
    )
    apps = result.scalars().all()
    assert len(apps) == 1
    assert apps[0].company == "Acme Corp"
    assert apps[0].role == "Engineer"
    assert apps[0].status == "Applied"


@pytest.mark.asyncio
async def test_save_application_duplicate_updates_if_more_advanced(
    db: AsyncSession, mock_user: User
):
    await save_application(
        user=mock_user, db=db, company="Acme", role="Dev", status="Applied",
        date=None, email_id=None,
    )
    await save_application(
        user=mock_user, db=db, company="Acme", role="Dev", status="Interview",
        date=None, email_id=None,
    )

    result = await db.execute(
        select(Application).where(Application.user_id == mock_user.id)
    )
    apps = result.scalars().all()
    assert len(apps) == 1
    assert apps[0].status == "Interview"


@pytest.mark.asyncio
async def test_save_application_does_not_downgrade(
    db: AsyncSession, mock_user: User
):
    await save_application(
        user=mock_user, db=db, company="Acme", role="Dev", status="Interview",
        date=None, email_id=None,
    )
    await save_application(
        user=mock_user, db=db, company="Acme", role="Dev", status="Applied",
        date=None, email_id=None,
    )

    result = await db.execute(
        select(Application).where(Application.user_id == mock_user.id)
    )
    apps = result.scalars().all()
    assert len(apps) == 1
    assert apps[0].status == "Interview"  # not downgraded


@pytest.mark.asyncio
async def test_save_application_skips_cached_email(
    db: AsyncSession, mock_user: User
):
    email_id = "unique_gmail_id_123"
    await save_application(
        user=mock_user, db=db, company="Corp A", role="Role A", status="Applied",
        date=None, email_id=email_id,
    )
    await save_application(
        user=mock_user, db=db, company="Corp B", role="Role B", status="Applied",
        date=None, email_id=email_id,  # same email_id → cached
    )

    result = await db.execute(
        select(Application).where(Application.user_id == mock_user.id)
    )
    apps = result.scalars().all()
    assert len(apps) == 1
    assert apps[0].company == "Corp A"


@pytest.mark.asyncio
async def test_save_application_manual_no_cache(
    db: AsyncSession, mock_user: User
):
    """email_id=None bypasses the cache check; two manual saves for same position merge."""
    await save_application(
        user=mock_user, db=db, company="Corp", role="SWE", status="Applied",
        date=None, email_id=None,
    )
    await save_application(
        user=mock_user, db=db, company="Corp", role="SWE", status="Applied",
        date=None, email_id=None,
    )

    result = await db.execute(
        select(Application).where(Application.user_id == mock_user.id)
    )
    apps = result.scalars().all()
    assert len(apps) == 1  # deduped by company+role


def test_is_valid_transition_applied_to_interview():
    assert is_valid_transition("Applied", "Interview") is True


def test_is_valid_transition_applied_to_rejected():
    assert is_valid_transition("Applied", "Rejected") is True


def test_is_valid_transition_interview_to_applied_blocked():
    assert is_valid_transition("Interview", "Applied") is False


def test_is_valid_transition_same_status_is_false():
    assert is_valid_transition("Applied", "Applied") is False


def test_is_valid_transition_rejected_is_terminal():
    assert is_valid_transition("Rejected", "Applied") is False
    assert is_valid_transition("Rejected", "Interview") is False


def test_is_valid_transition_offer_is_terminal():
    assert is_valid_transition("Offer", "Applied") is False
    assert is_valid_transition("Offer", "Interview") is False


def test_is_valid_transition_needs_review_can_go_anywhere():
    for status in ("Applied", "Assessment", "Interview", "Offer", "Rejected"):
        assert is_valid_transition("Needs Review", status) is True


def test_make_dedup_key_normalizes_spaces():
    key = make_dedup_key("EPAM Systems", "Data Engineer")
    assert key == "epamsystems_dataengineer"


def test_make_dedup_key_strips_special_chars():
    key = make_dedup_key("Google, Inc.", "SWE (Backend)")
    assert key == "googleinc_swebackend"


@pytest.mark.asyncio
async def test_get_user_applications_empty(db: AsyncSession, mock_user: User):
    result = await get_user_applications(user=mock_user, db=db)
    assert result == []


@pytest.mark.asyncio
async def test_get_user_applications_returns_own_only(
    db: AsyncSession, mock_user: User
):
    other_user = User(id=uuid.uuid4(), email="other@example.com")
    db.add(other_user)
    await db.commit()
    await db.refresh(other_user)

    await create_test_application(db, mock_user, "OwnCo", "Dev", "Applied")
    await create_test_application(db, other_user, "OtherCo", "PM", "Applied")

    result = await get_user_applications(user=mock_user, db=db)
    assert len(result) == 1
    assert result[0].company == "OwnCo"


@pytest.mark.asyncio
async def test_get_user_applications_filtered_by_status(
    db: AsyncSession, mock_user: User
):
    await create_test_application(db, mock_user, "A", "Dev", "Applied")
    await create_test_application(db, mock_user, "B", "Dev", "Rejected")
    await create_test_application(db, mock_user, "C", "Dev", "Interview")

    result = await get_user_applications(user=mock_user, db=db, status="Rejected")
    assert len(result) == 1
    assert result[0].company == "B"


@pytest.mark.asyncio
async def test_update_application_status(db: AsyncSession, mock_user: User):
    app_obj = await create_test_application(db, mock_user, "Corp", "Dev", "Applied")

    await update_application(
        user=mock_user, db=db, application_id=str(app_obj.id), status="Interview"
    )

    result = await db.execute(
        select(Application).where(Application.id == app_obj.id)
    )
    updated = result.scalar_one()
    assert updated.status == "Interview"


@pytest.mark.asyncio
async def test_update_application_notes(db: AsyncSession, mock_user: User):
    app_obj = await create_test_application(db, mock_user, "Corp", "Dev", "Applied")

    await update_application(
        user=mock_user, db=db, application_id=str(app_obj.id), notes="Had a call"
    )

    result = await db.execute(
        select(Application).where(Application.id == app_obj.id)
    )
    updated = result.scalar_one()
    assert updated.notes == "Had a call"
    assert updated.status == "Applied"  # not nulled out


@pytest.mark.asyncio
async def test_update_application_wrong_user(db: AsyncSession, mock_user: User):
    from fastapi import HTTPException

    other_user = User(id=uuid.uuid4(), email="stranger@example.com")
    db.add(other_user)
    await db.commit()

    app_obj = await create_test_application(db, other_user, "Corp", "Dev", "Applied")

    with pytest.raises(HTTPException) as exc_info:
        await update_application(
            user=mock_user, db=db, application_id=str(app_obj.id), status="Rejected"
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_application_own(db: AsyncSession, mock_user: User):
    app_obj = await create_test_application(db, mock_user, "Corp", "Dev", "Applied")

    await delete_application(
        user=mock_user, db=db, application_id=str(app_obj.id)
    )

    result = await db.execute(
        select(Application).where(Application.id == app_obj.id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_application_wrong_user(db: AsyncSession, mock_user: User):
    from fastapi import HTTPException

    other_user = User(id=uuid.uuid4(), email="stranger2@example.com")
    db.add(other_user)
    await db.commit()

    app_obj = await create_test_application(db, other_user, "Corp", "Dev", "Applied")

    with pytest.raises(HTTPException) as exc_info:
        await delete_application(
            user=mock_user, db=db, application_id=str(app_obj.id)
        )

    assert exc_info.value.status_code == 404

    result = await db.execute(
        select(Application).where(Application.id == app_obj.id)
    )
    assert result.scalar_one_or_none() is not None


def _empty_stats():
    return {
        "matched_by_thread": 0,
        "matched_by_job_id": 0,
        "matched_by_fingerprint": 0,
        "matched_by_company": 0,
    }


def test_find_existing_by_thread():
    app = MagicMock()
    stats = _empty_stats()
    result = _find_existing(
        thread_id="t1", job_id=None, fingerprint=None,
        company="Google", role="SWE", effective_status="Interview",
        existing_by_thread={"t1": app},
        existing_by_job_id={}, existing_by_fingerprint={}, existing_by_company={},
        stats=stats,
    )
    assert result is app
    assert stats["matched_by_thread"] == 1


def test_find_existing_by_job_id():
    app = MagicMock()
    stats = _empty_stats()
    result = _find_existing(
        thread_id=None, job_id="job123", fingerprint=None,
        company="Google", role="SWE", effective_status="Interview",
        existing_by_thread={},
        existing_by_job_id={"job123": app},
        existing_by_fingerprint={}, existing_by_company={},
        stats=stats,
    )
    assert result is app
    assert stats["matched_by_job_id"] == 1


def test_find_existing_by_fingerprint():
    app = MagicMock()
    stats = _empty_stats()
    result = _find_existing(
        thread_id=None, job_id=None, fingerprint="fp1",
        company="Google", role="SWE", effective_status="Interview",
        existing_by_thread={}, existing_by_job_id={},
        existing_by_fingerprint={"fp1": app},
        existing_by_company={},
        stats=stats,
    )
    assert result is app
    assert stats["matched_by_fingerprint"] == 1


def test_find_existing_fingerprint_skipped_for_unknown_role():
    """Fingerprint lookup is bypassed when role is Unknown."""
    app = MagicMock()
    stats = _empty_stats()
    result = _find_existing(
        thread_id=None, job_id=None, fingerprint="fp1",
        company="Google", role="Unknown", effective_status="Interview",
        existing_by_thread={}, existing_by_job_id={},
        existing_by_fingerprint={"fp1": app},
        existing_by_company={},
        stats=stats,
    )
    assert result is None
    assert stats["matched_by_fingerprint"] == 0


def test_find_existing_company_match_for_non_applied_status():
    """Non-Applied status on a known company triggers company-level match."""
    app = MagicMock()
    app.status = "Applied"
    app.applied_date = datetime.now(timezone.utc)
    stats = _empty_stats()
    result = _find_existing(
        thread_id=None, job_id=None, fingerprint=None,
        company="Google", role="SWE", effective_status="Interview",
        existing_by_thread={}, existing_by_job_id={}, existing_by_fingerprint={},
        existing_by_company={"google": [app]},
        stats=stats,
    )
    assert result is app
    assert stats["matched_by_company"] == 1


def test_find_existing_no_company_match_for_applied_status():
    """Applied status does not match by company (could be a new, independent application)."""
    app = MagicMock()
    app.status = "Applied"
    stats = _empty_stats()
    result = _find_existing(
        thread_id=None, job_id=None, fingerprint=None,
        company="Google", role="SWE", effective_status="Applied",
        existing_by_thread={}, existing_by_job_id={}, existing_by_fingerprint={},
        existing_by_company={"google": [app]},
        stats=stats,
    )
    assert result is None
    assert stats["matched_by_company"] == 0


def test_find_existing_unknown_company_never_matches():
    """Unknown company is excluded from all lookup paths."""
    app = MagicMock()
    app.status = "Interview"
    stats = _empty_stats()
    result = _find_existing(
        thread_id=None, job_id=None, fingerprint=None,
        company="Unknown", role="SWE", effective_status="Interview",
        existing_by_thread={}, existing_by_job_id={}, existing_by_fingerprint={},
        existing_by_company={"unknown": [app]},
        stats=stats,
    )
    assert result is None


def test_find_existing_thread_takes_priority_over_company():
    """Thread match wins even when company match is also available."""
    thread_app = MagicMock()
    thread_app.status = "Applied"
    company_app = MagicMock()
    company_app.status = "Interview"
    stats = _empty_stats()
    result = _find_existing(
        thread_id="t1", job_id=None, fingerprint=None,
        company="Google", role="SWE", effective_status="Interview",
        existing_by_thread={"t1": thread_app},
        existing_by_job_id={}, existing_by_fingerprint={},
        existing_by_company={"google": [company_app]},
        stats=stats,
    )
    assert result is thread_app
    assert stats["matched_by_thread"] == 1
    assert stats["matched_by_company"] == 0


def _sample_email(email_id="email1"):
    return {
        "id": email_id,
        "thread_id": None,
        "subject": "Interview scheduled for Software Engineer",
        "sender": "hr@company.com",
        "body": "We have an opening for the Software Engineer position.",
        "date": "Mon, 01 Jan 2024 12:00:00 +0000",
    }


def _fetched(emails, cursor):
    return FetchResult(emails=emails, cursor=cursor, failed=0)


def _open_source(cursor=None):
    connection = MagicMock()
    connection.source.close = AsyncMock()
    connection.cursor = cursor
    return patch("applications.sync_service.open_mail_source", new_callable=AsyncMock,
                 return_value=connection)


def _sync_patches(mock_fetch_return, mock_classify_return):
    """Return a stack of patches for sync_applications isolation."""
    return (
        patch("applications.sync_service.fetch_new_emails", new_callable=AsyncMock,
              return_value=mock_fetch_return),
        patch("applications.sync_service.classify_emails_batch", new_callable=AsyncMock,
              return_value=mock_classify_return),
        patch("applications.sync_service.filter_reason", return_value=None),
        patch("applications.sync_service.update_streak", new_callable=AsyncMock),
        patch("applications.sync_service.save_goal_record", new_callable=AsyncMock),
    )


@pytest.mark.asyncio
async def test_sync_does_not_pass_emails_waiting_in_an_ai_batch(
    db: AsyncSession, mock_user_with_gmail: User
):
    """The cursor stops before an email whose AI answer is still pending in a batch."""
    listing = MessageList(
        refs=[MessageRef("email1", cursor_after={"uid": 1}), MessageRef("email2", cursor_after={"uid": 2})],
        final_cursor={"uid": 2},
    )
    fetched = FetchResult(
        emails=[_sample_email(), {**_sample_email(), "id": "email2"}], cursor={"uid": 2}, failed=0,
        listing=listing, processed={"email1", "email2"},
    )
    patches = _sync_patches(
        mock_fetch_return=fetched,
        mock_classify_return={"email1": AiPending(), "email2": AiPending()},
    )
    with _open_source(), patches[0], patches[1], patches[2], patches[3], patches[4], \
         patch("applications.sync_service._save_cursor", new_callable=AsyncMock) as mock_save:
        result = await sync_applications(mock_user_with_gmail, db)

    assert result["error"] is False
    assert result["stats"]["waiting_for_ai"] == 2
    assert result["synced"] == 0
    mock_save.assert_not_called()


@pytest.mark.asyncio
async def test_sync_success_advances_cursor(
    db: AsyncSession, mock_user_with_gmail: User
):
    """A successful batch advances the mail cursor and returns error=False."""
    classification_result = {
        "email1": {
            "company": "Google",
            "role": "Software Engineer",
            "status": "Applied",
            "confidence": 0.9,
            "interview_date": None,
            "job_id": None,
            "location": None,
            "source": "deterministic",
        }
    }
    patches = _sync_patches(
        mock_fetch_return=_fetched([_sample_email()], {"history_id": "456"}),
        mock_classify_return=classification_result,
    )
    with _open_source(), patches[0], patches[1], patches[2], patches[3], patches[4], \
         patch("applications.sync_service._save_cursor", new_callable=AsyncMock) as mock_save, \
         patch("applications.sync_service._batch_save", new_callable=AsyncMock):
        result = await sync_applications(mock_user_with_gmail, db)

    assert result.get("error") is False
    assert mock_save.call_args.args[2] == {"history_id": "456"}


@pytest.mark.asyncio
async def test_sync_no_emails_skips_classification(
    db: AsyncSession, mock_user_with_gmail: User
):
    """Empty fetch result returns immediately without calling classify_emails_batch."""
    with _open_source(), \
         patch("applications.sync_service.fetch_new_emails", new_callable=AsyncMock,
               return_value=_fetched([], {"history_id": "789"})), \
         patch("applications.sync_service.classify_emails_batch", new_callable=AsyncMock) as mock_classify, \
         patch("applications.sync_service._save_cursor", new_callable=AsyncMock), \
         patch("applications.sync_service.update_streak", new_callable=AsyncMock), \
         patch("applications.sync_service.save_goal_record", new_callable=AsyncMock):
        result = await sync_applications(mock_user_with_gmail, db)

    mock_classify.assert_not_called()
    assert result["synced"] == 0


@pytest.mark.asyncio
async def test_sync_without_mail_account_returns_error(
    db: AsyncSession, mock_user: User
):
    """Without a connected mail account the sync stops with an error."""
    result = await sync_applications(mock_user, db)
    assert result["synced"] == 0
    assert result["error"] is True
    assert "no mail account" in result["message"].lower()


@pytest.mark.asyncio
async def test_sync_keeps_the_users_edits_on_the_timeline(
    db: AsyncSession, mock_user_with_gmail: User
):
    app = await create_test_application(db, mock_user_with_gmail, "Google", "Software Engineer", "Applied")
    async with make_client(mock_user_with_gmail, db) as client:
        await client.patch(f"/applications/{app.id}", json={"status": "Assessment"})

    classification_result = {
        "email1": {
            "company": "Google", "role": "Software Engineer", "status": "Interview", "confidence": 0.9,
            "interview_date": None, "job_id": None, "location": None, "source": "deterministic",
        }
    }
    patches = _sync_patches(
        mock_fetch_return=_fetched([_sample_email()], {"history_id": "456"}),
        mock_classify_return=classification_result,
    )
    with _open_source(), patches[0], patches[1], patches[2], patches[3], patches[4], \
         patch("applications.sync_service._save_cursor", new_callable=AsyncMock):
        await sync_applications(mock_user_with_gmail, db)

    await db.refresh(app)
    assert app.status == "Assessment"
    assert len(app.raw_metadata["history"]) == 1
    assert app.raw_metadata["edits"][0]["to"] == "Assessment"
