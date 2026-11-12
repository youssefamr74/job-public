"""A dry run of the rules to estimate how much an AI pass would send and roughly cost."""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.classify import batch_eligible, needs_ai
from ai.clients import AIError
from ai.models import PRIVACY_SUBJECT_SENDER
from ai.prompts import CLASSIFY_SYSTEM, classification_message
from ai.service import active
from applications.models import EmailCache
from auth.models import User
from classifier.batch_service import classify_with_rules
from classifier.heuristics import filter_reason
from classifier.text import clean_text
from constants.app_config import AI_BODY_CHARS_DEFAULT, AI_CHARS_PER_TOKEN, AI_OUTPUT_TOKENS_PER_EMAIL
from mail.base import MailMessage
from mail.service import open_mail_source

PRICES_PATH = Path(__file__).with_name("prices.json")


def load_prices() -> dict:
    try:
        return json.loads(PRICES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"models": {}, "batch_discount": {}}


def price_for(prices: dict, provider_id: str, model: str) -> Optional[dict]:
    models = prices.get("models") or {}
    return models.get(f"{provider_id}/{model}") or models.get(f"{provider_id}/*")


def _tokens(text: str) -> int:
    return math.ceil(len(text) / AI_CHARS_PER_TOKEN)


async def estimate(db: AsyncSession, user: User, since_date: date, max_messages: int) -> dict:
    connection = await open_mail_source(db, user)
    if connection is None:
        raise AIError("no_mail", "Connect a mail account first.")
    try:
        listing = await connection.source.list_new_messages(None, since_date, max_messages)
        fetched = await connection.source.fetch_messages([ref.id for ref in listing.refs])
    finally:
        await connection.source.close()
    emails = [m.as_email_dict() for m in fetched.values() if isinstance(m, MailMessage)]

    cached = set()
    if emails:
        cached = set((await db.execute(select(EmailCache.gmail_message_id).where(
            EmailCache.user_id == user.id, EmailCache.gmail_message_id.in_([e["id"] for e in emails])
        ))).scalars().all())
    fresh = [e for e in emails if e["id"] not in cached]
    passed = [
        e for e in fresh
        if not filter_reason(e.get("sender") or "", clean_text(e.get("subject") or ""), clean_text(e.get("body") or ""))
    ]
    rules = classify_with_rules(passed, {})
    to_ai = [e for e in passed if needs_ai(rules.get(e["id"]))]

    settings = active()
    privacy_mode = settings.privacy_mode if settings else PRIVACY_SUBJECT_SENDER
    body_chars = settings.body_chars if settings else AI_BODY_CHARS_DEFAULT
    input_tokens = sum(
        _tokens(CLASSIFY_SYSTEM) + _tokens(classification_message(e, rules.get(e["id"]), privacy_mode, body_chars))
        for e in to_ai
    )
    output_tokens = len(to_ai) * AI_OUTPUT_TOKENS_PER_EMAIL
    use_batch = bool(settings and batch_eligible(settings, len(to_ai)))

    prices = load_prices()
    price = price_for(prices, settings.provider.id, settings.model) if settings else None
    cost = None
    if price is not None:
        discount = (prices.get("batch_discount") or {}).get(settings.provider.id, 1.0) if use_batch else 1.0
        cost = round((input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000 * discount, 4)

    return {
        "estimate": True,
        "note": "This is an estimate: token counts are approximated from text length, and prices may be out of date.",
        "emails_checked": len(emails),
        "already_processed": len(cached),
        "filtered_out": len(fresh) - len(passed),
        "settled_by_rules": len(passed) - len(to_ai),
        "would_send_to_ai": len(to_ai),
        "privacy_mode": privacy_mode,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "would_use_batch": use_batch,
        "provider": settings.provider.id if settings else None,
        "model": settings.model if settings else None,
        "price_per_million": price,
        "estimated_cost_usd": cost,
        "prices_last_checked": prices.get("last_checked"),
    }
