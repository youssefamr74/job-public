import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Awaitable, Callable, Optional

from mail.base import Cursor, MailMessage, MailSource, MessageGoneError, MessageList, cursor_to_store

FETCH_CHUNK = 50

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    emails: list[dict]
    # Where the next sync should start; None keeps the stored cursor.
    cursor: Optional[Cursor]
    failed: int
    listing: Optional[MessageList] = None
    processed: set[str] = field(default_factory=set)
    stopped: bool = False

    def cursor_without(self, held: set[str]) -> Optional[Cursor]:
        """The cursor when some messages still have to come back next time."""
        if not held or self.listing is None:
            return self.cursor
        return cursor_to_store(self.listing, self.processed - held)


async def fetch_new_emails(
    source: MailSource, cursor: Optional[Cursor], since_date: date, max_messages: int,
    on_progress: Optional[Callable[[int, int], Awaitable[None]]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> FetchResult:
    listing = await source.list_new_messages(cursor, since_date, max_messages)
    logger.info(f"Listed {len(listing.refs)} new messages")
    ids = [ref.id for ref in listing.refs]
    results: dict = {}
    stopped = False
    for start in range(0, len(ids), FETCH_CHUNK):
        if should_stop is not None and should_stop():
            stopped = True
            break
        results.update(await source.fetch_messages(ids[start:start + FETCH_CHUNK]))
        if on_progress is not None:
            await on_progress(min(start + FETCH_CHUNK, len(ids)), len(ids))

    emails: list[dict] = []
    processed: set[str] = set()
    failed = 0
    for ref in listing.refs:
        result = results.get(ref.id)
        if isinstance(result, MailMessage):
            emails.append(result.as_email_dict())
            processed.add(ref.id)
        elif isinstance(result, MessageGoneError):
            processed.add(ref.id)
        else:
            failed += 1
            logger.warning(f"Couldn't fetch message {ref.id}: {getattr(result, 'code', 'unknown')}")

    return FetchResult(
        emails=emails, cursor=cursor_to_store(listing, processed), failed=failed,
        listing=listing, processed=processed, stopped=stopped,
    )
