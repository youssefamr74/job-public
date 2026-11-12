"""Tests for the mail sources, using fakes only: encryption, ids, parsing, cursors, retries, errors."""

import os
import socket
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from cryptography.fernet import Fernet
from imapclient.exceptions import LoginError

from config import settings
from mail import crypto, google_oauth, retry
from mail.base import (
    MailAuthError,
    MailError,
    MessageList,
    MessageRef,
    cursor_to_store,
    gmail_id_from_imap,
    imap_id_from_gmail,
    search_query,
)
from mail.fetch import fetch_new_emails
from mail.gmail_api import GmailApiSource
from mail.imap import ImapSource, map_imap_error
from mail.parsing import parse_api_message, parse_rfc822
from tests.fakes import FakeGmailApi, FakeIMAPClient, FakeImapMessage, api_message, raw_email

SINCE = date(2024, 1, 1)


@pytest.fixture(autouse=True)
def no_retry_delays():
    with patch.object(retry, "sleep", new=AsyncMock()) as fake_sleep:
        yield fake_sleep


@pytest.fixture
def fresh_key(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "SECRET_KEY", "")
    crypto._fernet.cache_clear()
    yield tmp_path
    crypto._fernet.cache_clear()


# Encryption

def test_encryption_round_trip_and_key_file(fresh_key):
    secret = {"app_password": "abcdabcdabcdabcd"}
    token = crypto.encrypt_json(secret)

    assert "abcdabcdabcdabcd" not in token
    assert crypto.decrypt_json(token) == secret
    assert (fresh_key / "secret.key").exists()
    if os.name == "posix":
        assert (fresh_key / "secret.key").stat().st_mode & 0o777 == 0o600


def test_key_file_is_reused(fresh_key):
    token = crypto.encrypt_json({"a": 1})
    crypto._fernet.cache_clear()
    assert crypto.decrypt_json(token) == {"a": 1}


