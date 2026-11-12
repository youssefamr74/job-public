import logging
from dataclasses import dataclass
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.models import User
from constants.app_config import DEFAULT_HTTP_TIMEOUT
from mail import google_oauth
from mail.base import Cursor, MailAuthError, MailError, MailSource
from mail.crypto import CredentialsError, decrypt_json, encrypt_json
from mail.gmail_api import GmailApiSource
from mail.imap import ImapSource
from mail.models import (
    SOURCE_IMAP,
    SOURCE_OAUTH,
    STATUS_CONNECTED,
    STATUS_ERROR,
    STATUS_NEEDS_RELINK,
    MailAccount,
)
from utils.timeutil import utc_now

logger = logging.getLogger(__name__)

TOKEN_FIELDS = ("access_token", "refresh_token")


@dataclass
class MailConnection:
    account: MailAccount
    source: MailSource

    @property
    def cursor(self) -> Optional[Cursor]:
        return self.account.cursor


async def get_mail_account(db: AsyncSession, user: User) -> Optional[MailAccount]:
    result = await db.execute(select(MailAccount).where(MailAccount.user_id == user.id))
    return result.scalar_one_or_none()


def read_credentials(account: MailAccount) -> dict:
    try:
        return decrypt_json(account.credentials)
    except CredentialsError as exc:
        raise MailError("credentials_unreadable", str(exc)) from exc


