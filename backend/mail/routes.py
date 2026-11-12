from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Path, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from auth.models import User
from config import settings
from database import get_db
from mail import google_oauth
from mail.base import MailAuthError, MailError, MessageGoneError
from mail.schemas import (
    AuthUrlResponse,
    DisconnectResponse,
    EmailContent,
    ImapConnectRequest,
    MailStatusResponse,
    MailTestResponse,
    OAuthClientRequest,
    RedirectUriResponse,
)
from mail.service import (
    connect_imap,
    connect_oauth,
    disconnect,
    get_mail_account,
    open_mail_source,
    record_mail_failure,
    stored_oauth_client,
    test_saved_connection,
)

router = APIRouter()


def mail_error(status_code: int, exc: MailError) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": exc.code, "message": exc.message})


def _connect_error(exc: MailError) -> HTTPException:
    return mail_error(400 if isinstance(exc, MailAuthError) else 502, exc)


def _setup_redirect(error: Optional[str] = None) -> RedirectResponse:
    params = {"mail": "error", "reason": error} if error else {"mail": "connected"}
    separator = "&" if "?" in settings.WEB_SETUP_URL else "?"
    return RedirectResponse(f"{settings.WEB_SETUP_URL}{separator}{urlencode(params)}", status_code=303)


@router.get("/status", response_model=MailStatusResponse)
async def mail_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MailStatusResponse:
    account = await get_mail_account(db, user)
    if account is None:
        return MailStatusResponse(status="none")
    return MailStatusResponse(
        status=account.status,
        source=account.source_type,
        email=account.email,
        last_error=account.last_error,
        connected_at=account.connected_at,
        updated_at=account.updated_at,
    )


@router.post("/imap", response_model=MailStatusResponse)
async def connect_imap_account(
    body: ImapConnectRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MailStatusResponse:
    try:
        account = await connect_imap(db, user, body.email, body.app_password.get_secret_value())
    except MailError as exc:
        raise _connect_error(exc)
    return MailStatusResponse(
        status=account.status, source=account.source_type, email=account.email,
        connected_at=account.connected_at, updated_at=account.updated_at,
    )


@router.post("/test", response_model=MailTestResponse)
async def test_mail(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MailTestResponse:
    account = await get_mail_account(db, user)
    if account is None:
        raise mail_error(404, MailError("not_connected", "No mail account connected."))
    email, error = await test_saved_connection(db, user, account)
    if error:
        return MailTestResponse(ok=False, code=error.code, message=error.message)
    return MailTestResponse(ok=True, email=email)


@router.post("/oauth/client", response_model=AuthUrlResponse)
async def start_oauth(body: OAuthClientRequest) -> AuthUrlResponse:
    state = google_oauth.new_state(body.client_id, body.client_secret.get_secret_value())
    return AuthUrlResponse(auth_url=google_oauth.consent_url(body.client_id, state))


@router.post("/oauth/reconnect", response_model=AuthUrlResponse)
async def reconnect_oauth(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuthUrlResponse:
    try:
        client = stored_oauth_client(await get_mail_account(db, user))
    except MailError as exc:
        raise mail_error(400, exc)
    if client is None:
        raise mail_error(400, MailError("no_oauth_client", "No saved Google Cloud client. Enter the client ID and secret."))
    state = google_oauth.new_state(*client)
    return AuthUrlResponse(auth_url=google_oauth.consent_url(client[0], state))


@router.get("/oauth/redirect-uri", response_model=RedirectUriResponse)
async def oauth_redirect_uri() -> RedirectUriResponse:
    return RedirectUriResponse(redirect_uri=google_oauth.redirect_uri())


@router.get("/oauth/callback")
async def oauth_callback(
    state: Optional[str] = None,
    code: Optional[str] = None,
    error: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    pending = google_oauth.consume_state(state) if state else None
    if pending is None:
        return _setup_redirect("invalid_state")
    if error or not code:
        return _setup_redirect("access_denied" if error == "access_denied" else "authorization_failed")
    try:
        await connect_oauth(db, user, pending.client_id, pending.client_secret, code)
    except MailError as exc:
        return _setup_redirect(exc.code)
    return _setup_redirect()


@router.delete("", response_model=DisconnectResponse)
async def disconnect_mail(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DisconnectResponse:
    disconnected, revoked = await disconnect(db, user)
    return DisconnectResponse(disconnected=disconnected, revoked=revoked)


def _header_date(value: str):
    try:
        return parsedate_to_datetime(value) if value else None
    except (TypeError, ValueError):
        return None


@router.get("/messages/{message_id}", response_model=EmailContent)
async def read_message(
    response: Response,
    message_id: str = Path(pattern=r"^[0-9a-fA-F]{1,32}$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailContent:
    """The email as cleaned text, straight from the mail source. Nothing is stored or logged."""
    response.headers["Cache-Control"] = "no-store"
    try:
        connection = await open_mail_source(db, user)
    except MailError as exc:
        raise _connect_error(exc)
    if connection is None:
        raise mail_error(400, MailError("not_connected", "No mail account connected."))
    try:
        message = await connection.source.read_message(message_id.lower())
    except MessageGoneError:
        raise mail_error(404, MailError("message_gone", "This email is no longer in your mailbox."))
    except MailError as exc:
        if isinstance(exc, MailAuthError):
            await record_mail_failure(db, connection.account, exc)
        raise _connect_error(exc)
    finally:
        await connection.source.close()
    return EmailContent(
        id=message.id, subject=message.subject, sender=message.sender,
        date=_header_date(message.date), body=message.body,
    )