def test_secret_key_setting_wins_and_wrong_key_fails(fresh_key, monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", Fernet.generate_key().decode())
    crypto._fernet.cache_clear()
    token = crypto.encrypt_json({"a": 1})
    assert not (fresh_key / "secret.key").exists()

    monkeypatch.setattr(settings, "SECRET_KEY", Fernet.generate_key().decode())
    crypto._fernet.cache_clear()
    with pytest.raises(crypto.CredentialsError):
        crypto.decrypt_json(token)


def test_invalid_secret_key_is_reported(fresh_key, monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "not-a-key")
    crypto._fernet.cache_clear()
    with pytest.raises(crypto.CredentialsError):
        crypto.ensure_key()


# Ids and parsing

def test_imap_ids_convert_to_gmail_api_hex():
    # Example X-GM-MSGID from Google's IMAP extensions page, and a typical API id.
    assert gmail_id_from_imap(1278455344230334865) == "11bdfc5cae0c8191"
    assert imap_id_from_gmail("11bdfc5cae0c8191") == 1278455344230334865
    assert gmail_id_from_imap(imap_id_from_gmail("18c3b2f6a1d2e4f5")) == "18c3b2f6a1d2e4f5"


def test_both_sources_produce_the_same_message():
    raw = raw_email("Your application to Northwind Labs", "Thank you for applying.\n\nThe team",
                    html="<p>Thank you for <b>applying</b>.</p>")
    from_api = parse_api_message(api_message("18c3b2f6a1d2e4f5", "18c3b2f6a1d2e4f0", raw))
    from_imap = parse_rfc822(raw, gmail_id_from_imap(0x18c3b2f6a1d2e4f5), gmail_id_from_imap(0x18c3b2f6a1d2e4f0))

    assert from_api.as_email_dict() == from_imap.as_email_dict()
    assert from_api.body == "Thank you for applying. The team"


def test_blank_plain_part_falls_back_to_html_for_both_sources():
    raw = raw_email("Hi", "", html="<style>p{}</style><p>" + "word " * 1000 + "</p>")
    from_imap = parse_rfc822(raw, "1", None)
    from_api = parse_api_message(api_message("1", None, raw))

    assert from_imap.body.startswith("word word")
    assert len(from_imap.body) == 3000
    assert from_api.body == from_imap.body


def test_search_query_matches_the_api_query():
    assert search_query(date(2024, 1, 1), today=date(2024, 3, 1)) == "newer_than:60d -in:sent"


# Cursor rule

def test_cursor_stops_before_the_first_failed_message():
    listing = MessageList(
        [MessageRef("a", {"n": 1}), MessageRef("b", {"n": 2}), MessageRef("c", {"n": 3})],
        final_cursor={"n": 9},
    )
    assert cursor_to_store(listing, {"a", "b", "c"}) == {"n": 9}
    assert cursor_to_store(listing, {"a", "c"}) == {"n": 1}
    assert cursor_to_store(listing, {"b", "c"}) is None


# IMAP

def _imap_messages():
    return [
        FakeImapMessage(10, 0x18c3b2f6a1d2e4f5, 0x18c3b2f6a1d2e4f0, raw_email("Application received", "Thanks")),
        FakeImapMessage(11, 0x18c3b2f6a1d2e4f6, 0x18c3b2f6a1d2e4f0, raw_email("My reply", "Sent"), sent=True),
        FakeImapMessage(12, 0x18c3b2f6a1d2e4f7, 0x18c3b2f6a1d2e4f7, raw_email("Interview invitation", "Hi")),
    ]


def _imap(fake):
    return ImapSource("me@gmail.com", "abcd abcd abcd abcd", client_factory=lambda: fake)


@pytest.mark.asyncio
async def test_imap_finds_all_mail_by_flag_and_strips_password_spaces():
    fake = FakeIMAPClient(folder_name="[Gmail]/Tous les messages")
    source = _imap(fake)
    assert await source.test_connection() == "me@gmail.com"
    assert fake.logged_in_with == ("me@gmail.com", "abcdabcdabcdabcd")
    await source.close()


@pytest.mark.asyncio
async def test_imap_first_sync_then_incremental_cursor():
    fake = FakeIMAPClient(_imap_messages())
    source = _imap(fake)

    first = await fetch_new_emails(source, None, SINCE, 2000)
    assert [e["subject"] for e in first.emails] == ["Application received", "Interview invitation"]
    assert first.emails[0]["id"] == "18c3b2f6a1d2e4f5"
    assert first.emails[0]["thread_id"] == "18c3b2f6a1d2e4f0"
    assert first.cursor == {"uidvalidity": 1, "last_uid": 12}
    assert fake.searches[0][0] == "X-GM-RAW" and fake.searches[0][1].endswith("-in:sent")

    fake.messages[13] = FakeImapMessage(13, 0x18c3b2f6a1d2e4f8, 0x18c3b2f6a1d2e4f8, raw_email("Offer", "Yes"))
    second = await fetch_new_emails(source, first.cursor, SINCE, 2000)
    assert [e["subject"] for e in second.emails] == ["Offer"]
    assert second.cursor == {"uidvalidity": 1, "last_uid": 13}

    third = await fetch_new_emails(source, second.cursor, SINCE, 2000)
    assert third.emails == []
    assert third.cursor == {"uidvalidity": 1, "last_uid": 13}
    await source.close()


@pytest.mark.asyncio
async def test_imap_uidvalidity_change_resyncs_by_date():
    fake = FakeIMAPClient(_imap_messages(), uidvalidity=7)
    result = await fetch_new_emails(_imap(fake), {"uidvalidity": 6, "last_uid": 12}, SINCE, 2000)

    assert [e["subject"] for e in result.emails] == ["Application received", "Interview invitation"]
    assert result.cursor == {"uidvalidity": 7, "last_uid": 12}
    assert fake.searches[-1][0] == "X-GM-RAW"


@pytest.mark.asyncio
async def test_imap_cursor_does_not_pass_a_failed_fetch():
    messages = _imap_messages() + [
        FakeImapMessage(13, 0x18c3b2f6a1d2e4f8, 0x18c3b2f6a1d2e4f8, raw_email("Offer", "Yes")),
    ]
    fake = FakeIMAPClient(messages)
    source = _imap(fake)
    with patch("mail.imap.FETCH_BATCH", 1):
        fake.fail_fetch_uids = {12}
        result = await fetch_new_emails(source, {"uidvalidity": 1, "last_uid": 9}, SINCE, 2000)

    assert [e["subject"] for e in result.emails] == ["Application received", "Offer"]
    assert result.failed == 1
    assert result.cursor == {"uidvalidity": 1, "last_uid": 10}


@pytest.mark.parametrize("error,code", [
    (LoginError("[AUTHENTICATIONFAILED] Invalid credentials (Failure)"), "invalid_credentials"),
    (LoginError("[ALERT] Application-specific password required: https://support.google.com/accounts/answer/185833 (Failure)"), "app_password_required"),
    (LoginError("[ALERT] Your account is not enabled for IMAP use. (Failure)"), "imap_disabled"),
    (LoginError("[ALERT] Please log in via your web browser (Failure)"), "web_login_required"),
    (socket.gaierror("getaddrinfo failed"), "network"),
    (TimeoutError("timed out"), "network"),
    (Exception("[UNAVAILABLE] Temporary System Error"), "unavailable"),
])
def test_imap_error_mapping(error, code):
    mapped = map_imap_error(error)
    assert mapped.code == code
    assert mapped.message
    assert isinstance(mapped, MailAuthError) == (code not in ("network", "unavailable"))


@pytest.mark.asyncio
async def test_imap_wrong_password_is_an_auth_error_and_not_retried(no_retry_delays):
    source = ImapSource("me@gmail.com", "wrong", client_factory=lambda: FakeIMAPClient())
    with pytest.raises(MailAuthError) as exc:
        await source.test_connection()
    assert exc.value.code == "invalid_credentials"
    no_retry_delays.assert_not_called()


@pytest.mark.asyncio
async def test_imap_network_error_is_retried_with_a_new_connection(no_retry_delays):
    attempts = []

    def factory():
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionResetError("reset")
        return FakeIMAPClient()

    source = ImapSource("me@gmail.com", "abcdabcdabcdabcd", client_factory=factory)
    assert await source.test_connection() == "me@gmail.com"
    assert len(attempts) == 2
    no_retry_delays.assert_awaited_once()


# Gmail API

def _api_messages():
    return [
        api_message("a1", "t1", raw_email("Application received", "Thanks")),
        api_message("a2", "t2", raw_email("Assessment", "Please complete")),
        api_message("a3", "t3", raw_email("Interview invitation", "Hi")),
    ]


def _gmail(fake, access_token="good-token", on_tokens=None):
    return GmailApiSource("cid", "csec", access_token, "refresh-0", on_tokens=on_tokens,
                          http=httpx.AsyncClient(transport=fake.transport()))


@pytest.mark.asyncio
async def test_gmail_first_sync_pages_through_messages():
    fake = FakeGmailApi(_api_messages(), history_id=500, page_size=2)
    result = await fetch_new_emails(_gmail(fake), None, SINCE, 2000)

    assert [e["id"] for e in result.emails] == ["a1", "a2", "a3"]
    assert result.cursor == {"history_id": "500"}
    assert fake.requests.count("GET /gmail/v1/users/me/messages") == 2


@pytest.mark.asyncio
async def test_gmail_history_follows_next_page_token_and_skips_sent():
    fake = FakeGmailApi(_api_messages(), history_id=100, page_size=1)
    fake.add_history(101, "a1")
    fake.add_history(102, "a2")
    fake.add_history(103, "sent-1", labels=("SENT",))
    fake.add_history(104, "a3")

    result = await fetch_new_emails(_gmail(fake), {"history_id": "100"}, SINCE, 2000)

    assert [e["id"] for e in result.emails] == ["a1", "a2", "a3"]
    assert result.cursor == {"history_id": "104"}
    assert fake.requests.count("GET /gmail/v1/users/me/history") == 4


@pytest.mark.asyncio
async def test_gmail_expired_history_falls_back_to_date_sync():
    fake = FakeGmailApi(_api_messages(), history_id=900, oldest_history_id=500)
    result = await fetch_new_emails(_gmail(fake), {"history_id": "100"}, SINCE, 2000)

    assert [e["id"] for e in result.emails] == ["a1", "a2", "a3"]
    assert result.cursor == {"history_id": "900"}


@pytest.mark.asyncio
async def test_gmail_cursor_does_not_pass_a_failed_fetch():
    fake = FakeGmailApi(_api_messages(), history_id=100)
    fake.add_history(101, "a1")
    fake.add_history(102, "a2")
    fake.add_history(103, "a3")
    fake.fail_ids = {"a2"}

    result = await fetch_new_emails(_gmail(fake), {"history_id": "100"}, SINCE, 2000)

    assert [e["id"] for e in result.emails] == ["a1", "a3"]
    assert result.failed == 1
    assert result.cursor == {"history_id": "101"}


@pytest.mark.asyncio
async def test_gmail_deleted_message_does_not_block_the_cursor():
    fake = FakeGmailApi(_api_messages(), history_id=100)
    fake.add_history(101, "gone")
    fake.add_history(102, "a1")

    result = await fetch_new_emails(_gmail(fake), {"history_id": "100"}, SINCE, 2000)
    assert [e["id"] for e in result.emails] == ["a1"]
    assert result.cursor == {"history_id": "102"}


@pytest.mark.asyncio
async def test_gmail_refreshes_an_expired_token_and_reports_it():
    fake = FakeGmailApi(_api_messages())
    saved = []

    async def on_tokens(access_token, refresh_token):
        saved.append(access_token)

    source = _gmail(fake, access_token="expired", on_tokens=on_tokens)
    assert await source.test_connection() == "me@gmail.com"
    assert saved == ["token-1"]


@pytest.mark.asyncio
async def test_gmail_invalid_grant_is_an_auth_error():
    fake = FakeGmailApi(_api_messages())
    fake.refresh_mode = "invalid_grant"
    with pytest.raises(MailAuthError) as exc:
        await _gmail(fake, access_token="expired").test_connection()
    assert exc.value.code == "invalid_grant"
    assert "7 days" in exc.value.message


# Retries

@pytest.mark.asyncio
async def test_retry_honours_retry_after_then_backs_off(no_retry_delays):
    responses = iter([
        httpx.Response(429, headers={"Retry-After": "7"}),
        httpx.Response(503),
        httpx.Response(403, json={"error": {"errors": [{"reason": "userRateLimitExceeded"}]}}),
        httpx.Response(200),
    ])
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: next(responses))) as http:
        response = await retry.send_with_retry(http, "GET", "https://example.test")

    assert response.status_code == 200
    assert [c.args[0] for c in no_retry_delays.await_args_list] == [7.0, 2.0, 4.0]


