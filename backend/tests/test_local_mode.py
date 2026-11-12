"""Tests for the single-user local setup: local user, OAuth state, SQLite behaviour, local days, no-AI paths."""

import io

import httpx  # noqa: F401
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.service import get_timeline, get_weekly_review
from applications.models import Application, EmailCache
from applications.service import parse_email_date, update_application
from applications.sync_service import _batch_save
from auth.dependencies import LOCAL_USER_ID, get_current_user
from auth.models import User
from companion.models import CompanionMoment
from companion.service import generate_moment
from goals.service import get_today_progress
from utils.timeutil import local_date
from tests.conftest import create_test_application, make_client
from tests.fake_ai import FakeOpenAI


@pytest.mark.asyncio
async def test_get_current_user_creates_one_local_user(db: AsyncSession):
    first = await get_current_user(db=db)
    second = await get_current_user(db=db)

    assert first.id == LOCAL_USER_ID
    assert second.id == LOCAL_USER_ID
    assert (await db.execute(select(func.count(User.id)))).scalar() == 1


@pytest.mark.asyncio
async def test_sync_task_reloads_user_in_its_own_session(db: AsyncSession, mock_user_with_gmail: User):
    reloaded = MagicMock()
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value="task-session")
    session_context.__aexit__ = AsyncMock(return_value=False)

    session_factory = MagicMock(return_value=session_context)

    # After the sync the task runs the notification checks with the same session factory; they open a
    # real session of their own, so they are checked here and not run.
    with patch("sync_runs.runner.get_local_user", new=AsyncMock(return_value=reloaded)) as get_user,          patch("sync_runs.runner.sync_applications", new=AsyncMock()) as sync,          patch("sync_runs.runner.run_checks_safely", new=AsyncMock()) as checks,          patch("applications.routes.AsyncSessionLocal", new=session_factory):
        async with make_client(mock_user_with_gmail, db) as client:
            response = await client.post("/applications/sync")

    assert response.status_code == 200
    run_id = response.json()["run_id"]
    get_user.assert_awaited_once_with("task-session")
    sync.assert_awaited_once()
    assert sync.await_args.kwargs["user"] is reloaded
    assert sync.await_args.kwargs["db"] == "task-session"
    assert str(sync.await_args.kwargs["run_id"]) == run_id
    checks.assert_awaited_once_with(session_factory)


def _new_app_row(user: User, fingerprint: str) -> dict:
    return {
        "id": uuid.uuid4(), "user_id": user.id, "company": "Northwind Labs", "role": "Data Engineer",
        "status": "Applied", "applied_date": datetime.now(timezone.utc), "interview_date": None,
        "source": "gmail", "notes": None, "raw_metadata": {"history": []}, "manually_modified": False,
        "email_thread_id": None, "job_id": None, "location": None, "application_fingerprint": fingerprint,
    }


@pytest.mark.asyncio
async def test_batch_save_skips_duplicates_on_sqlite(db: AsyncSession, mock_user: User):
    cache = [{"gmail_message_id": "m1", "user_id": mock_user.id, "processed": True}]
    await _batch_save(db, [_new_app_row(mock_user, "fp1")], cache)
    await _batch_save(db, [_new_app_row(mock_user, "fp1"), _new_app_row(mock_user, "fp2")], cache)

    assert (await db.execute(select(func.count(Application.id)))).scalar() == 2
    assert (await db.execute(select(func.count()).select_from(EmailCache))).scalar() == 1


@pytest.mark.asyncio
async def test_deleting_user_cascades_to_email_cache(db: AsyncSession, mock_user: User):
    await _batch_save(db, [], [{"gmail_message_id": "m1", "user_id": mock_user.id, "processed": True}])
    await db.delete(mock_user)
    await db.commit()

    assert (await db.execute(select(func.count()).select_from(EmailCache))).scalar() == 0


