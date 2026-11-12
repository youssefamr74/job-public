"""Turn a Gmail API message or a raw RFC 822 message into the same MailMessage."""

import base64
import email
import email.policy
from email.message import EmailMessage
from typing import Optional

from classifier.text import clean_text, readable_text, strip_markup
from mail.base import BODY_LIMIT, MailMessage


def clean_body(text: str) -> str:
    return clean_text(text)[:BODY_LIMIT]


def _b64(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _api_find(payload: dict, mime: str) -> str:
    if payload.get("mimeType", "") == mime:
        data = payload.get("body", {}).get("data", "")
        if data:
            text = _b64(data)
            # A blank text/plain part next to a real HTML part is common; it doesn't count.
            if text.strip():
                return strip_markup(text) if mime == "text/html" else text
    for part in payload.get("parts", []):
        found = _api_find(part, mime)
        if found:
            return found
    return ""


def _api_body(payload: dict) -> str:
    body = _api_find(payload, "text/plain") or _api_find(payload, "text/html")
    if not body:
        data = payload.get("body", {}).get("data", "")
        body = _b64(data) if data else ""
    return body


def _api_header(message: dict, name: str) -> str:
    headers = message.get("payload", {}).get("headers", [])
    return next((h["value"] for h in headers if h["name"].lower() == name.lower()), "")


def parse_api_message(message: dict, readable: bool = False) -> MailMessage:
    """With readable=True the body keeps its paragraphs and isn't cut short, for showing to the user."""
    finish = readable_text if readable else clean_body
    try:
        body = finish(_api_body(message.get("payload", {})))
    except Exception:
        body = ""
    return MailMessage(
        id=message["id"],
        thread_id=message.get("threadId"),
        subject=_api_header(message, "Subject"),
        sender=_api_header(message, "From"),
        date=_api_header(message, "Date"),
        body=body,
    )


def _part_text(part) -> str:
    try:
        return part.get_content()
    except Exception:
        payload = part.get_payload(decode=True) or b""
        return payload.decode("utf-8", errors="ignore")


def _rfc822_find(msg, subtype: str) -> str:
    for part in msg.walk():
        if part.get_content_maintype() == "multipart" or part.get_content_disposition() == "attachment":
            continue
        if part.get_content_type() == f"text/{subtype}":
            text = _part_text(part)
            if text and text.strip():
                return strip_markup(text) if subtype == "html" else text
    return ""


def _header(msg: EmailMessage, name: str) -> str:
    try:
        value = msg.get(name)
    except Exception:
        return ""
    return str(value) if value is not None else ""


def parse_rfc822(raw: bytes, message_id: str, thread_id: Optional[str], readable: bool = False) -> MailMessage:
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    finish = readable_text if readable else clean_body
    try:
        body = finish(_rfc822_find(msg, "plain") or _rfc822_find(msg, "html"))
    except Exception:
        body = ""
    return MailMessage(
        id=message_id,
        thread_id=thread_id,
        subject=_header(msg, "Subject"),
        sender=_header(msg, "From"),
        date=_header(msg, "Date"),
        body=body,
    )
