"""What every mail source provides, so the sync doesn't care which one is connected.

Message and thread ids use the Gmail API form (lowercase hex) for every source. IMAP's
X-GM-MSGID and X-GM-THRID are the decimal form of the same numbers, so switching sources
doesn't duplicate applications or re-process emails.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

from constants.app_config import GMAIL_DETAIL_FETCH_CONCURRENCY

BODY_LIMIT = 3000

Cursor = dict[str, Any]


class MailError(Exception):
    """A failure with a short code and a message that is safe to show the user."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class MailAuthError(MailError):
    """The stored credentials stopped working; the user has to reconnect."""


class MessageGoneError(MailError):
    """The message was deleted between listing and fetching; nothing left to process."""

    def __init__(self, message_id: str):
        super().__init__("message_gone", f"Message {message_id} no longer exists")


@dataclass
class MessageRef:
    id: str
    # Cursor to store once this message and every one before it are processed.
    # None means the cursor can't move yet.
    cursor_after: Optional[Cursor] = None


@dataclass
class MessageList:
    refs: list[MessageRef]
    final_cursor: Optional[Cursor]


@dataclass
class MailMessage:
    id: str
    thread_id: Optional[str]
    subject: str
    sender: str
    date: str
    body: str

    def as_email_dict(self) -> dict:
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "subject": self.subject,
            "sender": self.sender,
            "date": self.date,
            "body": self.body,
        }


class MailSource(ABC):
    @abstractmethod
    async def test_connection(self) -> str:
        """Returns the account's email address, or raises MailError."""

    @abstractmethod
    async def list_new_messages(
        self, cursor: Optional[Cursor], since_date: date, max_messages: int
    ) -> MessageList:
        """New messages oldest first. Without a usable cursor, everything since since_date."""

    @abstractmethod
    async def fetch_message(self, message_id: str) -> MailMessage:
        ...

    @abstractmethod
    async def read_message(self, message_id: str) -> MailMessage:
        """One message with its whole body as readable text, to show the user. Never stored."""

    async def fetch_messages(self, message_ids: list[str]) -> dict[str, MailMessage | MailError]:
        """Fetch many messages; a failure is returned per message, except auth errors, which stop everything."""
        sem = asyncio.Semaphore(GMAIL_DETAIL_FETCH_CONCURRENCY)

        async def one(message_id: str):
            async with sem:
                try:
                    return await self.fetch_message(message_id)
                except MailAuthError:
                    raise
                except MailError as exc:
                    return exc

        results = await asyncio.gather(*(one(m) for m in message_ids))
        return dict(zip(message_ids, results))

    async def close(self) -> None:
        pass


def search_query(since_date: date, today: Optional[date] = None) -> str:
    days = max(1, ((today or date.today()) - since_date).days)
    return f"newer_than:{days}d -in:sent"


def gmail_id_from_imap(value: int) -> str:
    return format(int(value), "x")


def imap_id_from_gmail(value: str) -> int:
    return int(value, 16)


def cursor_to_store(listing: MessageList, processed: set[str]) -> Optional[Cursor]:
    """The furthest cursor that doesn't skip a message that wasn't processed. None keeps the old one."""
    cursor = None
    for ref in listing.refs:
        if ref.id not in processed:
            return cursor
        if ref.cursor_after is not None:
            cursor = ref.cursor_after
    return listing.final_cursor
