"""Tests for the setup and mail endpoints and the sync's handling of mail account states."""

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from applications.sync_service import sync_applications
from auth.models import User
from mail import retry
from mail.gmail_api import GmailApiSource
from mail.imap import ImapSource
from mail.models import STATUS_CONNECTED, STATUS_NEEDS_RELINK, MailAccount
from mail.service import build_source, get_mail_account, read_credentials, save_account
from tests.conftest import make_client
from tests.fakes import FakeGmailApi, FakeIMAPClient, FakeImapMessage, raw_email

CLIENT = {"client_id": "123-abc.apps.googleusercontent.com", "client_secret": "csec-123"}


@pytest.fixture(autouse=True)
def no_retry_delays():
    with patch.object(retry, "sleep", new=AsyncMock()):
        yield


@contextmanager
def fake_imap(fake: FakeIMAPClient):
    with patch("mail.service.ImapSource",
               side_effect=lambda **kw: ImapSource(**kw, client_factory=lambda: fake)):
        yield fake


@contextmanager
def fake_google(fake: FakeGmailApi):
    """Route every Google call made by the mail service through the fake."""
    real_client = httpx.AsyncClient

    class Httpx:
        TransportError = httpx.TransportError

        @staticmethod
        def AsyncClient(**kwargs):
            return real_client(transport=fake.transport())

    with patch("mail.service.httpx", Httpx), \
         patch("mail.service.GmailApiSource",
               side_effect=lambda **kw: GmailApiSource(**kw, http=real_client(transport=fake.transport()))):
        yield fake


async def _account(db: AsyncSession, user: User) -> MailAccount:
    return await get_mail_account(db, user)


# Setup status