async def save_account(
    db: AsyncSession, user: User, source_type: str, email: Optional[str], credentials: dict
) -> MailAccount:
    """Store a freshly connected account, replacing any previous one.

    Reconnecting the same mailbox the same way keeps the cursor; anything else starts over."""
    existing = await get_mail_account(db, user)
    cursor = None
    if existing:
        if existing.source_type == source_type and existing.email and existing.email == email:
            cursor = existing.cursor
        await db.delete(existing)
        await db.flush()
    account = MailAccount(
        user_id=user.id,
        source_type=source_type,
        email=email,
        credentials=encrypt_json(credentials),
        cursor=cursor,
        status=STATUS_CONNECTED,
        last_error=None,
        connected_at=utc_now(),
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


async def update_credentials(db: AsyncSession, account: MailAccount, **changes) -> None:
    credentials = read_credentials(account)
    credentials.update(changes)
    account.credentials = encrypt_json(credentials)
    await db.commit()


async def set_status(db: AsyncSession, account: MailAccount, status: str, last_error: Optional[str]) -> None:
    account.status = status
    account.last_error = last_error
    await db.commit()


async def mark_needs_relink(db: AsyncSession, account: MailAccount, message: str) -> None:
    if account.source_type == SOURCE_OAUTH:
        try:
            credentials = read_credentials(account)
            for field in TOKEN_FIELDS:
                credentials.pop(field, None)
            account.credentials = encrypt_json(credentials)
        except MailError:
            pass
    await set_status(db, account, STATUS_NEEDS_RELINK, message)


async def record_mail_failure(db: AsyncSession, account: MailAccount, exc: MailError) -> None:
    if isinstance(exc, MailAuthError):
        await mark_needs_relink(db, account, exc.message)
    else:
        await set_status(db, account, STATUS_ERROR, exc.message)


async def save_cursor(db: AsyncSession, account: MailAccount, cursor: Cursor) -> None:
    account.cursor = cursor
    await db.commit()


async def mark_sync_ok(db: AsyncSession, user: User, account: MailAccount, record_time: bool = True) -> None:
    account.status = STATUS_CONNECTED
    account.last_error = None
    if record_time:
        user.last_sync_at = utc_now()
    await db.commit()


def build_source(db: AsyncSession, account: MailAccount) -> MailSource:
    credentials = read_credentials(account)
    if account.source_type == SOURCE_OAUTH:
        if not credentials.get("refresh_token"):
            raise MailAuthError("no_refresh_token", account.last_error or "Reconnect Gmail to continue.")

        async def save_tokens(access_token: str, refresh_token: Optional[str]) -> None:
            changes = {"access_token": access_token}
            if refresh_token:
                changes["refresh_token"] = refresh_token
            await update_credentials(db, account, **changes)

        return GmailApiSource(
            client_id=credentials["client_id"],
            client_secret=credentials["client_secret"],
            access_token=credentials.get("access_token"),
            refresh_token=credentials["refresh_token"],
            on_tokens=save_tokens,
        )
    if account.source_type == SOURCE_IMAP:
        return ImapSource(email=account.email, app_password=credentials["app_password"])
    raise MailError("unknown_source", f"Unknown mail source '{account.source_type}'.")


async def open_mail_source(db: AsyncSession, user: User) -> Optional[MailConnection]:
    """The connected source, None if there is no account. Raises MailError if it can't be used."""
    account = await get_mail_account(db, user)
    if account is None:
        return None
    if account.status == STATUS_NEEDS_RELINK:
        raise MailAuthError("needs_relink", account.last_error or "Reconnect Gmail to continue.")
    return MailConnection(account=account, source=build_source(db, account))


async def connect_oauth(
    db: AsyncSession, user: User, client_id: str, client_secret: str, code: str
) -> MailAccount:
    async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as http:
        try:
            tokens = await google_oauth.exchange_code(http, client_id, client_secret, code)
        except httpx.TransportError as exc:
            raise MailError("network", "Couldn't reach Google. Check your internet connection.") from exc
    if not tokens.get("refresh_token"):
        raise MailError(
            "no_refresh_token",
            "Google didn't return a refresh token. Remove Jōb's access in your Google Account and connect again.",
        )
    source = GmailApiSource(
        client_id=client_id,
        client_secret=client_secret,
        access_token=tokens.get("access_token"),
        refresh_token=tokens["refresh_token"],
    )
    try:
        email = await source.test_connection()
    finally:
        await source.close()
    credentials = {
        "client_id": client_id,
        "client_secret": client_secret,
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens["refresh_token"],
    }
    return await save_account(db, user, SOURCE_OAUTH, email, credentials)


def stored_oauth_client(account: Optional[MailAccount]) -> Optional[tuple[str, str]]:
    if account is None or account.source_type != SOURCE_OAUTH:
        return None
    credentials = read_credentials(account)
    if not credentials.get("client_id") or not credentials.get("client_secret"):
        return None
    return credentials["client_id"], credentials["client_secret"]


async def disconnect(db: AsyncSession, user: User) -> tuple[bool, Optional[bool]]:
    """Returns (disconnected, revoked). Revoked is None when there was nothing to revoke."""
    account = await get_mail_account(db, user)
    if account is None:
        return False, None
    revoked = None
    if account.source_type == SOURCE_OAUTH:
        try:
            credentials = read_credentials(account)
        except MailError:
            credentials = {}
        token = credentials.get("refresh_token") or credentials.get("access_token")
        if token:
            async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as http:
                revoked = await google_oauth.revoke_token(http, token)
            if not revoked:
                logger.warning("Couldn't revoke the Google token; removing the account anyway")
    await db.delete(account)
    await db.commit()
    return True, revoked


async def connect_imap(db: AsyncSession, user: User, email: str, app_password: str) -> MailAccount:
    """Saves the account only after Gmail accepted the login."""
    source = ImapSource(email=email, app_password=app_password)
    try:
        await source.test_connection()
    finally:
        await source.close()
    return await save_account(db, user, SOURCE_IMAP, email.lower(), {"app_password": "".join(app_password.split())})


async def test_saved_connection(db: AsyncSession, user: User, account: MailAccount) -> tuple[Optional[str], Optional[MailError]]:
    """Returns (email, None) when the saved connection works, otherwise (None, error), and updates the status."""
    try:
        source = build_source(db, account)
    except MailError as exc:
        await record_mail_failure(db, account, exc)
        return None, exc
    try:
        email = await source.test_connection()
    except MailError as exc:
        await record_mail_failure(db, account, exc)
        return None, exc
    finally:
        await source.close()
    await set_status(db, account, STATUS_CONNECTED, None)
    return email, None