@pytest.mark.asyncio
async def test_retry_gives_up_and_returns_the_last_response(no_retry_delays):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500))) as http:
        response = await retry.send_with_retry(http, "GET", "https://example.test")
    assert response.status_code == 500
    assert no_retry_delays.await_count == retry.MAX_ATTEMPTS - 1


@pytest.mark.asyncio
async def test_retry_does_not_retry_client_errors(no_retry_delays):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404))) as http:
        response = await retry.send_with_retry(http, "GET", "https://example.test")
    assert response.status_code == 404
    no_retry_delays.assert_not_called()


def test_retry_after_accepts_an_http_date():
    when = datetime.now(timezone.utc) + timedelta(seconds=30)
    assert 25 <= retry.retry_after_seconds(format_datetime(when, usegmt=True)) <= 30
    assert retry.retry_after_seconds("nonsense") is None


@pytest.mark.asyncio
async def test_gmail_api_retries_server_errors(no_retry_delays):
    fake = FakeGmailApi(_api_messages())
    real_handle = fake.handle
    failures = iter([True, True, False])

    def flaky(request):
        if request.url.path.endswith("/profile") and next(failures):
            return httpx.Response(502)
        return real_handle(request)

    source = GmailApiSource("cid", "csec", "good-token", "refresh-0",
                            http=httpx.AsyncClient(transport=httpx.MockTransport(flaky)))
    assert await source.test_connection() == "me@gmail.com"
    assert no_retry_delays.await_count == 2


