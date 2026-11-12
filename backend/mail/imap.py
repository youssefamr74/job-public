"""Mail source for Gmail over IMAP, signed in with an app password."""

from __future__ import annotations

import asyncio
import imaplib
import logging
import socket
import ssl
from datetime import date
from typing import Callable, Optional

from imapclient import IMAPClient
from imapclient.exceptions import LoginError

from mail.base import (
    Cursor,
    MailAuthError,
    MailError,
    MailMessage,
    MailSource,
    MessageGoneError,
    MessageList,
    MessageRef,
    gmail_id_from_imap,
    imap_id_from_gmail,
    search_query,
)
from mail.parsing import parse_rfc822
from mail.retry import call_with_retry

logger = logging.getLogger(__name__)

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
IMAP_TIMEOUT = 30
FETCH_BATCH = 50
# Enough for the text of almost any email; attachments past this point are never downloaded.
MAX_FETCH_BYTES = 512 * 1024
ALL_MAIL_FLAG = b"\\all"

INVALID_CREDENTIALS = (
    "Gmail rejected the email address or app password. Check both, and make sure "
    "2-Step Verification is on. App passwords don't work with Advanced Protection or most "
    "work and school accounts; use the Google Cloud option for those."
)


def normalize_app_password(value: str) -> str:
    return "".join(value.split())


def map_imap_error(exc: BaseException) -> MailError:
    if isinstance(exc, MailError):
        return exc
    text = str(exc).lower()
    if "not enabled for imap" in text:
        return MailAuthError(
            "imap_disabled",
            "IMAP is turned off for this account. For a work or school account, ask the admin to allow IMAP.",
        )
    if "application-specific password required" in text:
        return MailAuthError(
            "app_password_required",
            "Gmail wants an app password, not your normal Google password. "
            "Turn on 2-Step Verification and create an app password.",
        )
    if "web login required" in text or "log in via your web browser" in text:
        return MailAuthError(
            "web_login_required",
            "Google blocked this sign-in. Sign in to Gmail in a browser once, then try again.",
        )
    if isinstance(exc, LoginError) or "authenticationfailed" in text or "invalid credentials" in text:
        return MailAuthError("invalid_credentials", INVALID_CREDENTIALS)
    if "too many simultaneous connections" in text:
        return MailError(
            "too_many_connections",
            "Gmail has too many IMAP connections open for this account. Close other mail apps or wait a few minutes.",
        )
    if "[unavailable]" in text:
        return MailError("unavailable", "Gmail's IMAP server is temporarily unavailable. Try again later.")
    if isinstance(exc, (socket.gaierror, socket.timeout, TimeoutError, ConnectionError, ssl.SSLError, imaplib.IMAP4.abort)):
        return MailError("network", f"Couldn't reach {IMAP_HOST}. Check your internet connection.")
    if isinstance(exc, OSError):
        return MailError("network", f"Couldn't reach {IMAP_HOST}. Check your internet connection.")
    return MailError("imap_error", "Gmail's IMAP server returned an unexpected error.")


def _find_all_mail(client: IMAPClient) -> str:
    # The folder's name depends on the Gmail language, so look for its special-use flag.
    for flags, _delimiter, name in client.list_folders():
        if any(bytes(flag).lower() == ALL_MAIL_FLAG for flag in flags):
            return name
    raise MailError(
        "all_mail_hidden",
        "Couldn't find Gmail's All Mail folder over IMAP. In Gmail settings, open Labels and "
        "make sure All Mail has \"Show in IMAP\" ticked.",
    )


def _body_bytes(data: dict) -> bytes:
    for key, value in data.items():
        if isinstance(key, bytes) and key.upper().startswith(b"BODY[") and value is not None:
            return bytes(value)
    return b""


