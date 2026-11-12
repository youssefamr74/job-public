"""Mail source for the Gmail API, using the user's own OAuth client."""

from __future__ import annotations

from datetime import date
from typing import Awaitable, Callable, Optional

import httpx

from constants.app_config import DEFAULT_HTTP_TIMEOUT
from mail import google_oauth
from mail.base import (
    Cursor,
    MailAuthError,
    MailError,
    MailMessage,
    MailSource,
    MessageGoneError,
    MessageList,
    MessageRef,
    search_query,
)
from mail.parsing import parse_api_message
from mail.retry import is_retryable_response, send_with_retry

API = "https://gmail.googleapis.com/gmail/v1/users/me"
SKIPPED_LABELS = {"SENT", "DRAFT"}

TokenCallback = Callable[[str, Optional[str]], Awaitable[None]]


class GmailApiSource(MailSource):
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        access_token: Optional[str],
        refresh_token: str,
        on_tokens: Optional[TokenCallback] = None,
        http: Optional[httpx.AsyncClient] = None,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._on_tokens = on_tokens
        self._http = http or httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT)

    async def close(self) -> None:
        await self._http.aclose()

    async def _send(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            return await send_with_retry(self._http, method, url, **kwargs)
        except httpx.TransportError as exc:
            raise MailError("network", "Couldn't reach Google. Check your internet connection.") from exc

    async def _refresh(self) -> None:
        try:
            tokens = await google_oauth.refresh_access_token(
                self._http, self._client_id, self._client_secret, self._refresh_token
            )
        except httpx.TransportError as exc:
            raise MailError("network", "Couldn't reach Google. Check your internet connection.") from exc
        self._access_token = tokens["access_token"]
        if tokens.get("refresh_token"):
            self._refresh_token = tokens["refresh_token"]
        if self._on_tokens:
            await self._on_tokens(self._access_token, tokens.get("refresh_token"))

    async def _get(self, path: str, params: Optional[dict] = None) -> httpx.Response:
        if not self._access_token:
            await self._refresh()
        for attempt in range(2):
            response = await self._send(
                "GET", f"{API}{path}", params=params,
                headers={"Authorization": f"Bearer {self._access_token}"},
            )
            if response.status_code != 401:
                return response
            if attempt == 0:
                await self._refresh()
        raise MailAuthError("unauthorized", "Gmail rejected the access token. Reconnect Gmail.")

    @staticmethod
    def _check(response: httpx.Response) -> None:
        if response.status_code == 200:
            return
        if is_retryable_response(response):
            raise MailError("unavailable", "Gmail isn't responding right now. Try again later.")
        if response.status_code == 403:
            raise MailError(
                "forbidden",
                "Gmail refused access. Check that the Gmail API is enabled in your Google Cloud project.",
            )
        raise MailError("gmail_error", f"Gmail returned HTTP {response.status_code}.")

    async def test_connection(self) -> str:
        response = await self._get("/profile")
        self._check(response)
        return response.json()["emailAddress"]

    async def list_new_messages(
        self, cursor: Optional[Cursor], since_date: date, max_messages: int
    ) -> MessageList:
        if cursor and cursor.get("history_id"):
            listing = await self._list_history(str(cursor["history_id"]), max_messages)
            if listing is not None:
                return listing
        return await self._list_recent(since_date, max_messages)

    async def _list_history(self, start: str, max_messages: int) -> Optional[MessageList]:
        refs: list[MessageRef] = []
        seen: set[str] = set()
        boundary = start
        latest = start
        page_token = None
        while True:
            params = {"startHistoryId": start, "historyTypes": "messageAdded", "maxResults": 500}
            if page_token:
                params["pageToken"] = page_token
            response = await self._get("/history", params)
            # Gmail answers 404 when the history id is too old; the caller falls back to a date-based sync.
            if response.status_code == 404:
                return None
            self._check(response)
            data = response.json()
            latest = str(data.get("historyId", latest))
            for record in data.get("history", []):
                kept = []
                for added in record.get("messagesAdded", []):
                    message = added.get("message", {})
                    message_id = message.get("id")
                    if not message_id or message_id in seen:
                        continue
                    if SKIPPED_LABELS & set(message.get("labelIds", [])):
                        continue
                    seen.add(message_id)
                    kept.append(message_id)
                # A history record is only done once all of its messages are.
                for i, message_id in enumerate(kept):
                    done = i == len(kept) - 1
                    refs.append(MessageRef(message_id, {"history_id": str(record["id"]) if done else boundary}))
                boundary = str(record["id"])
                if len(refs) >= max_messages:
                    refs = refs[:max_messages]
                    return MessageList(refs, refs[-1].cursor_after)
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return MessageList(refs, {"history_id": latest})

    async def _list_recent(self, since_date: date, max_messages: int) -> MessageList:
        profile = await self._get("/profile")
        self._check(profile)
        history_id = str(profile.json()["historyId"])

        ids: list[str] = []
        page_token = None
        while len(ids) < max_messages:
            params = {"q": search_query(since_date), "maxResults": min(500, max_messages - len(ids))}
            if page_token:
                params["pageToken"] = page_token
            response = await self._get("/messages", params)
            self._check(response)
            data = response.json()
            ids.extend(m["id"] for m in data.get("messages", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        refs = [MessageRef(message_id) for message_id in reversed(ids[:max_messages])]
        return MessageList(refs, {"history_id": history_id})

    async def fetch_message(self, message_id: str, readable: bool = False) -> MailMessage:
        response = await self._get(f"/messages/{message_id}", {"format": "full"})
        if response.status_code == 404:
            raise MessageGoneError(message_id)
        self._check(response)
        return parse_api_message(response.json(), readable=readable)

    async def read_message(self, message_id: str) -> MailMessage:
        return await self.fetch_message(message_id, readable=True)