# OAuth state

def test_oauth_state_is_single_use_and_expires():
    state = google_oauth.new_state("cid", "csec")
    pending = google_oauth.consume_state(state)
    assert (pending.client_id, pending.client_secret) == ("cid", "csec")
    assert google_oauth.consume_state(state) is None

    old = google_oauth.new_state("cid", "csec")
    google_oauth._pending[old].created -= google_oauth.STATE_TTL + timedelta(seconds=1)
    assert google_oauth.consume_state(old) is None


def test_consent_url_asks_for_offline_read_only_access():
    from urllib.parse import parse_qs, urlparse
    query = parse_qs(urlparse(google_oauth.consent_url("cid", "st")).query)
    assert query["scope"] == ["https://www.googleapis.com/auth/gmail.readonly"]
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["state"] == ["st"]
    assert query["redirect_uri"] == [google_oauth.redirect_uri()]


@pytest.mark.asyncio
async def test_mail_error_messages_never_contain_secrets():
    fake = FakeIMAPClient(login_error="[AUTHENTICATIONFAILED] Invalid credentials (Failure)")
    source = ImapSource("me@gmail.com", "supersecretpassw", client_factory=lambda: fake)
    with pytest.raises(MailError) as exc:
        await source.test_connection()
    assert "supersecretpassw" not in exc.value.message