def test_parse_email_date_converts_to_utc():
    parsed = parse_email_date("Mon, 15 Jan 2024 22:30:00 -0500")
    assert parsed == datetime(2024, 1, 16, 3, 30, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_days_are_counted_in_local_time(db: AsyncSession, mock_user: User):
    # Just after midnight UTC: in timezones west of UTC this is still the previous local day.
    now = datetime.now(timezone.utc)
    applied = now.replace(hour=0, minute=30, second=0, microsecond=0)
    if applied > now:
        applied -= timedelta(days=1)
    await create_test_application(db, mock_user, "Northwind Labs", "Data Engineer", "Applied", applied)
    app = (await db.execute(select(Application))).scalar_one()
    app.raw_metadata = {"history": [{"status": "Applied"}]}
    await db.commit()

    timeline = await get_timeline(user=mock_user, db=db)
    assert timeline["timeline"] == [{"date": str(local_date(applied)), "count": 1}]

    today = await get_today_progress(user=mock_user, db=db)
    assert today["achieved"] == (1 if local_date(applied) == datetime.now().date() else 0)


@pytest.mark.asyncio
async def test_no_moment_without_ai(db: AsyncSession, mock_user: User):
    app = await create_test_application(db, mock_user, "Northwind Labs", "Data Engineer", "Applied")
    assert await generate_moment(user=mock_user, db=db, application=app, moment_type="interview") is None

    await update_application(user=mock_user, db=db, application_id=str(app.id), status="Interview")
    assert (await db.execute(select(func.count(CompanionMoment.id)))).scalar() == 0


@pytest.mark.asyncio
async def test_moment_created_with_ai(db: AsyncSession, mock_user: User, fake_ai):
    fake_ai(FakeOpenAI(["Interview at Northwind Labs\nGood luck."]))
    app = await create_test_application(db, mock_user, "Northwind Labs", "Data Engineer", "Applied")
    moment = await generate_moment(user=mock_user, db=db, application=app, moment_type="interview")

    assert moment.title == "Interview at Northwind Labs"
    assert moment.body == "Good luck."


@pytest.mark.asyncio
async def test_moment_skipped_when_ai_call_fails(db: AsyncSession, mock_user: User, fake_ai):
    fake_ai(FakeOpenAI([httpx.Response(503)]))
    app = await create_test_application(db, mock_user, "Northwind Labs", "Data Engineer", "Applied")
    moment = await generate_moment(user=mock_user, db=db, application=app, moment_type="interview")

    assert moment is None
    assert (await db.execute(select(func.count(CompanionMoment.id)))).scalar() == 0


@pytest.mark.asyncio
async def test_weekly_review_without_ai_has_numbers_and_no_text(db: AsyncSession, mock_user: User):
    await create_test_application(db, mock_user, "Northwind Labs", "Data Engineer", "Applied")
    review = await get_weekly_review(user=mock_user, db=db)

    assert review["applications_this_week"] == 1
    assert review["highlight"] is None
    assert review["concern"] is None
    assert review["focus_items"] is None


@pytest.mark.asyncio
async def test_weekly_review_with_ai_fills_text(db: AsyncSession, mock_user: User, fake_ai):
    fake_ai(FakeOpenAI(["Highlight\nConcern\nFocus one\nFocus two\nFocus three"]))
    review = await get_weekly_review(user=mock_user, db=db)

    assert review["highlight"] == "Highlight"
    assert review["concern"] == "Concern"
    assert review["focus_items"] == ["Focus one", "Focus two", "Focus three"]


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,kwargs", [
    ("post", "/companion/chat", {"json": {"message": "hi"}}),
    ("post", "/companion/mood-insight", {"json": {"mood": "good"}}),
    ("post", "/cv/upload", {"files": {"file": ("cv.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")}}),
])
async def test_ai_endpoints_report_ai_not_configured(db: AsyncSession, mock_user: User, method, path, kwargs):
    async with make_client(mock_user, db) as client:
        response = await getattr(client, method)(path, **kwargs)

    assert response.status_code == 403
    assert response.json()["detail"] == "AI is not configured"


@pytest.mark.asyncio
async def test_validation_error_from_field_validator_returns_json(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.patch("/users/me", json={"name": "   "})

    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert detail["loc"] == ["body", "name"]
    assert detail["ctx"]["error"] == "name must not be empty or whitespace"


@pytest.mark.asyncio
async def test_weekly_review_uses_shared_response_definition(db: AsyncSession, mock_user: User):
    now = datetime.now(timezone.utc).isoformat()
    for company, status in [("A", "Rejected"), ("B", "Assessment"), ("C", "Needs Review"), ("D", "Applied")]:
        app = await create_test_application(db, mock_user, company, "Data Engineer", status)
        app.raw_metadata = {"history": [{"status": status, "date": now}]}
    await db.commit()

    review = await get_weekly_review(user=mock_user, db=db)
    assert review["responses_this_week"] == 2