class ImapSource(MailSource):
    def __init__(
        self,
        email: str,
        app_password: str,
        client_factory: Optional[Callable[[], IMAPClient]] = None,
    ):
        self._email = email
        self._password = normalize_app_password(app_password)
        self._factory = client_factory or (
            lambda: IMAPClient(IMAP_HOST, port=IMAP_PORT, ssl=True, timeout=IMAP_TIMEOUT)
        )
        self._client: Optional[IMAPClient] = None
        self._folder: Optional[str] = None
        self._uid_by_id: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def _run_once(self, fn, *args):
        # One IMAP connection, used from one worker thread at a time.
        async with self._lock:
            try:
                return await asyncio.to_thread(fn, *args)
            except MailError:
                raise
            except Exception as exc:
                error = map_imap_error(exc)
                if error.code in ("network", "unavailable"):
                    self._client = None
                raise error from exc

    async def _run(self, fn, *args):
        return await call_with_retry(lambda: self._run_once(fn, *args))

    def _connect(self) -> IMAPClient:
        if self._client is None:
            client = self._factory()
            try:
                client.login(self._email, self._password)
                self._folder = _find_all_mail(client)
                # Searching and fetching by id need a selected folder, even without a listing first.
                client.select_folder(self._folder, readonly=True)
            except Exception:
                self._safe_logout(client)
                raise
            self._client = client
        return self._client

    @staticmethod
    def _safe_logout(client: IMAPClient) -> None:
        try:
            client.logout()
        except Exception:
            pass

    def _disconnect(self) -> None:
        if self._client is not None:
            self._safe_logout(self._client)
            self._client = None

    async def close(self) -> None:
        await self._run_once(self._disconnect)

    async def test_connection(self) -> str:
        def check():
            client = self._connect()
            client.select_folder(self._folder, readonly=True)
        await self._run(check)
        return self._email

    async def list_new_messages(
        self, cursor: Optional[Cursor], since_date: date, max_messages: int
    ) -> MessageList:
        return await self._run(self._list, cursor, since_date, max_messages)

    def _list(self, cursor: Optional[Cursor], since_date: date, max_messages: int) -> MessageList:
        client = self._connect()
        info = client.select_folder(self._folder, readonly=True)
        uidvalidity = int(info[b"UIDVALIDITY"])
        highest = int(info.get(b"UIDNEXT") or 1) - 1

        incremental = bool(cursor) and cursor.get("uidvalidity") == uidvalidity and cursor.get("last_uid") is not None
        if incremental:
            last = int(cursor["last_uid"])
            # "n:*" always matches the newest message, even when it's older than n.
            uids = sorted(u for u in client.search(["UID", f"{last + 1}:*", "X-GM-RAW", "-in:sent"]) if u > last)
            truncated = len(uids) > max_messages
            uids = uids[:max_messages]
        else:
            if cursor:
                logger.info("IMAP UIDVALIDITY changed; resyncing by date")
            last = 0
            uids = sorted(client.gmail_search(search_query(since_date)))[-max_messages:]
            truncated = False

        ids = self._gmail_ids(client, uids)
        refs = [
            MessageRef(ids[uid], {"uidvalidity": uidvalidity, "last_uid": uid})
            for uid in uids if uid in ids
        ]
        if truncated:
            final = refs[-1].cursor_after if refs else cursor
        else:
            final = {"uidvalidity": uidvalidity, "last_uid": max([highest, last, *uids])}
        return MessageList(refs, final)

    def _gmail_ids(self, client: IMAPClient, uids: list[int]) -> dict[int, str]:
        ids: dict[int, str] = {}
        for start in range(0, len(uids), FETCH_BATCH):
            chunk = uids[start:start + FETCH_BATCH]
            for uid, data in client.fetch(chunk, ["X-GM-MSGID"]).items():
                message_id = gmail_id_from_imap(data[b"X-GM-MSGID"])
                ids[uid] = message_id
                self._uid_by_id[message_id] = uid
        return ids

    def _uids_for(self, client: IMAPClient, message_ids: list[str]) -> dict[str, int]:
        found = {}
        for message_id in message_ids:
            uid = self._uid_by_id.get(message_id)
            if uid is None:
                matches = client.search(["X-GM-MSGID", imap_id_from_gmail(message_id)])
                uid = matches[0] if matches else None
            if uid is not None:
                found[message_id] = uid
        return found

    def _fetch_chunk(self, message_ids: list[str], readable: bool = False) -> dict[str, MailMessage | MailError]:
        client = self._connect()
        uids = self._uids_for(client, message_ids)
        results: dict[str, MailMessage | MailError] = {
            m: MessageGoneError(m) for m in message_ids if m not in uids
        }
        if not uids:
            return results
        response = client.fetch(
            list(uids.values()), ["X-GM-MSGID", "X-GM-THRID", f"BODY.PEEK[]<0.{MAX_FETCH_BYTES}>"]
        )
        for message_id, uid in uids.items():
            data = response.get(uid)
            if data is None:
                results[message_id] = MessageGoneError(message_id)
                continue
            thread = data.get(b"X-GM-THRID")
            results[message_id] = parse_rfc822(
                _body_bytes(data), message_id, gmail_id_from_imap(thread) if thread is not None else None,
                readable=readable,
            )
        return results

    async def fetch_messages(self, message_ids: list[str]) -> dict[str, MailMessage | MailError]:
        results: dict[str, MailMessage | MailError] = {}
        for start in range(0, len(message_ids), FETCH_BATCH):
            chunk = message_ids[start:start + FETCH_BATCH]
            try:
                results.update(await self._run(self._fetch_chunk, chunk))
            except MailAuthError:
                raise
            except MailError as exc:
                results.update({m: exc for m in chunk})
        return results

    async def fetch_message(self, message_id: str) -> MailMessage:
        result = (await self.fetch_messages([message_id]))[message_id]
        if isinstance(result, MailError):
            raise result
        return result

    async def read_message(self, message_id: str) -> MailMessage:
        result = (await self._run(self._fetch_chunk, [message_id], True))[message_id]
        if isinstance(result, MailError):
            raise result
        return result
