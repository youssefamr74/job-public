"""Exporting applications and deleting all data."""

import csv
import io
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.service import ai_configured
from applications.models import Application, EmailCache
from auth.models import User
from diagnostics.models import DroppedEmail
from mail.models import MailAccount
from notifications.models import Notification
from opportunities.models import Opportunity
from tests.conftest import create_test_application, make_client
from tests.fakes import FakeGmailApi
from tests.test_mail_routes import fake_google


@pytest.mark.asyncio
async def test_export_csv_and_json(db: AsyncSession, mock_user: User):
    app = await create_test_application(db, mock_user, "Zürich Labs", "Data Engineer, Platform", "Interview",
                                        datetime(2026, 10, 1, 12, tzinfo=timezone.utc))
    app.notes = 'Asked about "remote"'
    await db.commit()
    async with make_client(mock_user, db) as client:
        csv_response = await client.get("/data/export/applications.csv")
        json_response = await client.get("/data/export/applications.json")

    assert csv_response.headers["content-type"].startswith("text/csv")
    assert 'attachment; filename="job-applications-' in csv_response.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
    assert len(rows) == 1
    assert rows[0]["company"] == "Zürich Labs"
    assert rows[0]["role"] == "Data Engineer, Platform"
    assert rows[0]["notes"] == 'Asked about "remote"'
    assert rows[0]["applied_date"].startswith("2026-10-01T12:00:00")

    data = json.loads(json_response.content)
    assert data[0]["company"] == "Zürich Labs" and data[0]["status"] == "Interview"
    assert data[0]["timeline"] == []


def test_export_is_not_served_as_the_web_page():
    from web_app import wants_web_page
    from starlette.requests import Request

    request = Request({"type": "http", "method": "GET", "path": "/data/export/applications.csv",
                       "headers": [(b"accept", b"text/html")]})
    assert wants_web_page(request) is False


@pytest.mark.asyncio
async def test_delete_all_needs_the_word_and_removes_everything(db: AsyncSession, mock_user_with_gmail: User, ai_on):
    user = mock_user_with_gmail
    await create_test_application(db, user, "Contoso", "Data Engineer", "Applied")
    db.add_all([
        EmailCache(user_id=user.id, gmail_message_id="m1"),
        DroppedEmail(user_id=user.id, gmail_message_id="m2", reason="not_job"),
        Opportunity(user_id=user.id, message_id="m3"),
        Notification(user_id=user.id, key="k", kind="weekly_summary", title="T"),
    ])
    user.last_sync_at = datetime.now(timezone.utc)
    await db.commit()

    fake = FakeGmailApi()
    with fake_google(fake):
        async with make_client(user, db) as client:
            assert (await client.post("/data/delete-all", json={"confirm": "delete"})).status_code == 422
            response = await client.post("/data/delete-all", json={"confirm": "DELETE"})
    assert response.json() == {"deleted": True}

    for model in (Application, EmailCache, DroppedEmail, Opportunity, Notification, MailAccount):
        assert (await db.execute(select(func.count()).select_from(model))).scalar_one() == 0, model
    assert fake.revoked == ["fake_refresh_token"]
    assert not ai_configured()
    await db.refresh(user)
    assert user.last_sync_at is None
    assert (await db.execute(select(User))).scalar_one().id == user.id
