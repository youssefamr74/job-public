"""Retries for temporary failures: rate limits, server errors and dropped connections."""

from __future__ import annotations

import asyncio
import email.utils
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional, TypeVar

import httpx

from mail.base import MailError

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
BASE_DELAY = 1.0
MAX_DELAY = 30.0
MAX_RETRY_AFTER = 120.0
# Gmail reports some rate limits as 403 rather than 429.
RATE_LIMIT_REASONS = {"rateLimitExceeded", "userRateLimitExceeded"}
RETRYABLE_MAIL_CODES = {"network", "unavailable", "too_many_connections"}

T = TypeVar("T")


async def sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def backoff(attempt: int) -> float:
    return min(MAX_DELAY, BASE_DELAY * 2 ** attempt)


def retry_after_seconds(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


def _is_rate_limited_403(response: httpx.Response) -> bool:
    if response.status_code != 403:
        return False
    try:
        errors = response.json().get("error", {}).get("errors", [])
    except (ValueError, AttributeError):
        return False
    return any(e.get("reason") in RATE_LIMIT_REASONS for e in errors if isinstance(e, dict))


def is_retryable_response(response: httpx.Response) -> bool:
    return response.status_code == 429 or response.status_code >= 500 or _is_rate_limited_403(response)


async def send_with_retry(http: httpx.AsyncClient, method: str, url: str, **kwargs) -> httpx.Response:
    """Send a request, retrying temporary failures. The last response or error is passed on."""
    for attempt in range(MAX_ATTEMPTS):
        last = attempt == MAX_ATTEMPTS - 1
        try:
            response = await http.request(method, url, **kwargs)
        except httpx.TransportError:
            if last:
                raise
            logger.info(f"Network error calling {url}; retrying")
            await sleep(backoff(attempt))
            continue
        if last or not is_retryable_response(response):
            return response
        delay = retry_after_seconds(response.headers.get("Retry-After"))
        logger.info(f"HTTP {response.status_code} from {url}; retrying")
        await sleep(min(MAX_RETRY_AFTER, delay) if delay is not None else backoff(attempt))
    raise AssertionError("unreachable")


async def call_with_retry(fn: Callable[[], Awaitable[T]]) -> T:
    """Run fn, retrying MailErrors that are worth another try."""
    for attempt in range(MAX_ATTEMPTS):
        try:
            return await fn()
        except MailError as exc:
            if exc.code not in RETRYABLE_MAIL_CODES or attempt == MAX_ATTEMPTS - 1:
                raise
            logger.info(f"Mail error {exc.code}; retrying")
            await sleep(backoff(attempt))
    raise AssertionError("unreachable")