@pytest.mark.asyncio
async def test_setup_status_without_mail(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        data = (await client.get("/setup/status")).json()
    assert data == {"mail": "none", "mail_source": None, "mail_email": None,
                    "ai_configured": False, "first_sync_done": False, "sync_running": False,
                    "last_sync_at": None}


@pytest.mark.asyncio
async def test_setup_status_reports_account_ai_and_first_sync(db: AsyncSession, mock_user: User, ai_on):
    await save_account(db, mock_user, "imap", "me@gmail.com", {"app_password": "x"})
    mock_user.last_sync_at = datetime.now(timezone.utc)
    await db.commit()

    async with make_client(mock_user, db) as client:
        data = (await client.get("/setup/status")).json()
    assert {k: v for k, v in data.items() if k != "last_sync_at"} == {
        "mail": "connected", "mail_source": "imap", "mail_email": "me@gmail.com",
        "ai_configured": True, "first_sync_done": True, "sync_running": False}
    assert data["last_sync_at"] is not None


# IMAP endpoint

@pytest.mark.asyncio
async def test_connect_imap_saves_encrypted_credentials(db: AsyncSession, mock_user: User):
    with fake_imap(FakeIMAPClient()):
        async with make_client(mock_user, db) as client:
            response = await client.post("/mail/imap", json={"email": "Me@Gmail.com", "app_password": "abcd abcd abcd abcd"})

    assert response.status_code == 200
    assert response.json()["status"] == "connected"
    assert "abcd" not in response.text
    account = await _account(db, mock_user)
    assert account.source_type == "imap" and account.email == "me@gmail.com"
    assert "abcdabcdabcdabcd" not in account.credentials
    assert read_credentials(account) == {"app_password": "abcdabcdabcdabcd"}


@pytest.mark.asyncio
async def test_connect_imap_with_wrong_password_saves_nothing(db: AsyncSession, mock_user: User):
    with fake_imap(FakeIMAPClient(password="the-right-one")):
        async with make_client(mock_user, db) as client:
            response = await client.post("/mail/imap", json={"email": "me@gmail.com", "app_password": "wrongwrongwrong1"})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_credentials"
    assert "wrongwrongwrong1" not in response.text
    assert await _account(db, mock_user) is None


@pytest.mark.asyncio
async def test_connect_imap_validation_never_echoes_the_password(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.post("/mail/imap", json={"email": "not-an-email", "app_password": "secretsecret1234"})
    assert response.status_code == 422
    assert "secretsecret1234" not in response.text


@pytest.mark.asyncio
async def test_mail_status_and_test_endpoints(db: AsyncSession, mock_user: User):
    fake = FakeIMAPClient()
    with fake_imap(fake):
        async with make_client(mock_user, db) as client:
            assert (await client.get("/mail/status")).json()["status"] == "none"
            assert (await client.post("/mail/test")).status_code == 404
            await client.post("/mail/imap", json={"email": "me@gmail.com", "app_password": "abcdabcdabcdabcd"})
            ok = (await client.post("/mail/test")).json()
            fake.password = "changed-in-google"
            broken = (await client.post("/mail/test")).json()
            status = (await client.get("/mail/status")).json()

    assert ok == {"ok": True, "email": "me@gmail.com", "code": None, "message": None}
    assert broken["ok"] is False and broken["code"] == "invalid_credentials"
    assert status["status"] == "needs_relink"
    assert status["last_error"] == broken["message"]


# OAuth endpoints

@pytest.mark.asyncio
async def test_oauth_redirect_uri_is_built_from_the_backend_url(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        data = (await client.get("/mail/oauth/redirect-uri")).json()
    assert data == {"redirect_uri": "http://127.0.0.1:8000/mail/oauth/callback"}


@pytest.mark.asyncio
async def test_oauth_flow_stores_encrypted_tokens_and_redirects_to_setup(db: AsyncSession, mock_user: User):
    fake = FakeGmailApi()
    with fake_google(fake):
        async with make_client(mock_user, db) as client:
            start = (await client.post("/mail/oauth/client", json=CLIENT)).json()
            state = parse_qs(urlparse(start["auth_url"]).query)["state"][0]
            done = await client.get("/mail/oauth/callback", params={"state": state, "code": "good"})
            reused = await client.get("/mail/oauth/callback", params={"state": state, "code": "good"})

    assert "csec-123" not in start["auth_url"]
    assert done.status_code == 303
    assert done.headers["location"] == "http://localhost:5173/setup?mail=connected"
    assert reused.headers["location"] == "http://localhost:5173/setup?mail=error&reason=invalid_state"
    account = await _account(db, mock_user)
    assert account.source_type == "oauth" and account.email == "me@gmail.com"
    assert "refresh-1" not in account.credentials and "csec-123" not in account.credentials
    assert read_credentials(account) == {
        "client_id": CLIENT["client_id"], "client_secret": "csec-123",
        "access_token": "token-1", "refresh_token": "refresh-1",
    }


@pytest.mark.asyncio
async def test_oauth_callback_reports_errors_to_setup(db: AsyncSession, mock_user: User):
    fake = FakeGmailApi()
    with fake_google(fake):
        async with make_client(mock_user, db) as client:
            async def callback(**params):
                start = (await client.post("/mail/oauth/client", json=CLIENT)).json()
                params["state"] = parse_qs(urlparse(start["auth_url"]).query)["state"][0]
                return (await client.get("/mail/oauth/callback", params=params)).headers["location"]

            denied = await callback(error="access_denied")
            bad_code = await callback(code="bad")

    assert denied.endswith("mail=error&reason=access_denied")
    assert bad_code.endswith("mail=error&reason=exchange_failed")
    assert await _account(db, mock_user) is None


@pytest.mark.asyncio
async def test_oauth_client_id_is_validated(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.post("/mail/oauth/client", json={"client_id": "nope", "client_secret": "s"})
    assert response.status_code == 422
    assert '"s"' not in response.text


@pytest.mark.asyncio
async def test_token_refresh_is_saved(db: AsyncSession, mock_user_with_gmail: User):
    fake = FakeGmailApi(access_token="good-token")
    account = await _account(db, mock_user_with_gmail)
    with fake_google(fake):
        source = build_source(db, account)
        await source.test_connection()
        await source.close()

    await db.refresh(account)
    assert read_credentials(account)["access_token"] == "token-1"


@pytest.mark.asyncio
async def test_invalid_grant_during_sync_needs_relink(db: AsyncSession, mock_user_with_gmail: User):
    fake = FakeGmailApi(access_token="good-token")
    fake.refresh_mode = "invalid_grant"
    with fake_google(fake):
        first = await sync_applications(mock_user_with_gmail, db)
        second = await sync_applications(mock_user_with_gmail, db)

    account = await _account(db, mock_user_with_gmail)
    assert first["error"] is True and "7 days" in first["message"]
    assert account.status == STATUS_NEEDS_RELINK
    assert "refresh_token" not in read_credentials(account)
    assert read_credentials(account)["client_id"] == "client-id"
    assert second == {"synced": 0, "message": account.last_error, "error": True}

    async with make_client(mock_user_with_gmail, db) as client:
        sync = await client.post("/applications/sync")
        setup = (await client.get("/setup/status")).json()
        reconnect = (await client.post("/mail/oauth/reconnect")).json()
    assert sync.status_code == 400 and "7 days" in sync.json()["detail"]
    assert setup["mail"] == "needs_relink"
    assert "client_id=client-id" in reconnect["auth_url"]


@pytest.mark.asyncio
async def test_reconnecting_the_same_mailbox_keeps_the_cursor(db: AsyncSession, mock_user: User):
    account = await save_account(db, mock_user, "imap", "me@gmail.com", {"app_password": "a"})
    account.cursor = {"uidvalidity": 1, "last_uid": 42}
    await db.commit()

    same = await save_account(db, mock_user, "imap", "me@gmail.com", {"app_password": "b"})
    assert same.cursor == {"uidvalidity": 1, "last_uid": 42}
    switched = await save_account(db, mock_user, "oauth", "me@gmail.com", {"client_id": "c"})
    assert switched.cursor is None
    assert len((await db.execute(select(MailAccount))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_disconnect_revokes_the_google_token(db: AsyncSession, mock_user_with_gmail: User):
    fake = FakeGmailApi()
    with fake_google(fake):
        async with make_client(mock_user_with_gmail, db) as client:
            response = (await client.delete("/mail")).json()

    assert response == {"disconnected": True, "revoked": True}
    assert fake.revoked == ["fake_refresh_token"]
    assert await _account(db, mock_user_with_gmail) is None


@pytest.mark.asyncio
async def test_sync_uses_imap_and_saves_the_cursor(db: AsyncSession, mock_user: User):
    fake = FakeIMAPClient([
        FakeImapMessage(5, 0x18c3b2f6a1d2e4f5, 0x18c3b2f6a1d2e4f5,
                        raw_email("Thank you for applying for the Data Engineer position", "We received your application.")),
    ])
    await save_account(db, mock_user, "imap", "me@gmail.com", {"app_password": "abcdabcdabcdabcd"})
    with fake_imap(fake):
        result = await sync_applications(mock_user, db)

    account = await _account(db, mock_user)
    assert result["error"] is False
    assert account.cursor == {"uidvalidity": 1, "last_uid": 5}
    assert account.status == STATUS_CONNECTED
    assert mock_user.last_sync_at is not None
