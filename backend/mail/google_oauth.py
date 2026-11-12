"""Google OAuth for the user's own Cloud client: consent URL, state, code exchange, refresh, revoke."""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx

from config import settings
from mail.base import MailAuthError, MailError
from mail.retry import send_with_retry

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
STATE_TTL = timedelta(minutes=10)

RELINK_MESSAGE = (
    "Google access expired or was revoked. Reconnect Gmail. If your Google Cloud app is "
    "still in Testing mode, Google ends access after 7 days."
)


@dataclass
class PendingConsent:
    client_id: str
    client_secret: str
    created: datetime


# Kept in memory until Google redirects back: a restart only means starting the consent again.
_pending: dict[str, PendingConsent] = {}


def redirect_uri() -> str:
    return f"{settings.BACKEND_URL.rstrip('/')}/mail/oauth/callback"


def new_state(client_id: str, client_secret: str) -> str:
    now = datetime.now(timezone.utc)
    for state, pending in list(_pending.items()):
        if now - pending.created > STATE_TTL:
            del _pending[state]
    state = secrets.token_urlsafe(32)
    _pending[state] = PendingConsent(client_id, client_secret, now)
    return state


def consume_state(state: str) -> Optional[PendingConsent]:
    pending = _pending.pop(state, None)
    if pending is None or datetime.now(timezone.utc) - pending.created > STATE_TTL:
        return None
    return pending


def consent_url(client_id: str, state: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def _error_code(response: httpx.Response) -> str:
    try:
        return response.json().get("error", "")
    except ValueError:
        return ""


async def exchange_code(http: httpx.AsyncClient, client_id: str, client_secret: str, code: str) -> dict:
    response = await send_with_retry(
        http, "POST", TOKEN_URL,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri(),
            "grant_type": "authorization_code",
        },
    )
    if response.status_code == 200:
        return response.json()
    error = _error_code(response)
    if error in ("invalid_client", "unauthorized_client"):
        raise MailError("invalid_client", "Google rejected the client ID or secret. Check both and try again.")
    if error == "redirect_uri_mismatch":
        raise MailError("redirect_uri_mismatch", "The redirect URI in Google Cloud doesn't match this app's.")
    raise MailError("exchange_failed", f"Google didn't accept the sign-in (HTTP {response.status_code}).")


async def refresh_access_token(
    http: httpx.AsyncClient, client_id: str, client_secret: str, refresh_token: str
) -> dict:
    """Returns Google's token response; raises MailAuthError when the refresh token is dead."""
    response = await send_with_retry(
        http, "POST", TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )
    if response.status_code == 200:
        return response.json()
    error = _error_code(response)
    if error == "invalid_grant":
        raise MailAuthError("invalid_grant", RELINK_MESSAGE)
    if error in ("invalid_client", "unauthorized_client"):
        raise MailAuthError(
            "invalid_client", "Google rejected the OAuth client. Check the client ID and secret in setup."
        )
    raise MailError("token_refresh_failed", f"Google token refresh failed (HTTP {response.status_code}).")


async def revoke_token(http: httpx.AsyncClient, token: str) -> bool:
    """True once Google no longer honours the token, including when it was already invalid."""
    try:
        response = await send_with_retry(http, "POST", REVOKE_URL, data={"token": token})
    except httpx.TransportError:
        return False
    return response.status_code == 200 or (
        response.status_code == 400 and _error_code(response) == "invalid_token"
    )
